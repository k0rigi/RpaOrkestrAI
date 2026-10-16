"""Web servisi (API) bağlantısı: ana adres, kimlik doğrulama ve varsayılan başlıklar.

Credentials are added only to requests for the connection's own server (same scheme, host and port):
a step, a flow variable or an agent can never send them elsewhere. OAuth 2.0 client-credential tokens
are kept in memory until shortly before they expire; they are never written to disk or to the run log.
"""

from __future__ import annotations

import base64
import hashlib
import json
import ssl
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

from ..errors import WorkflowError

_tokens: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()


def origin(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    port = parts.port or {"https": 443, "http": 80}.get(parts.scheme)
    return parts.scheme.lower(), f"{(parts.hostname or '').lower()}:{port}"


class SameServer(HTTPRedirectHandler):
    """Credentials never follow a redirect to another server, or from https to http."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if origin(newurl) != origin(req.full_url):
            raise WorkflowError("Sunucu isteği başka bir sunucuya yönlendirdi. Kimlik bilgileri başka bir sunucuya "
                                "gönderilmediği için istek durduruldu; bağlantının ana adresini kontrol edin.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def opener():
    import certifi

    return build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())), SameServer())


def resolve_url(config: dict, url: str) -> str:
    """A path is appended to the base address; a full address must point to the same server."""
    base = config.get("base_url", "").rstrip("/")
    if not base:
        raise WorkflowError("API bağlantısında ana adres yok. Ayarlar → Bağlantılar'dan ekleyin.")
    url = (url or "").strip()
    if "://" in url:
        if origin(url) != origin(base):
            raise WorkflowError("Adres, seçilen API bağlantısının sunucusunda değil. Kimlik bilgileri başka bir "
                                "sunucuya gönderilmez; bağlantıya göre bir yol yazın (ör. /v1/siparisler).")
        return url
    if not url:
        return base
    return f"{base}{url}" if url.startswith(("/", "?")) else f"{base}/{url}"


def _oauth_token(profile_id: str, config: dict, timeout: float) -> str:
    fingerprint = hashlib.sha256(json.dumps([profile_id, config.get("token_url"), config.get("client_id"),
                                             config.get("client_secret"), config.get("scope")]).encode()).hexdigest()
    with _lock:
        cached = _tokens.get(fingerprint)
        if cached and cached[1] > time.monotonic():
            return cached[0]
    form = {"grant_type": "client_credentials", "client_id": config.get("client_id", ""),
            "client_secret": config.get("client_secret", "")}
    if config.get("scope"):
        form["scope"] = config["scope"]
    request = Request(config["token_url"], data=urlencode(form).encode(), method="POST",
                      headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json",
                               "User-Agent": "RpaOrkestrAI"})
    try:
        with opener().open(request, timeout=timeout) as response:
            data = json.loads(response.read(1024 * 1024).decode("utf-8"))
    except WorkflowError:
        raise
    except HTTPError as exc:
        raise WorkflowError(f"OAuth token alınamadı: sunucu {exc.code} döndürdü. İstemci kimliğini, sırrını ve "
                            "kapsamı kontrol edin.") from None
    except (URLError, OSError, ValueError) as exc:
        raise WorkflowError(f"OAuth token adresine ulaşılamadı: {getattr(exc, 'reason', exc)}") from None
    token = data.get("access_token") if isinstance(data, dict) else None
    if not isinstance(token, str) or not token:
        raise WorkflowError("OAuth yanıtında erişim belirteci (access_token) yok.")
    lifetime = data.get("expires_in", 3600)
    lifetime = lifetime if isinstance(lifetime, (int, float)) and lifetime > 0 else 3600
    with _lock:
        _tokens[fingerprint] = (token, time.monotonic() + max(30, lifetime - 60))
    return token


def authorize(profile: dict, url: str, headers: dict[str, str], timeout: float) -> tuple[str, dict[str, str]]:
    """The final address and headers: connection defaults, the step's own headers, then credentials."""
    config = profile["config"]
    final = resolve_url(config, url)
    merged = {**(config.get("headers") or {}), **headers}
    auth = config.get("auth", "none")
    if auth == "bearer":
        merged["Authorization"] = f"Bearer {config.get('token', '')}"
    elif auth == "basic":
        pair = f"{config.get('user', '')}:{config.get('password', '')}".encode()
        merged["Authorization"] = "Basic " + base64.b64encode(pair).decode()
    elif auth == "api_key":
        if config.get("key_in") == "query":
            final += ("&" if "?" in final else "?") + urlencode({config.get("key_name", "api_key"): config.get("api_key", "")})
        else:
            merged[config.get("key_name") or "X-API-Key"] = config.get("api_key", "")
    elif auth == "oauth2":
        merged["Authorization"] = f"Bearer {_oauth_token(profile.get('id', ''), config, timeout)}"
    return final, merged


def test(profile: dict, timeout: float = 20) -> str:
    """GET the base address (or the test path) with credentials; the answer says what happened."""
    url, headers = authorize(profile, profile["config"].get("test_path") or "", {"Accept": "application/json",
                                                                                     "User-Agent": "RpaOrkestrAI"},
                             timeout)
    try:
        with opener().open(Request(url, method="GET", headers=headers), timeout=timeout) as response:
            status = response.status
    except WorkflowError:
        raise
    except HTTPError as exc:
        status = exc.code
    except (URLError, OSError, ValueError) as exc:
        raise WorkflowError(f"Sunucuya ulaşılamadı: {getattr(exc, 'reason', exc)}") from None
    if status in {401, 403}:
        raise WorkflowError(f"Sunucu {status} döndürdü: kimlik bilgileri kabul edilmedi.")
    if status >= 500:
        raise WorkflowError(f"Sunucu {status} hatası döndürdü.")
    return f"Sunucuya ulaşıldı (HTTP {status})." + (" Adres bulunamadı; Test adresi alanına var olan bir yol yazın."
                                                    if status == 404 else "")
