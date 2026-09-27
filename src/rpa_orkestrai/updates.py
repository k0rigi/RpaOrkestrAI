"""Verify and stage desktop updates; this module never installs or executes them.

The web server only hosts public, immutable packages and a signed manifest. The
private signing key must never be shipped with Studio or stored on that server.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import http.client
import json
import os
import platform
import re
import ssl
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

import certifi
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from packaging.version import InvalidVersion, Version

MANIFEST_LIMIT = 128 * 1024
CHUNK_SIZE = 64 * 1024
PLATFORMS = {"windows-x64": "exe", "macos-arm64": "dmg", "macos-x64": "dmg"}


class UpdateError(RuntimeError):
    """An update cannot be trusted or staged; keep the installed app intact."""


class UpdateUnavailable(UpdateError):
    """The feed or package cannot currently be reached."""


@dataclass(frozen=True)
class UpdateAsset:
    url: str
    sha256: str
    size: int
    type: str
    min_os: str | None = None


@dataclass(frozen=True)
class Release:
    version: str
    channel: str
    platform_key: str
    asset: UpdateAsset
    published_at: datetime
    expires_at: datetime
    manifest: bytes = field(repr=False)

    @property
    def manifest_bytes(self) -> bytes:
        return self.manifest


@dataclass(frozen=True)
class UpdateCheck:
    status: str
    current_version: str
    release: Release | None = None
    message: str = ""


def current_platform_key() -> str | None:
    """Select the running build's architecture, including x64 under emulation."""
    system, machine = platform.system(), platform.machine().lower()
    if system == "Windows" and machine in {"amd64", "x86_64"}:
        return "windows-x64"
    if system == "Darwin":
        if machine in {"arm64", "aarch64"}:
            return "macos-arm64"
        if machine in {"x86_64", "amd64"}:
            return "macos-x64"
    return None


def _json_object(raw: bytes) -> dict:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise UpdateError("Güncelleme bildirimi yinelenen alan içeriyor.")
            value[key] = item
        return value

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise UpdateError("Güncelleme bildirimi geçerli JSON değil.") from exc
    if not isinstance(value, dict):
        raise UpdateError("Güncelleme bildirimi bir nesne olmalıdır.")
    return value


def _decode_base64(value, expected_size: int | None = None) -> bytes:
    try:
        if not isinstance(value, str):
            raise ValueError("not a string")
        raw = base64.b64decode(value, validate=True)
        if expected_size is not None and len(raw) != expected_size:
            raise ValueError("invalid length")
        return raw
    except (ValueError, binascii.Error) as exc:
        raise UpdateError("Güncelleme imzası veya anahtarı geçersiz.") from exc


def _version(value) -> Version:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise UpdateError("Güncelleme sürümü geçersiz.")
    try:
        parsed = Version(value)
    except InvalidVersion as exc:
        raise UpdateError("Güncelleme sürümü geçersiz.") from exc
    if parsed.epoch or parsed.local or len(parsed.release) != 3:
        raise UpdateError("Güncelleme sürümü geçersiz.")
    return parsed


def _timestamp(value) -> datetime:
    try:
        if not isinstance(value, str) or len(value) > 40:
            raise ValueError("invalid timestamp")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone missing")
        return parsed.astimezone(timezone.utc)
    except ValueError as exc:
        raise UpdateError("Güncelleme bildiriminin tarihi geçersiz.") from exc


def _os_version(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,5}(?:\.\d{1,5}){0,2}", value):
        raise UpdateError("Güncellemenin işletim sistemi sürümü geçersiz.")
    parts = [int(part) for part in value.split(".")]
    return tuple(parts + [0] * (3 - len(parts)))


