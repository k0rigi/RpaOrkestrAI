from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def uid() -> str:
    return uuid4().hex


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Step(Model):
    id: str = Field(default_factory=uid, pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    title: str = Field(default="", max_length=200)
    action: str = Field(max_length=100)
    params: dict[str, Any] = Field(default_factory=dict)
    children: list[Step] = Field(default_factory=list)
    otherwise: list[Step] = Field(default_factory=list)


class WorkflowInput(Model):
    name: str = Field(default="Yeni akış", min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    department: str = Field(default="Genel", min_length=1, max_length=120)
    steps: list[Step] = Field(default_factory=list)

    @model_validator(mode="after")
    def bounded_tree(self) -> WorkflowInput:
        seen: set[str] = set()

        def walk(steps: list[Step], depth: int) -> None:
            if depth > 8:
                raise ValueError("Akış en fazla 8 seviyede iç içe olabilir.")
            for step in steps:
                if step.id in seen:
                    raise ValueError("Adım kimlikleri benzersiz olmalıdır.")
                seen.add(step.id)
                if len(seen) > 200:
                    raise ValueError("Bir akışta en fazla 200 adım olabilir.")
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


class StepTestRequest(Model):
    variables: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False


class LicenseLoginRequest(Model):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=256)


class FavoriteRequest(Model):
    favorite: bool = Field(strict=True)


class WindowCheckRequest(Model):
    application: str = Field(default="", max_length=200)
    title: str = Field(min_length=1, max_length=500)
    match: Literal["exact", "contains"] = "exact"


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
