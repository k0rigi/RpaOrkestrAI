import base64
import hashlib
import io
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from rpa_orkestrai import update_install, update_service
from rpa_orkestrai.config import atomic_json
from rpa_orkestrai.locking import WorkspaceLock
from rpa_orkestrai.updates import UpdateCheck, UpdateClient


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    data = tmp_path / "data"
    data.mkdir()
    (data / "workflow.json").write_text("keep my workflow", encoding="utf-8")
    cache = tmp_path / "updates"
    cache.mkdir()
    asset = cache / "package.exe"
    asset.write_bytes(b"the verified update")
    key = Ed25519PrivateKey.generate()
    raw = json.dumps({
        "schema": 1, "channel": "stable", "version": "9.0.0",
        "published_at": (now - timedelta(hours=1)).isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(),
        "assets": {"windows-x64": {
            "url": "https://orkestrai.net/rpa/releases/9.0.0/Studio.exe",
            "sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
            "size": asset.stat().st_size, "type": "exe",
        }},
    }).encode("utf-8")
    envelope = json.dumps({"payload": base64.b64encode(raw).decode(),
                           "signature": base64.b64encode(key.sign(raw)).decode()}).encode()
    client = UpdateClient("https://orkestrai.net/rpa/stable.manifest", key.public_key().public_bytes_raw(),
                          cache_dir=cache, opener=Mock())
    executable = tmp_path / "installed" / "RpaOrkestrAI.exe"
    executable.parent.mkdir()
    executable.write_bytes(b"old app")
    updater = update_service.DesktopUpdates(tmp_path, enabled=True, client=client,
                                           executable=executable, platform_key="windows-x64")
    atomic_json(updater.pending, {"manifest": base64.b64encode(envelope).decode(), "asset": asset.name})
    plan = SimpleNamespace(target=executable.parent)
    prepare = Mock(return_value=plan)
    handoff = Mock(return_value=SimpleNamespace(pid=98765))
    cleanup = Mock()
    monkeypatch.setattr(update_install, "prepare_install", prepare)
    monkeypatch.setattr(update_install, "handoff", handoff)
    monkeypatch.setattr(update_install, "cleanup", cleanup)
    yield SimpleNamespace(updater=updater, client=client, envelope=envelope, asset=asset,
                          settings=SimpleNamespace(data_dir=data), prepare=prepare, handoff=handoff,
                          cleanup=cleanup, plan=plan, workspace=tmp_path)
    updater.stop()


def marker(updater, **changes):
    return {"version": "9.0.0", "pid": 98765, "phase": "helper", "created_at": time.time(),
            "executable": os.path.normcase(str(updater.executable.resolve())), **changes}


def test_source_checkout_does_not_check_download_or_install(prepared):
    updater = update_service.DesktopUpdates(prepared.workspace, enabled=False, client=Mock())
    assert updater.apply_pending(prepared.settings) is False
    updater.start()
    updater.stop()
    assert updater.status()["status"] == "source"
    assert not updater.client.method_calls
    prepared.handoff.assert_not_called()


def test_pending_signed_package_handoff_exits_without_opening_or_modifying_workspace(prepared):
    updater = prepared.updater
    assert updater.apply_pending(prepared.settings) is True
    prepared.prepare.assert_called_once_with(prepared.asset, "exe", "9.0.0", updater.executable, updater.cache)
    prepared.handoff.assert_called_once_with(prepared.plan)
    prepared.cleanup.assert_not_called()
    assert updater._read(updater.installing)["pid"] == 98765
    assert updater._read(updater.installing)["phase"] == "helper"
    assert updater._read(updater.attempt)["version"] == "9.0.0"
    assert (prepared.settings.data_dir / "workflow.json").read_text(encoding="utf-8") == "keep my workflow"
    assert updater.executable.read_bytes() == b"old app"


def test_existing_workspace_owner_prevents_installation(prepared):
    with WorkspaceLock(prepared.settings.data_dir):
        assert prepared.updater.apply_pending(prepared.settings) is False
    prepared.prepare.assert_not_called()
    prepared.handoff.assert_not_called()
    assert prepared.updater.status()["status"] == "ready"
    assert not prepared.updater.attempt.exists()


def test_failed_handoff_cleans_stage_and_cannot_create_restart_loop(prepared):
    prepared.handoff.side_effect = OSError("installer unavailable")
    assert prepared.updater.apply_pending(prepared.settings) is False
    prepared.cleanup.assert_called_once_with(prepared.plan)
    assert not prepared.updater.installing.exists()
    assert prepared.updater.status()["status"] == "manual"
    assert prepared.updater.apply_pending(prepared.settings) is False
    assert prepared.handoff.call_count == 1


