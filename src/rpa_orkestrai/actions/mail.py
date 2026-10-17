"""E-posta gönder: plain-text mail with attachments through a named SMTP connection."""

from __future__ import annotations

import mimetypes
import re
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path
from typing import Any

from ..connections import EMAIL
from ..errors import WorkflowError
from . import handler
from .common import number, path, text

MAX_RECIPIENTS = 100
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


def addresses(value: Any, label: str, *, required: bool) -> list[str]:
    items = value if isinstance(value, list) else re.split(r"[,;\n]", str(value or ""))
    result = [str(item).strip() for item in items if str(item).strip()]
    if required and not result:
        raise WorkflowError(f"{label} alanına en az bir e-posta adresi yazın.")
    for item in result:
        if not EMAIL.fullmatch(item):
            raise WorkflowError(f"{label}: “{item}” geçerli bir e-posta adresi değil.")
    return result


def attachments(value: Any) -> list[Path]:
    items = value if isinstance(value, list) else str(value or "").splitlines()
    files = [path(item, "Ek dosya") for item in items if str(item).strip()]
    total = 0
    for item in files:
        if not item.is_file():
            raise WorkflowError(f"Ek dosya bulunamadı: {item}. E-posta gönderilmedi.")
        total += item.stat().st_size
    if total > MAX_ATTACHMENT_BYTES:
        raise WorkflowError("Eklerin toplamı 25 MB'ı aşıyor; çoğu e-posta sunucusu kabul etmez. Gönderilmedi.")
    return files


MESSAGE_ID = re.compile(r"<[^<>\s@]+@[^<>\s]+>")


def reply_headers(value: Any) -> tuple[str, str]:
    """In-Reply-To and References for a reply. The last id is the answered message; earlier ids (e.g.
    ${eposta.references}) keep the whole conversation together. A bare id gets its angle brackets."""
    text_value = str(value or "").strip()
    if not text_value:
        return "", ""
    if any(char in text_value for char in "\r\n") or len(text_value) > 4000:
        raise WorkflowError("Yanıtlanan e-postanın kimliği tek satır olmalıdır.")
    ids = MESSAGE_ID.findall(text_value)
    if not ids and "<" not in text_value and MESSAGE_ID.fullmatch(f"<{text_value}>"):
        ids = [f"<{text_value}>"]
    if not ids:
        raise WorkflowError("Yanıtlanan e-posta kimliği <...@...> biçiminde olmalıdır (ör. ${eposta.message_id}).")
    chain = list(dict.fromkeys(ids))[-20:]
    return ids[-1], " ".join(chain)


def build(config: dict, p: dict) -> tuple[EmailMessage, list[str]]:
    to = addresses(p.get("to"), "Kime", required=True)
    cc = addresses(p.get("cc"), "Bilgi (CC)", required=False)
    bcc = addresses(p.get("bcc"), "Gizli (BCC)", required=False)
    if len(to) + len(cc) + len(bcc) > MAX_RECIPIENTS:
        raise WorkflowError(f"Bir e-posta en fazla {MAX_RECIPIENTS} alıcıya gönderilebilir.")
    subject = text(p.get("subject"), "Konu", limit=500)
    if any(char in subject for char in "\r\n"):
        raise WorkflowError("Konu satır sonu içeremez.")
    message = EmailMessage()
    message["From"] = formataddr((config.get("sender_name") or "", config["sender"]))
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(domain=config["sender"].rsplit("@", 1)[-1])
    parent, chain = reply_headers(p.get("in_reply_to"))
    if parent:
        # Threading headers: the reply appears under the original message in the recipient's mail program.
        message["In-Reply-To"] = parent
        message["References"] = chain
    message.set_content(text(p.get("body"), "İleti", required=False, limit=1_000_000) or " ", charset="utf-8")
    for item in attachments(p.get("attachments")):
        kind, _ = mimetypes.guess_type(item.name)
        main, sub = (kind or "application/octet-stream").split("/", 1)
        message.add_attachment(item.read_bytes(), maintype=main, subtype=sub, filename=item.name)
    return message, to + cc + bcc


