"""Atomic local workflow/run persistence. File paths never come from flow parameters."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from .catalog import library_catalog
from .config import atomic_json
from .models import Event, Run, Workflow, now


class Store:
    def __init__(self, root: Path):
        self.root = root
        self._lock = threading.RLock()
        for folder in ("workflows", "runs", "artifacts"):
            (root / folder).mkdir(parents=True, exist_ok=True)

    def path(self, kind: str, key: str) -> Path:
        if kind not in {"workflows", "runs"} or not re.fullmatch(r"[a-f0-9]{32}", key):
            raise KeyError(key)
        return self.root / kind / f"{key}.json"

    def favorites(self) -> list[str]:
        with self._lock:
            path = self.root / "favorites.json"
            if not path.exists():
                return []
            saved = json.loads(path.read_text(encoding="utf-8"))
            available = {entry["type"] for entry in library_catalog()}
            return list(dict.fromkeys(kind for kind in saved if kind in available))

    def set_favorite(self, action_type: str, favorite: bool) -> list[str]:
        if action_type not in {entry["type"] for entry in library_catalog()}:
            raise KeyError(action_type)
        with self._lock:
            favorites = self.favorites()
            if favorite and action_type not in favorites:
                favorites.append(action_type)
            elif not favorite and action_type in favorites:
                favorites.remove(action_type)
            atomic_json(self.root / "favorites.json", favorites)
            return favorites

    def save_workflow(self, workflow: Workflow) -> Workflow:
        with self._lock:
            atomic_json(self.path("workflows", workflow.id), workflow.model_dump())
        return workflow

    def workflows(self) -> list[Workflow]:
        with self._lock:
            return sorted(
                [Workflow.model_validate_json(p.read_text(encoding="utf-8"))
                 for p in (self.root / "workflows").glob("*.json")],
                key=lambda w: w.updated_at, reverse=True,
            )

    def workflow(self, key: str) -> Workflow:
        with self._lock:
            path = self.path("workflows", key)
            if not path.exists():
                raise KeyError(key)
            return Workflow.model_validate_json(path.read_text(encoding="utf-8"))

    def delete_workflow(self, key: str) -> None:
        with self._lock:
            path = self.path("workflows", key)
            if not path.exists():
                raise KeyError(key)
            path.unlink()

    def save_run(self, run: Run) -> None:
        with self._lock:
            atomic_json(self.path("runs", run.id), run.model_dump())

    def run(self, key: str) -> Run:
        with self._lock:
            path = self.path("runs", key)
            if not path.exists():
                raise KeyError(key)
            return Run.model_validate_json(path.read_text(encoding="utf-8"))

    def runs(self) -> list[Run]:
        with self._lock:
            return sorted(
                [Run.model_validate_json(p.read_text(encoding="utf-8"))
                 for p in (self.root / "runs").glob("*.json")],
                key=lambda r: r.started_at, reverse=True,
            )

    def recover_runs(self) -> None:
        for run in self.runs():
            if run.status in {"queued", "running"}:
                run.status = "failed"
                run.finished_at = now()
                run.error = "Uygulama kapandığı için çalışma kesildi. Yeniden başlatabilirsiniz."
                run.events.append(Event(level="error", message=run.error))
                self.save_run(run)
