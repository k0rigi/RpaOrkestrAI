"""Bitmiş ajan çalışmalarından süreç kartı istatistikleri ve insana bırakılan işler.

Çalışma kayıtları bir kez okunur; sonra her biten çalışma eklenir. Bir görev silinince özet yeniden kurulur.
"""

from __future__ import annotations

import threading
from collections import Counter
from datetime import datetime, timedelta, timezone

HANDOFF_DAYS = 14
NO_CARD = "kartsiz"


class RunInsights:
    def __init__(self, store):
        self.store = store
        self._lock = threading.RLock()
        self._ready = False
        self._stats: dict[str, dict[str, Counter]] = {}
        self._handoffs: dict[str, dict] = {}
        self._seen: set[str] = set()

    def _load(self):
        if self._ready:
            return
        self._stats, self._handoffs, self._seen = {}, {}, set()
        for run in self.store.runs():
            if run.finished_at:
                self._absorb(run)
        self._ready = True

    def _absorb(self, run):
        if run.id in self._seen:
            return
        self._seen.add(run.id)
        agent = self._stats.setdefault(run.agent_id, {})
        for event in run.events:
            data = event.data or {}
            card = data.get("playbook_id") or NO_CARD
            if event.kind == "approval_decision" and type(data.get("approved")) is bool:
                key = "edited" if data.get("edited") else "approved" if data["approved"] else "rejected"
                agent.setdefault(card, Counter())[key] += 1
            elif event.kind == "approval_expired":
                agent.setdefault(card, Counter())["expired"] += 1
        if run.handoff:
            agent.setdefault(run.playbook_id or NO_CARD, Counter())["handoffs"] += 1
            if not run.handoff_resolved_at:
                self._handoffs[run.id] = {"run_id": run.id, "agent_id": run.agent_id, "company_id": run.actor.company_id,
                                          "office_id": run.office_id, "user_id": run.actor.user_id,
                                          "title": run.title or run.task[:200], "finished_at": run.finished_at,
                                          "summary": run.summary[:500]}

    def record(self, run):
        with self._lock:
            if self._ready and run.finished_at:
                self._absorb(run)

    def resolved(self, run_id):
        with self._lock:
            self._handoffs.pop(run_id, None)

    def reset(self):
        with self._lock:
            self._ready = False

    def stats(self, agent_id) -> dict[str, dict[str, int]]:
        with self._lock:
            self._load()
            return {card: dict(counter) for card, counter in self._stats.get(agent_id, {}).items()}

    def handoffs(self, company_id) -> list[dict]:
        limit = datetime.now(timezone.utc) - timedelta(days=HANDOFF_DAYS)
        with self._lock:
            self._load()
            items = []
            for item in self._handoffs.values():
                try:
                    finished = datetime.fromisoformat(item["finished_at"])
                except (TypeError, ValueError):
                    continue
                if finished.tzinfo is None:
                    finished = finished.replace(tzinfo=timezone.utc)
                if item["company_id"] == company_id and finished >= limit:
                    items.append(dict(item))
        return sorted(items, key=lambda item: item["finished_at"], reverse=True)