def describe(exc: Exception) -> str:
    import smtplib

    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return ("Sunucu kullanıcı adını veya şifreyi kabul etmedi. Gmail ve Microsoft 365 için hesabın normal "
                "şifresi yerine uygulama şifresi gerekebilir.")
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "Sunucu alıcı adreslerini reddetti: " + ", ".join(exc.recipients)
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "Sunucu gönderen adresini reddetti; adres, giriş yapılan hesaba ait olmalıdır."
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return "Sunucu seçilen şifrelemeyi desteklemiyor; bağlantıda şifreleme türünü değiştirin."
    if isinstance(exc, ssl.SSLError):
        return "Güvenli bağlantı kurulamadı; bağlantıda port ve şifreleme türünü (465 SSL/TLS, 587 STARTTLS) kontrol edin."
    if isinstance(exc, (TimeoutError, OSError)) and not isinstance(exc, smtplib.SMTPException):
        return "SMTP sunucusuna bağlanılamadı; sunucu adını, portu ve ağ/güvenlik duvarı erişimini kontrol edin."
    return f"E-posta sunucusu hata döndürdü: {exc}"


def connect(config: dict, timeout: float):
    """Open and authenticate; the caller closes it."""
    import smtplib

    import certifi

    context = ssl.create_default_context(cafile=certifi.where())
    port = int(config["port"])
    if config["security"] == "ssl":
        server = smtplib.SMTP_SSL(config["host"], port, timeout=timeout, context=context)
    else:
        server = smtplib.SMTP(config["host"], port, timeout=timeout)
        if config["security"] == "starttls":
            server.starttls(context=context)
    try:
        if config.get("user"):
            server.login(config["user"], config.get("password") or "")
    except BaseException:
        server.close()
        raise
    return server


@handler("mail.send")
def send(ctx, p):
    profile = ctx.connections.resolve(p.get("connection"), "smtp")
    config = profile["config"]
    message, recipients = build(config, p)
    timeout = number(p.get("timeout", 60), "Zaman aşımı", 5, 300)
    try:
        server = connect(config, timeout)
        try:
            # Sent once: an unclear result is reported, never retried (a retry could deliver twice).
            refused = server.send_message(message, to_addrs=recipients)
        finally:
            try:
                server.quit()
            except Exception:
                server.close()
    except Exception as exc:
        raise WorkflowError(f"E-posta gönderilemedi. {describe(exc)}") from exc
    delivered = [item for item in recipients if item not in (refused or {})]
    ctx.log(f"E-posta gönderildi: {message['Subject']} → {', '.join(delivered)}")
    if refused:
        ctx.log("Sunucu bazı alıcıları reddetti: " + ", ".join(refused), level="warning")
    return {"sent": True, "to": delivered, "refused": sorted(refused or {}), "subject": str(message["Subject"])}


@handler("mail.read")
def read(ctx, p):
    """E-postaları oku: IMAP messages as a list; reading never marks them unless the step asks to."""
    from ..integrations.imap import describe as describe_imap
    from ..integrations.imap import read as read_messages

    profile = ctx.connections.resolve(p.get("connection"), "imap")
    folder = text(p.get("folder"), "Klasör", required=False, limit=200).strip()
    count = int(number(p.get("max_messages", 20), "En fazla e-posta", 1, 200))
    days = int(number(p.get("since_days", 0) or 0, "Son kaç gün", 0, 3650))
    target = None
    if str(p.get("attachment_folder") or "").strip():
        target = path(p["attachment_folder"], "Eklerin kaydedileceği klasör")
        target.mkdir(parents=True, exist_ok=True)
    try:
        messages, _ = read_messages(
            profile["config"], folder=folder, unread_only=p.get("unread_only", True) is True,
            from_contains=text(p.get("from_contains"), "Gönderen", required=False, limit=320),
            subject_contains=text(p.get("subject_contains"), "Konu", required=False, limit=500),
            since_days=days, max_messages=count, mark_read=p.get("mark_read") is True, attachment_folder=target,
            timeout=number(p.get("timeout", 60), "Zaman aşımı", 5, 300))
    except WorkflowError:
        raise
    except Exception as exc:
        raise WorkflowError(describe_imap(exc)) from exc
    ctx.log(f"{len(messages)} e-posta okundu" + (" ve okundu olarak işaretlendi." if p.get("mark_read") is True and messages
                                                 else "."))
    return messages
