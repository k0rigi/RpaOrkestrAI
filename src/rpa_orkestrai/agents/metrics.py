"""Görev kayıtlarından hesaplanan performans; bağımsız sayaç tutulmaz."""

from __future__ import annotations

import csv
import io
import threading
from datetime import datetime, timedelta, timezone

from pydantic import Field, model_validator

from ..config import atomic_json
from ..models import Model
from .models import TERMINAL_STATUSES, Identifier


def timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ValueError("Tarih saat dilimi içeren ISO biçiminde olmalıdır.") from None


def interval(start: str, end: str) -> tuple[datetime, datetime]:
    first, last = timestamp(start), timestamp(end)
    if not first < last or last - first > timedelta(days=366):
        raise ValueError("Tarih aralığı sıfırdan büyük ve en fazla 366 gün olmalıdır.")
    return first, last


class ModelPrice(Model):
    connection_id: Identifier
    model: str = Field(min_length=1, max_length=200)
    input_per_million: float = Field(ge=0, le=1_000_000)
    output_per_million: float = Field(ge=0, le=1_000_000)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class MetricSettings(Model):
    prices: list[ModelPrice] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def unique(self):
        keys = [(row.connection_id, row.model) for row in self.prices]
        if len(keys) != len(set(keys)):
            raise ValueError("Bağlantı ve model için yalnız bir fiyat tanımlanabilir.")
        return self


class MetricSettingsStore:
    def __init__(self, root):
        self.root = root.resolve()
        self.lock = threading.RLock()

    def path(self, company_id):
        if type(company_id) is not int or company_id < 1:
            raise ValueError("Firma kimliği geçersiz.")
        path = self.root / ("agent_metrics_" + str(company_id) + ".json")
        if self.root.is_symlink() or path.is_symlink() or path.with_suffix(".tmp").is_symlink():
            raise ValueError("Performans ayarları sembolik bağlantı olamaz.")
        return path

    def get(self, company_id):
        with self.lock:
            path = self.path(company_id)
            if not path.exists():
                return MetricSettings()
            if path.stat().st_size > 256 * 1024:
                raise ValueError("Performans ayarları boyut sınırını aşıyor.")
            return MetricSettings.model_validate_json(path.read_bytes())

    def save(self, company_id, value):
        checked = MetricSettings.model_validate(value.model_dump())
        with self.lock:
            atomic_json(self.path(company_id), checked.model_dump(mode="json"))
        return checked


def _empty():
    return dict(total=0, succeeded=0, failed=0, cancelled=0, terminal=0, success_rate=0.0,
                total_seconds=0.0, average_seconds=0.0, duration_missing_count=0,
                workflow_count=0, approval_count=0, approval_wait_seconds=0.0,
                tokens_in=0, tokens_out=0, total_tokens=0, unpriced_tasks=0, estimated_cost={})


def calculate(tasks, *, company_id: int, start: str, end: str, settings=None):
    first, last = interval(start, end)
    prices = {(p.connection_id, p.model): p for p in (settings or MetricSettings()).prices}
    totals, agents, departments = _empty(), {}, {}
    for task in tasks:
        if task.company_id != company_id or task.assignee_type != "agent":
            continue
        if not first <= timestamp(task.created_at) < last:
            continue
        group = agents.setdefault(task.assignee_id, {"id": task.assignee_id, "name": task.agent_name,
                                                    "department": task.department, **_empty()})
        department = departments.setdefault(task.department, {"name": task.department, **_empty()})
        duration, missing = 0.0, False
        if task.status in TERMINAL_STATUSES:
            if task.started_at and task.finished_at:
                duration = max(0.0, (timestamp(task.finished_at) - timestamp(task.started_at)).total_seconds())
            else:
                missing = True
        price = prices.get((task.provider_connection_id, task.model))
        for row in (totals, group, department):
            row["total"] += 1
            if task.status in TERMINAL_STATUSES:
                row[task.status] += 1
                row["terminal"] += 1
            row["duration_missing_count"] += int(missing)
            row["total_seconds"] += duration
            row["workflow_count"] += len(task.workflow_run_ids)
            row["approval_count"] += sum(event.kind == "approval_requested" for event in task.approvals)
            row["approval_wait_seconds"] += task.approval_wait_seconds
            for key in ("tokens_in", "tokens_out", "total_tokens"):
                row[key] += getattr(task, key)
            if price:
                cost = (task.tokens_in * price.input_per_million + task.tokens_out * price.output_per_million) / 1e6
                costs = row["estimated_cost"]
                costs[price.currency] = costs.get(price.currency, 0.0) + cost
            elif task.total_tokens:
                row["unpriced_tasks"] += 1
    for row in [totals, *agents.values(), *departments.values()]:
        count = row["terminal"]
        row["success_rate"] = row["succeeded"] / count if count else 0.0
        row["average_seconds"] = row["total_seconds"] / count if count else 0.0
        row["estimated_cost"] = {key: round(value, 8) for key, value in row["estimated_cost"].items()}
    def ranking(rows):
        return sorted(rows, key=lambda row: (-row["succeeded"], row["name"], row.get("id", "")))

    return {"start": first.isoformat(), "end": last.isoformat(), "range_basis": "created_at", "totals": totals,
            "agents": ranking(agents.values()), "departments": ranking(departments.values()),
            "cost_basis": "current_configured_prices", "scope": "local_agent_tasks"}


def csv_export(metrics):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["Tür", "Ad", "Departman", "Toplam", "Tamamlanan", "Başarısız", "İptal", "Başarı oranı",
                     "Toplam saniye", "Ortalama saniye", "Akış", "Onay", "Onay bekleme saniye", "Token",
                     "Tahmini maliyet", "Fiyatı eksik görev"])

    def safe(value):
        value = str(value)
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")) else value

    for kind, rows in (("Ajan", metrics["agents"]), ("Departman", metrics["departments"])):
        for row in rows:
            writer.writerow([kind, safe(row["name"]), safe(row.get("department", "")), row["total"], row["succeeded"],
                             row["failed"], row["cancelled"], row["success_rate"], row["total_seconds"],
                             row["average_seconds"], row["workflow_count"], row["approval_count"],
                             row["approval_wait_seconds"], row["total_tokens"],
                             "; ".join(f"{amount:.8f} {currency}" for currency, amount in row["estimated_cost"].items()),
                             row["unpriced_tasks"]])
    return "\ufeff" + stream.getvalue()
