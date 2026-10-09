from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def uid() -> str:
    return uuid4().hex


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


# Parameters that hold the *name* a step gives to its result; "name" only for these two steps.
NAME_PARAMETERS = ("output", "item_name", "error_name")
NAMING_ACTIONS = {"core.set", "data.append"}
WRAPPED_NAME = re.compile(r"\$\{\s*([A-Za-z][A-Za-z0-9_]*)\s*\}")


class Step(Model):
    id: str = Field(default_factory=uid, pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    title: str = Field(default="", max_length=200)
    action: str = Field(max_length=100)
    params: dict[str, Any] = Field(default_factory=dict)
    children: list[Step] = Field(default_factory=list)
    otherwise: list[Step] = Field(default_factory=list)
    # Where the user dragged the box in the diagram, relative to its automatic place: [dx, dy].
    offset: tuple[float, float] | None = None

    @model_validator(mode="after")
    def earlier_wait_choice(self) -> Step:
        # Dosya / script çalıştır in 0.9.2 had a yes/no box; it is now auto / wait / no.
        if self.action == "system.run_file" and isinstance(self.params.get("wait_finish"), bool):
            self.params["wait_finish"] = "wait" if self.params["wait_finish"] else "no"
        return self

    @field_validator("offset")
    @classmethod
    def bounded_offset(cls, value: tuple[float, float] | None) -> tuple[float, float] | None:
        if value is not None and any(abs(part) > 5000 for part in value):
            raise ValueError("Kutu konumu geçerli aralıkta olmalıdır.")
        return value

    @model_validator(mode="after")
    def bare_result_names(self) -> Step:
        """A name typed the way it is later used (${erp_window}) means the name itself (erp_window)."""
        keys = (*NAME_PARAMETERS, "name") if self.action in NAMING_ACTIONS else NAME_PARAMETERS
        for key in keys:
            value = self.params.get(key)
            if isinstance(value, str):
                wrapped = WRAPPED_NAME.fullmatch(value.strip())
                self.params[key] = wrapped.group(1) if wrapped else value.strip()
        return self


def walk_steps(steps: list[Step]):
    for step in steps:
        yield step
        yield from walk_steps(step.children)
        yield from walk_steps(step.otherwise)


# The editor checks the same nesting limit before a step is placed (MAX_DEPTH in static/app.js).
MAX_DEPTH = 8
MAX_STEPS = 200


class Note(Model):
    """A note over part of a flow, drawn around its steps; a run ignores it."""

    id: str = Field(default_factory=uid, pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    title: str = Field(default="Not", max_length=120)
    text: str = Field(default="", max_length=4000)
    color: Literal["yellow", "blue", "green", "pink", "gray"] = "yellow"
    steps: list[str] = Field(default_factory=list, max_length=MAX_STEPS)


class WorkflowInput(Model):
    name: str = Field(default="Yeni akış", min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    department: str = Field(default="Genel", min_length=1, max_length=120)
    steps: list[Step] = Field(default_factory=list)
    notes: list[Note] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def notes_on_existing_steps(self) -> WorkflowInput:
        # A note keeps only the steps the flow still has; one left without steps goes with them.
        present = {step.id for step in walk_steps(self.steps)}
        kept = []
        for note in self.notes:
            steps = [step_id for step_id in dict.fromkeys(note.steps) if step_id in present]
            if steps:
                kept.append(note if steps == note.steps else note.model_copy(update={"steps": steps}))
        self.notes = kept
        return self

    @model_validator(mode="after")
    def bounded_tree(self) -> WorkflowInput:
        seen: set[str] = set()

        def walk(steps: list[Step], depth: int) -> None:
            if depth > MAX_DEPTH:
                raise ValueError(f"Akış en fazla {MAX_DEPTH} seviyede iç içe olabilir.")
            for step in steps:
                if step.id in seen:
                    raise ValueError("Adım kimlikleri benzersiz olmalıdır.")
                seen.add(step.id)
                if len(seen) > MAX_STEPS:
                    raise ValueError(f"Bir akışta en fazla {MAX_STEPS} adım olabilir.")
                if step.children or step.otherwise:
                    from .catalog import CONTAINERS

                    branches = CONTAINERS.get(step.action, ())
                    if not branches:
                        raise ValueError("Yalnız döngü, koşul ve hata yakalama adımları alt adım içerebilir.")
                    if step.otherwise and "otherwise" not in branches:
                        raise ValueError("İkinci dal yalnız koşul ve hata yakalama adımlarında kullanılabilir.")
                    walk(step.children, depth + 1)
                    walk(step.otherwise, depth + 1)

        walk(self.steps, 1)
        return self


class Workflow(WorkflowInput):
    id: str = Field(default_factory=uid, pattern=r"^[a-f0-9]{32}$")
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)


class WorkflowImport(WorkflowInput):
    """A flow file from any Studio: its identity is replaced, its reference images are saved."""

    id: str | None = Field(default=None, max_length=100)
    created_at: str | None = Field(default=None, max_length=100)
    updated_at: str | None = Field(default=None, max_length=100)
    # Reference image name (as the steps use it) → base64 PNG or JPEG; see template_bundle.py.
    templates: dict[str, str] = Field(default_factory=dict, max_length=500)


class Event(Model):
    timestamp: str = Field(default_factory=now)
    level: str = "info"
    message: str
    step_id: str | None = None


class Artifact(Model):
    id: str = Field(default_factory=uid)
    name: str
    department: str
    rows: int
    url: str = ""


class Run(Model):
    id: str = Field(default_factory=uid, pattern=r"^[a-f0-9]{32}$")
    workflow_id: str
    workflow_name: str
    department: str
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"] = "queued"
    dry_run: bool = False
    started_at: str = Field(default_factory=now)
    finished_at: str | None = None
    events: list[Event] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    error: str | None = None
    # A single-step test records the step and the variables it left behind.
    test_step_id: str | None = None
    variables: dict[str, Any] | None = None
    # step id → {"runs", "ok", "errors", "skipped"}: shown on the diagram after a run.
    step_stats: dict[str, dict[str, int]] = Field(default_factory=dict)
    # Who started it: a person in the Studio or the scheduler.
    trigger: Literal["manual", "schedule"] = "manual"


HOUR_MINUTE = r"^([01]\d|2[0-3]):[0-5]\d$"


class ScheduleInput(Model):
    """When a flow runs by itself: once, daily, on some weekdays, or every N minutes."""

    workflow_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    enabled: bool = True
    kind: Literal["once", "daily", "weekly", "interval"] = "daily"
    date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")  # once
    time: str = Field(default="09:00", pattern=HOUR_MINUTE)  # once, daily, weekly; interval: window start
    days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], max_length=7)  # 0 Monday … 6 Sunday
    every_minutes: int = Field(default=60, ge=1, le=1440)  # interval
    until: str | None = Field(default=None, pattern=HOUR_MINUTE)  # interval: window end, none = midnight
    # Like the Task Scheduler option: a run missed while the Studio was closed runs once when it opens.
    catch_up: bool = False
    # When flows meet: who goes first, how late a waiting run may still start, and how long a run may take.
    priority: Literal["high", "normal", "low"] = "normal"
    max_delay: int = Field(default=60, ge=1, le=1440)  # minutes; a run that would start later is skipped
    max_duration: int = Field(default=0, ge=0, le=1440)  # minutes; 0 = no limit, otherwise the run is stopped

    @model_validator(mode="after")
    def consistent(self) -> ScheduleInput:
        if any(day not in range(7) for day in self.days) or len(set(self.days)) != len(self.days):
            raise ValueError("Günler 0 (Pazartesi) ile 6 (Pazar) arasında ve tekrarsız olmalıdır.")
        if self.kind == "once" and not self.date:
            raise ValueError("Bir kez çalışacak zamanlama için tarih gereklidir.")
        if self.date is not None:
            try:
                datetime.strptime(self.date, "%Y-%m-%d")
            except ValueError:
                raise ValueError("Geçerli bir tarih girin.") from None
        if self.kind in {"weekly", "interval"} and not self.days:
            raise ValueError("En az bir gün seçin.")
        if self.kind == "interval" and self.until is not None and self.until <= self.time:
            raise ValueError("Saat aralığının bitişi başlangıcından sonra olmalıdır.")
        return self


