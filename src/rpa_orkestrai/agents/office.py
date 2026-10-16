"""Ofise yalnız firma kapsamındaki kimlik ve durum özetleri verilir."""

import re
import time
from collections import Counter

from .models import TERMINAL_STATUSES

LABELS = {"idle": "Görev bekliyor", "queued": "Görev sırasında", "running": "Görev üzerinde çalışıyor",
          "waiting_user": "Kullanıcı yanıtını bekliyor", "waiting_approval": "İşlem onayını bekliyor",
          "succeeded": "Son görev tamamlandı", "failed": "Son görev başarısız", "cancelled": "Son görev durduruldu"}


def remember_completion(service, context) -> None:
    """Keep a bounded, short-lived visual state; never store task contents or counters."""
    instant = time.monotonic()
    with service._lock:
        recent = {key: value for key, value in getattr(service, "_office_recent", {}).items()
                  if instant - value["at"] < 60}
        recent[(context.run.actor.company_id, context.agent.id)] = {
            "at": instant, "agent_id": context.agent.id, "status": context.run.status,
            "task_id": context.run.task_id, "run_id": context.run.id,
            "event": ({"id": context.run.id, "kind": "completed", "to_agent_id": context.agent.manager_id}
                      if context.run.status == "succeeded" else None),
        }
        service._office_recent = dict(sorted(recent.items(), key=lambda item: item[1]["at"])[-500:])


def _open_question(context):
    question = getattr(context, "manager_question", None)
    return question if question and not question["answered"] else None


def human_snapshot(value: dict) -> dict:
    """Fail closed if a central scene record cannot be safely projected."""
    if not isinstance(value, dict):
        raise ValueError("Çalışanların ofis durumu doğrulanamadı.")
    people = value.get("people")
    if value.get("success") is not True or not isinstance(people, list) or len(people) > 500:
        raise ValueError("Çalışanların ofis durumu doğrulanamadı.")
    safe = []
    for person in people:
        if not isinstance(person, dict):
            raise ValueError("Çalışanların ofis durumu doğrulanamadı.")
        user = person.get("user_id")
        visible = person.get("can_view_tasks")
        state = person.get("status")
        task = person.get("task_id")
        queued = person.get("queue_count")
        name = person.get("name")
        if (type(user) is not int or user < 1 or person.get("id") != f"human-{user}"
                or type(visible) is not bool or type(queued) is not int or not 0 <= queued <= 2147483647
                or not isinstance(name, str) or len(name) > 1200
                or state not in {*LABELS, "unknown"}
                or (task is not None and (not isinstance(task, str) or not re.fullmatch(r"[a-f0-9]{32}", task)))):
            raise ValueError("Çalışanların ofis durumu doğrulanamadı.")
        if not visible:
            state, task, queued = "unknown", None, 0
        safe.append({"id": f"human-{user}", "user_id": user, "name": name[:120], "kind": "human",
                     "role": "human", "department": "", "status": state, "task_id": task,
                     "task_label": LABELS.get(state, "Görev bilgisine erişiminiz yok"),
                     "queue_count": queued, "can_view_tasks": visible})
    if len({item["id"] for item in safe}) != len(safe):
        raise ValueError("Çalışanların ofis durumu doğrulanamadı.")
    return {"success": True, "people": safe}


def snapshot(service) -> dict:
    """Never serialize a model wholesale here: new model fields are private by default."""
    actor = service._authorize()
    agents = [agent for agent in service.agent_store.agents() if agent.company_id == actor.company_id]
    identities = {agent.id for agent in agents}
    # Polling must not repeatedly deserialize megabytes of historical messages/results.
    # Copy only active context metadata while the runtime owns its lock.
    with service._lock:
        runs = []
        for context in service._contexts.values():
            if (context.run.actor.company_id != actor.company_id or context.run.agent_id not in identities
                    or context.run.status in TERMINAL_STATUSES):
                continue
            state = "queued" if context.thread is None else context.run.status
            events = context.run.events[-50:]
            # Only the kind and the counterpart travel to the office; question/answer texts stay in the run.
            message = next((event for event in reversed(events)
                            if event.kind in {"task_delegated", "department_answered"}), None)
            recent_event = events[-1].kind if events else ""
            asking = _open_question(context)
            parent = service._contexts.get(context.run.parent_run_id) if context.run.parent_run_id else None
            reviewing = any(child.run.parent_run_id == context.run.id and _open_question(child)
                            for child in service._contexts.values())
            researching = getattr(context, "current_tool", None) in {"web_search", "fetch_page"}
            activity = ("asking_manager" if asking else "reviewing" if reviewing else "researching" if researching else
                        "workflow" if getattr(context, "active_workflow_id", None) else
                        "queued" if recent_event == "queue" else "thinking") if state == "running" else state
            if asking and parent is not None:
                event = {"id": asking["id"], "kind": "question", "to_agent_id": parent.agent.id}
            elif message is not None:
                event = {"id": message.id, "kind": "delegated" if message.kind == "task_delegated" else "answered",
                         "to_agent_id": message.data.get("agent_id")}
            else:
                event = None
            runs.append({"agent_id": context.run.agent_id, "status": state, "run_id": context.run.id,
                         "task_id": context.run.task_id, "created_at": context.run.created_at,
                         "activity": activity, "event": event})
        recent = {key: value for key, value in getattr(service, "_office_recent", {}).items()
                  if time.monotonic() - value["at"] < 60}
        service._office_recent = recent
    redactor = service._new_redactor()
    summaries = []
    for agent in agents:
        active = sorted((run for run in runs if run["agent_id"] == agent.id), key=lambda item: item["created_at"])
        selected = next((run for run in active if run["status"] != "queued"), next(iter(active), None))
        selected = selected or recent.get((actor.company_id, agent.id))
        state = selected["status"] if selected and selected["status"] in LABELS else "idle"
        event = selected.get("event") if selected else None
        if event and event["to_agent_id"] not in identities:
            event = None
        summaries.append({"id": agent.id, "name": redactor.text(agent.name)[:120],
                          "department": redactor.text(agent.department)[:120], "role": agent.role,
                          "kind": "agent", "manager_id": agent.manager_id if agent.manager_id in identities else None,
                          "run_id": selected["run_id"] if selected else None,
                          "activity": selected.get("activity", state) if selected else "idle", "event": event,
                          "status": state, "task_id": selected["task_id"] if selected else None,
                          "task_label": LABELS[state], "queue_count": sum(run["status"] == "queued" for run in active)})
    departments = Counter(item["department"] for item in summaries if item["role"] == "department")
    return {"agents": summaries,
            "departments": [{"name": name, "agent_count": count} for name, count in sorted(departments.items())],
            "totals": {"agents": len(summaries), "queued": sum(item["queue_count"] for item in summaries),
                       "running": sum(item["status"] == "running" for item in summaries),
                       "waiting": sum(item["status"] in {"waiting_user", "waiting_approval"} for item in summaries)}}