class _SameOriginRedirect(HTTPRedirectHandler):
    def __init__(self, validate: Callable[[str], None]):
        self.validate = validate

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.validate(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class UpdateClient:
    def __init__(
        self,
        feed_url: str,
        public_key: str | bytes,
        *,
        cache_dir: Path,
        channel: str = "stable",
        timeout: float = 5,
        download_timeout: float = 600,
        max_download_bytes: int = 1024 * 1024 * 1024,
        opener=None,
        now: Callable[[], datetime] | None = None,
        os_version: str | None = None,
    ):
        self.feed_url = feed_url
        self.cache_dir = Path(cache_dir)
        self.channel = channel
        self.timeout = timeout
        self.download_timeout = download_timeout
        self.max_download_bytes = max_download_bytes
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.os_version = os_version
        if not 0 < timeout <= 30 or not 0 < download_timeout <= 1800:
            raise UpdateError("Güncelleme bağlantı süresi geçersiz.")
        if type(max_download_bytes) is not int or not 0 < max_download_bytes <= 4 * 1024**3:
            raise UpdateError("Güncelleme boyut sınırı geçersiz.")
        if channel not in {"stable", "preview"}:
            raise UpdateError("Güncelleme kanalı geçersiz.")
        try:
            parsed = urlsplit(feed_url)
            self._origin = (parsed.hostname, parsed.port or 443)
            self._prefix = unquote(parsed.path).rsplit("/", 1)[0] + "/"
        except (ValueError, TypeError) as exc:
            raise UpdateError("Güncelleme adresi geçersiz.") from exc
        self._validate_url(feed_url)
        raw_key = public_key if isinstance(public_key, bytes) else _decode_base64(public_key, 32)
        try:
            self._key = Ed25519PublicKey.from_public_bytes(raw_key)
        except (TypeError, ValueError) as exc:
            raise UpdateError("Güncelleme anahtarı geçersiz.") from exc
        self._opener = opener or build_opener(
            HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())),
            _SameOriginRedirect(self._validate_url),
        )

    def _validate_url(self, url: str) -> None:
        try:
            if not isinstance(url, str) or len(url) > 2048 or re.search(r"[\s\x00-\x1f\x7f]", url):
                raise ValueError("invalid url")
            parsed = urlsplit(url)
            path = unquote(parsed.path)
            if (
                parsed.scheme != "https" or not parsed.hostname
                or (parsed.hostname, parsed.port or 443) != self._origin
                or parsed.username is not None or parsed.password is not None
                or parsed.fragment or parsed.query or "\\" in path or "%" in path
                or re.search(r"[\s\x00-\x1f\x7f]", path)
                or any(part in {".", ".."} for part in path.split("/"))
                or not path.startswith(self._prefix)
            ):
                raise ValueError("unapproved url")
        except (ValueError, TypeError) as exc:
            raise UpdateError("Güncelleme adresi izin verilen HTTPS kaynağına ait değil.") from exc

    def _response(self, url: str):
        self._validate_url(url)
        request = Request(url, headers={"User-Agent": "RpaOrkestrAI-Updater/1", "Accept-Encoding": "identity"})
        try:
            response = self._opener.open(request, timeout=self.timeout)
            # Also enforce the final URL when a custom transport is used.
            try:
                self._validate_url(response.geturl())
                if response.status != 200 or response.headers.get("Content-Encoding", "identity") != "identity":
                    raise UpdateError("Güncelleme sunucusunun yanıtı geçersiz.")
            except UpdateError:
                response.close()
                raise
            return response
        except (HTTPError, URLError, OSError, http.client.HTTPException) as exc:
            raise UpdateUnavailable("Güncelleme sunucusuna ulaşılamadı; mevcut sürüm kullanılabilir.") from exc

    @staticmethod
    def _chunks(response, limit: int, deadline: float, cancelled: Callable[[], bool] | None = None):
        received = 0
        read = getattr(response, "read1", response.read)
        while True:
            if cancelled is not None and cancelled():
                raise UpdateUnavailable("Güncelleme indirmesi durduruldu.")
            if time.monotonic() >= deadline:
                raise UpdateUnavailable("Güncelleme indirme süresi doldu.")
            try:
                chunk = read(min(CHUNK_SIZE, limit - received + 1))
            except (OSError, http.client.HTTPException) as exc:
                raise UpdateUnavailable("Güncelleme indirmesi tamamlanamadı.") from exc
            if time.monotonic() >= deadline:
                raise UpdateUnavailable("Güncelleme indirme süresi doldu.")
            if not chunk:
                return
            received += len(chunk)
            if received > limit:
                raise UpdateError("Güncelleme indirmesi izin verilen boyutu aştı.")
            yield chunk

    def _release(self, envelope: bytes, platform_key: str) -> Release | None:
        if len(envelope) > MANIFEST_LIMIT:
            raise UpdateError("Güncelleme bildirimi çok büyük.")
        outer = _json_object(envelope)
        if set(outer) != {"payload", "signature"}:
            raise UpdateError("Güncelleme imza zarfı geçersiz.")
        payload = _decode_base64(outer["payload"])
        signature = _decode_base64(outer["signature"], 64)
        try:
            self._key.verify(signature, payload)
        except InvalidSignature as exc:
            raise UpdateError("Güncellemenin yayıncı imzası doğrulanamadı.") from exc
        data = _json_object(payload)
        if type(data.get("schema")) is not int or data["schema"] != 1 or data.get("channel") != self.channel:
            raise UpdateError("Güncelleme bildiriminin sürümü veya kanalı uyumsuz.")
        version = _version(data.get("version"))
        if self.channel == "stable" and (version.is_prerelease or version.is_devrelease):
            raise UpdateError("Kararlı güncelleme kanalı bir deneme sürümü içeriyor.")
        published = _timestamp(data.get("published_at"))
        expires = _timestamp(data.get("expires_at"))
        now = self.now().astimezone(timezone.utc)
        if published > now + timedelta(minutes=10) or expires <= now or expires <= published:
            raise UpdateError("Güncelleme bildiriminin geçerlilik süresi dolmuş veya tarihi uyumsuz.")
        assets = data.get("assets")
        if not isinstance(assets, dict) or not assets or set(assets) - PLATFORMS.keys():
            raise UpdateError("Güncelleme paket listesi geçersiz.")
        parsed_assets = {}
        for key, item in assets.items():
            if not isinstance(item, dict):
                raise UpdateError("Güncelleme paket bilgisi geçersiz.")
            url, digest, size, kind = (item.get(name) for name in ("url", "sha256", "size", "type"))
            self._validate_url(url)
            if (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                    or type(size) is not int or not 0 < size <= self.max_download_bytes
                    or kind != PLATFORMS[key] or not urlsplit(url).path.lower().endswith("." + kind)):
                raise UpdateError("Güncelleme paketinin türü, boyutu veya özeti geçersiz.")
            minimum = item.get("min_os")
            if minimum is not None:
                _os_version(minimum)
            parsed_assets[key] = UpdateAsset(url, digest, size, kind, minimum)
        asset = parsed_assets.get(platform_key)
        if asset is None:
            return None
        return Release(data["version"], self.channel, platform_key, asset, published, expires, envelope)

    def check(self, current_version: str, platform_key: str | None) -> UpdateCheck:
        """Check once. Network and validation failures never block Studio startup."""
        try:
            _version(current_version)
            if platform_key not in PLATFORMS:
                return UpdateCheck("unsupported", current_version, message="Bu platform için otomatik güncelleme yok.")
            deadline = time.monotonic() + self.timeout
            with self._response(self.feed_url) as response:
                envelope = b"".join(self._chunks(response, MANIFEST_LIMIT, deadline))
            return self.authenticate_manifest(envelope, current_version, platform_key)
        except UpdateUnavailable as exc:
            return UpdateCheck("unavailable", current_version, message=str(exc))
        except UpdateError as exc:
            return UpdateCheck("invalid", current_version, message=str(exc))

    def authenticate_manifest(self, envelope: bytes, current_version: str, platform_key: str | None) -> UpdateCheck:
        """Authenticate a saved envelope offline before using a staged update."""
        try:
            installed = _version(current_version)
            if platform_key not in PLATFORMS:
                return UpdateCheck("unsupported", current_version, message="Bu platform için otomatik güncelleme yok.")
            release = self._release(envelope, platform_key)
            if release is None:
                return UpdateCheck("unsupported", current_version, message="Bu platform için güncelleme paketi yok.")
            if _version(release.version) <= installed:
                return UpdateCheck("current", current_version, message="Uygulamanız güncel.")
            if release.asset.min_os:
                local_os = self.os_version or (
                    platform.mac_ver()[0] if platform_key.startswith("macos-") else platform.version()
                )
                if _os_version(local_os) < _os_version(release.asset.min_os):
                    return UpdateCheck("unsupported", current_version,
                                       message="Yeni sürüm daha güncel bir işletim sistemi gerektiriyor.")
            return UpdateCheck("available", current_version, release, "Yeni sürüm hazır.")
        except UpdateError as exc:
            return UpdateCheck("invalid", current_version, message=str(exc))

    def _validated(self, release: Release) -> Release:
        checked = self._release(release.manifest, release.platform_key)
        if checked != release:
            raise UpdateError("Güncelleme paket bilgileri imzalı bildirimle eşleşmiyor.")
        return checked

    def verify_download(self, release: Release, path: Path) -> None:
        """Recheck signature, expiration, file size and hash immediately before use."""
        self._validated(release)
        path = Path(path)
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size != release.asset.size:
                raise UpdateError("İndirilen güncelleme dosyasının boyutu geçersiz.")
            digest, received = hashlib.sha256(), 0
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
                    received += len(chunk)
                    if received > release.asset.size:
                        raise UpdateError("İndirilen güncelleme dosyasının boyutu geçersiz.")
                    digest.update(chunk)
            if received != release.asset.size or digest.hexdigest() != release.asset.sha256:
                raise UpdateError("İndirilen güncelleme dosyası doğrulanamadı.")
        except OSError as exc:
            raise UpdateError("İndirilen güncelleme dosyası okunamadı.") from exc

    def download(self, release: Release, *, cancelled: Callable[[], bool] | None = None) -> Path:
        """Stage a verified package atomically; interrupted downloads are discarded."""
        if cancelled is not None and cancelled():
            raise UpdateUnavailable("Güncelleme indirmesi durduruldu.")
        self._validated(release)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        target = self.cache_dir / f"{release.asset.sha256}.{release.asset.type}"
        if target.exists() and not target.is_symlink():
            try:
                self.verify_download(release, target)
                return target
            except UpdateError:
                pass
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.cache_dir, prefix=".download-", suffix=".part", delete=False) as handle:
                temporary = Path(handle.name)
                digest, received = hashlib.sha256(), 0
                deadline = time.monotonic() + self.download_timeout
                with self._response(release.asset.url) as response:
                    advertised = response.headers.get("Content-Length")
                    if advertised is not None and advertised != str(release.asset.size):
                        raise UpdateError("Güncelleme sunucusu farklı bir dosya boyutu bildirdi.")
                    for chunk in self._chunks(response, release.asset.size, deadline, cancelled):
                        received += len(chunk)
                        digest.update(chunk)
                        handle.write(chunk)
                if received != release.asset.size or digest.hexdigest() != release.asset.sha256:
                    raise UpdateError("İndirilen güncelleme dosyası doğrulanamadı.")
                handle.flush()
                os.fsync(handle.fileno())
            self._validated(release)
            if cancelled is not None and cancelled():
                raise UpdateUnavailable("Güncelleme indirmesi durduruldu.")
            temporary.replace(target)
            return target
        except (HTTPError, URLError, TimeoutError, ConnectionError) as exc:
            raise UpdateUnavailable("Güncelleme indirmesi tamamlanamadı.") from exc
        except OSError as exc:
            raise UpdateError("Güncelleme dosyası kaydedilemedi; mevcut sürüm korunuyor.") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