def test_failed_preparation_does_not_repeat_on_every_start(prepared):
    prepared.prepare.side_effect = RuntimeError("invalid bundle")
    assert prepared.updater.apply_pending(prepared.settings) is False
    assert prepared.updater.apply_pending(prepared.settings) is False
    assert prepared.prepare.call_count == 1
    prepared.handoff.assert_not_called()


def test_marker_cannot_be_written_before_handoff_so_existing_app_stays_open(prepared, monkeypatch):
    original = update_service.atomic_json

    def write(path, data):
        if path == prepared.updater.installing:
            raise PermissionError("disk unavailable")
        return original(path, data)

    monkeypatch.setattr(update_service, "atomic_json", write)
    assert prepared.updater.apply_pending(prepared.settings) is False
    prepared.handoff.assert_not_called()
    prepared.cleanup.assert_called_once_with(prepared.plan)


def test_failure_writing_helper_pid_after_handoff_must_still_exit(prepared, monkeypatch):
    original = update_service.atomic_json

    def write(path, data):
        if path == prepared.updater.installing and data.get("phase") == "helper":
            raise PermissionError("disk unavailable")
        return original(path, data)

    monkeypatch.setattr(update_service, "atomic_json", write)
    assert prepared.updater.apply_pending(prepared.settings) is True
    prepared.handoff.assert_called_once()
    prepared.cleanup.assert_not_called()
    assert prepared.updater._read(prepared.updater.installing)["phase"] == "parent"
    monkeypatch.setattr(update_service, "_process_alive", lambda pid: False)
    assert prepared.updater._install_in_progress() is True  # covers the handoff interval/fallback


def test_second_launch_obeys_active_install_marker_before_acquiring_cache_lease(prepared, monkeypatch):
    updater = prepared.updater
    atomic_json(updater.installing, marker(updater))
    monkeypatch.setattr(update_service, "_process_alive", lambda pid: True)
    acquire = Mock(side_effect=AssertionError("must not need the busy cache lock"))
    monkeypatch.setattr(updater, "_acquire", acquire)
    assert updater.apply_pending(prepared.settings) is True
    acquire.assert_not_called()
    prepared.handoff.assert_not_called()
    assert updater.status()["status"] == "installing"


def test_second_launch_cannot_race_the_cache_owner_before_install_marker_exists(prepared):
    updater = prepared.updater
    assert not updater.installing.exists()
    with WorkspaceLock(updater.cache):
        assert updater.apply_pending(prepared.settings) is True
    assert updater.status()["status"] == "busy"
    prepared.handoff.assert_not_called()


@pytest.mark.parametrize("changes", [
    {"created_at": time.time() - update_service.INSTALL_MARKER_TTL - 30},
    {"created_at": time.time() + 3600},
    {"created_at": float("inf")}, {"pid": True}, {"pid": -1}, {"pid": 2**40},
    {"phase": "unknown"}, {"executable": "/different/application"},
    {"version": update_service.__version__},
])
def test_stale_invalid_or_completed_marker_does_not_block_startup(prepared, monkeypatch, changes):
    updater = prepared.updater
    # json.dumps deliberately allows Infinity here to exercise untrusted local state.
    updater.installing.write_text(json.dumps(marker(updater, **changes)), encoding="utf-8")
    monkeypatch.setattr(update_service, "_process_alive", lambda pid: True)
    assert updater._install_in_progress() is False


def test_the_new_version_reports_the_silent_installation_once(prepared):
    updater = prepared.updater
    updater.pending.unlink()  # the package was installed, so nothing is pending any more
    # The installer leaves this behind; nothing else tells the user the update went through.
    atomic_json(updater.installing, marker(updater, version=update_service.__version__))
    assert updater.apply_pending(prepared.settings) is False
    assert updater.status()["installed"] == update_service.__version__
    assert not updater.installing.exists()
    # A background check keeps the note, and another computer's marker is ignored.
    updater._set("current", "En güncel sürümü kullanıyorsunuz.")
    assert updater.status()["installed"] == update_service.__version__
    assert "installed" not in update_service.source_status()
    other = update_service.DesktopUpdates(prepared.workspace, enabled=True, client=prepared.client,
                                          executable=updater.executable, platform_key="windows-x64")
    atomic_json(other.installing, marker(other, version=update_service.__version__,
                                         executable="/another/application"))
    other._note_installed()
    assert "installed" not in other.status() and other.installing.exists()


def test_dead_helper_allows_existing_app_to_open_without_retrying_failed_install(prepared, monkeypatch):
    updater = prepared.updater
    atomic_json(updater.installing, marker(updater))
    atomic_json(updater.attempt, {"version": "9.0.0"})
    monkeypatch.setattr(update_service, "_process_alive", lambda pid: False)
    assert updater.apply_pending(prepared.settings) is False
    assert updater.status()["status"] == "manual"
    prepared.handoff.assert_not_called()


