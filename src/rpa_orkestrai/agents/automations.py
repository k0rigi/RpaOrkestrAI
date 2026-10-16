"""Ajan otomasyonları: zamanında, bir akış bitince veya klasöre dosya gelince ajana görev verir.

Otomasyon yalnız görev başlatır; ajanın izinleri, onay kuralı ve sınırları elle verilen görevle aynıdır.
Studio açık ve lisans/oturum geçerli değilken hiçbir şey başlatılmaz.
"""

from __future__ import annotations

import fnmatch
import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from ..config import atomic_json
from ..models import HOUR_MINUTE, Model, now, uid
from ..scheduler import next_occurrence, summary
from .models import TERMINAL_STATUSES, AgentRunRequest, Identifier, validate_inputs
from .runner import AgentServiceError

MAX_AUTOMATIONS = 50
MAX_PER_HOUR = 30
MAX_DELAY = timedelta(minutes=60)  # a run due longer ago (Studio closed or asleep) is recorded as missed
FILES_PER_SCAN = 5
IGNORED_SUFFIXES = (".tmp", ".part", ".crdownload", ".download", ".partial")


class AutomationTrigger(Model):
    kind: Literal["schedule", "workflow", "folder"] = "schedule"
    # schedule: the same timing as the flow scheduler
    schedule_kind: Literal["once", "daily", "weekly", "interval"] = "daily"
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(default="09:00", pattern=HOUR_MINUTE)
    days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], max_length=7)
    every_minutes: int = Field(default=60, ge=5, le=1440)
    until: str | None = Field(default=None, pattern=HOUR_MINUTE)
    # workflow: a flow run started by a person or the scheduler (never by an agent) finishes
    workflow_id: Identifier | None = None
    outcome: Literal["succeeded", "failed", "any"] = "any"
    # folder: a new, completely written file appears directly in the folder
    folder: str | None = Field(default=None, max_length=2000)
    pattern: str = Field(default="*", min_length=1, max_length=100)

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
        return self

    def timing(self) -> SimpleNamespace:
        return SimpleNamespace(kind=self.schedule_kind, date=self.date, time=self.time, days=self.days,
                               every_minutes=self.every_minutes, until=self.until)


class AutomationInput(Model):
    name: str = Field(min_length=1, max_length=120)
    agent_id: Identifier
    task: str = Field(min_length=1, max_length=16_000)
    inputs: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    trigger: AutomationTrigger = Field(default_factory=AutomationTrigger)

    @field_validator("inputs", mode="before")
    @classmethod
    def bounded_inputs(cls, value: Any) -> dict[str, Any]:
        return validate_inputs(value)


class Automation(AutomationInput):
    id: Identifier = Field(default_factory=uid)
    company_id: int = Field(ge=1)
    user_id: int = Field(ge=1)
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_run_id: Identifier | None = None
    last_status: Literal["started", "skipped", "missed", "error"] | None = None
    last_message: str | None = Field(default=None, max_length=500)
    recent_starts: list[str] = Field(default_factory=list, max_length=MAX_PER_HOUR + 1)
    known_files: list[str] = Field(default_factory=list, max_length=2000)
    pending_files: dict[str, int] = Field(default_factory=dict)


class AutomationBook(Model):
    automations: list[Automation] = Field(default_factory=list, max_length=500)


def describe(trigger: AutomationTrigger, workflow_name: str = "") -> str:
    if trigger.kind == "schedule":
        return summary(trigger.timing())
    if trigger.kind == "workflow":
        outcome = {"succeeded": "başarıyla bittiğinde", "failed": "hata verdiğinde", "any": "bittiğinde"}[trigger.outcome]
        return f"«{workflow_name or 'Seçilen akış'}» {outcome}"
    return f"{trigger.folder} klasörüne yeni {trigger.pattern} dosyası geldiğinde"


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


