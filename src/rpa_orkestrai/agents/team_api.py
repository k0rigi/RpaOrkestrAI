"""İnsan görevleri ve kurum onaylarını Studio'daki lisans kapısına bağlar."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from ..models import Model
from .central import RESPONSE_LIMIT, CentralError, record_id
from .models import Identifier, validate_json_value
from .runner import AgentServiceError


class TaskInput(Model):
    request_id: Identifier
    title: str = Field(min_length=1, max_length=160)
    instructions: str = Field(min_length=1, max_length=16_000)
    assignee_user_id: int = Field(ge=1, strict=True)
    priority: Literal["low", "normal", "high"] = "normal"


class TaskTransition(Model):
    status: Literal["queued", "running", "waiting_user", "succeeded", "failed", "cancelled"]
    expected_version: int = Field(ge=1, strict=True)
    summary: str = Field(default="", max_length=4000)


class TaskAssignment(Model):
    assignee_user_id: int = Field(ge=1, strict=True)
    expected_version: int = Field(ge=1, strict=True)


class Decision(Model):
    approved: bool = Field(strict=True)


def router(service, client, approval_backend):
    result = APIRouter(prefix="/api/agents/central", tags=["Kurum görevleri"])

    def call(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except AgentServiceError as exc:
            raise HTTPException(exc.status_code, str(exc)) from None
        except CentralError as exc:
            raise HTTPException(exc.status, str(exc)) from None
        except (KeyError, ValueError, TypeError):
            raise HTTPException(422, "Kurum görev kaydı doğrulanamadı.") from None

    def request(method, path, body=None, *, permission="agents.use"):
        actor = service._authorize(permission)
        redactor = service._new_redactor()
        # This is a user-authored task, not a model excerpt: reject oversize data instead of truncating it.
        redactor.max_bytes = RESPONSE_LIMIT * 16
        redactor.max_string = RESPONSE_LIMIT * 4
        # Local protected values never become central task descriptions or approval text.
        safe_body = None if body is None else redactor.sanitize(body)
        if safe_body is not None:
            validate_json_value(safe_body, max_bytes=64 * 1024)
        answer = client.request(method, path, safe_body, expected_actor=actor)
        answer = redactor.sanitize(answer)
        validate_json_value(answer, max_bytes=RESPONSE_LIMIT)
        return answer

    @result.get("/members")
    def members():
        return call(request, "GET", "/uyeler")

    @result.get("/office")
    def office():
        from .office import human_snapshot

        # Explicit projection prevents future central fields from leaking into the public scene.
        return call(human_snapshot, call(request, "GET", "/ofis"))

    @result.get("/tasks")
    def tasks():
        return call(request, "GET", "/gorevler")

    @result.post("/tasks", status_code=201)
    def create_task(body: TaskInput):
        return call(request, "POST", "/gorevler", body.model_dump(), permission="agents.manage")

    @result.get("/tasks/{task_id}")
    def get_task(task_id: str):
        return call(lambda: request("GET", "/gorevler/" + record_id(task_id)))

    @result.post("/tasks/{task_id}/status")
    def change_task(task_id: str, body: TaskTransition):
        return call(lambda: request("POST", "/gorevler/" + record_id(task_id) + "/durum", body.model_dump()))

    @result.post("/tasks/{task_id}/assign")
    def assign_task(task_id: str, body: TaskAssignment):
        return call(lambda: request("POST", "/gorevler/" + record_id(task_id) + "/ata", body.model_dump(),
                                    permission="agents.manage"))

    @result.get("/approvals")
    def approvals():
        return call(request, "GET", "/onaylar")

    @result.get("/approvals/{approval_id}")
    def get_approval(approval_id: str):
        return call(lambda: request("GET", "/onaylar/" + record_id(approval_id)))

    @result.post("/approvals/{approval_id}/decision")
    def decide(approval_id: str, body: Decision):
        call(service._authorize, "agents.approve")
        return {"approval": call(approval_backend.decide, approval_id, body.approved)}

    @result.get("/models")
    def models():
        return call(request, "GET", "/llm/models")

    @result.get("/metrics")
    def metrics(start: str = Query(max_length=40), end: str = Query(max_length=40)):
        from .metrics import interval

        first, last = call(interval, start, end)
        return call(request, "GET", "/metrics?" + urlencode({"start": first.isoformat(), "end": last.isoformat()}))

    return result
