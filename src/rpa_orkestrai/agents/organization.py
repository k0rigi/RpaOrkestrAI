"""Tek yönetici, doğrudan departman ilişkileri ve ortak görev bütçesi."""

from __future__ import annotations

import threading
import time


class OrganizationError(ValueError):
    pass


class BudgetExceeded(ValueError):
    pass


def validate_organization(body, actor, store, *, identity=None) -> None:
    company = [agent for agent in store.agents() if agent.company_id == actor.company_id]
    if body.role == "manager":
        if any(agent.role == "manager" and agent.id != identity for agent in company):
            raise OrganizationError("Bir firmada yalnız bir yönetici ajan bulunabilir.")
    elif identity and any(agent.manager_id == identity for agent in company):
        raise OrganizationError("Bağlı departmanlar varken yönetici ajan departmana dönüştürülemez.")
    if body.manager_id:
        parent = next((agent for agent in company if agent.id == body.manager_id), None)
        if parent is None or parent.role != "manager" or parent.id == identity:
            raise OrganizationError("Departman ajanı yalnız aynı firmanın yönetici ajanına bağlanabilir.")


class TeamBudget:
    """All children consume one root budget; reservations prevent concurrent over-allocation."""

    def __init__(self, limits, deadline: float):
        self.limits = limits.model_copy(deep=True)
        self.deadline = deadline
        self.lock = threading.RLock()
        self.turns = self.workflows = self.tasks = self.tokens_in = self.tokens_out = 0
        self.reserved: dict[str, int] = {}
        self.reason: str | None = None

    def _fail(self, message):
        self.reason = message
        raise BudgetExceeded(message)

    def check(self):
        with self.lock:
            if self.reason:
                raise BudgetExceeded(self.reason)
            if time.monotonic() >= self.deadline:
                self._fail("Ekibin azami çalışma süresi doldu.")

    def reserve_turn(self, identity: str, requested: int) -> int | None:
        with self.lock:
            self.check()
            if self.turns >= self.limits.max_turns:
                self._fail("Ekibin toplam tur sınırına ulaşıldı.")
            remaining = self.limits.max_tokens - self.tokens_in - self.tokens_out
            if remaining <= 0:
                self._fail("Ekibin toplam token sınırına ulaşıldı.")
            available = remaining - sum(self.reserved.values())
            if available <= 0:
                return None
            # Thinking models spend part of the answer room on reasoning; 8K leaves space for the reply itself.
            allowance = min(requested, available, 8192)
            if allowance <= 0:
                self._fail("Ajanın token sınırına ulaşıldı.")
            self.reserved[identity] = allowance
            self.turns += 1
            return allowance

    def release_turn(self, identity: str, usage=None) -> None:
        with self.lock:
            self.reserved.pop(identity, None)
            if usage is not None:
                self.tokens_in += usage.input_tokens
                self.tokens_out += usage.output_tokens
                if self.tokens_in + self.tokens_out > self.limits.max_tokens:
                    self._fail("Ekibin toplam token sınırı aşıldı; yeni araç çalıştırılmadı.")

    def add_task(self) -> None:
        with self.lock:
            self.check()
            if self.tasks >= self.limits.max_tasks:
                self._fail("Ekibin toplam alt görev sınırına ulaşıldı.")
            self.tasks += 1

    def add_workflow(self) -> None:
        with self.lock:
            self.check()
            if self.workflows >= self.limits.max_workflow_runs:
                self._fail("Ekibin toplam akış çalıştırma sınırına ulaşıldı.")
            self.workflows += 1

    def snapshot(self) -> dict:
        with self.lock:
            return {"turns": self.turns, "workflow_count": self.workflows, "task_count": self.tasks,
                    "tokens_in": self.tokens_in, "tokens_out": self.tokens_out,
                    "total_tokens": self.tokens_in + self.tokens_out}