class AutomationService:
    def __init__(self, service, data_dir: Path | str, *, clock=datetime.now, interval: float = 15):
        self.service = service
        self.path = Path(data_dir) / "agent_automations.json"
        self.clock = clock
        self.interval = interval
        self._lock = threading.RLock()
        self._events: deque[dict] = deque(maxlen=200)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ----- storage ---------------------------------------------------------------------------
    def _read(self) -> AutomationBook:
        if not self.path.is_file():
            return AutomationBook()
        if self.path.stat().st_size > 8 * 1024 * 1024:
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

    # ----- management --------------------------------------------------------------------------
    def _check_body(self, body: AutomationInput, actor) -> None:
        self.service._find_agent(body.agent_id, actor)
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
        redactor = self.service._new_redactor()
        if any(redactor.contains_secret(text) for text in (body.name, body.task, json.dumps(body.inputs, ensure_ascii=False))):
            raise AgentServiceError("Otomasyon kayıtlı bir şifre veya anahtar içeremez.", 422)

    def _prepared(self, item: Automation) -> Automation:
        """Reset trigger state after a change so existing files and past times never fire."""
        moment = self.clock()
        item.pending_files = {}
        if item.trigger.kind == "schedule":
            due = next_occurrence(item.trigger.timing(), moment)
            item.next_run_at = due.isoformat(timespec="minutes") if due else None
        else:
            item.next_run_at = None
        if item.trigger.kind == "folder":
            try:
                item.known_files = sorted(_files(item.trigger.folder, item.trigger.pattern))[-2000:]
            except OSError:
                raise AgentServiceError("İzlenecek klasör okunamadı.", 422) from None
        else:
            item.known_files = []
        return item

    def view(self, item: Automation) -> dict:
        workflow_name = ""
        if item.trigger.workflow_id:
            try:
                workflow_name = self.service.store.workflow(item.trigger.workflow_id).name
            except (KeyError, ValueError):
                workflow_name = "Silinmiş akış"
        data = item.model_dump(exclude={"known_files", "pending_files", "recent_starts", "company_id"})
        data["summary"] = describe(item.trigger, workflow_name)
        return data

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
            book.automations.append(item)
            self._write(book)
            return self.view(item)

    def update(self, identity: str, body: AutomationInput) -> dict:
        actor = self.service._authorize("agents.manage")
        self._check_body(body, actor)

        def edit(item: Automation) -> Automation:
            changed = Automation(**{**item.model_dump(), **body.model_dump(), "updated_at": now()})
            return self._prepared(changed) if (changed.trigger != item.trigger or changed.enabled != item.enabled) else changed

        return self.view(self._change(identity, actor.company_id, edit))

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
        self._fire(item, {"tetikleyici": "elle"}, manual=True)
        with self._lock:
            return self.view(next(value for value in self._read().automations if value.id == identity))

    # ----- triggering ------------------------------------------------------------------------------
    def workflow_finished(self, run) -> None:
        """Called by the flow worker; keeps only metadata and returns at once."""
        if run.status not in {"succeeded", "failed"}:
            return
        self._events.append({"workflow_id": run.workflow_id, "status": run.status, "run_id": run.id,
                             "name": run.workflow_name, "error": (run.error or "")[:500]})
        self.poke()

    def poke(self) -> None:
        self._wake = True

    def _running(self, item: Automation) -> bool:
        if not item.last_run_id:
            return False
        try:
            return self.service.agent_store.run(item.last_run_id).status not in TERMINAL_STATUSES
        except (KeyError, ValueError):
            return False

    def _record(self, identity: str, **changes) -> None:
        def edit(item: Automation) -> Automation:
            return item.model_copy(update=changes)

        try:
            with self._lock:
                book = self._read()
                company = next((item.company_id for item in book.automations if item.id == identity), None)
            if company is not None:
                self._change(identity, company, edit)
        except AgentServiceError:
            pass

    def _fire(self, item: Automation, trigger_inputs: dict, *, manual: bool = False) -> None:
        moment = self.clock()
        stamp = moment.isoformat(timespec="seconds")
        hour_ago = (moment - timedelta(hours=1)).isoformat(timespec="seconds")
        recent = [value for value in item.recent_starts if value > hour_ago]
        if self._running(item):
            if manual:
                raise AgentServiceError("Bu otomasyonun önceki görevi henüz bitmedi.", 409)
            self._record(item.id, last_status="skipped", last_run_at=stamp,
                         last_message="Önceki görev sürdüğü için bu tetikleme atlandı.")
            return
        if len(recent) >= MAX_PER_HOUR:
            if manual:
                raise AgentServiceError("Bu otomasyon son bir saatte çok sık çalıştı; biraz bekleyin.", 429)
            self._record(item.id, last_status="skipped", last_run_at=stamp,
                         last_message=f"Bir saatte en fazla {MAX_PER_HOUR} kez çalışabilir; tetikleme atlandı.")
            return
        try:
            body = AgentRunRequest(task=item.task, title=f"Otomatik: {item.name}"[:200],
                                   inputs={**item.inputs, **trigger_inputs})
            run = self.service.start_automated(item.agent_id, body, {
                "automation_id": item.id, "name": item.name, "trigger": item.trigger.kind, "manual": manual})
        except (AgentServiceError, ValueError) as exc:
            if manual:
                raise
            self._record(item.id, last_status="error", last_run_at=stamp, last_message=str(exc)[:500])
            return
        self._record(item.id, last_status="started", last_run_at=stamp, last_run_id=run.id,
                     last_message="Görev başlatıldı.", recent_starts=[*recent, stamp][-MAX_PER_HOUR:])

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
            if trigger.kind == "schedule":
                self._schedule(item, moment)
            elif trigger.kind == "workflow":
                for event in events:
                    if event["workflow_id"] == trigger.workflow_id and trigger.outcome in {"any", event["status"]}:
                        self._fire(item, {"tetikleyen_akis": event["name"], "akis_durumu": event["status"],
                                          "akis_hatasi": event["error"], "akis_calisma_id": event["run_id"]})
            else:
                self._scan(item)

    def _schedule(self, item: Automation, moment: datetime) -> None:
        timing = item.trigger.timing()
        if not item.next_run_at:
            return
        due = datetime.fromisoformat(item.next_run_at)
        if moment < due:
            return
        following = next_occurrence(timing, moment)
        update = {"next_run_at": following.isoformat(timespec="minutes") if following else None}
        if following is None and item.trigger.schedule_kind == "once":
            update["enabled"] = False
        self._record(item.id, **update)
        if moment - due > MAX_DELAY:
            self._record(item.id, last_status="missed", last_run_at=moment.isoformat(timespec="seconds"),
                         last_message=f"{due.strftime('%d.%m.%Y %H:%M')} çalışması Studio kapalı olduğu için kaçırıldı.")
            return
        self._fire(item, {"tetikleme_zamani": due.isoformat(timespec="minutes")})

    def _scan(self, item: Automation) -> None:
        try:
            current = _files(item.trigger.folder, item.trigger.pattern)
        except OSError:
            if item.last_status != "error":
                self._record(item.id, last_status="error", last_message="İzlenen klasör okunamadı.")
            return
        known = set(item.known_files)
        # A file triggers only after two scans with the same size, so half-copied files are not handed over.
        ready = [name for name, size in sorted(current.items()) if name not in known and item.pending_files.get(name) == size]
        pending = {name: size for name, size in current.items() if name not in known and name not in ready[:FILES_PER_SCAN]}
        started = ready[:FILES_PER_SCAN]
        if pending != item.pending_files or started:
            self._record(item.id, pending_files=dict(list(pending.items())[:500]),
                         known_files=(item.known_files + started)[-2000:])
        folder = Path(item.trigger.folder).expanduser()
        for name in started:
            fresh = next((value for value in self._read().automations if value.id == item.id), item)
            self._fire(fresh, {"dosya_adi": name, "dosya_yolu": str(folder / name)})

    # ----- lifecycle -------------------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="rpa-agent-automations", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
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
