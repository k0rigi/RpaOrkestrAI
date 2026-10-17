"""Ajanın akış gerektirmeyen yetenekleri: belge okuma, e-posta okuma ve gönderme, mesaj gönderme.

Akışlar masaüstü ve sistem işleri içindir. Metni anlamak, özetlemek ve yanıt yazmak ajanın kendi işidir; yazdığı
yanıtı göndermek için akış kurmak gerekmez. Yetenekler yalnız ajan formunda açılırsa sunulur. Gönderen yetenekler
akışlarla aynı onay, düzeltilerek onay ve süreç kartı kurallarıyla çalışır; okuyanlar yalnız seçilen klasör ve
hesaplarda okur.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from ..errors import WorkflowError
from .knowledge import SUPPORTED, extract, files_of
from .risk import WRITE

DOCUMENT_PART = 20_000
MAX_DOCUMENT_READS = 30
MAX_EMAIL_READS = 5
MAX_SENDS = 10
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}")
ABILITY_TOOLS = frozenset({"list_documents", "read_document", "read_emails", "send_email", "send_message"})
CARD_REQUIRED = ("Bu ajanın süreç kartları var: göndermeden önce use_playbook ile işe uyan kartı seçin. Uyan kart yoksa "
                 "göndermeyin; durumu özetleyip finish ile handoff=true olarak işi insana bırakın.")


@dataclass
class AbilityRequest:
    """Shaped like a prepared workflow, so approvals, corrections and central records treat both alike."""

    root: SimpleNamespace
    inputs: dict
    digest: str
    kind: str
    connection_id: str
    risk: str = WRITE


def tool_names(agent) -> set[str]:
    abilities = agent.abilities
    names = set()
    if abilities.document_folders:
        names |= {"list_documents", "read_document"}
    if abilities.inbox_connection_id:
        names.add("read_emails")
    if abilities.email_connection_id:
        names.add("send_email")
    if abilities.message_connection_id:
        names.add("send_message")
    return names


def ability_id(agent_id: str, kind: str) -> str:
    return hashlib.sha256(f"ability:{kind}:{agent_id}".encode()).hexdigest()[:32]


def _local(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone().isoformat(timespec="minutes")


class Abilities:
    def __init__(self, service):
        self.service = service

    def _note(self, context, kind, message, data):
        # A chat has no run to write a timeline event to; a task records every read and send.
        if getattr(context, "run_events", True):
            self.service._event(context, kind, message, data)

    def connections(self):
        from ..connections import Connections

        return Connections(self.service.settings.data_dir, self.service.settings)

    def _profile(self, identity, kind, label):
        try:
            profile = self.connections().get(identity)
        except KeyError:
            raise WorkflowError(f"{label} bağlantısı bulunamadı; ajan formundan yeniden seçin.") from None
        if profile["type"] != kind:
            raise WorkflowError(f"Seçilen bağlantı bir {label} bağlantısı değil.")
        return profile

    # ----- reading -------------------------------------------------------------------
    def _folders(self, agent):
        return [Path(folder).expanduser().resolve() for folder in agent.abilities.document_folders]

    def _inside(self, agent, raw) -> Path:
        path = Path(str(raw or "").strip()).expanduser()
        if not path.is_absolute():
            raise WorkflowError("Belgenin tam yolunu verin; önce list_documents ile izinli klasörlere bakın.")
        if path.is_symlink():
            raise WorkflowError("Kısayol (sembolik bağlantı) olan belge okunmaz.")
        resolved = path.resolve()
        if not any(resolved == folder or folder in resolved.parents for folder in self._folders(agent)):
            raise WorkflowError("Bu belge ajanın izinli klasörlerinde değil.")
        self.service.knowledge.check_source(str(resolved))
        return resolved

    def list_documents(self, context, folder=""):
        roots = [self._inside(context.agent, folder)] if folder else self._folders(context.agent)
        found = set()
        for root in roots:
            if root.is_dir():
                found.update(files_of(root)[0])
        items = []
        for file in found:
            try:
                stat = file.stat()
            except OSError:
                continue
            items.append((stat.st_mtime, {"path": str(file), "name": file.name, "size_kb": round(stat.st_size / 1024, 1),
                                          "modified": _local(stat.st_mtime)}))
        items.sort(key=lambda item: item[0], reverse=True)
        return {"documents": context.redactor.sanitize([item for _, item in items[:50]])}

    def read_document(self, context, path, part=1):
        if context.document_reads >= MAX_DOCUMENT_READS:
            raise WorkflowError(f"Bir görevde en fazla {MAX_DOCUMENT_READS} belge okunabilir.")
        file = self._inside(context.agent, path)
        if not file.is_file():
            raise WorkflowError("Belge bulunamadı.")
        if file.suffix.casefold() not in SUPPORTED:
            raise WorkflowError("Bu dosya türü okunmaz; PDF, Word (.docx), Excel (.xlsx), metin, CSV veya HTML okunur.")
        context.document_reads += 1
        try:
            sections = extract(file)
        except WorkflowError:
            raise
        except Exception:
            raise WorkflowError("Belge okunamadı (bozuk, şifreli veya başka bir programda açık olabilir).") from None
        text = context.redactor.text("\n\n".join(f"[{location}]\n{body}" if location else body
                                                 for location, body in sections))
        parts = max(1, math.ceil(len(text) / DOCUMENT_PART))
        part = min(max(1, int(part)), parts)
        self._note(context, "document_read", "Belge okundu.", {"name": file.name, "part": part, "parts": parts})
        return {"name": file.name, "part": part, "parts": parts, "text": text[(part - 1) * DOCUMENT_PART:part * DOCUMENT_PART]}

    def read_emails(self, context, arguments):
        from ..integrations.imap import describe, read

        if context.email_reads >= MAX_EMAIL_READS:
            raise WorkflowError(f"Bir görevde en fazla {MAX_EMAIL_READS} kez e-posta okunabilir.")
        profile = self._profile(context.agent.abilities.inbox_connection_id, "imap", "gelen e-posta")
        context.email_reads += 1
        try:
            messages, _ = read(profile["config"], folder=arguments.folder, unread_only=arguments.unread_only,
                               from_contains=arguments.from_contains, subject_contains=arguments.subject_contains,
                               since_days=arguments.since_days, max_messages=arguments.max_messages, mark_read=False,
                               attachment_folder=None, text_limit=6000, timeout=30)
        except WorkflowError:
            raise
        except Exception as exc:
            raise WorkflowError(describe(exc)) from None
        emails = [{**{key: message[key] for key in ("from", "from_name", "subject", "date", "text", "message_id",
                                                    "references") if key in message},
                   "attachments": [item["name"] for item in message.get("attachments", [])]} for message in messages]
        self._note(context, "emails_read", "Gelen kutusu okundu.", {"count": len(emails)})
        return {"emails": context.redactor.sanitize(emails)}

    # ----- sending -------------------------------------------------------------------
    def _digest(self, context, kind, connection_id, inputs):
        actor = context.run.actor
        payload = {"agent": context.agent.id, "revision": context.agent.revision, "kind": kind, "connection": connection_id,
                   "actor": [actor.user_id, actor.company_id, actor.session_id], "inputs": inputs}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def _check_recipients(self, context, recipients):
        abilities = context.agent.abilities
        if abilities.email_recipients == "any":
            return
        if abilities.email_recipients == "domains":
            def allowed(address):
                domain = address.rsplit("@", 1)[-1].casefold()
                return any(domain == item or domain.endswith("." + item) for item in abilities.email_domains)

            if not all(allowed(address) for address in recipients):
                raise WorkflowError("Bu ajan yalnız şu alan adlarına e-posta gönderebilir: "
                                    + ", ".join(abilities.email_domains) + ".")
            return
        known = {item.casefold() for item in EMAIL_PATTERN.findall(json.dumps(context.run.inputs, ensure_ascii=False))}
        if not all(address.casefold() in known for address in recipients):
            raise WorkflowError("Bu ajan yalnız göreve verilen adreslere (ör. gelen e-postanın gönderenine) yanıt "
                                "verebilir; başka bir adrese gönderemez.")

    def request(self, context, kind, inputs) -> AbilityRequest:
        """Validated send request; the approver's corrected values come through here again."""
        from ..actions.mail import addresses, reply_headers

        agent = context.agent
        if kind == "email":
            to = addresses(inputs.get("kime"), "Kime", required=True)
            cc = addresses(inputs.get("bilgi"), "Bilgi (CC)", required=False)
            if len(to) + len(cc) > 10:
                raise WorkflowError("Ajan bir e-postayı en fazla 10 alıcıya gönderebilir.")
            subject = str(inputs.get("konu") or "").strip()
            if not subject or len(subject) > 500 or any(char in subject for char in "\r\n"):
                raise WorkflowError("Konu tek satır olmalı ve en fazla 500 karakter olabilir.")
            body = str(inputs.get("metin") or "")
            if not body.strip() or len(body) > 20_000:
                raise WorkflowError("E-posta metni boş olamaz ve en fazla 20.000 karakter olabilir.")
            parent = str(inputs.get("yanitlanan") or "").strip()
            reply_headers(parent)
            self._check_recipients(context, to + cc)
            identity = agent.abilities.email_connection_id
            profile = self._profile(identity, "smtp", "e-posta (SMTP)")
            clean = {"kime": to, "bilgi": cc, "konu": subject, "metin": body, "yanitlanan": parent}
            name = f"E-posta gönder · {profile['name']}"
        else:
            title = str(inputs.get("baslik") or "").strip()
            body = str(inputs.get("metin") or "")
            if len(title) > 200 or not body.strip() or len(body) > 4000:
                raise WorkflowError("Mesaj boş olamaz; başlık en fazla 200, metin en fazla 4000 karakter olabilir.")
            identity = agent.abilities.message_connection_id
            profile = self._profile(identity, "webhook", "mesajlaşma")
            clean = {"baslik": title, "metin": body}
            name = f"Mesaj gönder · {profile['name']}"
        return AbilityRequest(root=SimpleNamespace(id=ability_id(agent.id, kind), name=name), inputs=clean,
                              digest=self._digest(context, kind, identity, clean), kind=kind, connection_id=identity)

    def send(self, context, kind, inputs, reason):
        service = self.service
        card = context.playbook
        if context.agent.playbooks:
            if card is None:
                raise WorkflowError(CARD_REQUIRED)
            if card.mode == "handoff":
                raise WorkflowError(f"«{card.title}» kartında iş insana bırakılır; gönderim yapılamaz. Durumu özetleyip "
                                    "finish ile handoff=true olarak bitirin.")
        if context.sends >= MAX_SENDS:
            raise WorkflowError(f"Bir görevde en fazla {MAX_SENDS} gönderim yapılabilir.")
        request = self.request(context, kind, inputs)
        abilities = context.agent.abilities
        trusted = abilities.email_without_approval if kind == "email" else abilities.message_without_approval
        approval = None
        if not trusted or (card is not None and card.mode == "review"):
            approval = service._wait_approval(context, request, reason,
                                              reprepare=lambda values: self.request(context, kind, values))
            if approval is None:
                return {"status": "rejected", "message": "Onay verilmedi; gönderilmedi."}
            if approval.get("edited"):
                request = approval["edited"]["prepared"]
            service._consume_approval(context, approval, request.digest)
        service._check(context)
        context.sends += 1
        result = self._deliver(request)
        detail = ({"to": result.get("to"), "subject": request.inputs["konu"]} if kind == "email"
                  else {"title": request.inputs["baslik"], "to": result.get("to") or result.get("chat")})
        service._event(context, "email_sent" if kind == "email" else "message_sent",
                       "E-posta gönderildi." if kind == "email" else "Mesaj gönderildi.", detail)
        answer = {"status": "sent", **result}
        if approval is not None and approval.get("edited"):
            answer["approver_edits"] = {
                "changed_inputs": {key: change["after"] for key, change in approval["edited"]["changes"].items()},
                "message": "Onaylayan kişi taslağı düzenledi; gönderilen hâli budur. Düzeltmeden sonraki işler için "
                           "genel bir kural çıkıyorsa suggest_note ile öner."}
        return context.redactor.sanitize(answer)

    def _deliver(self, request):
        from ..actions.mail import send
        from ..actions.transfer import notify_send

        ctx = SimpleNamespace(connections=self.connections(), log=lambda *args, **kwargs: None)
        values = request.inputs
        if request.kind == "email":
            result = send(ctx, {"connection": request.connection_id, "to": values["kime"], "cc": values["bilgi"],
                                "subject": values["konu"], "body": values["metin"], "in_reply_to": values["yanitlanan"]})
            return {"to": result["to"], "refused": result["refused"]}
        result = notify_send(ctx, {"connection": request.connection_id, "title": values["baslik"], "text": values["metin"]})
        return {key: value for key, value in result.items() if key in {"to", "chat", "id"}}
