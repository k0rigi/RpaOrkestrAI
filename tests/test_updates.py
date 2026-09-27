import base64
import hashlib
import io
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from urllib.error import URLError
from urllib.request import Request

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from rpa_orkestrai import updates

FEED = "https://orkestrai.net/rpa/stable.manifest"
ASSET = "https://orkestrai.net/rpa/releases/0.2.0/Studio.exe"
NOW = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
PACKAGE = b"verified installer bytes"


class Response(io.BytesIO):
    def __init__(self, data, url, headers=None, status=200):
        super().__init__(data)
        self.url, self.headers, self.status = url, headers or {}, status
        self.bytes_read = 0

    def geturl(self):
        return self.url

    def read1(self, count):
        value = super().read(count)
        self.bytes_read += len(value)
        return value


class Transport:
    def __init__(self):
        self.routes, self.calls = {}, []

    def open(self, request, timeout):
        self.calls.append((request.full_url, timeout))
        value = self.routes[request.full_url]
        if isinstance(value, Exception):
            raise value
        return value() if callable(value) else value


@pytest.fixture
def signed(tmp_path):
    key = Ed25519PrivateKey.generate()
    payload = {
        "schema": 1,
        "channel": "stable",
        "version": "0.2.0",
        "published_at": (NOW - timedelta(days=1)).isoformat(),
        "expires_at": (NOW + timedelta(days=30)).isoformat(),
        "assets": {
            "windows-x64": {
                "url": ASSET,
                "sha256": hashlib.sha256(PACKAGE).hexdigest(),
                "size": len(PACKAGE),
                "type": "exe",
            }
        },
    }
    transport = Transport()
    client = updates.UpdateClient(
        FEED, key.public_key().public_bytes_raw(), cache_dir=tmp_path / "updates",
        opener=transport, now=lambda: NOW, os_version="10.0.26100",
    )

    def envelope(data=None, signing_key=None):
        raw = json.dumps(payload if data is None else data, ensure_ascii=False).encode("utf-8")
        return json.dumps({
            "payload": base64.b64encode(raw).decode("ascii"),
            "signature": base64.b64encode((signing_key or key).sign(raw)).decode("ascii"),
        }).encode("utf-8")

    transport.routes[FEED] = lambda: Response(envelope(), FEED)
    transport.routes[ASSET] = lambda: Response(PACKAGE, ASSET, {"Content-Length": str(len(PACKAGE))})
    return client, payload, envelope, transport


def available(signed):
    client = signed[0]
    result = client.check("0.1.1", "windows-x64")
    assert result.status == "available", result.message
    return result.release


def test_signed_update_can_be_staged_and_verified_offline_without_touching_workspace(signed, tmp_path):
    client, _, _, transport = signed
    workspace = tmp_path / "workspace" / "flows.json"
    workspace.parent.mkdir()
    workspace.write_text("my saved flows", encoding="utf-8")
    release = available(signed)
    path = client.download(release)
    assert path.read_bytes() == PACKAGE
    assert path.parent == client.cache_dir
    assert len(transport.calls) == 2
    transport.routes = {}
    assert client.authenticate_manifest(release.manifest_bytes, "0.1.1", "windows-x64").release == release
    client.verify_download(release, path)
    assert client.download(release) == path  # verified cache does not need the network
    assert len(transport.calls) == 2
    assert workspace.read_text(encoding="utf-8") == "my saved flows"


def test_manifest_version_uses_numeric_order_and_does_not_downgrade(signed):
    client, payload, _, _ = signed
    payload["version"] = "0.10.0"
    assert client.check("0.9.0", "windows-x64").status == "available"
    assert client.check("0.10.0", "windows-x64").status == "current"
    assert client.check("0.11.0", "windows-x64").status == "current"


@pytest.mark.parametrize("change", [
    {"expires_at": NOW.isoformat()},
    {"expires_at": (NOW - timedelta(days=2)).isoformat()},
    {"published_at": (NOW + timedelta(hours=1)).isoformat()},
    {"published_at": "2026-09-27T12:00:00"},
    {"schema": 2},
    {"schema": True},
    {"channel": "preview"},
    {"version": "garbage"},
    {"version": "0.2.0rc1"},
    {"version": "1!0.2.0"},
    {"version": "0.2.0+local"},
    {"version": 2},
    {"assets": []},
    {"assets": {}},
    {"assets": {"unrecognized-platform": {}}},
])
def test_signed_but_invalid_or_expired_metadata_never_offers_an_update(signed, change):
    client, payload, _, _ = signed
    payload.update(change)
    result = client.check("0.1.1", "windows-x64")
    assert result.status == "invalid"
    assert result.release is None


