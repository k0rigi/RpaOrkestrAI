"""Gelen e-posta (IMAP): messages are read with BODY.PEEK, so reading never marks them as read.

Marking as read and saving attachments happen only when the step asks for them. Folder names are
sent in IMAP's modified UTF-7 so Turkish names (ör. "İşlenenler") work on every server.
"""

from __future__ import annotations

import base64
import email
import imaplib
import re
import ssl
from datetime import date, timedelta
from email import policy
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from ..errors import WorkflowError

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MESSAGE_LIMIT = 25 * 1024 * 1024
SAFE_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def folder_name(name: str) -> str:
    """RFC 3501 modified UTF-7, quoted."""
    result, buffer = [], []

    def flush():
        if buffer:
            encoded = base64.b64encode("".join(buffer).encode("utf-16-be")).decode().rstrip("=").replace("/", ",")
            result.append(f"&{encoded}-")
            buffer.clear()

    for char in name:
        if 0x20 <= ord(char) <= 0x7E:
            flush()
            result.append("&-" if char == "&" else char)
        else:
            buffer.append(char)
    flush()
    return '"' + "".join(result).replace("\\", "\\\\").replace('"', '\\"') + '"'


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head"}:
            self._skip += 1
        elif tag in {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "table"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "head"} and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_text(html: str) -> str:
    parser = _Text()
    try:
        parser.feed(html)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t\r\f\v]+", " ", "".join(parser.parts))).strip()


def describe(exc: Exception) -> str:
    message = str(exc)
    lowered = message.lower()
    if any(word in lowered for word in ("authenticationfailed", "invalid credentials", "login failed", "authentication failed",
                                        "logindisabled", "[auth]")):
        return ("Kullanıcı adı veya şifre kabul edilmedi. Gmail'de uygulama şifresi gerekir; Microsoft 365 bu tür "
                "girişi kapatmış olabilir (yöneticinizden IMAP erişimini isteyin).")
    if any(word in lowered for word in ("timed out", "timeout", "connection refused", "name or service not known",
                                        "nodename nor servname", "getaddrinfo", "unreachable")):
        return "E-posta sunucusuna ulaşılamadı. Sunucu adını, portu ve şifreleme seçeneğini kontrol edin."
    return f"E-posta sunucusu işlemi tamamlayamadı: {message.splitlines()[0][:200] if message else type(exc).__name__}"


def connect(config: dict, timeout: float = 30) -> imaplib.IMAP4:
    import certifi

    context = ssl.create_default_context(cafile=certifi.where())
    host, port = config["host"], int(config.get("port") or 993)
    if config.get("security", "ssl") == "ssl":
        client = imaplib.IMAP4_SSL(host, port, ssl_context=context, timeout=timeout)
    else:
        client = imaplib.IMAP4(host, port, timeout=timeout)
        if config.get("security") == "starttls":
            client.starttls(ssl_context=context)
    try:
        client.login(config.get("user", ""), config.get("password", ""))
    except BaseException:
        try:
            client.shutdown()
        except Exception:
            pass
        raise
    return client


def open_folder(client: imaplib.IMAP4, folder: str, *, readonly: bool = True) -> int:
    status, data = client.select(folder_name(folder or "INBOX"), readonly=readonly)
    if status != "OK":
        raise WorkflowError(f"“{folder}” klasörü bulunamadı. Gelen kutusu için INBOX yazın.")
    validity = client.response("UIDVALIDITY")[1]
    try:
        return int(validity[0]) if validity and validity[0] else 0
    except (TypeError, ValueError):
        return 0


def search(client: imaplib.IMAP4, *, unread_only: bool, since_days: int = 0, after_uid: int = 0) -> list[int]:
    criteria = ["UNSEEN"] if unread_only else ["ALL"]
    if since_days:
        day = date.today() - timedelta(days=since_days)
        criteria += ["SINCE", f"{day.day:02d}-{MONTHS[day.month - 1]}-{day.year}"]
    if after_uid:
        criteria += ["UID", f"{after_uid + 1}:*"]
    status, data = client.uid("SEARCH", None, *criteria)
    if status != "OK":
        raise WorkflowError("E-posta sunucusu aramayı yapamadı.")
    uids = sorted(int(item) for item in (data[0] or b"").split() if item.isdigit())
    return [uid for uid in uids if uid > after_uid]


