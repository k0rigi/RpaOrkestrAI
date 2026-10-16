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


def post_message(config: dict, title: str, body: str, timeout: float = 30) -> int:
    import certifi

    data = json.dumps(message_payload(config["service"], title, body), ensure_ascii=False).encode("utf-8")
    request = Request(config["url"], data=data, method="POST",
                      headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "RpaOrkestrAI"})
    opener = build_opener(HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status
    except HTTPError as exc:
        raise WorkflowError(f"Mesaj gönderilemedi: servis {exc.code} döndürdü. Webhook adresini kontrol edin.") from None
    except (URLError, OSError, ValueError) as exc:
        raise WorkflowError(f"Mesaj servisine ulaşılamadı: {getattr(exc, 'reason', exc)}") from None


@handler("notify.send")
def notify_send(ctx, p):
    profile = ctx.connections.resolve(p.get("connection"), "webhook")
    body = text(p.get("text"), "Mesaj", limit=4000)
    title = text(p.get("title"), "Başlık", required=False, limit=200)
    # Sent once: an unclear result is reported, never retried (a retry could post twice).
    status = post_message(profile["config"], title, body, number(p.get("timeout", 30), "Zaman aşımı", 5, 120))
    ctx.log(f"Mesaj gönderildi: {profile['name']}")
    return {"sent": True, "status": status}
