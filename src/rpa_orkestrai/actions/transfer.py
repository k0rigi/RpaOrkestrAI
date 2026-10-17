"""FTP aktarımı and Mesaj gönder (Teams, Slack, Google Chat, Discord webhooks)."""

from __future__ import annotations

import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, Request, build_opener

from ..errors import WorkflowError
from . import handler
from .common import choice, number, path, text


@handler("ftp.transfer")
def ftp_transfer(ctx, p):
    from ..integrations import ftp

    profile = ctx.connections.resolve(p.get("connection"), "ftp")
    operation = choice(p.get("operation", "download"), "İşlem", {"list", "download", "upload"})
    remote = ftp.remote(text(p.get("remote_path"), "Uzak yol", required=operation != "list", limit=1000))
    overwrite = p.get("overwrite") is True
    try:
        client = ftp.connect(profile["config"], number(p.get("timeout", 60), "Zaman aşımı", 5, 600))
        try:
            if operation == "list":
                items = ftp.listing(client, remote)
                ctx.log(f"FTP: {remote} klasöründe {len(items)} öğe listelendi.")
                return {"operation": "list", "path": remote, "items": items}
            local = path(p.get("local_path"), "Yerel dosya")
            if operation == "download":
                size = ftp.download(client, remote, local, overwrite=overwrite)
                ctx.log(f"FTP: {remote} indirildi → {local}")
            else:
                size = ftp.upload(client, local, remote, overwrite=overwrite)
                ctx.log(f"FTP: {local} yüklendi → {remote}")
            return {"operation": operation, "path": remote, "local_path": str(local), "size": size}
        finally:
            try:
                client.quit()
            except Exception:
                client.close()
    except WorkflowError:
        raise
    except Exception as exc:
        raise WorkflowError(ftp.describe(exc)) from exc


def message_payload(service: str, title: str, body: str) -> dict:
    if service == "teams":
        blocks = ([{"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "wrap": True}] if title else [])
        blocks.append({"type": "TextBlock", "text": body, "wrap": True})
        return {"type": "message", "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive", "contentUrl": None,
            "content": {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard",
                        "version": "1.4", "body": blocks}}]}
    combined = f"{title}\n{body}" if title else body
    if service == "slack":
        return {"text": f"*{title}*\n{body}" if title else body}
    if service == "google_chat":
        return {"text": combined}
    if service == "discord":
        return {"content": combined[:2000]}
    return {"title": title, "text": body}


def _opener():
    import certifi

    return build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))


def _post_json(url: str, payload: dict, headers: dict, timeout: float) -> tuple[int, dict]:
    """POST JSON; the status and the decoded answer, also for HTTP errors. The URL (it may hold a token) is never
    put into an error message."""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, method="POST", headers={"Content-Type": "application/json; charset=utf-8",
                                                              "User-Agent": "RpaOrkestrAI", **headers})
    try:
        with _opener().open(request, timeout=timeout) as response:
            raw, status = response.read(1024 * 1024), response.status
    except HTTPError as exc:
        raw, status = exc.read(64 * 1024), exc.code
        exc.close()
    except (URLError, OSError, ValueError) as exc:
        reason = getattr(exc, "reason", None)
        raise WorkflowError("Mesaj servisine ulaşılamadı" + (f": {reason}" if isinstance(reason, str) else ".")) from None
    try:
        answer = json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError:
        answer = {}
    return status, answer if isinstance(answer, dict) else {}


TELEGRAM_HINTS = {
    401: "Bot anahtarı geçersiz; @BotFather'dan aldığınız anahtarı kontrol edin.",
    403: "Bot bu sohbete yazamıyor: kişi botu engellemiş ya da bot gruptan çıkarılmış.",
    429: "Telegram istek sınırı aşıldı; biraz sonra yeniden deneyin.",
}


def send_telegram(config: dict, title: str, body: str, to: str, timeout: float) -> dict:
    chat = (to or config.get("chat_id") or "").strip()
    if not chat:
        raise WorkflowError("Telegram sohbet kimliği yok; bağlantıya varsayılan sohbeti veya adıma alıcıyı yazın.")
    text = f"{title}\n\n{body}" if title else body
    status, answer = _post_json(f"https://api.telegram.org/bot{config['token']}/sendMessage",
                                {"chat_id": chat, "text": text[:4096], "disable_web_page_preview": True}, {}, timeout)
    if status == 200 and answer.get("ok") is True:
        return {"service": "telegram", "chat": chat, "id": (answer.get("result") or {}).get("message_id")}
    description = str(answer.get("description") or "").casefold()
    hint = TELEGRAM_HINTS.get(status) or ("Sohbet bulunamadı: kişi bota önce /start yazmalı ya da bot gruba eklenmeli; "
                                          "sohbet kimliğini kontrol edin." if "chat not found" in description
                                          else "Telegram isteği reddetti.")
    raise WorkflowError(f"Telegram mesajı gönderilemedi ({status}). {hint}")


def telegram_chats(token: str, timeout: float = 20) -> list[dict]:
    """Chats that recently wrote to the bot, to fill in the chat id; nothing is sent."""
    status, answer = _post_json(f"https://api.telegram.org/bot{token}/getUpdates", {"limit": 100}, {}, timeout)
    if status != 200 or answer.get("ok") is not True:
        raise WorkflowError(f"Telegram sohbetleri okunamadı ({status}). {TELEGRAM_HINTS.get(status, 'Bot anahtarını kontrol edin.')}")
    chats = {}
    for update in answer.get("result") or []:
        for key in ("message", "channel_post", "my_chat_member", "edited_message"):
            chat = (update.get(key) or {}).get("chat") if isinstance(update, dict) else None
            if isinstance(chat, dict) and "id" in chat:
                name = chat.get("title") or " ".join(part for part in (chat.get("first_name"), chat.get("last_name")) if part)
                chats[str(chat["id"])] = {"id": str(chat["id"]), "name": str(name or chat.get("username") or "")[:120],
                                          "type": str(chat.get("type") or "")}
    return list(chats.values())[-20:]


