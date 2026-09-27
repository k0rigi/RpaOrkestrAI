"""orkestrai.net license gate for the local Studio API.

orkestrai.net signs a short-lived license with Ed25519: at most seven days after
the last successful check and never past the company's MOD_RPA end date. Studio
verifies it offline with the embedded public key and renews it with a device-bound
refresh token; the password is never stored. The device id mixes this computer's
identifier into a random install id, so a copied workspace does not carry the
license to another computer.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import http.client
import json
import platform
import re
import ssl
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from datetime import time as day_time
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

import certifi
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import __version__
from .config import atomic_json

LICENSE_API = "https://orkestrai.net/api/rpa/lisans"
# Served at LICENSE_API/anahtar; the private key never leaves orkestrai.net.
LICENSE_PUBLIC_KEY = "ZPxj98IYClRDVdbSPDY4fLrPZBKBhichNXmx6FGTTqA="
PRODUCT, MODULE = "rpa-orkestrai", "MOD_RPA"
REFRESH_SECONDS = 3600
RETRY_SECONDS = 300
CLOCK_TOLERANCE = 600
LAST_SEEN_WRITE_INTERVAL = 300
RESPONSE_LIMIT = 64 * 1024
# Everything else under /api/ requires a valid license.
OPEN_PATHS = frozenset({
    "/api/health", "/api/instance", "/api/license", "/api/license/login",
    "/api/license/refresh", "/api/license/logout", "/api/license/quit",
})
DENIALS = {"SURE_DOLDU": "expired", "YETKI_YOK": "denied"}
OFFLINE_MESSAGE = ("Lisans 7 gündür orkestrai.net üzerinden doğrulanamadı. "
                   "İnternet bağlantınızı kontrol edip yeniden deneyin.")
CLOCK_MESSAGE = ("Bilgisayarın tarih ve saati geri alınmış görünüyor. Saati düzeltip "
                 "lisansı internet bağlantısıyla yeniden doğrulayın.")
UNAVAILABLE_MESSAGE = "orkestrai.net lisans sunucusuna ulaşılamadı. İnternet bağlantınızı kontrol edin."


class LicenseError(RuntimeError):
    """A public message for the login form."""


class LicenseUnavailable(LicenseError):
    """The server could not be reached or answered unexpectedly; keep the cached license."""


class LicenseDenied(LicenseError):
    def __init__(self, code: str, message: str, ends_on: str | None = None):
        super().__init__(message)
        self.code, self.ends_on = code, ends_on


def expired_message(ends_on: date | None) -> str:
    if ends_on is None:
        return "RpaOrkestrAI kullanım süreniz dolmuştur."
    return f"RpaOrkestrAI kullanım süreniz {ends_on.strftime('%d.%m.%Y')} tarihinde dolmuştur."


@dataclass(frozen=True)
class License:
    user: str
    full_name: str
    user_id: int
    company: str
    company_id: int
    ends_on: date | None
    device: str
    issued: datetime
    valid_until: datetime

    def public(self) -> dict:
        return {"user": self.user, "full_name": self.full_name, "company": self.company,
                "ends_on": self.ends_on.isoformat() if self.ends_on else None,
                "valid_until": self.valid_until.isoformat()}

    def end_of_term(self) -> datetime | None:
        if self.ends_on is None:
            return None
        return datetime.combine(self.ends_on, day_time(23, 59, 59), tzinfo=self.valid_until.tzinfo)


def _base64(value: Any, size: int | None = None) -> bytes:
    try:
        if not isinstance(value, str) or len(value) > RESPONSE_LIMIT:
            raise ValueError("not a string")
        raw = base64.b64decode(value, validate=True)
        if size is not None and len(raw) != size:
            raise ValueError("invalid length")
        return raw
    except (ValueError, binascii.Error) as exc:
        raise LicenseError("Lisans imzası geçersiz.") from exc


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("invalid timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("timezone missing")
    return parsed


def verify_license(envelope: Any, key: Ed25519PublicKey, device: str) -> License:
    if not isinstance(envelope, dict) or set(envelope) != {"payload", "signature"}:
        raise LicenseError("Lisans biçimi geçersiz.")
    payload = _base64(envelope["payload"])
    try:
        key.verify(_base64(envelope["signature"], 64), payload)
    except InvalidSignature as exc:
        raise LicenseError("Lisans imzası doğrulanamadı.") from exc
    try:
        claims = json.loads(payload.decode("utf-8"))
        if (not isinstance(claims, dict) or claims.get("surum") != 1 or claims.get("urun") != PRODUCT
                or claims.get("modul") != MODULE):
            raise ValueError("wrong product")
        ends_on = claims.get("bitis")
        result = License(
            user=str(claims["kullanici"]), full_name=str(claims.get("ad_soyad") or ""),
            user_id=int(claims["kullanici_id"]), company=str(claims.get("firma_adi") or ""),
            company_id=int(claims["firma_id"]), ends_on=date.fromisoformat(ends_on) if ends_on else None,
            device=str(claims["cihaz"]), issued=_timestamp(claims["verildi"]),
            valid_until=_timestamp(claims["gecerlilik"]),
        )
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise LicenseError("Lisans içeriği geçersiz.") from exc
    if result.device != device:
        raise LicenseError("Lisans bu bilgisayara ait değil.")
    return result


def machine_identifier() -> str:
    """Stable per-computer identifier; never sent in clear, only inside the device hash."""
    system = platform.system()
    try:
        if system == "Windows":
            import winreg

            access = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, access) as key:
                return str(winreg.QueryValueEx(key, "MachineGuid")[0])
        if system == "Darwin":
            output = subprocess.run(["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                                    capture_output=True, text=True, timeout=5, check=True).stdout
            match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', output)
            if match:
                return match.group(1)
        for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            path = Path(candidate)
            if path.is_file():
                value = path.read_text(encoding="ascii").strip()
                if value:
                    return value
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return f"node-{uuid.getnode():012x}"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LicenseService:
    def __init__(
        self, data_dir: Path | str, *, api_url: str = LICENSE_API, public_key: str = LICENSE_PUBLIC_KEY,
        opener: Any = None, clock: Callable[[], float] = time.time,
        machine_id: Callable[[], str] = machine_identifier, timeout: float = 15,
    ):
        self._path = Path(data_dir) / "license.json"
        self._api = api_url.rstrip("/")
        self._key = Ed25519PublicKey.from_public_bytes(_base64(public_key, 32))
        self._opener = opener or build_opener(
            HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())), _NoRedirect())
        self._clock, self._timeout = clock, timeout
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._online: bool | None = None
        stored = self._load()
        install = stored.get("install")
        if not isinstance(install, str) or not re.fullmatch(r"[0-9a-f]{32}", install):
            install = uuid.uuid4().hex
        self._install = install
        self.device = hashlib.sha256(f"{PRODUCT}:{machine_id()}:{install}".encode()).hexdigest()[:32]
        self._skew = float(stored.get("skew") or 0) if isinstance(stored.get("skew"), (int, float)) else 0.0
        self._last_seen = float(stored["last_seen"]) if isinstance(stored.get("last_seen"), (int, float)) else 0.0
        self._last_written = self._last_seen
        token = stored.get("refresh")
        self._refresh_token = token if isinstance(token, str) and len(token) <= 4096 else None
        denial = stored.get("denial")
        self._denial = denial if isinstance(denial, dict) and denial.get("state") in DENIALS.values() else None
        self._license: License | None = None
        if stored.get("license") is not None:
            try:
                self._license = verify_license(stored["license"], self._key, self.device)
                self._envelope = stored["license"]
            except LicenseError:
                # Tampered, from another computer or signed by a retired key.
                self._license, self._refresh_token = None, None
        if self._license is None:
            self._envelope = None
        if install != stored.get("install"):
            self._save()

    # ----- persistence -------------------------------------------------------------
    def _load(self) -> dict:
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        atomic_json(self._path, {
            "install": self._install, "license": self._envelope, "refresh": self._refresh_token,
            "skew": self._skew, "last_seen": self._last_seen, "denial": self._denial,
        })
        self._last_written = self._last_seen

    # ----- evaluation --------------------------------------------------------------
    def _now(self) -> float:
        return self._clock() + self._skew

    def _evaluate(self) -> tuple[str, str]:
        if self._denial:
            return self._denial["state"], str(self._denial.get("message") or "")
        current = self._license
        if current is None:
            return "login_required", ""
        now = self._now()
        if now + CLOCK_TOLERANCE < self._last_seen:
            return "verification_required", CLOCK_MESSAGE
        if now >= current.valid_until.timestamp():
            end = current.end_of_term()
            if end is not None and now >= end.timestamp():
                return "expired", expired_message(current.ends_on)
            return "verification_required", OFFLINE_MESSAGE
        return "valid", ""

    def allowed(self) -> bool:
        with self._lock:
            if self._evaluate()[0] != "valid":
                return False
            now = self._now()
            if now > self._last_seen:
                self._last_seen = now
                if now - self._last_written >= LAST_SEEN_WRITE_INTERVAL:
                    try:
                        self._save()
                    except OSError:
                        pass  # The in-memory guard still applies for this session.
            return True

    def status(self) -> dict:
        with self._lock:
            state, message = self._evaluate()
            public = self._license.public() if self._license else None
            if public is None and self._denial and self._denial.get("user"):
                public = {"user": self._denial["user"], "full_name": "", "company": "",
                          "ends_on": self._denial.get("ends_on"), "valid_until": None}
            return {"state": state, "message": message, "online": self._online, "license": public,
                    "remembered": self._refresh_token is not None}

    # ----- server ------------------------------------------------------------------
    def _post(self, endpoint: str, body: dict) -> dict:
        request = Request(f"{self._api}/{endpoint}", data=json.dumps(body).encode("utf-8"), method="POST",
                          headers={"Content-Type": "application/json", "Accept": "application/json",
                                   "User-Agent": f"RpaOrkestrAI/{__version__}"})
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                status, raw = response.status, response.read(RESPONSE_LIMIT + 1)
        except HTTPError as exc:
            status = exc.code
            try:
                raw = exc.read(RESPONSE_LIMIT + 1)
            except (OSError, http.client.HTTPException):
                raw = b""
            finally:
                exc.close()
        except (URLError, OSError, http.client.HTTPException, ValueError) as exc:
            raise LicenseUnavailable(UNAVAILABLE_MESSAGE) from exc
        try:
            if len(raw) > RESPONSE_LIMIT:
                raise ValueError("too large")
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise LicenseUnavailable(UNAVAILABLE_MESSAGE) from exc
        if status == 200 and data.get("success") is True:
            return data
        code, message = data.get("kod"), data.get("message")
        if status >= 500 or not isinstance(code, str) or not isinstance(message, str):
            raise LicenseUnavailable(UNAVAILABLE_MESSAGE)
        ends_on = data.get("bitis") if isinstance(data.get("bitis"), str) else None
        raise LicenseDenied(code, message[:300], ends_on)

    def _accept(self, response: dict) -> None:
        token = response.get("yenileme")
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_\-.]{20,4096}", token):
            raise LicenseUnavailable("Lisans sunucusunun yanıtı geçersiz.")
        try:
            accepted = verify_license(response.get("lisans"), self._key, self.device)
        except LicenseError as exc:
            raise LicenseUnavailable("Lisans sunucusunun imzası doğrulanamadı. Uygulamayı güncelleyin.") from exc
        with self._lock:
            # Server time is authoritative; the skew keeps wrong local clocks usable.
            self._skew = accepted.issued.timestamp() - self._clock()
            self._license, self._envelope, self._refresh_token = accepted, response["lisans"], token
            self._last_seen, self._denial, self._online = self._now(), None, True
            self._save()

    def _deny(self, exc: LicenseDenied, user: str | None = None) -> None:
        with self._lock:
            if exc.code == "OTURUM_GECERSIZ":
                self._license = self._envelope = self._refresh_token = None
                self._denial = None
            else:
                ends_on = None
                try:
                    ends_on = date.fromisoformat(exc.ends_on) if exc.ends_on else None
                except ValueError:
                    pass
                state = DENIALS[exc.code]
                message = expired_message(ends_on) if state == "expired" else str(exc)
                known = user or (self._license.user if self._license else None)
                # A renewed license is picked up by the kept refresh token on the next check;
                # a refused login for another account must not fall back to the previous one.
                if user is not None:
                    self._refresh_token = None
                self._license = self._envelope = None
                self._denial = {"state": state, "message": message, "user": known,
                                "ends_on": ends_on.isoformat() if ends_on else None}
            self._online = True
            self._save()

    def refresh(self) -> dict:
        with self._refresh_lock:
            with self._lock:
                token = self._refresh_token
            if not token:
                return self.status()
            try:
                self._accept(self._post("yenile", {"token": token, "cihaz": self.device, "surum": __version__}))
            except LicenseDenied as exc:
                if exc.code in DENIALS or exc.code == "OTURUM_GECERSIZ":
                    self._deny(exc)
                else:
                    with self._lock:
                        self._online = False
            except LicenseUnavailable:
                with self._lock:
                    self._online = False
            return self.status()

    def login(self, username: str, password: str) -> dict:
        if not isinstance(username, str) or not isinstance(password, str):
            raise LicenseError("Kullanıcı adı ve şifre gereklidir.")
        username = username.strip()
        if not username or not password:
            raise LicenseError("Kullanıcı adı ve şifre gereklidir.")
        if len(username) > 150 or len(password) > 256:
            raise LicenseError("Kullanıcı adı veya şifre çok uzun.")
        with self._refresh_lock:
            try:
                response = self._post("giris", {"kullanici": username, "sifre": password,
                                                "cihaz": self.device, "surum": __version__})
            except LicenseDenied as exc:
                if exc.code not in DENIALS:
                    raise LicenseError(str(exc)) from exc
                self._deny(exc, username)
                return self.status()
            self._accept(response)
            return self.status()

    def logout(self) -> dict:
        with self._lock:
            self._license = self._envelope = self._refresh_token = None
            self._denial, self._online = None, None
            self._save()
        return self.status()

    # ----- background renewal ------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="rpa-license", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        delay = 0.0
        while not self._stop.wait(delay):
            self.refresh()
            delay = RETRY_SECONDS if self._online is False else REFRESH_SECONDS

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._timeout + 5)
            self._thread = None
