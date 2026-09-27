import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rpa_orkestrai import update_install as installer


def make_bundle(path, *, version="0.2.0", identifier=installer.BUNDLE_ID):
    executable = path / "Contents/MacOS/RpaOrkestrAI"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"test executable")
    (path / "Contents/Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": identifier, "CFBundleShortVersionString": version,
    }))
    return executable


@pytest.fixture
def mac_install(monkeypatch, tmp_path):
    monkeypatch.setattr(installer.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(installer.platform, "machine", lambda: "arm64")
    cache = tmp_path / "private cache"
    cache.mkdir()
    asset = cache / "update.dmg"
    asset.write_bytes(b"already authenticated image")
    target = tmp_path / "Applications/RpaOrkestrAI.app"
    executable = make_bundle(target, version="0.1.1")
    calls = []
    options = {"version": "0.2.0", "identifier": installer.BUNDLE_ID}

    def run(arguments, **kwargs):
        calls.append(arguments)
        assert kwargs["check"] is True
        assert kwargs["capture_output"] is True
        if arguments[:2] == ["/usr/bin/hdiutil", "attach"]:
            mount = Path(arguments[arguments.index("-mountpoint") + 1])
            make_bundle(mount / installer.APP_NAME, **options)
            return SimpleNamespace(stdout=plistlib.dumps({"system-entities": [{"mount-point": str(mount)}]}))
        if arguments[0] == "/usr/bin/ditto":
            shutil.copytree(arguments[1], arguments[2])
        if arguments[:2] == ["/usr/bin/hdiutil", "detach"]:
            shutil.rmtree(Path(arguments[2]) / installer.APP_NAME)
        return SimpleNamespace(stdout=b"")

    monkeypatch.setattr(installer.subprocess, "run", run)
    return SimpleNamespace(cache=cache, asset=asset, target=target, executable=executable,
                           calls=calls, options=options, run=run)


def prepare_mac(env):
    return installer.prepare_install(env.asset, "dmg", "0.2.0", env.executable, env.cache)


def test_mac_stages_verified_bundle_and_unmounts_before_handoff(mac_install):
    env = mac_install
    plan = prepare_mac(env)
    assert plan.target == env.target.resolve()
    assert plan.staging_dir.parent == env.target.parent.resolve()
    assert plan.staging_dir.name.startswith(".rpa-update-")
    assert installer._bundle_metadata(env.target)["CFBundleShortVersionString"] == "0.1.1"
    assert installer._bundle_metadata(plan.staging_dir / installer.APP_NAME)["CFBundleShortVersionString"] == "0.2.0"
    assert "-readonly" in env.calls[0]
    assert "-noautoopen" in env.calls[0]
    assert len([call for call in env.calls if call[0] == "/usr/bin/codesign"]) == 2
    assert env.calls[-1][:2] == ["/usr/bin/hdiutil", "detach"]
    assert plan.command[:2] == ("/bin/sh", str(plan.helper_path))
    assert plan.command[2] == str(os.getpid())
    assert str(env.target) not in plan.helper_path.read_text()
    if os.name != "nt":
        assert env.cache.stat().st_mode & 0o777 == 0o700
        assert plan.helper_path.stat().st_mode & 0o777 == 0o600
    installer.cleanup(plan)
    assert env.target.is_dir()
    assert not plan.staging_dir.exists()
    assert not plan.helper_path.exists()


@pytest.mark.parametrize("field,value", [("identifier", "com.other.application"), ("version", "1.0.0")])
def test_mac_rejects_wrong_identity_or_version_and_keeps_installed_app(mac_install, field, value):
    env = mac_install
    env.options[field] = value
    with pytest.raises(installer.UpdateInstallError):
        prepare_mac(env)
    assert env.calls[-1][:2] == ["/usr/bin/hdiutil", "detach"]
    assert not list(env.target.parent.glob(".rpa-update-*"))
    assert installer._bundle_metadata(env.target)["CFBundleShortVersionString"] == "0.1.1"


def test_mac_rejects_signature_failure_and_detaches(mac_install, monkeypatch):
    env = mac_install

    def run(arguments, **kwargs):
        if arguments[0] == "/usr/bin/codesign":
            raise subprocess.CalledProcessError(1, arguments)
        return env.run(arguments, **kwargs)

    monkeypatch.setattr(installer.subprocess, "run", run)
    with pytest.raises(installer.UpdateInstallError):
        prepare_mac(env)
    assert env.calls[-1][:2] == ["/usr/bin/hdiutil", "detach"]
    assert env.executable.exists()


def test_mac_failed_detach_discards_stage_before_caller_exits(mac_install, monkeypatch):
    env = mac_install

    def run(arguments, **kwargs):
        if arguments[:2] == ["/usr/bin/hdiutil", "detach"]:
            raise subprocess.CalledProcessError(1, arguments)
        return env.run(arguments, **kwargs)

    monkeypatch.setattr(installer.subprocess, "run", run)
    with pytest.raises(installer.UpdateInstallError):
        prepare_mac(env)
    assert not list(env.target.parent.glob(".rpa-update-*"))
    assert not list(env.cache.glob("install-*.sh"))
    assert env.executable.exists()


def test_mac_launched_from_disk_image_requires_install_first(monkeypatch):
    with pytest.raises(installer.ManualUpdateRequired, match="Uygulamalar"):
        installer._mac_target(Path("/Volumes/Studio/RpaOrkestrAI.app/Contents/MacOS/RpaOrkestrAI"))


def test_mac_nonwritable_install_requests_manual_update(mac_install, monkeypatch):
    monkeypatch.setattr(installer.os, "access", lambda *_: False)
    with pytest.raises(installer.ManualUpdateRequired, match="yazma izni"):
        prepare_mac(mac_install)
    assert not mac_install.calls


def test_malformed_version_and_cache_escape_never_launch_tools(mac_install):
    env = mac_install
    with pytest.raises(installer.UpdateInstallError, match="sürümü"):
        installer.prepare_install(env.asset, "dmg", "../../evil", env.executable, env.cache)
    outsider = env.cache.parent / "outside.dmg"
    outsider.write_bytes(b"payload")
    with pytest.raises(installer.UpdateInstallError, match="özel güncelleme"):
        installer.prepare_install(outsider, "dmg", "0.2.0", env.executable, env.cache)
    assert not env.calls


@pytest.mark.skipif(os.name == "nt", reason="Symbolic links require extra Windows privileges")
def test_asset_symlink_and_bundle_structure_symlink_are_rejected(mac_install):
    env = mac_install
    alias = env.cache / "alias.dmg"
    alias.symlink_to(env.asset)
    with pytest.raises(installer.UpdateInstallError, match="dosyası bulunamadı"):
        installer.prepare_install(alias, "dmg", "0.2.0", env.executable, env.cache)
    fake = env.cache / installer.APP_NAME
    fake.mkdir()
    (fake / "Contents").symlink_to(env.target / "Contents", target_is_directory=True)
    with pytest.raises(installer.UpdateInstallError, match="yapısı"):
        installer._bundle_metadata(fake)


def test_windows_installer_uses_separate_argv_wait_pid_and_no_forced_close(monkeypatch, tmp_path):
    monkeypatch.setattr(installer.platform, "system", lambda: "Windows")
    cache = tmp_path / "user's update cache $(never-execute)"
    cache.mkdir()
    asset = cache / "verified.exe"
    asset.write_bytes(b"verified exe")
    target = tmp_path / "Programs/RpaOrkestrAI"
    target.mkdir(parents=True)
    executable = target / "RpaOrkestrAI.exe"
    executable.touch()
    (target / "unins000.exe").touch()
    plan = installer.prepare_install(asset, "exe", "0.2.0", executable, cache)
    assert plan.command[0] == str(asset.resolve())
    assert f"/DIR={target.resolve()}" in plan.command
    assert f"/RPAPID={os.getpid()}" in plan.command
    assert "/RPAUPDATE" in plan.command
    assert "/NOCLOSEAPPLICATIONS" in plan.command
    popen = Mock(return_value=SimpleNamespace(pid=1234))
    monkeypatch.setattr(installer.subprocess, "Popen", popen)
    assert installer.handoff(plan).pid == 1234
    assert popen.call_args.args[0] == plan.command
    assert popen.call_args.kwargs["creationflags"] == 0x208
    assert "shell" not in popen.call_args.kwargs


def test_windows_source_or_portable_app_requires_installer(monkeypatch, tmp_path):
    monkeypatch.setattr(installer.platform, "system", lambda: "Windows")
    cache = tmp_path / "cache"
    cache.mkdir()
    asset = cache / "verified.exe"
    asset.touch()
    executable = tmp_path / "RpaOrkestrAI.exe"
    executable.touch()
    with pytest.raises(installer.ManualUpdateRequired, match="kurulum EXE"):
        installer.prepare_install(asset, "exe", "0.2.0", executable, cache)


def test_mac_handoff_detaches_and_spawn_failure_leaves_running_app_untouched(mac_install, monkeypatch):
    env = mac_install
    plan = prepare_mac(env)
    popen = Mock(side_effect=OSError("Cannot spawn"))
    monkeypatch.setattr(installer.subprocess, "Popen", popen)
    with pytest.raises(installer.UpdateInstallError, match="devam edebilirsiniz"):
        installer.handoff(plan)
    assert popen.call_args.kwargs["start_new_session"] is True
    assert popen.call_args.kwargs["stdin"] == subprocess.DEVNULL
    assert env.executable.exists()
    installer.cleanup(plan)


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS shell handoff")
@pytest.mark.parametrize("scenario", [
    "healthy", "launch_failure", "health_exit", "health_false", "wrong_version",
    "wrong_platform", "not_frozen", "malformed_report", "timeout",
])
def test_shell_transaction_requires_healthy_matching_package_and_preserves_workspace(tmp_path, scenario):
    # Exercise the actual swap script with a fixture health-check executable and
    # LaunchServices replaced. Only the timed-out fixture child can be terminated.
    import shlex

    target = tmp_path / "User's Apps $(ignored)/RpaOrkestrAI.app"
    make_bundle(target, version="0.1.1")
    stage = target.parent / ".rpa-update-test"
    staged = stage / installer.APP_NAME
    candidate = make_bundle(staged, version="0.2.0")
    report = {"ok": scenario != "health_false", "frozen": scenario != "not_frozen",
              "version": "0.1.0" if scenario == "wrong_version" else "0.2.0",
              "platform": "windows-x64" if scenario == "wrong_platform" else "macos-arm64"}
    contents = "invalid JSON" if scenario == "malformed_report" else json.dumps(report)
    if scenario == "timeout":
        candidate.write_text("#!/bin/sh\nexec /bin/sleep 30\n")
    else:
        candidate.write_text(
            '#!/bin/sh\n[ "$1" = --self-test ] || exit 2\n'
            + "printf '%s' " + shlex.quote(contents) + ' > "$2"\n'
            + ("exit 1\n" if scenario == "health_exit" else "exit 0\n")
        )
    candidate.chmod(0o700)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    flow = workspace / "workflow.json"
    flow.write_text('{"name":"keep"}')
    marker = tmp_path / "installing.json"
    marker.write_text('{"phase":"helper"}')
    launcher = tmp_path / "launch-app"
    launcher.write_text("#!/bin/sh\nexit " + ("1" if scenario == "launch_failure" else "0") + "\n")
    launcher.chmod(0o700)
    helper = tmp_path / "helper.sh"
    # POSIX quoting for this test fixture; production paths are argv, never source.
    script = installer._MAC_HELPER.replace("/usr/bin/open", shlex.quote(str(launcher)))
    helper.write_text(script.replace('"$count" -ge 90', '"$count" -ge 1'))
    result = subprocess.run(
        ["/bin/sh", str(helper), "2147483647", str(target), str(staged), str(stage / "previous.app"),
         str(stage), "0.2.0", "macos-arm64", str(marker)],
        capture_output=True, timeout=10,
    )
    success = scenario == "healthy"
    assert (result.returncode == 0) is success, result.stdout.decode() + result.stderr.decode()
    version = installer._bundle_metadata(target)["CFBundleShortVersionString"]
    assert version == ("0.2.0" if success else "0.1.1")
    assert flow.read_text() == '{"name":"keep"}'
    assert stage.exists() is not success
    assert not marker.exists()


def test_cleanup_rejects_unrecognized_directory_without_deleting_it(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    plan = installer.InstallPlan("Darwin", (), tmp_path / "log", tmp_path / installer.APP_NAME, workspace)
    with pytest.raises(installer.UpdateInstallError):
        installer.cleanup(plan)
    assert workspace.is_dir()


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS shell handoff")
def test_handoff_rechecks_identity_and_does_not_replace_unrecognized_target(tmp_path):
    target = tmp_path / installer.APP_NAME
    make_bundle(target, identifier="com.unrelated.application")
    stage = tmp_path / ".rpa-update-test"
    staged = stage / installer.APP_NAME
    make_bundle(staged)
    helper = tmp_path / "helper.sh"
    helper.write_text(installer._MAC_HELPER)
    result = subprocess.run(
        ["/bin/sh", str(helper), "2147483647", str(target), str(staged), str(stage / "previous.app"),
         str(stage), "0.2.0", "macos-arm64", str(tmp_path / "installing.json")],
        capture_output=True, timeout=10,
    )
    assert result.returncode != 0
    assert b"identity changed" in result.stdout
    assert not (stage / "previous.app").exists()
    assert target.is_dir() and staged.is_dir()
