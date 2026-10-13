"""Performans görünümü yalnız kayıt okur; ajan veya akış başlatamaz."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from .metrics import MetricSettings, MetricSettingsStore, calculate, csv_export
from .runner import AgentServiceError


def router(service, connections):
    result = APIRouter(prefix="/api/agents/metrics", tags=["Ajan performansı"])
    settings = MetricSettingsStore(service.agent_store.root)

    def call(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except AgentServiceError as exc:
            raise HTTPException(exc.status_code, str(exc)) from None
        except (ValueError, TypeError, KeyError, OSError):
            raise HTTPException(422, "Performans kaydı veya tarih aralığı doğrulanamadı.") from None

    def report(start, end):
        actor = service._authorize()
        data = calculate(service.tasks(), company_id=actor.company_id, start=start, end=end,
                         settings=settings.get(actor.company_id))
        redactor = service._new_redactor()
        # Only labels can contain business text; numerical aggregates remain numerical.
        for row in [*data["agents"], *data["departments"]]:
            row["name"] = redactor.text(row["name"])
            if "department" in row:
                row["department"] = redactor.text(row["department"])
        return data

    @result.get("")
    def get_metrics(start: str = Query(max_length=40), end: str = Query(max_length=40)):
        return call(report, start, end)

    @result.get("/csv")
    def export_metrics(start: str = Query(max_length=40), end: str = Query(max_length=40)):
        data = call(report, start, end)
        return Response(csv_export(data), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="ajan-performansi.csv"'})

    @result.get("/settings")
    def get_settings():
        actor = call(service._authorize)
        return call(settings.get, actor.company_id)

    @result.put("/settings")
    def put_settings(body: MetricSettings):
        actor = call(service._authorize, "agents.manage")
        redactor = service._new_redactor()
        for row in body.prices:
            call(connections.get, row.connection_id, actor.company_id)
            if redactor.text(row.model) != row.model:
                raise HTTPException(422, "Model adı gizli bilgi içeremez.")
        return call(settings.save, actor.company_id, body)

    return result
