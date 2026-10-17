"""Mevcut lisans ve kaynak denetiminin arkasında kalan ajan API uçları."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import Field, field_validator

from ..models import Model
from .models import AgentInput, AgentRunRequest, NoteInput, validate_json_value
from .runner import AgentService, AgentServiceError


class AnswerRequest(Model):
    answer: Any

    @field_validator("answer", mode="before")
    @classmethod
    def bounded_answer(cls, value):
        return validate_json_value(value)


class ApprovalRequest(Model):
    approved: bool = Field(strict=True)
    # Only with an approval: the approver's edited draft (same fields as the request).
    inputs: dict[str, Any] | None = None

    @field_validator("inputs", mode="before")
    @classmethod
    def bounded_inputs(cls, value):
        return None if value is None else validate_json_value(value)


class KnowledgeQuery(Model):
    query: str = Field(min_length=1, max_length=300)


class SearchInput(Model):
    provider: str = Field(max_length=20)
    searxng_url: str = Field(default="", max_length=2000)
    language: str = Field(default="tr", max_length=3)
    key: str | None = Field(default=None, max_length=500)
    remove_key: bool = False


def router(service: AgentService) -> APIRouter:
    result = APIRouter(prefix="/api/agents", tags=["Ajanlar"])

    def call(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except AgentServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
        except (ValueError, KeyError, OSError):
            raise HTTPException(status_code=422, detail="Ajan isteği veya kayıt biçimi geçersiz.") from None

    @result.get("")
    def list_agents():
        return call(service.agents)

    @result.post("", status_code=201)
    def create_agent(body: AgentInput):
        return call(service.create_agent, body)

    # Static paths precede the dynamic agent identifier.
    @result.get("/runs")
    def list_runs(agent_id: str | None = None):
        return call(service.runs, agent_id=agent_id)

    @result.get("/tasks")
    def list_tasks(agent_id: str | None = None, status: str | None = None):
        return call(service.tasks, agent_id=agent_id, status=status)

    @result.get("/tasks/{task_id}")
    def get_task(task_id: str):
        return call(service.get_task, task_id)

    @result.delete("/tasks/{task_id}")
    def delete_task(task_id: str):
        return {"deleted": call(service.delete_task, task_id)}

    @result.get("/team")
    def team():
        return call(service.team)

    @result.get("/queue")
    def queue():
        return call(service.queue)

    @result.get("/notes")
    def notes():
        return call(service.notes)

    @result.get("/handoffs")
    def handoffs():
        return call(service.handoffs)

    @result.get("/search")
    def search_settings():
        actor = call(service._authorize)
        return service.search_settings.get(actor.company_id)

    @result.put("/search")
    def save_search(body: SearchInput):
        actor = call(service._authorize, "agents.manage")
        return call(service.search_settings.save, actor.company_id, body.model_dump(exclude_none=True))

    @result.post("/search/test")
    def test_search():
        from ..errors import WorkflowError
        from .web import search

        actor = call(service._authorize, "agents.manage")
        settings = service.search_settings
        try:
            results = search(settings.get(actor.company_id), settings.key(actor.company_id), "RpaOrkestrAI", 3)
        except WorkflowError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
        return {"ok": True, "message": f"Arama çalışıyor: {len(results)} sonuç geldi.", "results": results}

    @result.get("/runs/{run_id}")
    def get_run(run_id: str):
        return call(service.get_run, run_id)

    @result.delete("/runs/{run_id}")
    def delete_run(run_id: str):
        return {"deleted": call(service.delete_run, run_id)}

    @result.post("/runs/{run_id}/cancel", status_code=202)
    def cancel_run(run_id: str):
        return call(service.cancel, run_id)

    @result.post("/runs/{run_id}/questions/{question_id}/answer")
    def answer(run_id: str, question_id: str, body: AnswerRequest):
        return call(service.answer, run_id, question_id, body.answer)

    @result.post("/runs/{run_id}/approvals/{approval_id}/decision")
    def approve(run_id: str, approval_id: str, body: ApprovalRequest):
        return call(service.approve, run_id, approval_id, body.approved, body.inputs)

    @result.post("/runs/{run_id}/handoff/resolve")
    def resolve_handoff(run_id: str):
        return call(service.resolve_handoff, run_id)

    @result.get("/{agent_id}")
    def get_agent(agent_id: str):
        return call(service.get_agent, agent_id)

    @result.put("/{agent_id}")
    def update_agent(agent_id: str, body: AgentInput):
        return call(service.update_agent, agent_id, body)

    @result.delete("/{agent_id}", status_code=204)
    def delete_agent(agent_id: str):
        call(service.delete_agent, agent_id)
        return Response(status_code=204)

    @result.get("/{agent_id}/knowledge")
    def knowledge_status(agent_id: str):
        return call(service.knowledge_status, agent_id)

    @result.post("/{agent_id}/knowledge/search")
    def knowledge_search(agent_id: str, body: KnowledgeQuery):
        return call(service.knowledge_test, agent_id, body.query)

    @result.get("/{agent_id}/playbook-stats")
    def playbook_stats(agent_id: str):
        return call(service.playbook_stats, agent_id)

    @result.post("/{agent_id}/notes", status_code=201)
    def add_note(agent_id: str, body: NoteInput):
        return call(service.add_note, agent_id, body)

    @result.put("/{agent_id}/notes/{note_id}")
    def update_note(agent_id: str, note_id: str, body: NoteInput):
        return call(service.update_note, agent_id, note_id, body)

    @result.delete("/{agent_id}/notes/{note_id}", status_code=204)
    def delete_note(agent_id: str, note_id: str):
        call(service.delete_note, agent_id, note_id)
        return Response(status_code=204)

    @result.post("/{agent_id}/runs", status_code=202)
    def start_run(agent_id: str, body: AgentRunRequest):
        return call(service.start, agent_id, body)

    return result
