"""Ofise yalnız firma kapsamındaki kimlik ve durum özetleri verilir."""

from collections import Counter

from .models import TERMINAL_STATUSES

LABELS = {"idle": "Görev bekliyor", "queued": "Görev sırasında", "running": "Görev üzerinde çalışıyor",
          "waiting_user": "Kullanıcı yanıtını bekliyor", "waiting_approval": "İşlem onayını bekliyor",
          "succeeded": "Son görev tamamlandı", "failed": "Son görev başarısız", "cancelled": "Son görev durduruldu"}


def snapshot(service) -> dict:
    """Never serialize a model wholesale here: new model fields are private by default."""
    actor = service._authorize()
    agents = [agent for agent in service.agent_store.agents() if agent.company_id == actor.company_id]
    identities = {agent.id for agent in agents}
    # Polling must not repeatedly deserialize megabytes of historical messages/results.
    # Copy only active context metadata while the runtime owns its lock.
    with service._lock:
        runs = [{"agent_id": context.run.agent_id, "status": "queued" if context.thread is None else context.run.status,
                 "task_id": context.run.task_id, "created_at": context.run.created_at}
                for context in service._contexts.values()
                if context.run.actor.company_id == actor.company_id and context.run.agent_id in identities
                and context.run.status not in TERMINAL_STATUSES]
    redactor = service._new_redactor()
    summaries = []
    for agent in agents:
        active = sorted((run for run in runs if run["agent_id"] == agent.id), key=lambda item: item["created_at"])
        selected = next((run for run in active if run["status"] != "queued"), next(iter(active), None))
        state = selected["status"] if selected and selected["status"] in LABELS else "idle"
        summaries.append({"id": agent.id, "name": redactor.text(agent.name)[:120],
                          "department": redactor.text(agent.department)[:120], "role": agent.role,
                          "status": state, "task_id": selected["task_id"] if selected else None,
                          "task_label": LABELS[state], "queue_count": sum(run["status"] == "queued" for run in active)})
    departments = Counter(item["department"] for item in summaries if item["role"] == "department")
    return {"agents": summaries,
            "departments": [{"name": name, "agent_count": count} for name, count in sorted(departments.items())],
            "totals": {"agents": len(summaries), "queued": sum(item["queue_count"] for item in summaries),
                       "running": sum(item["status"] == "running" for item in summaries),
                       "waiting": sum(item["status"] in {"waiting_user", "waiting_approval"} for item in summaries)}}
