"""Identify a local Studio before reusing its HTTP server."""

from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from . import __version__


class StartupError(RuntimeError):
    """A startup problem that can be shown without a Python traceback."""


def identity(data_dir: Path) -> dict[str, str]:
    workspace = hashlib.sha256(os.path.normcase(str(data_dir.resolve())).encode("utf-8")).hexdigest()
    return {"application": "rpa-orkestrai", "version": __version__, "workspace": workspace}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def existing_instance(url: str, data_dir: Path) -> bool:
    """False means no listener. A different service/workspace is never reused."""
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(f"{url}/api/instance", timeout=2) as response:
            metadata = json.loads(response.read(8193))
    except HTTPError as exc:
        raise StartupError(
            "Bu portta başka veya eski bir uygulama açık. Önce onu kapatın ya da --port ile başka port seçin."
        ) from exc
    except URLError as exc:
        reason = exc.reason
        if isinstance(reason, ConnectionRefusedError) or getattr(reason, "errno", None) == errno.ECONNREFUSED:
            return False
        raise StartupError("Yerel uygulama yanıt vermiyor. Açık uygulamayı ve port ayarını kontrol edin.") from exc
    except (TimeoutError, ValueError, OSError) as exc:
        raise StartupError("Bu porttaki uygulama doğrulanamadı. Başka bir port seçin veya açık uygulamayı kapatın.") from exc
    if metadata != identity(data_dir):
        raise StartupError("Bu port farklı bir uygulama sürümüne veya çalışma alanına ait; başka bir port seçin.")
    return True
