import base64
import hashlib
import importlib.util
import io
import json
import tarfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def load_script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / (name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


deploy = load_script("deploy_update_bundle")
prepare = load_script("prepare_update_release")


@pytest.fixture
def publication(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    public = base64.b64encode(key.public_key().public_bytes_raw()).decode("ascii")
    monkeypatch.setattr(deploy, "UPDATE_PUBLIC_KEY", public)
    monkeypatch.setattr(prepare.update_config, "PUBLIC_KEY", public)
    private = tmp_path / "private.pem"
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption()))
    windows, mac = tmp_path / "Studio.exe", tmp_path / "Studio-arm64.dmg"
    windows.write_bytes(b"installer")
    mac.write_bytes(b"disk image")
    archive = tmp_path / "bundle.tar.gz"
    site = prepare.prepare_release(version="0.2.0", windows=windows, macos_arm64=mac, signing_key=private,
                                   output=tmp_path / "site", archive=archive)
    namespace = {"__name__": "test_remote_program"}
    exec(compile(deploy.REMOTE_CODE, "test_remote_program", "exec"), namespace)
    root = tmp_path.resolve() / "webroot" / "rpa"
    root.parent.mkdir()
    namespace["ROOT"] = root
    return archive, site, namespace


def upload_to_fixture(archive, namespace):
    root = namespace["ROOT"]
    root.mkdir(exist_ok=True)
    token = "a" * 32
    uploaded = root / (".upload-" + token + ".tar.gz")
    uploaded.write_bytes(archive.read_bytes())
    digest = hashlib.sha256(uploaded.read_bytes()).hexdigest()
    return digest, token


def rewrite_tar(source, target, transform=None, extra=None):
    with tarfile.open(source) as original, tarfile.open(target, "w:gz") as rewritten:
        for member in original:
            data = original.extractfile(member).read()
            if transform:
                data = transform(member.name, data)
            member.size = len(data)
            rewritten.addfile(member, io.BytesIO(data))
        if extra:
            rewritten.addfile(*extra)


def test_pin_matches_the_app_trust_anchor():
    # This test is outside the fixture's temporary signing-key replacement.
    assert deploy.UPDATE_PUBLIC_KEY == prepare.update_config.PUBLIC_KEY


def test_signed_publication_changes_only_rpa_and_feed_is_published_last(publication, monkeypatch):
    archive, site, namespace = publication
    root = namespace["ROOT"]
    unrelated = root.parent / "index.php"
    unrelated.write_text("keep main website")
    deploy.validate_local_bundle(archive, "0.2.0")
    replacements = []
    original_replace = namespace["os"].replace

    def replace(source, destination):
        replacements.append(Path(destination).name)
        return original_replace(source, destination)

    monkeypatch.setattr(namespace["os"], "replace", replace)
    digest, token = upload_to_fixture(archive, namespace)
    result = namespace["publish"]("0.2.0", digest, token)
    assert result["ok"] and result["package_count"] == 2
    assert replacements[-2:] == ["index.html", "stable.manifest"]
    assert (root / "stable.manifest").read_bytes() == (site / "stable.manifest").read_bytes()
    assert unrelated.read_text() == "keep main website"
    assert not list(root.glob(".upload-*"))
    assert not list(root.glob(".publish-*"))


def test_read_only_inspection_does_not_create_rpa(publication):
    _, _, namespace = publication
    result = namespace["inspect_root"]()
    assert result["exists"] is False and result["current_version"] is None
    assert result["python_version"].count(".") == 2
    assert not namespace["ROOT"].exists()


def test_manifest_with_changed_payload_and_same_length_signature_is_rejected(publication, tmp_path):
    archive, _, _ = publication

    def tamper(name, data):
        if name != "stable.manifest":
            return data
        envelope = json.loads(data)
        payload = json.loads(base64.b64decode(envelope["payload"]))
        payload["release_notes"] = "Unsigned added field"
        envelope["payload"] = base64.b64encode(json.dumps(payload).encode()).decode()
        return json.dumps(envelope).encode()

    altered = tmp_path / "tampered.tar.gz"
    rewrite_tar(archive, altered, transform=tamper)
    # A matching archive checksum cannot replace the publisher's signature.
    assert hashlib.sha256(altered.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="publisher signature"):
        deploy.validate_local_bundle(altered, "0.2.0")


