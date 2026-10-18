"""Ajanın size Telegram'dan ulaşması: kişinin kendi ayarı, yalnız bu bilgisayarda."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .runner import AgentServiceError
from .telegram_bridge import TelegramSettings


def router(service, bridge) -> APIRouter:
    result = APIRouter(prefix="/api/agents/telegram", tags=["Telegram ile soru ve onay"])

    def actor():
        try:
            return service._authorize()
        except AgentServiceError as exc:
            raise HTTPException(exc.status_code, str(exc)) from None

    def call(function, *args):
        try:
            return function(*args)
        except KeyError:
            raise HTTPException(404, "Seçilen Telegram bağlantısı bu bilgisayarda yok.") from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @result.get("")
    def settings():
        return bridge.public(actor())

    @result.put("")
    def save(body: TelegramSettings):
        return call(bridge.save, actor(), body)

    @result.delete("")
    def remove():
        return bridge.remove(actor())

    @result.post("/test")
    def test(body: TelegramSettings):
        return call(bridge.test, actor(), body)

    return result