class Schedule(ScheduleInput):
    id: str = Field(default_factory=uid, pattern=r"^[a-f0-9]{32}$")
    created_at: str = Field(default_factory=now)
    # The next time it is due, kept so a run missed while the Studio was closed can be noticed.
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_run_id: str | None = None
    last_status: Literal["started", "skipped", "missed", "cancelled", "error", "stopped"] | None = None
    last_message: str | None = Field(default=None, max_length=500)


class ScheduleSettings(Model):
    # Seconds the Studio shows "starting soon" (with Cancel) before a scheduled run takes the screen.
    countdown: int = Field(default=10, ge=0, le=120)


class AutostartRequest(Model):
    enabled: bool


class SecretRequest(Model):
    value: str = Field(min_length=1, max_length=1000)


class RunRequest(Model):
    dry_run: bool = False


class PointerRequest(Model):
    delay: int = Field(default=3, ge=1, le=10, strict=True)


class RecordRequest(Model):
    delay: int = Field(default=3, ge=1, le=10, strict=True)
    record_waits: bool = True
    relative_windows: bool = True


class PathRequest(Model):
    kind: Literal["open", "folder", "save"] = "open"
    preserve_shortcuts: bool = False


class StepTestRequest(Model):
    variables: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False
    # Only move the pointer to the step's target; nothing is clicked or typed.
    locate: bool = False


class LicenseLoginRequest(Model):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=256)


class FavoriteRequest(Model):
    favorite: bool = Field(strict=True)


class WindowCheckRequest(Model):
    application: str = Field(default="", max_length=200)
    title: str = Field(min_length=1, max_length=500)
    match: Literal["exact", "contains"] = "exact"


class TableInspectRequest(WindowCheckRequest):
    x: int = Field(ge=0, le=20000, strict=True)
    y: int = Field(ge=0, le=20000, strict=True)
    header: bool = True
    header_row: int = Field(default=1, ge=1, le=10000, strict=True)
    window_id: int = Field(gt=0, strict=True)
    pid: int = Field(gt=0, strict=True)
    width: int = Field(gt=0, le=20000, strict=True)
    height: int = Field(gt=0, le=20000, strict=True)


class TemplateCropRequest(Model):
    capture_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    x: int = Field(ge=0, strict=True)
    y: int = Field(ge=0, strict=True)
    width: int = Field(ge=8, le=4000, strict=True)
    height: int = Field(ge=8, le=4000, strict=True)


class DesktopPickRequest(WindowCheckRequest):
    mode: Literal["coordinates", "image", "image_only"] = "coordinates"
    delay: int = Field(default=5, ge=3, le=10, strict=True)

    @model_validator(mode="after")
    def supported_delay(self):
        if self.delay not in {3, 5, 10}:
            raise ValueError("Geri sayım 3, 5 veya 10 saniye olmalıdır.")
        return self