@pytest.mark.parametrize("name,kind", [("../outside", tarfile.REGTYPE),
                                       ("index.html", tarfile.SYMTYPE),
                                       ("secrets.pem", tarfile.REGTYPE)])
def test_unlisted_members_and_links_are_rejected(publication, tmp_path, name, kind):
    archive, _, _ = publication
    member = tarfile.TarInfo(name)
    member.type = kind
    member.size = 4 if kind == tarfile.REGTYPE else 0
    if kind == tarfile.SYMTYPE:
        member.linkname = "/etc/passwd"
    altered = tmp_path / "unexpected.tar.gz"
    rewrite_tar(archive, altered, extra=(member, io.BytesIO(b"data")))
    with pytest.raises(ValueError, match="unexpected member"):
        deploy.validate_local_bundle(altered, "0.2.0")
    assert not (tmp_path / "outside").exists()


def test_immutable_release_is_not_overwritten(publication):
    archive, _, namespace = publication
    digest, token = upload_to_fixture(archive, namespace)
    namespace["publish"]("0.2.0", digest, token)
    root = namespace["ROOT"]
    asset = root / "releases" / "0.2.0" / "Studio.exe"
    asset.write_bytes(b"previous package must survive")
    existing_manifest = (root / "stable.manifest").read_bytes()
    digest, token = upload_to_fixture(archive, namespace)
    with pytest.raises(ValueError, match="immutable"):
        namespace["publish"]("0.2.0", digest, token)
    assert asset.read_bytes() == b"previous package must survive"
    assert (root / "stable.manifest").read_bytes() == existing_manifest


@pytest.mark.parametrize("url", ["http://release-assets.githubusercontent.com/file",
                                 "https://github.com/file", "https://release-assets.githubusercontent.com.evil/file",
                                 "https://user@release-assets.githubusercontent.com/file"])
def test_bundle_download_cannot_leave_approved_https_host(url):
    with pytest.raises(ValueError, match="approved HTTPS"):
        deploy.validate_bundle_url(url)


def test_dispatch_input_url_is_read_without_shell_interpolation_or_logging(tmp_path, monkeypatch, capsys):
    event = tmp_path / "event.json"
    url = "https://release-assets.githubusercontent.com/file?token=private"
    event.write_text(json.dumps({"inputs": {"action": "publish", "bundle_url": url}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.delenv("RPA_BUNDLE_URL", raising=False)
    assert deploy.settings()["bundle_url"] == url
    assert capsys.readouterr().out == ""


def test_remote_publication_uses_python36_compatible_date_and_cleanup_apis(publication, monkeypatch):
    archive, _, namespace = publication
    # Older server datetime has no fromisoformat, and Path.unlink has no
    # missing_ok keyword. Exercise actual extraction, publication and cleanup.
    namespace["datetime"] = SimpleNamespace(now=datetime.now, strptime=datetime.strptime)
    original_unlink = Path.unlink

    def old_unlink(self):
        return original_unlink(self)

    monkeypatch.setattr(Path, "unlink", old_unlink)
    digest, token = upload_to_fixture(archive, namespace)
    assert namespace["publish"]("0.2.0", digest, token)["ok"]
    assert not list(namespace["ROOT"].glob(".upload-*"))


@pytest.mark.parametrize("error_type,reason,expected_reason", [
    ("ValueError", "Uploaded bundle checksum does not match.", "Uploaded bundle checksum does not match."),
    ("AttributeError", "secret_url=https://private.example/?password=hidden", None),
    ("ValueError", "PASSWORD=hidden", None),
    ("PasswordIsHidden", "hidden", None),
])
def test_remote_failure_diagnostics_include_only_safe_metadata(error_type, reason, expected_reason, capsys):
    result = {"ok": False, "error_type": error_type, "error": reason}
    stdout = io.BytesIO(json.dumps(result).encode())
    stdout.channel = SimpleNamespace(recv_exit_status=lambda: 1)
    client = SimpleNamespace(exec_command=lambda *args, **kwargs: (io.BytesIO(), stdout, io.BytesIO()))
    with pytest.raises(RuntimeError, match="inspect /rpa"):
        deploy.remote(client, "publish")
    output = capsys.readouterr().err
    assert '"action": "publish"' in output
    assert "hidden" not in output and "https://private.example" not in output
    if expected_reason:
        assert expected_reason in output
    elif error_type == "AttributeError":
        assert "AttributeError" in output
    else:
        assert '"reason"' not in output