WHATSAPP_HINTS = {
    190: "Erişim anahtarı geçersiz veya süresi dolmuş; Meta'da kalıcı (sistem kullanıcısı) anahtar oluşturun.",
    131047: "Bu kişi son 24 saatte size yazmadığı için serbest metin gönderilemez; onaylı bir şablonla gönderin.",
    131026: "Mesaj teslim edilemedi: numara WhatsApp kullanmıyor olabilir ya da şartları kabul etmemiş.",
    131030: "Alıcı, test numarasının izinli alıcılar listesinde değil (Meta'da numarayı ekleyin).",
    132000: "Şablondaki değişken sayısı ile gönderilen değer sayısı uyuşmuyor.",
    132001: "Şablon bulunamadı: adı ve dili Meta'da onaylandığı gibi yazın.",
    131056: "Aynı kişiye çok sık mesaj gönderildi; biraz sonra deneyin.",
    130429: "WhatsApp gönderim hızı sınırı aşıldı; biraz sonra deneyin.",
    100: "İstek parametreleri geçersiz: telefon numarası kimliğini ve alıcı numarasını kontrol edin.",
}


def send_whatsapp(config: dict, title: str, body: str, to: str, values: list[str], timeout: float) -> dict:
    from ..connections import phone_number

    try:
        recipient = phone_number(to or config.get("to"))
    except ValueError as exc:
        raise WorkflowError(str(exc)) from None
    if not recipient:
        raise WorkflowError("WhatsApp alıcısı yok; adıma alıcı numarasını veya bağlantıya varsayılan alıcıyı yazın.")
    if config.get("mode") == "template":
        template = {"name": config["template_name"], "language": {"code": config.get("template_language") or "tr"}}
        if values:
            template["components"] = [{"type": "body", "parameters": [{"type": "text", "text": value[:1024]}
                                                                      for value in values]}]
        payload = {"messaging_product": "whatsapp", "to": recipient, "type": "template", "template": template}
    else:
        text = f"*{title}*\n{body}" if title else body
        payload = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": recipient, "type": "text",
                   "text": {"preview_url": False, "body": text[:4096]}}
    url = (f"https://graph.facebook.com/{config.get('api_version') or 'v26.0'}/"
           f"{config['phone_number_id']}/messages")
    status, answer = _post_json(url, payload, {"Authorization": f"Bearer {config['token']}"}, timeout)
    if status == 200 and answer.get("messages"):
        return {"service": "whatsapp", "to": recipient, "id": str((answer["messages"][0] or {}).get("id", ""))}
    error = answer.get("error") if isinstance(answer.get("error"), dict) else {}
    code = error.get("code")
    hint = WHATSAPP_HINTS.get(code if type(code) is int else -1, "WhatsApp isteği reddetti; bağlantı ayarlarını kontrol edin.")
    raise WorkflowError(f"WhatsApp mesajı gönderilemedi ({status}{f', kod {code}' if type(code) is int else ''}). {hint}")


def post_message(config: dict, title: str, body: str, timeout: float = 30, *, to: str = "",
                 values: list[str] | None = None) -> dict:
    if config.get("service") == "telegram":
        return send_telegram(config, title, body, to, timeout)
    if config.get("service") == "whatsapp":
        return send_whatsapp(config, title, body, to, values or [], timeout)
    data = json.dumps(message_payload(config["service"], title, body), ensure_ascii=False).encode("utf-8")
    request = Request(config["url"], data=data, method="POST",
                      headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "RpaOrkestrAI"})
    try:
        with _opener().open(request, timeout=timeout) as response:
            return {"service": config["service"], "status": response.status}
    except HTTPError as exc:
        raise WorkflowError(f"Mesaj gönderilemedi: servis {exc.code} döndürdü. Webhook adresini kontrol edin.") from None
    except (URLError, OSError, ValueError) as exc:
        raise WorkflowError(f"Mesaj servisine ulaşılamadı: {getattr(exc, 'reason', exc)}") from None


@handler("notify.send")
def notify_send(ctx, p):
    profile = ctx.connections.resolve(p.get("connection"), "webhook")
    body = text(p.get("text"), "Mesaj", limit=4000)
    title = text(p.get("title"), "Başlık", required=False, limit=200)
    to = text(p.get("to"), "Alıcı", required=False, limit=60).strip()
    values = [line.strip() for line in str(p.get("template_values") or "").splitlines() if line.strip()][:20]
    if to and profile["config"].get("service") not in {"telegram", "whatsapp"}:
        raise WorkflowError("Alıcı yalnız WhatsApp ve Telegram bağlantılarında yazılır; kanal adresi bağlantıdadır.")
    # Sent once: an unclear result is reported, never retried (a retry could post twice).
    sent = post_message(profile["config"], title, body, number(p.get("timeout", 30), "Zaman aşımı", 5, 120),
                        to=to, values=values)
    ctx.log(f"Mesaj gönderildi: {profile['name']}" + (f" → {sent.get('to') or sent.get('chat')}"
                                                       if sent.get("to") or sent.get("chat") else ""))
    return {"sent": True, **{key: value for key, value in sent.items() if key != "service"}}
