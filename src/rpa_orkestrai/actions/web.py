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
    profile = ctx.connections.resolve(p["connection"], "api") if p.get("connection") else None
    url = text(p.get("url"), "Adres", required=profile is None, limit=4096).strip()
    if profile is not None and url.lower() in {"https://", "http://"}:
        url = ""  # The untouched default means the connection's base address.
    if profile is None and not url.lower().startswith(("https://", "http://")):
        raise WorkflowError("Adres http:// veya https:// ile başlamalıdır. API bağlantısı seçerseniz yalnız yolu "
                            "yazabilirsiniz (ör. /v1/siparisler).")
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
    if profile is not None:
        from ..integrations import api

        # Credentials are added last and only for the connection's own server; redirects must stay there.
        url, headers = api.authorize(profile, url, headers, timeout)
        opener = api.opener()
    else:
        opener = build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))
    try:
        response = opener.open(Request(url, data=data, method=method, headers=headers), timeout=timeout)
        status = response.status
    except WorkflowError:
        raise
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


# ----- Web sayfası adımları (the computer's own Edge or Chrome) -----------------------------
def web_target(p, *, required: bool = True):
    from ..integrations.web_session import TARGETS, Target

    if not required and not str(p.get("target") or "").strip():
        return None
    return Target(by=choice(p.get("by", "text"), "Hedefi bulma yöntemi", TARGETS),
                  value=text(p.get("target"), "Hedef", limit=4096),
                  exact=p.get("exact") is True,
                  frame=text(p.get("frame"), "Çerçeve", required=False, limit=1000).strip(),
                  timeout_ms=int(number(p.get("timeout", 15), "En fazla bekle", 0.5, 300) * 1000))


def session(ctx):
    """The run's web session; tab changes it made on its own are written to the log."""
    web = ctx.web()
    return web


def report(ctx, web):
    while web.notices:
        ctx.log(web.notices.pop(0))


def act(ctx, work):
    web = session(ctx)
    try:
        return work(web)
    finally:
        report(ctx, web)


@handler("web.open")
def web_open(ctx, p):
    url = text(p.get("url"), "Adres", limit=4096).strip()
    browser = choice(p.get("browser", "auto"), "Tarayıcı", {"auto", "msedge", "chrome"})
    web = session(ctx)
    final = act(ctx, lambda web: web.open(url, browser=browser, headless=p.get("headless") is True))
    ctx.log(f"Sayfa açıldı ({web.channel}): {final}")
    return final


@handler("web.click")
def web_click(ctx, p):
    target = web_target(p)
    kind = choice(p.get("click", "single"), "Tıklama türü", {"single", "double", "right", "middle", "hover"})
    act(ctx, lambda web: web.click(target, kind))


@handler("web.fill")
def web_fill(ctx, p):
    target = web_target(p)
    value = text(p.get("text"), "Yazılacak değer", required=False, limit=100_000)
    act(ctx, lambda web: web.fill(target, value))


@handler("web.read")
def web_read(ctx, p):
    target = web_target(p)
    return act(ctx, lambda web: web.read(target))


@handler("web.select")
def web_select(ctx, p):
    target = web_target(p)
    option = text(p.get("option"), "Seçilecek seçenek", limit=1000)
    return act(ctx, lambda web: web.select(target, option))


@handler("web.wait")
def web_wait(ctx, p):
    condition = choice(p.get("condition", "visible"), "Ne beklensin", {"visible", "hidden", "url"})
    target = None if condition == "url" else web_target(p)
    wanted = text(p.get("url_text"), "Adreste geçecek metin", limit=2000) if condition == "url" else ""
    timeout = int(number(p.get("wait", 30), "En fazla bekle", 0.5, 600) * 1000)
    met = act(ctx, lambda web: web.wait(condition, target=target, text=wanted, timeout_ms=timeout))
    if not met and p.get("on_missing", "stop") == "stop":
        raise WorkflowError({"visible": "Beklenen öğe süre içinde görünmedi.",
                             "hidden": "Öğe süre içinde kaybolmadı.",
                             "url": "Sayfa adresi süre içinde beklenen metni içermedi."}[condition])
    return met


@handler("web.press")
def web_press(ctx, p):
    from ..integrations.web_session import KEYS, MODIFIERS

    key = choice(p.get("key", "Enter"), "Tuş", KEYS)
    modifier = choice(p.get("modifier", ""), "Birlikte basılacak tuş", MODIFIERS)
    target = web_target(p, required=False)
    act(ctx, lambda web: web.press(key, modifier, target))


@handler("web.navigate")
def web_navigate(ctx, p):
    action = choice(p.get("action", "back"), "Gezinme", {"back", "forward", "reload"})
    return act(ctx, lambda web: web.navigate(action))


@handler("web.tab")
def web_tab(ctx, p):
    action = choice(p.get("action", "last"), "Sekme", {"last", "first", "title", "url", "close"})
    wanted = text(p.get("match"), "Aranacak metin", required=action in {"title", "url"}, limit=1000)
    url = act(ctx, lambda web: web.tab(action, wanted))
    ctx.log(f"Etkin sekme: {url}")
    return url


@handler("web.read_table")
def web_read_table(ctx, p):
    target = web_target(p)
    rows = act(ctx, lambda web: web.read_table(target, p.get("header", True) is not False))
    ctx.log(f"Web tablosundan {len(rows)} satır okundu.")
    return rows


@handler("web.download")
def web_download(ctx, p):
    from ..file_types import describe, parse_extensions, problem
    from .common import path

    target = web_target(p)
    folder = path(p.get("folder"), "Kaydedilecek klasör")
    allowed = parse_extensions(p.get("extensions"))
    saved = act(ctx, lambda web: web.download(target, folder, p.get("overwrite") is True))
    ctx.log(f"Dosya indirildi: {saved}")
    if allowed:
        # Wrong kind (e.g. the site's error page saved as .xlsx): stop before a later step works on it.
        reason = problem(describe(saved), allowed, True)
        if reason:
            raise WorkflowError(f"{reason} Dosya silinmedi: {saved}. Akış durduruldu.")
    return str(saved)


@handler("web.upload")
def web_upload(ctx, p):
    from .common import path

    target = web_target(p)
    raw = p.get("files")
    items = raw if isinstance(raw, list) else str(raw or "").splitlines()
    files = [path(item, "Yüklenecek dosya") for item in items if str(item).strip()]
    if not files:
        raise WorkflowError("Yüklenecek dosyanın yolunu yazın (her satıra bir dosya).")
    missing = [str(item) for item in files if not item.is_file()]
    if missing:
        raise WorkflowError(f"Yüklenecek dosya bulunamadı: {missing[0]}. Hiçbir dosya yüklenmedi.")
    act(ctx, lambda web: web.upload(target, files))
    return [str(item) for item in files]


@handler("web.screenshot")
def web_screenshot(ctx, p):
    name = text(p.get("filename") or "web-sayfasi.png", "Dosya adı", limit=120).strip()
    if not name.lower().endswith(".png"):
        name += ".png"
    image = act(ctx, lambda web: web.screenshot(p.get("full_page", True) is not False))
    return str(ctx.save_artifact(name, image))


@handler("web.script")
def web_script(ctx, p):
    code = text(p.get("code"), "JavaScript", limit=200_000)
    return act(ctx, lambda web: web.script(code, p.get("input")))
