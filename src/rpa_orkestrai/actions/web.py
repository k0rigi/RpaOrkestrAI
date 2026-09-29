"""HTTP/JSON requests for APIs and webhooks (no browser needed)."""

from __future__ import annotations

import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, Request, build_opener

from ..errors import WorkflowError
from . import handler
from .common import choice, number, text

RESPONSE_LIMIT = 10 * 1024 * 1024


@handler("http.request")
def request(ctx, p):
    import certifi

    method = choice(p.get("method", "GET"), "Yöntem", {"GET", "POST", "PUT", "PATCH", "DELETE"})
    url = text(p.get("url"), "Adres", limit=4096).strip()
    if not url.lower().startswith(("https://", "http://")):
        raise WorkflowError("Adres http:// veya https:// ile başlamalıdır.")
    headers = p.get("headers") or {}
    if not isinstance(headers, dict) or not all(isinstance(k, str) for k in headers):
        raise WorkflowError("Başlıklar {\"Ad\": \"değer\"} biçiminde bir nesne olmalıdır.")
    headers = {key: str(value) for key, value in headers.items()}
    body, data = p.get("body"), None
    if body not in (None, "") and method != "GET":
        if isinstance(body, (dict, list)):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers.setdefault("Content-Type", "application/json")
        else:
            data = str(body).encode("utf-8")
            headers.setdefault("Content-Type", "text/plain; charset=utf-8")
    headers.setdefault("User-Agent", "RpaOrkestrAI")
    timeout = number(p.get("timeout", 30), "Zaman aşımı", 1, 300)
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))
    try:
        response = opener.open(Request(url, data=data, method=method, headers=headers), timeout=timeout)
        status = response.status
    except HTTPError as exc:
        response, status = exc, exc.code
    except (URLError, OSError, ValueError) as exc:
        raise WorkflowError(f"İstek gönderilemedi: {getattr(exc, 'reason', exc)}") from exc
    with response:
        raw = response.read(RESPONSE_LIMIT + 1)
        content_type = response.headers.get("Content-Type", "")
    if len(raw) > RESPONSE_LIMIT:
        raise WorkflowError("Yanıt 10 MB sınırını aşıyor.")
    decoded = raw.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(decoded) if "json" in content_type or decoded.lstrip()[:1] in "[{" else decoded
    except ValueError:
        parsed = decoded
    if status >= 400 and p.get("fail_on_error", True) is True:
        raise WorkflowError(f"Sunucu {status} hatası döndürdü.")
    return {"status": status, "ok": status < 400, "body": parsed}