@pytest.mark.parametrize("url", [
    "http://orkestrai.net/rpa/releases/Studio.exe",
    "https://malicious.example/rpa/releases/Studio.exe",
    "https://orkestrai.net:444/rpa/releases/Studio.exe",
    "https://user:password@orkestrai.net/rpa/releases/Studio.exe",
    "https://orkestrai.net/another-app/Studio.exe",
    "https://orkestrai.net/rpa/../another-app/Studio.exe",
    "https://orkestrai.net/rpa/%2e%2e/another-app/Studio.exe",
    "https://orkestrai.net/rpa/%252e%252e/another-app/Studio.exe",
    "https://orkestrai.net/rpa/releases/Studio.exe?token=secret",
    "https://orkestrai.net/rpa/releases/Studio.exe#anything",
    "https://orkestrai.net/rpa/releases/%0aStudio.exe",
    "file:///tmp/Studio.exe",
    "/rpa/releases/Studio.exe",
])
def test_even_signed_asset_urls_cannot_escape_the_approved_source(signed, url):
    client, payload, _, _ = signed
    payload["assets"]["windows-x64"]["url"] = url
    assert client.check("0.1.1", "windows-x64").status == "invalid"


@pytest.mark.parametrize("change", [
    {"size": True}, {"size": 0}, {"size": -1}, {"size": 2**40},
    {"sha256": "0" * 63}, {"sha256": "G" * 64}, {"type": "dmg"},
    {"url": ASSET + ".dmg"}, {"min_os": "nonsense"},
])
def test_asset_size_digest_type_and_os_are_validated(signed, change):
    client, payload, _, _ = signed
    payload["assets"]["windows-x64"].update(change)
    assert client.check("0.1.1", "windows-x64").status == "invalid"


def test_platform_and_minimum_os_must_match(signed):
    client, payload, _, transport = signed
    assert client.check("0.1.1", "linux-x64").status == "unsupported"
    assert transport.calls == []
    assert client.check("0.1.1", "macos-arm64").status == "unsupported"
    payload["assets"]["windows-x64"]["min_os"] = "10.0.30000"
    assert client.check("0.1.1", "windows-x64").status == "unsupported"
    payload["assets"]["windows-x64"]["min_os"] = "10"
    assert client.check("0.1.1", "windows-x64").status == "available"


@pytest.mark.parametrize("platform_key", ["macos-arm64", "macos-x64"])
def test_mac_packages_have_separate_architecture_selection(signed, platform_key):
    client, payload, _, _ = signed
    payload["assets"][platform_key] = {
        **payload["assets"]["windows-x64"],
        "url": f"https://orkestrai.net/rpa/releases/0.2.0/{platform_key}.dmg",
        "type": "dmg", "min_os": "12.0",
    }
    client.os_version = "14.0"
    result = client.check("0.1.1", platform_key)
    assert result.status == "available"
    assert result.release.platform_key == platform_key
    assert result.release.asset.type == "dmg"


def test_wrong_signing_key_and_altered_payload_are_rejected(signed):
    client, _, envelope, transport = signed
    forged = envelope(signing_key=Ed25519PrivateKey.generate())
    transport.routes[FEED] = lambda: Response(forged, FEED)
    assert client.check("0.1.1", "windows-x64").status == "invalid"
    altered = json.loads(envelope())
    raw = base64.b64decode(altered["payload"]).replace(b"0.2.0", b"9.9.9")
    altered["payload"] = base64.b64encode(raw).decode()
    transport.routes[FEED] = lambda: Response(json.dumps(altered).encode(), FEED)
    assert client.check("0.1.1", "windows-x64").status == "invalid"


@pytest.mark.parametrize("raw", [b"not JSON", b"[]", b'{"payload":"bad!", "signature":"bad!"}',
                                     b'{"payload":"", "payload":"", "signature":""}', b"\xff"])
def test_malformed_feed_returns_status_instead_of_crashing_startup(signed, raw):
    client, _, _, transport = signed
    transport.routes[FEED] = Response(raw, FEED)
    assert client.check("0.1.1", "windows-x64").status == "invalid"


@pytest.mark.parametrize("exception", [URLError("offline"), TimeoutError(), ConnectionResetError()])
def test_offline_feed_does_not_prevent_startup(signed, exception):
    client, _, _, transport = signed
    transport.routes[FEED] = exception
    result = client.check("0.1.1", "windows-x64")
    assert result.status == "unavailable"
    assert result.release is None
    assert not client.cache_dir.exists()


def test_manifest_download_is_size_bounded(signed):
    client, _, _, transport = signed
    response = Response(b"x" * (updates.MANIFEST_LIMIT * 2), FEED)
    transport.routes[FEED] = response
    assert client.check("0.1.1", "windows-x64").status == "invalid"
    assert response.bytes_read == updates.MANIFEST_LIMIT + 1


def test_manifest_download_has_an_overall_deadline(signed, monkeypatch):
    client, _, envelope, transport = signed
    monotonic = [0]
    monkeypatch.setattr(updates.time, "monotonic", lambda: monotonic[0])

    class SlowResponse(Response):
        def read1(self, count):
            monotonic[0] += 10
            return super().read1(count)

    transport.routes[FEED] = SlowResponse(envelope(), FEED)
    assert client.check("0.1.1", "windows-x64").status == "unavailable"


