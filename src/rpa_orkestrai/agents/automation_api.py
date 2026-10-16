"""Ajan otomasyonlarının HTTP uçları; ajan uçlarıyla aynı lisans, Origin ve gövde kapısının arkasındadır."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from pydantic import ValidationError

from .automations import AutomationInput, AutomationService
from .runner import AgentServiceError


def router(automations: AutomationService) -> APIRouter:
    result = APIRouter(prefix="/api/agents/automations", tags=["Ajan otomasyonları"])

    def call(function, *args):
        try:
            return function(*args)
        except AgentServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from None
        except (ValidationError, ValueError, KeyError, OSError):
            raise HTTPException(status_code=422, detail="Otomasyon isteği veya kayıt biçimi geçersiz.") from None

    @result.get("")
    def list_automations():
        return call(automations.automations)

    @result.post("", status_code=201)
    def create(body: AutomationInput):
        return call(automations.create, body)

    @result.put("/{automation_id}")
    def update(automation_id: str, body: AutomationInput):
        return call(automations.update, automation_id, body)

    @result.delete("/{automation_id}", status_code=204)
    def delete(automation_id: str):
        call(automations.delete, automation_id)
        return Response(status_code=204)

    @result.post("/{automation_id}/run")
    def run_now(automation_id: str):
        return call(automations.run_now, automation_id)

    return result
