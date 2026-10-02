"""orkestrai.net license gate for the local Studio API.

The Studio opens only after orkestrai.net has confirmed the license during this run.
At every start, and every few minutes after that, it asks for a fresh license: an
Ed25519-signed answer that carries a random value the Studio chose for that request,
so an earlier answer never stands in for a new one. Nothing kept on disk opens the
Studio. The workspace stores only a device-bound session, never the password, and the
session advances with every check, so one account runs on one computer at a time.

While the Studio is running and orkestrai.net cannot be reached, work continues for a
limited time. That time is measured by a clock that does not follow the computer's
date, and it ends when the Studio is closed: a restart always needs a new confirmation.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import http.client
import json
import platform
import re
import secrets
import ssl
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime
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
PROTOCOL = 2
# The signed license names both values; these apply until the first one arrives and bound it.
REFRESH_SECONDS, REFRESH_RANGE = 600, (60, 3600)
TOLERANCE_SECONDS, TOLERANCE_RANGE = 3600, (300, 6 * 3600)
# An unanswered check is repeated after 5, 10, 20 and then every RETRY_SECONDS seconds.
RETRY_SECONDS = 30
# A computer waking from sleep gets this long to reconnect before running work is stopped.
STOP_GRACE = 60
RESPONSE_LIMIT = 64 * 1024
# Everything else under /api/ requires a valid license.
OPEN_PATHS = frozenset({
    "/api/health", "/api/instance", "/api/license", "/api/license/login",
    "/api/license/refresh", "/api/license/logout", "/api/license/quit",
})
DENIALS = {"SURE_DOLDU": "expired", "YETKI_YOK": "denied"}
STARTUP_MESSAGE = ("Lisans doğrulanamadı. RpaOrkestrAI'yi açmak için internet bağlantısı ve orkestrai.net "
                   "erişimi gerekir. Bağlantınızı kontrol edin; uygulama kendiliğinden yeniden dener.")
TOLERANCE_MESSAGE = ("Lisans uzun süredir doğrulanamadığı için Studio kilitlendi. İnternet bağlantınızı "
                     "kontrol edin; bağlantı gelince Studio kendiliğinden açılır.")
UNAVAILABLE_MESSAGE = "orkestrai.net lisans sunucusuna ulaşılamadı. İnternet bağlantınızı kontrol edin."
SESSION_MESSAGE = "Oturumun süresi doldu. Yeniden giriş yapın."


class LicenseError(RuntimeError):
    """A public message for the login form."""


class LicenseUnavailable(LicenseError):
    """The server could not be reached or answered unexpectedly; nothing was confirmed."""


class LicenseDenied(LicenseError):
    def __init__(self, code: str, message: str, ends_on: str | None = None, cause: str | None = None):
        super().__init__(message)
        self.code, self.ends_on, self.cause = code, ends_on, cause


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
    # How often to ask again, and how long a running Studio may go without an answer (seconds).
    interval: int = REFRESH_SECONDS
    tolerance: int = TOLERANCE_SECONDS

    def public(self) -> dict:
        return {"user": self.user, "full_name": self.full_name, "company": self.company,
                "ends_on": self.ends_on.isoformat() if self.ends_on else None}


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


def _bounded(value: Any, default: int, limits: tuple[int, int]) -> int:
    return max(limits[0], min(limits[1], value)) if type(value) is int else default


def verify_license(envelope: Any, key: Ed25519PublicKey, device: str, nonce: str | None = None) -> License:
    """Check the signature, the product, the device and, when given, that it answers this request."""
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
            interval=_bounded(claims.get("aralik"), REFRESH_SECONDS, REFRESH_RANGE),
            tolerance=_bounded(claims.get("tolerans"), TOLERANCE_SECONDS, TOLERANCE_RANGE),
        )
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
        raise LicenseError("Lisans içeriği geçersiz.") from exc
    if result.device != device:
        raise LicenseError("Lisans bu bilgisayara ait değil.")
    if nonce is not None and claims.get("nonce") != nonce:
        raise LicenseError("Lisans yanıtı bu isteğe ait değil.")
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
        opener: Any = None, monotonic: Callable[[], float] = time.monotonic,
        machine_id: Callable[[], str] = machine_identifier, timeout: float = 15,
    ):
        self._path = Path(data_dir) / "license.json"
        self._api = api_url.rstrip("/")
        self._key = Ed25519PublicKey.from_public_bytes(_base64(public_key, 32))
        self._opener = opener or build_opener(
            HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())), _NoRedirect())
        self._monotonic, self._timeout = monotonic, timeout
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # Called when the Studio locks: orkestrai.net refused the license ("expired", "denied"),
        # closed this session ("session"), or has not confirmed it for too long ("unverified").
        self.on_locked: Callable[[str], None] | None = None
        stored = self._load()
        install = stored.get("install")
        if not isinstance(install, str) or not re.fullmatch(r"[0-9a-f]{32}", install):
            install = uuid.uuid4().hex
        self._install = install
        self.device = hashlib.sha256(f"{PRODUCT}:{machine_id()}:{install}".encode()).hexdigest()[:32]
        # Names this running Studio, so a request repeated after a lost answer is not taken for a copy.
        self._instance = secrets.token_hex(16)
        token = stored.get("refresh")
        self._refresh_token = token if isinstance(token, str) and len(token) <= 4096 else None
        user = stored.get("user")
        self._user = user if isinstance(user, str) and len(user) <= 200 else None
        # Only what orkestrai.net confirmed in this run counts; the file never holds a usable license.
        self._license: License | None = None
        self._verified: float | None = None
        self._attempted = False
        self._failures = 0
        self._locked_since: float | None = None
        self._online: bool | None = None
        self._denial: dict | None = None
        self._notice = ""
        self._interval, self._tolerance = REFRESH_SECONDS, TOLERANCE_SECONDS
        if install != stored.get("install") or set(stored) - {"install", "refresh", "user"}:
            self._save()  # also drops what earlier versions kept here

    # ----- persistence -------------------------------------------------------------
    def _load(self) -> dict:
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self) -> None:
        try:
            atomic_json(self._path, {"install": self._install, "refresh": self._refresh_token, "user": self._user})
        except OSError:
            pass  # The session then asks for the password again at the next start.

    # ----- evaluation --------------------------------------------------------------
    def _evaluate(self) -> tuple[str, str]:
        if self._denial:
            return self._denial["state"], str(self._denial.get("message") or "")
        if self._refresh_token is None:
            return "login_required", self._notice
        if self._verified is None or self._license is None:
            return ("verification_required", STARTUP_MESSAGE) if self._attempted else ("verifying", "")
        if self._monotonic() - self._verified > self._tolerance:
            return "verification_required", TOLERANCE_MESSAGE
        return "valid", ""

    def allowed(self) -> bool:
        with self._lock:
            return self._evaluate()[0] == "valid"

    def status(self) -> dict:
        with self._lock:
            state, message = self._evaluate()
            public = self._license.public() if self._license else None
            known = (self._denial or {}).get("user") or self._user
            if public is None and known:
                public = {"user": known, "full_name": "", "company": "",
                          "ends_on": (self._denial or {}).get("ends_on")}
            # "detail" tells the two refusals apart: no license, or a version no longer served.
            return {"state": state, "message": message, "online": self._online, "license": public,
                    "remembered": self._refresh_token is not None,
                    "detail": (self._denial or {}).get("detail")}

    # ----- server ------------------------------------------------------------------
    def _post(self, endpoint: str, body: dict, timeout: float | None = None) -> dict:
        request = Request(f"{self._api}/{endpoint}", data=json.dumps(body).encode("utf-8"), method="POST",
                          headers={"Content-Type": "application/json", "Accept": "application/json",
                                   "User-Agent": f"RpaOrkestrAI/{__version__}"})
        try:
            with self._opener.open(request, timeout=timeout or self._timeout) as response:
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
        cause = data.get("neden") if isinstance(data.get("neden"), str) else None
        raise LicenseDenied(code, message[:300], ends_on, cause)

    def _request(self, endpoint: str, body: dict) -> dict:
        """Ask for a license that answers this very request; anything else is not a confirmation."""
        nonce = secrets.token_hex(16)
        response = self._post(endpoint, {**body, "cihaz": self.device, "surum": __version__,
                                         "protokol": PROTOCOL, "nonce": nonce, "ornek": self._instance})
        token = response.get("yenileme")
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_\-.]{20,4096}", token):
            raise LicenseUnavailable("Lisans sunucusunun yanıtı geçersiz.")
        try:
            accepted = verify_license(response.get("lisans"), self._key, self.device, nonce)
        except LicenseError as exc:
            raise LicenseUnavailable("Lisans sunucusunun yanıtı doğrulanamadı. Uygulamayı güncelleyin.") from exc
        with self._lock:
            self._license, self._refresh_token, self._user = accepted, token, accepted.user
            self._interval, self._tolerance = accepted.interval, accepted.tolerance
            self._verified, self._attempted, self._online = self._monotonic(), True, True
            self._denial, self._notice, self._failures = None, "", 0
            self._save()
        return response

    def _unconfirmed(self) -> None:
        with self._lock:
            self._attempted, self._online = True, False
            self._failures += 1

    def _deny(self, exc: LicenseDenied, user: str | None = None) -> None:
        with self._lock:
            self._license, self._verified = None, None
            self._attempted, self._online, self._failures = True, True, 0
            if exc.code == "OTURUM_GECERSIZ":
                # Closed on orkestrai.net: another computer signed in, the password changed or it expired.
                self._refresh_token, self._denial = None, None
                self._notice = str(exc) or SESSION_MESSAGE
                reason = "session"
            else:
                ends_on = None
                try:
                    ends_on = date.fromisoformat(exc.ends_on) if exc.ends_on else None
                except ValueError:
                    pass
                reason = DENIALS[exc.code]
                message = expired_message(ends_on) if reason == "expired" else str(exc)
                # A renewed license is picked up by the kept session on the next check; a refused
                # login for another account must not fall back to the previous one.
                if user is not None:
                    self._refresh_token = None
                self._denial = {"state": reason, "message": message, "user": user or self._user,
                                "ends_on": ends_on.isoformat() if ends_on else None,
                                "detail": "outdated" if exc.cause == "ESKI_SURUM" else None}
            self._save()
            callback = self.on_locked
        if callback is not None:
            callback(reason)

    def refresh(self) -> dict:
        with self._refresh_lock:
            with self._lock:
                token = self._refresh_token
            if not token:
                return self.status()
            try:
                self._request("yenile", {"token": token})
            except LicenseDenied as exc:
                if exc.code in DENIALS or exc.code == "OTURUM_GECERSIZ":
                    self._deny(exc)
                else:
                    self._unconfirmed()
            except LicenseUnavailable:
                self._unconfirmed()
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
                self._request("giris", {"kullanici": username, "sifre": password})
            except LicenseDenied as exc:
                if exc.code not in DENIALS:
                    raise LicenseError(str(exc)) from exc
                self._deny(exc, username)
            return self.status()

    def logout(self) -> dict:
        with self._refresh_lock:
            with self._lock:
                token = self._refresh_token
            if token:
                try:  # Frees this computer's session on orkestrai.net; signing out works without it.
                    self._post("cikis", {"token": token, "cihaz": self.device}, timeout=5)
                except LicenseError:
                    pass
            with self._lock:
                self._license, self._verified, self._refresh_token, self._user = None, None, None, None
                self._denial, self._notice, self._online, self._failures = None, "", None, 0
                self._save()
        return self.status()

    # ----- background renewal ------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="rpa-license", daemon=True)
        self._thread.start()

    def _tick(self) -> float:
        """One background check; returns the seconds until the next one."""
        self.refresh()
        with self._lock:
            now = self._monotonic()
            if self._evaluate()[0] != "verification_required":
                self._locked_since = None
            elif self._locked_since is None:
                self._locked_since = now
            overdue = self._locked_since is not None and now - self._locked_since >= STOP_GRACE
            delay = self._interval
            if self._online is False:
                delay = min(RETRY_SECONDS, 5 * 2 ** min(self._failures - 1, 3))
            callback = self.on_locked
        # Refusals are reported as they arrive. This covers a running Studio that has gone without
        # an answer for longer than the license allows: whatever is still running stops too.
        if overdue and callback is not None:
            callback("unverified")
        return delay

    def _run(self) -> None:
        delay = 0.0
        while not self._stop.wait(delay):
            delay = self._tick()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._timeout + 5)
            self._thread = None