def test_redirect_handler_rejects_foreign_host_and_https_downgrade_before_following(signed):
    client = signed[0]
    handler = updates._SameOriginRedirect(client._validate_url)
    for destination in ["https://attacker.example/package.exe", "http://orkestrai.net/rpa/package.exe"]:
        with pytest.raises(updates.UpdateError):
            handler.redirect_request(Request(FEED), None, 302, "Found", {}, destination)
    allowed = "https://orkestrai.net/rpa/releases/0.2.0/Studio.exe"
    assert handler.redirect_request(Request(FEED), None, 302, "Found", {}, allowed).full_url == allowed


def test_untrusted_final_response_url_is_rejected_and_closed(signed):
    client, _, envelope, transport = signed
    response = Response(envelope(), "https://attacker.example/feed")
    transport.routes[FEED] = response
    assert client.check("0.1.1", "windows-x64").status == "invalid"
    assert response.closed


@pytest.mark.parametrize("body", [PACKAGE[:-1], b"x" * len(PACKAGE), PACKAGE + b"excess"])
def test_corrupt_truncated_and_oversized_downloads_never_become_installable(signed, body):
    client, _, _, transport = signed
    release = available(signed)
    response = Response(body, ASSET)
    transport.routes[ASSET] = response
    with pytest.raises(updates.UpdateError):
        client.download(release)
    assert list(client.cache_dir.iterdir()) == []
    assert response.bytes_read <= release.asset.size + 1


def test_lied_about_content_length_is_rejected_before_download(signed):
    client, _, _, transport = signed
    release = available(signed)
    response = Response(PACKAGE, ASSET, {"Content-Length": "1000000000000"})
    transport.routes[ASSET] = response
    with pytest.raises(updates.UpdateError):
        client.download(release)
    assert response.bytes_read == 0
    assert list(client.cache_dir.iterdir()) == []


def test_interrupted_download_discards_partial_file(signed):
    client, _, _, transport = signed
    release = available(signed)

    class InterruptedResponse(Response):
        def read1(self, count):
            if self.bytes_read:
                raise ConnectionResetError()
            return super().read1(5)

    transport.routes[ASSET] = InterruptedResponse(PACKAGE, ASSET)
    with pytest.raises(updates.UpdateUnavailable):
        client.download(release)
    assert list(client.cache_dir.iterdir()) == []


def test_gui_shutdown_cancels_download_and_removes_partial_file(signed):
    client, _, _, transport = signed
    release = available(signed)
    cancelled = [False]

    class CancelledResponse(Response):
        def read1(self, count):
            cancelled[0] = True
            return super().read1(5)

    transport.routes[ASSET] = CancelledResponse(PACKAGE, ASSET)
    with pytest.raises(updates.UpdateUnavailable):
        client.download(release, cancelled=lambda: cancelled[0])
    assert list(client.cache_dir.iterdir()) == []
    calls = len(transport.calls)
    with pytest.raises(updates.UpdateUnavailable):
        client.download(release, cancelled=lambda: True)
    assert len(transport.calls) == calls


def test_encoded_response_is_not_accepted_as_verified_package(signed):
    client, _, _, transport = signed
    release = available(signed)
    response = Response(PACKAGE, ASSET, {"Content-Encoding": "gzip"})
    transport.routes[ASSET] = response
    with pytest.raises(updates.UpdateError):
        client.download(release)
    assert response.bytes_read == 0
    assert list(client.cache_dir.iterdir()) == []


def test_tampered_release_or_cached_file_requires_new_verification(signed):
    client = signed[0]
    release = available(signed)
    forged = replace(release, asset=replace(release.asset, sha256="0" * 64))
    with pytest.raises(updates.UpdateError):
        client.download(forged)
    assert not client.cache_dir.exists()
    path = client.download(release)
    path.write_bytes(b"x" * len(PACKAGE))
    with pytest.raises(updates.UpdateError):
        client.verify_download(release, path)
    assert client.download(release).read_bytes() == PACKAGE


def test_expired_cached_manifest_cannot_install_offline(signed):
    client = signed[0]
    release = available(signed)
    path = client.download(release)
    client.now = lambda: NOW + timedelta(days=31)
    assert client.authenticate_manifest(release.manifest_bytes, "0.1.1", "windows-x64").status == "invalid"
    with pytest.raises(updates.UpdateError):
        client.verify_download(release, path)
    assert path.read_bytes() == PACKAGE  # rejection does not modify the current app or package


@pytest.mark.parametrize("system,machine,expected", [
    ("Windows", "AMD64", "windows-x64"),
    ("Darwin", "arm64", "macos-arm64"),
    ("Darwin", "x86_64", "macos-x64"),
    ("Linux", "x86_64", None),
    ("Windows", "ARM64", None),
])
def test_platform_selection_matches_running_architecture(monkeypatch, system, machine, expected):
    monkeypatch.setattr(updates.platform, "system", lambda: system)
    monkeypatch.setattr(updates.platform, "machine", lambda: machine)
    assert updates.current_platform_key() == expected