@pytest.mark.parametrize("name", ["../outside.exe", "..\\outside.exe", "/tmp/outside.exe", "", None])
def test_pending_asset_path_cannot_escape_the_private_cache(prepared, name):
    updater = prepared.updater
    receipt = updater._read(updater.pending)
    atomic_json(updater.pending, {**receipt, "asset": name})
    assert updater.apply_pending(prepared.settings) is False
    prepared.prepare.assert_not_called()


def test_modified_cached_installer_cannot_reach_platform_handoff(prepared):
    prepared.asset.write_bytes(b"malicious replacement")
    assert prepared.updater.apply_pending(prepared.settings) is False
    prepared.prepare.assert_not_called()
    prepared.handoff.assert_not_called()


def test_unsigned_modified_pending_manifest_cannot_reach_platform_handoff(prepared):
    outer = json.loads(prepared.envelope)
    raw = base64.b64decode(outer["payload"]).replace(b"9.0.0", b"8.0.0")
    outer["payload"] = base64.b64encode(raw).decode()
    atomic_json(prepared.updater.pending, {
        "manifest": base64.b64encode(json.dumps(outer).encode()).decode(), "asset": prepared.asset.name,
    })
    assert prepared.updater.apply_pending(prepared.settings) is False
    prepared.prepare.assert_not_called()


def test_offline_background_check_does_not_change_pending_package_or_user_data(prepared):
    updater = prepared.updater
    prepared.client.check = Mock(return_value=UpdateCheck("unavailable", update_service.__version__))
    pending = updater.pending.read_bytes()
    updater.start()
    updater._worker.join(timeout=5)
    assert not updater._worker.is_alive()
    assert updater.status()["status"] == "unavailable"
    assert updater.pending.read_bytes() == pending
    prepared.handoff.assert_not_called()


def test_ready_status_survives_an_offline_recheck(prepared):
    updater = prepared.updater
    prepared.client.check = Mock(return_value=UpdateCheck("unavailable", update_service.__version__))
    updater._set("ready", "Already downloaded; next startup installs.", "9.0.0")
    expected = updater.status()
    updater.start()
    updater._worker.join(timeout=5)
    assert updater.status() == expected


def test_background_download_persists_only_authenticated_manifest_and_package_basename(prepared):
    updater = prepared.updater
    updater.pending.unlink()
    result = prepared.client.authenticate_manifest(prepared.envelope, update_service.__version__, "windows-x64")
    prepared.client.check = Mock(return_value=result)
    prepared.client.download = Mock(return_value=prepared.asset)
    updater.start()
    updater._worker.join(timeout=5)
    assert updater.status()["status"] == "ready"
    receipt = updater._read(updater.pending)
    assert receipt["asset"] == prepared.asset.name
    assert base64.b64decode(receipt["manifest"]) == prepared.envelope
    prepared.handoff.assert_not_called()  # live UI is never restarted by a background check


def test_stop_during_download_never_writes_a_pending_receipt(prepared):
    updater = prepared.updater
    updater.pending.unlink()
    result = prepared.client.authenticate_manifest(prepared.envelope, update_service.__version__, "windows-x64")
    prepared.client.check = Mock(return_value=result)

    def download(release, *, cancelled):
        updater._stop.set()
        assert cancelled()
        return prepared.asset

    prepared.client.download = download
    updater.start()
    updater._worker.join(timeout=5)
    assert not updater.pending.exists()
    assert updater._lease is None


def test_thread_creation_failure_does_not_block_app_or_break_shutdown(prepared, monkeypatch):
    def fail_start(thread):
        raise RuntimeError("no more thread resources")

    monkeypatch.setattr(update_service.threading.Thread, "start", fail_start)
    prepared.updater.start()
    assert prepared.updater.status()["status"] == "unavailable"
    assert prepared.updater._lease is None
    prepared.updater.stop()


def test_state_read_handles_permission_error_without_breaking_startup(prepared, monkeypatch):
    original = Path.is_file

    def denied(path):
        if path == prepared.updater.pending:
            raise PermissionError("cannot stat updater state")
        return original(path)

    monkeypatch.setattr(Path, "is_file", denied)
    assert prepared.updater.apply_pending(prepared.settings) is False
    prepared.handoff.assert_not_called()


def test_state_read_caps_actual_bytes_even_if_stat_underreports_size(prepared, monkeypatch):
    original = Path.open
    stream = io.BytesIO(b" " * (update_service.STATE_LIMIT + 1))

    def open_file(path, *args, **kwargs):
        return stream if path == prepared.updater.pending else original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_file)
    assert prepared.updater._read(prepared.updater.pending) == {}


def test_process_liveness_query_identifies_current_process_without_killing_it():
    assert update_service._process_alive(os.getpid()) is True