def _header(client: imaplib.IMAP4, uid: int) -> tuple[str, str]:
    status, data = client.uid("FETCH", str(uid), "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
    raw = next((part[1] for part in data or [] if isinstance(part, tuple)), b"") if status == "OK" else b""
    message = email.message_from_bytes(raw, policy=policy.default)
    return str(message.get("From", "")), str(message.get("Subject", ""))


def _message(client: imaplib.IMAP4, uid: int) -> email.message.EmailMessage | None:
    status, data = client.uid("FETCH", str(uid), "(RFC822.SIZE)")
    size = re.search(rb"RFC822\.SIZE (\d+)", b" ".join(part if isinstance(part, bytes) else part[0] for part in data or []))
    if status != "OK" or (size and int(size.group(1)) > MESSAGE_LIMIT):
        return None
    status, data = client.uid("FETCH", str(uid), "(BODY.PEEK[])")
    raw = next((part[1] for part in data or [] if isinstance(part, tuple)), None) if status == "OK" else None
    return email.message_from_bytes(raw, policy=policy.default) if raw else None


def _save(part, folder: Path) -> Path:
    name = SAFE_NAME.sub("_", Path(part.get_filename() or "ek").name).strip(" .") or "ek"
    target, number = folder / name, 2
    while target.exists():
        target = folder / f"{Path(name).stem} ({number}){Path(name).suffix}"
        number += 1
    target.write_bytes(part.get_payload(decode=True) or b"")
    return target


def summary(message, uid: int, *, text_limit: int = 20_000, attachment_folder: Path | None = None) -> dict[str, Any]:
    body = message.get_body(preferencelist=("plain", "html"))
    content = ""
    if body is not None:
        try:
            content = body.get_content()
        except (LookupError, ValueError):
            content = (body.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
        if body.get_content_type() == "text/html":
            content = html_text(content)
    attachments = []
    for part in message.iter_attachments():
        payload = part.get_payload(decode=True) or b""
        item = {"name": part.get_filename() or "ek", "size": len(payload), "type": part.get_content_type()}
        if attachment_folder is not None:
            item["path"] = str(_save(part, attachment_folder))
        attachments.append(item)
    try:
        sent = parsedate_to_datetime(str(message.get("Date"))).isoformat() if message.get("Date") else ""
    except (TypeError, ValueError):
        sent = str(message.get("Date") or "")
    name, address = parseaddr(str(message.get("From", "")))
    return {"uid": uid, "from": address, "from_name": name, "subject": str(message.get("Subject", "")),
            "to": [item[1] for item in getaddresses([str(message.get("To", ""))]) if item[1]],
            "cc": [item[1] for item in getaddresses([str(message.get("Cc", ""))]) if item[1]],
            "date": sent, "message_id": str(message.get("Message-ID", "")).strip(),
            "references": " ".join(str(message.get("References", "")).split())[:4000],
            "text": content[:text_limit], "truncated": len(content) > text_limit, "attachments": attachments}


def read(config: dict, *, folder: str = "", unread_only: bool = True, from_contains: str = "",
         subject_contains: str = "", since_days: int = 0, max_messages: int = 20, mark_read: bool = False,
         attachment_folder: Path | None = None, after_uid: int = 0, text_limit: int = 20_000,
         timeout: float = 30) -> tuple[list[dict], int]:
    """Matching messages (oldest first) and the folder's UIDVALIDITY."""
    client = connect(config, timeout)
    try:
        validity = open_folder(client, folder or config.get("folder") or "INBOX", readonly=not mark_read)
        uids = search(client, unread_only=unread_only, since_days=since_days, after_uid=after_uid)
        wanted_from, wanted_subject = from_contains.casefold().strip(), subject_contains.casefold().strip()
        result = []
        for uid in uids:
            if len(result) >= max_messages:
                break
            if wanted_from or wanted_subject:
                sender, subject = _header(client, uid)
                if wanted_from not in sender.casefold() or wanted_subject not in subject.casefold():
                    continue
            message = _message(client, uid)
            if message is None:
                continue
            result.append(summary(message, uid, text_limit=text_limit, attachment_folder=attachment_folder))
        if mark_read and result:
            client.uid("STORE", ",".join(str(item["uid"]) for item in result), "+FLAGS", "(\\Seen)")
        return result, validity
    finally:
        try:
            client.logout()
        except Exception:
            pass


def latest_uid(config: dict, folder: str = "", timeout: float = 30) -> tuple[int, int]:
    """The newest message's UID and UIDVALIDITY: a new trigger starts after the messages already there."""
    client = connect(config, timeout)
    try:
        validity = open_folder(client, folder or config.get("folder") or "INBOX")
        uids = search(client, unread_only=False)
        return (uids[-1] if uids else 0), validity
    finally:
        try:
            client.logout()
        except Exception:
            pass
