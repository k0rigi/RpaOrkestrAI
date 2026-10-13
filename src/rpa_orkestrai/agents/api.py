"""Mevcut lisans ve kaynak denetiminin arkasında kalan ajan API uçları."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import Field, field_validator

from ..models import Model
from .models import AgentInput, AgentRunRequest, validate_json_value
from .runner import AgentService, AgentServiceError


class AnswerRequest(Model):
    answer: Any

    @field_validator("answer", mode="before")
    @classmethod
    def bounded_answer(cls, value):
        return validate_json_value(value)


class ApprovalRequest(Model):
    approved: bool = Field(strict=True)


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

    @result.get("/runs/{run_id}")
    def get_run(run_id: str):
        return call(service.get_run, run_id)

    @result.post("/runs/{run_id}/cancel", status_code=202)
    def cancel_run(run_id: str):
        return call(service.cancel, run_id)

    @result.post("/runs/{run_id}/questions/{question_id}/answer")
    def answer(run_id: str, question_id: str, body: AnswerRequest):
        return call(service.answer, run_id, question_id, body.answer)

    @result.post("/runs/{run_id}/approvals/{approval_id}/decision")
    def approve(run_id: str, approval_id: str, body: ApprovalRequest):
        return call(service.approve, run_id, approval_id, body.approved)

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

    @result.post("/{agent_id}/runs", status_code=202)
    def start_run(agent_id: str, body: AgentRunRequest):
        return call(service.start, agent_id, body)

    return result
