"""Otomasyonlar: zamanında, bir akış bitince, klasöre dosya, tabloya kayıt veya posta kutusuna e-posta
gelince bir ajana görev verir ya da bir akışı doğrudan çalıştırır.

Otomasyon yalnız başlatır; ajanın izinleri, onay kuralı ve sınırları elle verilen görevle, akışın
çalışması da elle başlatılan çalışmayla aynıdır. Studio açık ve lisans/oturum geçerli değilken hiçbir şey
başlatılmaz. Gelen her iş (dosya, kayıt, e-posta, akış bitişi) sıraya girer ve önceki iş bitince sıradaki
başlar; hiçbiri sessizce atlanmaz. Otomasyonun başlattığı akışlar başka otomasyonu tetiklemez.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..config import atomic_json
from ..errors import WorkflowError
from ..models import HOUR_MINUTE, Model, now, uid
from ..scheduler import next_occurrence, summary
from .models import TERMINAL_STATUSES, AgentRunRequest, Identifier, validate_inputs
from .runner import AgentServiceError

MAX_AUTOMATIONS = 50
MAX_PER_HOUR = {"agent": 30, "workflow": 120}
MAX_DELAY = timedelta(minutes=60)  # a run due longer ago (Studio closed or asleep) is recorded as missed
FILES_PER_SCAN = 5
QUEUE_LIMIT = 200
SEEN_LIMIT = 10_000
ROW_LIMIT = 5_000
VALUE_LIMIT = 2_000
DESKTOP_WAIT = 30 * 60  # seconds a flow may wait for the desktop before the start is recorded as skipped
IGNORED_SUFFIXES = (".tmp", ".part", ".crdownload", ".download", ".partial")
QUEUED_KINDS = {"workflow", "folder", "rows", "email"}


class AutomationTrigger(Model):
    kind: Literal["schedule", "workflow", "folder", "rows", "email"] = "schedule"
    # schedule: the same timing as the flow scheduler
    schedule_kind: Literal["once", "daily", "weekly", "interval"] = "daily"
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(default="09:00", pattern=HOUR_MINUTE)
    days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], max_length=7)
    every_minutes: int = Field(default=60, ge=5, le=1440)
    until: str | None = Field(default=None, pattern=HOUR_MINUTE)
    # workflow: a flow run started by a person or the scheduler (never by an agent or an automation) finishes
    workflow_id: Identifier | None = None
    outcome: Literal["succeeded", "failed", "any"] = "any"
    # folder: a new, completely written file appears directly in the folder
    folder: str | None = Field(default=None, max_length=2000)
    pattern: str = Field(default="*", min_length=1, max_length=100)
    # rows: a new record (by its key column) appears in a Google Sheets tab, a database query or an Excel/CSV file
    source: Literal["sheets", "database", "file"] = "sheets"
    connection_id: str | None = Field(default=None, max_length=64)
    spreadsheet_id: str | None = Field(default=None, max_length=500)
    worksheet: str | None = Field(default=None, max_length=100)
    query: str | None = Field(default=None, max_length=20_000)
    file_path: str | None = Field(default=None, max_length=2000)
    sheet: str | None = Field(default=None, max_length=100)
    key_column: str | None = Field(default=None, max_length=100)
    filter_column: str | None = Field(default=None, max_length=100)
    filter_value: str | None = Field(default=None, max_length=500)
    process_existing: bool = False
    # email: a new message arrives in an IMAP folder (connection_id names the IMAP connection)
    mail_folder: str | None = Field(default=None, max_length=200)
    from_contains: str | None = Field(default=None, max_length=320)
    subject_contains: str | None = Field(default=None, max_length=500)
    attachment_folder: str | None = Field(default=None, max_length=2000)
    # rows and email: how often the source is checked
    check_minutes: int = Field(default=5, ge=1, le=1440)

    @model_validator(mode="after")
    def consistent(self) -> AutomationTrigger:
        if self.kind == "schedule":
            if any(day not in range(7) for day in self.days) or len(set(self.days)) != len(self.days):
                raise ValueError("Günler 0 (Pazartesi) ile 6 (Pazar) arasında ve tekrarsız olmalıdır.")
            if self.schedule_kind == "once":
                if not self.date:
                    raise ValueError("Bir kez çalışacak otomasyon için tarih gereklidir.")
                try:
                    datetime.strptime(self.date, "%Y-%m-%d")
                except ValueError:
                    raise ValueError("Geçerli bir tarih girin.") from None
            if self.schedule_kind in {"weekly", "interval"} and not self.days:
                raise ValueError("En az bir gün seçin.")
            if self.schedule_kind == "interval" and self.until is not None and self.until <= self.time:
                raise ValueError("Saat aralığının bitişi başlangıcından sonra olmalıdır.")
        elif self.kind == "workflow" and not self.workflow_id:
            raise ValueError("Tetikleyecek akışı seçin.")
        elif self.kind == "folder":
            if not self.folder or not Path(self.folder).expanduser().is_absolute():
                raise ValueError("İzlenecek klasörün tam yolunu yazın.")
            if any(part in self.pattern for part in ("/", "\\", "..")):
                raise ValueError("Dosya deseni yalnız dosya adına uygulanır (ör. *.pdf).")
        elif self.kind == "rows":
            if not (self.key_column or "").strip():
                raise ValueError("Her kaydı ayıran sütunu (ör. Fatura No veya ID) yazın.")
            if self.source == "sheets" and not (self.spreadsheet_id or "").strip():
                raise ValueError("Google Sheets tablosunun adresini yazın.")
            if self.source == "database":
                from ..database.query import check_read_only

                if not (self.query or "").strip():
                    raise ValueError("Kayıtları getiren SELECT sorgusunu yazın.")
                if "${" in self.query:
                    raise ValueError("Tetikleyici sorgusunda değişken kullanılamaz.")
                try:
                    check_read_only(self.query)
                except WorkflowError as exc:
                    raise ValueError(str(exc)) from None
            if self.source == "file" and (not self.file_path or not Path(self.file_path).expanduser().is_absolute()):
                raise ValueError("İzlenecek Excel veya CSV dosyasının tam yolunu yazın.")
        elif self.kind == "email":
            if self.attachment_folder and not Path(self.attachment_folder).expanduser().is_absolute():
                raise ValueError("Eklerin kaydedileceği klasörün tam yolunu yazın.")
        return self

    def timing(self) -> SimpleNamespace:
        return SimpleNamespace(kind=self.schedule_kind, date=self.date, time=self.time, days=self.days,
                               every_minutes=self.every_minutes, until=self.until)


class AutomationInput(Model):
    name: str = Field(min_length=1, max_length=120)
    target: Literal["agent", "workflow"] = "agent"
    agent_id: Identifier | None = None
    target_workflow_id: Identifier | None = None
    task: str = Field(default="", max_length=16_000)
    inputs: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    trigger: AutomationTrigger = Field(default_factory=AutomationTrigger)

    @field_validator("inputs", mode="before")
    @classmethod
    def bounded_inputs(cls, value: Any) -> dict[str, Any]:
        return validate_inputs(value)

    @model_validator(mode="after")
    def has_target(self) -> AutomationInput:
        if self.target == "agent" and (not self.agent_id or not self.task.strip()):
            raise ValueError("Görevi alacak ajanı seçin ve görevi yazın.")
        if self.target == "workflow" and not self.target_workflow_id:
            raise ValueError("Çalıştırılacak akışı seçin.")
        if self.target == "workflow" and self.trigger.kind == "workflow" \
                and self.trigger.workflow_id == self.target_workflow_id:
            raise ValueError("Bir akış kendi bitişiyle yeniden başlatılamaz.")
        return self


class Automation(AutomationInput):
    id: Identifier = Field(default_factory=uid)
    company_id: int = Field(ge=1)
    user_id: int = Field(ge=1)
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_run_id: Identifier | None = None
    last_status: Literal["started", "queued", "skipped", "missed", "error"] | None = None
    last_message: str | None = Field(default=None, max_length=500)
    recent_starts: list[str] = Field(default_factory=list, max_length=200)
    known_files: list[str] = Field(default_factory=list, max_length=2000)
    pending_files: dict[str, int] = Field(default_factory=dict)
    queue: list[dict[str, Any]] = Field(default_factory=list, max_length=QUEUE_LIMIT)
    seen_keys: list[str] = Field(default_factory=list, max_length=SEEN_LIMIT)
    mail_uid: int = Field(default=0, ge=0)
    mail_validity: int = Field(default=0, ge=0)
    last_check_at: str | None = None


class AutomationBook(Model):
    automations: list[Automation] = Field(default_factory=list, max_length=500)


def describe(trigger: AutomationTrigger, workflow_name: str = "", connection_name: str = "") -> str:
    if trigger.kind == "schedule":
        return summary(trigger.timing())
    if trigger.kind == "workflow":
        outcome = {"succeeded": "başarıyla bittiğinde", "failed": "hata verdiğinde", "any": "bittiğinde"}[trigger.outcome]
        return f"«{workflow_name or 'Seçilen akış'}» {outcome}"
    if trigger.kind == "folder":
        return f"{trigger.folder} klasörüne yeni {trigger.pattern} dosyası geldiğinde"
    every = f"{trigger.check_minutes} dakikada bir denetlenir"
    if trigger.kind == "email":
        where = connection_name or "posta kutusu"
        filters = " · ".join(part for part in (f"gönderen: {trigger.from_contains}" if trigger.from_contains else "",
                                               f"konu: {trigger.subject_contains}" if trigger.subject_contains else "") if part)
        return f"{where} ({trigger.mail_folder or 'INBOX'}) yeni e-posta geldiğinde{' · ' + filters if filters else ''} · {every}"
    source = {"sheets": f"Google Sheets «{trigger.worksheet or 'ilk sayfa'}»", "database": f"{connection_name or 'veritabanı'} sorgusu",
              "file": f"{Path(trigger.file_path or '').name} dosyası"}[trigger.source]
    condition = f" ({trigger.filter_column} = {trigger.filter_value})" if trigger.filter_column else ""
    return f"{source} tablosuna yeni kayıt geldiğinde{condition} · anahtar: {trigger.key_column} · {every}"


def _files(folder: str, pattern: str) -> dict[str, int]:
    """Plain files directly in the folder; hidden, temporary and Office lock files are ignored."""
    result = {}
    root = Path(folder).expanduser()
    with os.scandir(root) as entries:
        for entry in entries:
            name = entry.name
            if (name.startswith((".", "~$")) or name.lower().endswith(IGNORED_SUFFIXES)
                    or not fnmatch.fnmatch(name.lower(), pattern.lower())):
                continue
            try:
                if entry.is_file(follow_symlinks=False):
                    result[name] = entry.stat(follow_symlinks=False).st_size
            except OSError:
                continue
            if len(result) >= 5000:
                break
    return result


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = str(value)
    return text if len(text) <= VALUE_LIMIT else text[:VALUE_LIMIT]


TURKISH = str.maketrans("çğıöşüÇĞİÖŞÜâîûÂÎÛ", "cgiosuCGIOSUaiuAIU")


def safe_names(row: dict) -> dict:
    """Column titles as flow-variable names: «Fatura No» → Fatura_No, «Müşteri» → Musteri."""
    result: dict[str, Any] = {}
    for key, value in row.items():
        name = re.sub(r"[^A-Za-z0-9_]+", "_", str(key).translate(TURKISH)).strip("_") or "sutun"
        name = f"s_{name}" if name[0].isdigit() else name
        base, number = name[:60], 2
        while name in result:
            name, number = f"{base}_{number}", number + 1
        result[name] = _plain(value)
    return result


def _column(row: dict, name: str | None) -> Any:
    if not name:
        return None
    wanted = name.strip().casefold()
    return next((value for key, value in row.items() if str(key).strip().casefold() == wanted), None)


class AutomationService:
    def __init__(self, service, data_dir: Path | str, *, clock=datetime.now, interval: float = 15, manager=None,
                 dispatch=None, connections=None):
        self.service = service
        self.path = Path(data_dir) / "agent_automations.json"
        self.clock = clock
        self.interval = interval
        self.manager, self.dispatch = manager, dispatch
        self._connections = connections
        self._lock = threading.RLock()
        self._events: deque[dict] = deque(maxlen=200)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._waiting: set[str] = set()  # automations whose flow waits for the desktop
        self._runs_lock = threading.Lock()
        self._own_runs: deque[str] = deque(maxlen=1000)

    @property
    def connections(self):
        if self._connections is None:
            from ..connections import Connections

            self._connections = Connections(self.service.settings.data_dir, self.service.settings)
        return self._connections

    # ----- storage ---------------------------------------------------------------------------
    def _read(self) -> AutomationBook:
        if not self.path.is_file():
            return AutomationBook()
        if self.path.stat().st_size > 16 * 1024 * 1024:
            raise AgentServiceError("Otomasyon kaydı izin verilen boyutu aşıyor.", 500)
        return AutomationBook.model_validate_json(self.path.read_text(encoding="utf-8"))

    def _write(self, book: AutomationBook) -> None:
        atomic_json(self.path, json.loads(book.model_dump_json()))

    def _change(self, identity: str, company: int, edit) -> Automation:
        with self._lock:
            book = self._read()
            for index, item in enumerate(book.automations):
                if item.id == identity and item.company_id == company:
                    book.automations[index] = edit(item)
                    self._write(book)
                    return book.automations[index]
        raise AgentServiceError("Otomasyon bulunamadı.", 404)

    def _current(self, identity: str) -> Automation | None:
        with self._lock:
            return next((item for item in self._read().automations if item.id == identity), None)

    def _record(self, identity: str, **changes) -> None:
        def edit(item: Automation) -> Automation:
            return item.model_copy(update=changes)

        try:
            current = self._current(identity)
            if current is not None:
                self._change(identity, current.company_id, edit)
        except AgentServiceError:
            pass

    # ----- management --------------------------------------------------------------------------
    def _profile(self, connection_id: str | None, kind: str) -> dict:
        try:
            return self.connections.resolve(connection_id or None, kind)
        except WorkflowError as exc:
            raise AgentServiceError(str(exc), 422) from None

    def _check_body(self, body: AutomationInput, actor) -> None:
        if body.target == "agent":
            self.service._find_agent(body.agent_id, actor)
        else:
            try:
                self.service.store.workflow(body.target_workflow_id)
            except (KeyError, ValueError):
                raise AgentServiceError("Çalıştırılacak akış bulunamadı.", 422) from None
        trigger = body.trigger
        if trigger.kind == "workflow":
            try:
                self.service.store.workflow(trigger.workflow_id)
            except (KeyError, ValueError):
                raise AgentServiceError("Tetikleyecek akış bulunamadı.", 422) from None
        if trigger.kind == "folder" and not Path(trigger.folder).expanduser().is_dir():
            raise AgentServiceError("İzlenecek klasör bulunamadı veya erişilemiyor.", 422)
        if trigger.kind == "schedule" and body.enabled and next_occurrence(trigger.timing(), self.clock()) is None:
            raise AgentServiceError("Seçilen zaman geçmişte kaldı; ileri bir tarih veya saat seçin.", 422)
        if trigger.kind == "rows" and trigger.source in {"sheets", "database"}:
            self._profile(trigger.connection_id, "google_sheets" if trigger.source == "sheets" else "database")
        if trigger.kind == "rows" and trigger.source == "file" and not Path(trigger.file_path).expanduser().is_file():
            raise AgentServiceError("İzlenecek Excel veya CSV dosyası bulunamadı.", 422)
        if trigger.kind == "email":
            self._profile(trigger.connection_id, "imap")
        redactor = self.service._new_redactor()
        if any(redactor.contains_secret(text) for text in (body.name, body.task, json.dumps(body.inputs, ensure_ascii=False),
                                                           json.dumps(trigger.model_dump(), ensure_ascii=False))):
            raise AgentServiceError("Otomasyon kayıtlı bir şifre veya anahtar içeremez.", 422)

    def _prepared(self, item: Automation) -> Automation:
        """Reset trigger state after a change: existing files, rows and messages never fire, unless asked."""
        moment = self.clock()
        item.pending_files, item.queue, item.seen_keys = {}, [], []
        item.known_files, item.mail_uid, item.mail_validity, item.last_check_at = [], 0, 0, None
        trigger = item.trigger
        if trigger.kind == "schedule":
            due = next_occurrence(trigger.timing(), moment)
            item.next_run_at = due.isoformat(timespec="minutes") if due else None
        else:
            item.next_run_at = None
        try:
            if trigger.kind == "folder":
                item.known_files = sorted(_files(trigger.folder, trigger.pattern))[-2000:]
            elif trigger.kind == "rows":
                rows = self._rows(trigger)
                if not trigger.process_existing:
                    item.seen_keys = [key for key, _ in self._keyed(trigger, rows)][-SEEN_LIMIT:]
                    item.last_check_at = moment.isoformat(timespec="seconds")
            elif trigger.kind == "email":
                from ..integrations.imap import latest_uid

                item.mail_uid, item.mail_validity = latest_uid(self._profile(trigger.connection_id, "imap")["config"],
                                                               trigger.mail_folder or "", timeout=30)
                item.last_check_at = moment.isoformat(timespec="seconds")
        except AgentServiceError:
            raise
        except WorkflowError as exc:
            raise AgentServiceError(f"Kaynak okunamadı: {exc}", 422) from None
        except Exception as exc:
            raise AgentServiceError(f"Kaynak okunamadı: {self._describe(trigger, exc)}", 422) from None
        return item

    def view(self, item: Automation) -> dict:
        workflow_name = connection_name = target_name = ""
        if item.trigger.workflow_id:
            workflow_name = self._workflow_name(item.trigger.workflow_id)
        if item.target == "workflow":
            target_name = self._workflow_name(item.target_workflow_id)
        if item.trigger.kind in {"rows", "email"} and item.trigger.connection_id:
            try:
                connection_name = self.connections.get(item.trigger.connection_id)["name"]
            except KeyError:
                connection_name = "Silinmiş bağlantı"
        data = item.model_dump(exclude={"known_files", "pending_files", "recent_starts", "company_id", "queue", "seen_keys",
                                        "mail_uid", "mail_validity"})
        data.update(summary=describe(item.trigger, workflow_name, connection_name), queue_count=len(item.queue),
                    target_name=target_name, waiting=item.id in self._waiting)
        return data

    def _workflow_name(self, identity: str | None) -> str:
        try:
            return self.service.store.workflow(identity).name
        except (KeyError, ValueError, TypeError):
            return "Silinmiş akış"

    def automations(self) -> list[dict]:
        actor = self.service._authorize()
        with self._lock:
            return [self.view(item) for item in self._read().automations if item.company_id == actor.company_id]

    def create(self, body: AutomationInput) -> dict:
        actor = self.service._authorize("agents.manage")
        self._check_body(body, actor)
        with self._lock:
            book = self._read()
            if sum(item.company_id == actor.company_id for item in book.automations) >= MAX_AUTOMATIONS:
                raise AgentServiceError(f"En fazla {MAX_AUTOMATIONS} otomasyon tanımlanabilir.", 409)
        item = self._prepared(Automation(**body.model_dump(), company_id=actor.company_id, user_id=actor.user_id))
        with self._lock:
            book = self._read()
            book.automations.append(item)
            self._write(book)
            return self.view(item)

    def update(self, identity: str, body: AutomationInput) -> dict:
        actor = self.service._authorize("agents.manage")
        self._check_body(body, actor)
        with self._lock:
            previous = next((item for item in self._read().automations
                             if item.id == identity and item.company_id == actor.company_id), None)
        if previous is None:
            raise AgentServiceError("Otomasyon bulunamadı.", 404)
        changed = Automation(**{**previous.model_dump(), **body.model_dump(), "updated_at": now()})
        if changed.trigger != previous.trigger or changed.enabled != previous.enabled:
            changed = self._prepared(changed)
        return self.view(self._change(identity, actor.company_id, lambda item: changed))

    def delete(self, identity: str) -> None:
        actor = self.service._authorize("agents.manage")
        with self._lock:
            book = self._read()
            remaining = [item for item in book.automations if not (item.id == identity and item.company_id == actor.company_id)]
            if len(remaining) == len(book.automations):
                raise AgentServiceError("Otomasyon bulunamadı.", 404)
            book.automations = remaining
            self._write(book)

    def run_now(self, identity: str) -> dict:
        actor = self.service._authorize("agents.manage")
        with self._lock:
            item = next((value for value in self._read().automations
                         if value.id == identity and value.company_id == actor.company_id), None)
        if item is None:
            raise AgentServiceError("Otomasyon bulunamadı.", 404)
        self._start(item, {"tetikleyici": "elle"}, manual=True)
        return self.view(self._current(identity))

    # ----- triggering ------------------------------------------------------------------------------
    def workflow_finished(self, run) -> None:
        """Called by the flow worker; keeps only metadata and returns at once."""
        if run.status not in {"succeeded", "failed"}:
            return
        with self._runs_lock:
            if run.id in self._own_runs:
                return  # An automation's own flow never starts another automation.
        self._events.append({"workflow_id": run.workflow_id, "status": run.status, "run_id": run.id,
                             "name": run.workflow_name, "error": (run.error or "")[:500]})
        self.poke()

    def poke(self) -> None:
        self._wake = True

    def _running(self, item: Automation) -> bool:
        if item.id in self._waiting:
            return True
        if not item.last_run_id:
            return False
        try:
            if item.target == "workflow":
                return self.service.store.run(item.last_run_id).status not in TERMINAL_STATUSES
            return self.service.agent_store.run(item.last_run_id).status not in TERMINAL_STATUSES
        except (KeyError, ValueError, OSError):
            return False

    def _enqueue(self, item: Automation, entries: list[dict]) -> None:
        if not entries:
            return
        room = QUEUE_LIMIT - len(item.queue)
        accepted = entries[:max(0, room)]
        dropped = len(entries) - len(accepted)

        def edit(current: Automation) -> Automation:
            update = {"queue": (current.queue + accepted)[:QUEUE_LIMIT]}
            if dropped:
                update.update(last_status="error", last_message=f"Sıra dolu ({QUEUE_LIMIT}); {dropped} iş eklenemedi.")
            elif current.last_status != "started" or not current.queue:
                update.update(last_status="queued", last_message=f"{len(current.queue) + len(accepted)} iş sırada.")
            return current.model_copy(update=update)

        self._change(item.id, item.company_id, edit)

    def _start(self, item: Automation, trigger_inputs: dict, *, manual: bool = False) -> bool:
        """Start one task or flow; returns False when it could not start now (busy or over the hourly limit)."""
        moment = self.clock()
        stamp = moment.isoformat(timespec="seconds")
        hour_ago = (moment - timedelta(hours=1)).isoformat(timespec="seconds")
        recent = [value for value in item.recent_starts if value > hour_ago]
        limit = MAX_PER_HOUR[item.target]
        if self._running(item):
            if manual:
                raise AgentServiceError("Bu otomasyonun önceki işi henüz bitmedi.", 409)
            return False
        if len(recent) >= limit:
            if manual:
                raise AgentServiceError("Bu otomasyon son bir saatte çok sık çalıştı; biraz bekleyin.", 429)
            self._record(item.id, last_status="skipped", last_run_at=stamp,
                         last_message=f"Bir saatte en fazla {limit} kez çalışabilir; sıradaki iş bekletiliyor.")
            return False
        inputs = {**item.inputs, **trigger_inputs}
        if item.target == "workflow":
            return self._start_workflow(item, inputs, stamp, recent, manual)
        try:
            body = AgentRunRequest(task=item.task, title=f"Otomatik: {item.name}"[:200], inputs=inputs)
            run = self.service.start_automated(item.agent_id, body, {
                "automation_id": item.id, "name": item.name, "trigger": item.trigger.kind, "manual": manual})
        except (AgentServiceError, ValueError) as exc:
            if manual:
                raise
            self._record(item.id, last_status="error", last_run_at=stamp, last_message=str(exc)[:500])
            return True  # The item is consumed; a broken agent setup must not retry forever.
        self._record(item.id, last_status="started", last_run_at=stamp, last_run_id=run.id,
                     last_message="Görev başlatıldı.", recent_starts=[*recent, stamp][-200:])
        return True

    def _start_workflow(self, item: Automation, inputs: dict, stamp: str, recent: list[str], manual: bool) -> bool:
        if self.manager is None or self.dispatch is None:
            raise AgentServiceError("Akış başlatma bu ortamda kullanılamıyor.", 500)
        try:
            workflow = self.service.store.workflow(item.target_workflow_id)
        except (KeyError, ValueError):
            message = "Çalıştırılacak akış artık yok; otomasyon kapatıldı."
            self._record(item.id, enabled=False, last_status="error", last_run_at=stamp, last_message=message)
            if manual:
                raise AgentServiceError(message, 409) from None
            return True
        self._waiting.add(item.id)
        self._record(item.id, last_status="queued", last_run_at=stamp,
                     last_message="Akış, masaüstü boşalınca başlayacak.", recent_starts=[*recent, stamp][-200:])
        cancel = threading.Event()
        self._cancels = getattr(self, "_cancels", set())
        self._cancels.add(cancel)

        def launch():
            with self._runs_lock:
                run = self.manager.start(workflow, variables=dict(inputs), trigger="schedule")
                self._own_runs.append(run.id)
                return run

        def wait():
            try:
                run = self.dispatch.start_agent(f"automation:{item.id}:{uid()}", launch, cancel=cancel,
                                                deadline=time.monotonic() + DESKTOP_WAIT, check=lambda: None)
                if run is None:
                    self._record(item.id, last_status="skipped",
                                 last_message="Masaüstü 30 dakika boşalmadığı için akış başlatılamadı.")
                else:
                    self._record(item.id, last_status="started", last_run_id=run.id, last_message="Akış başlatıldı.")
            except Exception as exc:
                self._record(item.id, last_status="error", last_message=f"Akış başlatılamadı: {exc}"[:500])
            finally:
                self._waiting.discard(item.id)
                self._cancels.discard(cancel)
                self.poke()

        threading.Thread(target=wait, name=f"rpa-automation-{item.id[:8]}", daemon=True).start()
        return True

    def tick(self) -> None:
        try:
            actor = self.service._authorize()
        except AgentServiceError:
            return  # No licensed session: nothing starts; due times are judged when one exists.
        moment = self.clock()
        with self._lock:
            items = [item for item in self._read().automations if item.company_id == actor.company_id and item.enabled]
        events = []
        while self._events:
            events.append(self._events.popleft())
        for item in items:
            trigger = item.trigger
            try:
                if trigger.kind == "schedule":
                    self._schedule(item, moment)
                    continue
                if trigger.kind == "workflow":
                    self._enqueue(item, [{"tetikleyen_akis": event["name"], "akis_durumu": event["status"],
                                          "akis_hatasi": event["error"], "akis_calisma_id": event["run_id"]}
                                         for event in events if event["workflow_id"] == trigger.workflow_id
                                         and trigger.outcome in {"any", event["status"]}])
                elif trigger.kind == "folder":
                    self._scan_folder(item)
                elif self._due(item, moment):
                    self._scan_rows(item, moment) if trigger.kind == "rows" else self._scan_mail(item, moment)
            except Exception as exc:
                self._record(item.id, last_status="error", last_run_at=moment.isoformat(timespec="seconds"),
                             last_check_at=moment.isoformat(timespec="seconds"),
                             last_message=self._describe(trigger, exc)[:500])
            self._drain(item.id)

    def _drain(self, identity: str) -> None:
        """Start the oldest queued item when the previous one has finished."""
        item = self._current(identity)
        if item is None or not item.enabled or not item.queue:
            return
        entry = item.queue[0]
        if self._start(item, entry):
            self._record(identity, queue=item.queue[1:])

    def _due(self, item: Automation, moment: datetime) -> bool:
        if not item.last_check_at:
            return True
        return moment - datetime.fromisoformat(item.last_check_at) >= timedelta(minutes=item.trigger.check_minutes)

    def _schedule(self, item: Automation, moment: datetime) -> None:
        timing = item.trigger.timing()
        if not item.next_run_at:
            return
        due = datetime.fromisoformat(item.next_run_at)
        if moment < due:
            return
        following = next_occurrence(timing, moment)
        update: dict[str, Any] = {"next_run_at": following.isoformat(timespec="minutes") if following else None}
        if following is None and item.trigger.schedule_kind == "once":
            update["enabled"] = False
        self._record(item.id, **update)
        if moment - due > MAX_DELAY:
            self._record(item.id, last_status="missed", last_run_at=moment.isoformat(timespec="seconds"),
                         last_message=f"{due.strftime('%d.%m.%Y %H:%M')} çalışması Studio kapalı olduğu için kaçırıldı.")
            return
        if not self._start(item, {"tetikleme_zamani": due.isoformat(timespec="minutes")}) and self._running(item):
            self._record(item.id, last_status="skipped", last_run_at=moment.isoformat(timespec="seconds"),
                         last_message="Önceki iş sürdüğü için bu zaman atlandı.")

    def _scan_folder(self, item: Automation) -> None:
        try:
            current = _files(item.trigger.folder, item.trigger.pattern)
        except OSError:
            if item.last_status != "error":
                self._record(item.id, last_status="error", last_message="İzlenen klasör okunamadı.")
            return
        known = set(item.known_files)
        # A file is handed over only after two scans with the same size, so half-copied files wait.
        ready = [name for name, size in sorted(current.items()) if name not in known and item.pending_files.get(name) == size]
        started = ready[:FILES_PER_SCAN]
        pending = {name: size for name, size in current.items() if name not in known and name not in started}
        if pending != item.pending_files or started:
            self._record(item.id, pending_files=dict(list(pending.items())[:500]),
                         known_files=(item.known_files + started)[-2000:])
        folder = Path(item.trigger.folder).expanduser()
        fresh = self._current(item.id) or item
        self._enqueue(fresh, [{"dosya_adi": name, "dosya_yolu": str(folder / name)} for name in started])

    # ----- table rows ----------------------------------------------------------------------------
    def _rows(self, trigger: AutomationTrigger) -> list[dict]:
        if trigger.source == "file":
            from ..actions.files import read_table

            return read_table(None, {"path": trigger.file_path, "sheet": trigger.sheet or "", "max_rows": ROW_LIMIT})
        if trigger.source == "database":
            from ..database.query import QueryDatabase

            def no_variables(name):
                raise WorkflowError("Tetikleyici sorgusunda değişken kullanılamaz.")

            profile = self._profile(trigger.connection_id, "database")
            with QueryDatabase(profile["config"], timeout_seconds=60) as database:
                rows, _ = database.query(trigger.query, no_variables, ROW_LIMIT)
            return rows
        from ..actions.files import _headers
        from ..integrations.sheets import SheetsService, normalize_spreadsheet_id

        profile = self._profile(trigger.connection_id, "google_sheets")
        config = profile["config"]
        try:
            spreadsheet = normalize_spreadsheet_id(trigger.spreadsheet_id)
        except ValueError:
            raise WorkflowError("Geçerli bir Google Sheets adresi veya kimliği girin.") from None
        worksheet = trigger.worksheet or "Sayfa1"
        if config["method"] == "apps_script":
            from ..integrations.apps_script import AppsScriptSheets

            service = AppsScriptSheets(config["script_url"], config["script_token"], spreadsheet, worksheet, timeout=60)
        else:
            service = SheetsService(config["credentials_path"], spreadsheet, worksheet, timeout=60)
        with service:
            matrix = service.get_range(f"A1:BZ{ROW_LIMIT + 1}")
        if not matrix:
            return []
        headers = _headers(matrix[0], max(len(row) for row in matrix))
        return [{**{name: (row[index] if index < len(row) else None) for index, name in enumerate(headers)},
                 "row_number": number}
                for number, row in enumerate(matrix[1:], start=2) if any(value not in (None, "") for value in row)]

    def _keyed(self, trigger: AutomationTrigger, rows: list[dict]) -> list[tuple[str, dict]]:
        """Rows that pass the optional filter, with a non-empty key; the first copy of a key wins."""
        for name in (trigger.key_column, trigger.filter_column):
            if name and rows and all(_column(row, name) is None for row in rows[:50]):
                columns = ", ".join(str(column) for column in list(rows[0])[:25] if column != "row_number")
                raise WorkflowError(f"“{name}” sütunu bulunamadı. Tablodaki sütunlar: {columns}")
        result, seen = [], set()
        wanted = (trigger.filter_value or "").strip().casefold()
        for row in rows:
            if trigger.filter_column and str(_column(row, trigger.filter_column) or "").strip().casefold() != wanted:
                continue
            key = str(_column(row, trigger.key_column) or "").strip()
            if key and key not in seen:
                seen.add(key)
                result.append((key, row))
        return result

    def _scan_rows(self, item: Automation, moment: datetime) -> None:
        trigger = item.trigger
        keyed = self._keyed(trigger, self._rows(trigger))
        seen = set(item.seen_keys)
        fresh = [(key, row) for key, row in keyed if key not in seen]
        self._record(item.id, last_check_at=moment.isoformat(timespec="seconds"),
                     seen_keys=(item.seen_keys + [key for key, _ in fresh])[-SEEN_LIMIT:])
        current = self._current(item.id) or item
        self._enqueue(current, [{"kayit": safe_names(row), "kayit_anahtari": key} for key, row in fresh])

    # ----- mail ------------------------------------------------------------------------------------
    def _scan_mail(self, item: Automation, moment: datetime) -> None:
        from ..integrations.imap import latest_uid, read

        trigger = item.trigger
        config = self._profile(trigger.connection_id, "imap")["config"]
        folder = Path(trigger.attachment_folder).expanduser() if trigger.attachment_folder else None
        if folder is not None:
            folder.mkdir(parents=True, exist_ok=True)
        messages, validity = read(config, folder=trigger.mail_folder or "", unread_only=False,
                                  from_contains=trigger.from_contains or "", subject_contains=trigger.subject_contains or "",
                                  max_messages=20, after_uid=item.mail_uid, attachment_folder=folder, text_limit=4000,
                                  timeout=60)
        if item.mail_validity and validity != item.mail_validity:
            # The server renumbered the folder: start again after the messages that are there now.
            newest, validity = latest_uid(config, trigger.mail_folder or "", timeout=60)
            self._record(item.id, mail_uid=newest, mail_validity=validity, last_check_at=moment.isoformat(timespec="seconds"),
                         last_message="Posta klasörü yeniden numaralandı; yeni iletilerden devam ediliyor.")
            return
        newest = max([item.mail_uid, *(message["uid"] for message in messages)])
        self._record(item.id, mail_uid=newest, mail_validity=validity, last_check_at=moment.isoformat(timespec="seconds"))
        current = self._current(item.id) or item
        self._enqueue(current, [{"eposta": {key: message[key] for key in (
            "from", "from_name", "subject", "date", "text", "attachments", "message_id", "uid")}} for message in messages])

    @staticmethod
    def _describe(trigger: AutomationTrigger, exc: Exception) -> str:
        if isinstance(exc, (WorkflowError, AgentServiceError)):
            return str(exc)
        if trigger.kind == "email":
            from ..integrations.imap import describe as describe_imap

            return describe_imap(exc)
        if trigger.kind == "rows" and trigger.source == "database":
            from ..database.query import describe as describe_database

            return describe_database(exc)
        return f"Kaynak okunamadı: {str(exc).splitlines()[0][:200] if str(exc) else type(exc).__name__}"

    # ----- lifecycle -------------------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="rpa-agent-automations", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        for cancel in list(getattr(self, "_cancels", ())):
            cancel.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        last = 0.0
        while not self._stop.is_set():
            if getattr(self, "_wake", False) or time.monotonic() - last >= self.interval:
                self._wake = False
                last = time.monotonic()
                try:
                    self.tick()
                except Exception:
                    pass  # One broken record must not stop other automations; state stays on disk.
            self._stop.wait(1)
