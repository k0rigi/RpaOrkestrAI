"""Ajan kayıtları için atomik, kilitli ve sabit dizinli yerel depolama."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import TypeVar

from ..config import atomic_json
from ..models import Model, now
from .models import TERMINAL_STATUSES, Agent, AgentEvent, AgentRun, AgentTask

Record = TypeVar("Record", bound=Model)
MAX_RECORD_BYTES = 8 * 1024 * 1024


class AgentStore:
    _locks: dict[str, threading.RLock] = {}
    _locks_guard = threading.Lock()
    _folders = frozenset({"agents", "agent_runs", "agent_tasks"})

    def __init__(self, root: Path | str):
        candidate = Path(root).expanduser().absolute()
        if candidate.is_symlink():
            raise ValueError("Ajan veri dizini sembolik bağlantı olamaz.")
        candidate.mkdir(parents=True, exist_ok=True)
        self.root = candidate.resolve()
        with self._locks_guard:
            self._lock = self._locks.setdefault(str(self.root), threading.RLock())
        with self._lock:
            for folder in self._folders:
                self._folder(folder).mkdir(exist_ok=True)

    def _folder(self, kind: str) -> Path:
        if kind not in self._folders:
            raise KeyError("Ajan kayıt türü bulunamadı.")
        folder = self.root / kind
        if self.root.is_symlink() or folder.is_symlink():
            raise ValueError("Ajan kayıt dizini sembolik bağlantı olamaz.")
        if folder.resolve().parent != self.root:
            raise ValueError("Ajan kayıt dizini çalışma alanı dışında olamaz.")
        return folder

    def path(self, kind: str, key: str) -> Path:
        if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{32}", key):
            raise KeyError("Ajan kayıt kimliği geçersiz.")
        path = self._folder(kind) / f"{key}.json"
        if path.is_symlink() or path.with_suffix(".tmp").is_symlink():
            raise ValueError("Ajan kaydı sembolik bağlantı olamaz.")
        return path

    def _save(self, kind: str, record: Record, model: type[Record]) -> Record:
        # Revalidate mutable records: model_copy(update=...) intentionally skips validation.
        copy = model.model_validate(record.model_dump())
        data = copy.model_dump(mode="json")
        if len(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")) > MAX_RECORD_BYTES:
            raise ValueError("Ajan kaydı izin verilen boyutu aşıyor.")
        with self._lock:
            atomic_json(self.path(kind, copy.id), data)
        return copy.model_copy(deep=True)

    def _read(self, kind: str, key: str, model: type[Record]) -> Record:
        with self._lock:
            path = self.path(kind, key)
            if not path.is_file():
                raise KeyError(key)
            if path.stat().st_size > MAX_RECORD_BYTES:
                raise ValueError("Ajan kaydı izin verilen boyutu aşıyor.")
            with path.open("rb") as handle:
                content = handle.read(MAX_RECORD_BYTES + 1)
            if len(content) > MAX_RECORD_BYTES:
                raise ValueError("Ajan kaydı izin verilen boyutu aşıyor.")
            try:
                record = model.model_validate_json(content)
            except ValueError:
                raise ValueError("Ajan kaydı okunamadı; kayıt biçimi geçersiz.") from None
            if record.id != key:
                raise ValueError("Ajan kaydının kimliği dosyasıyla eşleşmiyor.")
            return record

    def _list(self, kind: str, model: type[Record], order: str) -> list[Record]:
        with self._lock:
            records = [self._read(kind, path.stem, model) for path in self._folder(kind).glob("*.json")]
            return sorted(records, key=lambda record: getattr(record, order), reverse=True)

    def save_agent(self, agent: Agent) -> Agent:
        return self._save("agents", agent, Agent)

    def agent(self, key: str) -> Agent:
        return self._read("agents", key, Agent)

    def agents(self) -> list[Agent]:
        return self._list("agents", Agent, "updated_at")

    def delete_agent(self, key: str) -> None:
        with self._lock:
            path = self.path("agents", key)
            if not path.is_file():
                raise KeyError(key)
            path.unlink()

    def save_run(self, run: AgentRun) -> AgentRun:
        return self._save("agent_runs", run, AgentRun)

    def run(self, key: str) -> AgentRun:
        return self._read("agent_runs", key, AgentRun)

    def runs(self) -> list[AgentRun]:
        return self._list("agent_runs", AgentRun, "created_at")

    def save_task(self, task: AgentTask) -> AgentTask:
        return self._save("agent_tasks", task, AgentTask)

    def task(self, key: str) -> AgentTask:
        return self._read("agent_tasks", key, AgentTask)

    def tasks(self) -> list[AgentTask]:
        return self._list("agent_tasks", AgentTask, "created_at")

    def recover_runs(self) -> None:
        """An interrupted approval or execution never silently becomes a new attempt."""
        message = "Studio kapandığı için çalışma kesildi. Bekleyen onaylar geçersiz kılındı."
        with self._lock:
            recovered = {}
            for run in self.runs():
                if run.status not in TERMINAL_STATUSES:
                    run.status = "failed"
                    run.finished_at = now()
                    run.error = message
                    run.pending_approval = None
                    run.pending_question = None
                    run.events = [*run.events[-1999:], AgentEvent(kind="interrupted", message=message)]
                    self.save_run(run)
                recovered[run.id] = run
            for task in self.tasks():
                # Human tasks survive a Studio restart; only local agent execution was interrupted.
                if task.assignee_type != "agent":
                    continue
                run = recovered.get(task.run_id)
                if (run and run.actor.company_id == task.company_id and run.task_id == task.id
                        and run.agent_id == task.assigned_agent_id):
                    # A crash between the two atomic writes is repaired from the execution record.
                    for name in ("status", "started_at", "finished_at", "workflow_run_ids", "tokens_in", "tokens_out",
                                 "total_tokens", "approval_wait_seconds", "summary", "result", "error"):
                        setattr(task, name, getattr(run, name))
                    task.events = [event for event in run.events if event.kind in {
                        "created", "workflow_started", "question", "user_answer", "approval_requested",
                        "approval_decision", "approval_consumed", "approval_expired", "task_delegated", "interrupted",
                    }]
                    task.approvals = [event for event in task.events if event.kind.startswith("approval_")]
                    self.save_task(task)
                elif task.status not in TERMINAL_STATUSES:
                    task.status = "failed"
                    task.finished_at = now()
                    task.summary = message
                    self.save_task(task)
