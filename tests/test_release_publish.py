import base64
import importlib.util
import json
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from rpa_orkestrai.updates import UpdateClient

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prepare_update_release.py"
SPEC = importlib.util.spec_from_file_location("release_publisher", SCRIPT)
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


@pytest.fixture
def release_files(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    private = tmp_path / "credentials" / "private.pem"
    private.parent.mkdir()
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption()))
    monkeypatch.setattr(publisher.update_config, "PUBLIC_KEY",
                        base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii"))
    windows = tmp_path / "RpaOrkestrAI-Setup-0.2.0-Windows-x64.exe"
    windows.write_bytes(b"test installer bytes")
    macos = tmp_path / "RpaOrkestrAI-0.2.0-macOS-arm64.dmg"
    macos.write_bytes(b"test disk image bytes")
    return dict(version="0.2.0", windows=windows, macos_arm64=macos, signing_key=private,
                output=tmp_path / "public", now=datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc))


def test_publication_is_consumable_by_update_client_and_archive_has_only_public_files(release_files, tmp_path):
    archive = tmp_path / "publish-bundle.tar.gz"
    output = publisher.prepare_release(**release_files, archive=archive)
    envelope = (output / "stable.manifest").read_bytes()
    payload = json.loads(base64.b64decode(json.loads(envelope)["payload"]))
    assert payload["schema"] == 1
    assert payload["version"] == "0.2.0"
    assert payload["expires_at"] == (release_files["now"] + timedelta(days=90)).isoformat().replace("+00:00", "Z")

    client = UpdateClient(publisher.update_config.FEED_URL, publisher.update_config.PUBLIC_KEY,
                          cache_dir=tmp_path / "cache", now=lambda: release_files["now"])
    expected_files = {"index.html", "stable.manifest"}
    for platform_key, source in (("windows-x64", release_files["windows"]),
                                 ("macos-arm64", release_files["macos_arm64"])):
        relative = f"releases/0.2.0/{source.name}"
        expected_files.add(relative)
        result = client.authenticate_manifest(envelope, "0.1.1", platform_key)
        assert result.status == "available", result.message
        assert result.release.asset.url == publisher.BASE_URL + relative
        client.verify_download(result.release, output / relative)
        assert (output / relative).read_bytes() == source.read_bytes()
    assert client.authenticate_manifest(envelope, "0.2.0", "windows-x64").status == "current"
    assert {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()} == expected_files
    with tarfile.open(archive) as bundle:
        assert set(bundle.getnames()) == expected_files
        assert all(member.isfile() for member in bundle.getmembers())
    page = (output / "index.html").read_text(encoding="utf-8")
    assert "Windows için indir" in page and "Mac için indir" in page
    assert "Intel Mac için indir" not in page
    assert "Python veya sanal ortam kurmanız gerekmez." in page
    assert release_files["signing_key"].read_bytes() not in envelope


def test_wrong_private_key_cannot_publish_an_update(release_files):
    other = Ed25519PrivateKey.generate()
    release_files["signing_key"].write_bytes(other.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    with pytest.raises(ValueError, match="gömülü yayıncı anahtarıyla eşleşmiyor"):
        publisher.prepare_release(**release_files)
    assert not release_files["output"].exists()


def test_existing_publication_is_preserved(release_files):
    output = release_files["output"]
    output.mkdir()
    sentinel = output / "stable.manifest"
    sentinel.write_text("previous release")
    with pytest.raises(ValueError, match="yeni veya boş"):
        publisher.prepare_release(**release_files)
    assert sentinel.read_text() == "previous release"


def test_optional_intel_package_has_distinct_verified_asset(release_files, tmp_path):
    intel = tmp_path / "RpaOrkestrAI-0.2.0-macOS-x64.dmg"
    intel.write_bytes(b"different architecture")
    output = publisher.prepare_release(**release_files, macos_x64=intel)
    client = UpdateClient(publisher.update_config.FEED_URL, publisher.update_config.PUBLIC_KEY,
                          cache_dir=tmp_path / "cache", now=lambda: release_files["now"])
    result = client.authenticate_manifest((output / "stable.manifest").read_bytes(), "0.1.1", "macos-x64")
    assert result.status == "available", result.message
    client.verify_download(result.release, output / "releases" / "0.2.0" / intel.name)
    assert "Intel Mac için indir" in (output / "index.html").read_text(encoding="utf-8")


def test_duplicate_mac_package_name_does_not_overwrite_architecture(release_files):
    with pytest.raises(ValueError, match="farklı bir ada"):
        publisher.prepare_release(**release_files, macos_x64=release_files["macos_arm64"])
    assert not release_files["output"].exists()


@pytest.mark.parametrize("version", ["../0.2.0", "0.2.0rc1", "0.2", "0.2.0+local"])
def test_stable_release_rejects_unsafe_or_preview_versions(release_files, version):
    release_files["version"] = version
    with pytest.raises(ValueError, match="Kararlı sürümü"):
        publisher.prepare_release(**release_files)
    assert not release_files["output"].exists()
