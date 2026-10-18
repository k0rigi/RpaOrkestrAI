"""Departman ofisleri: her ofis yalnız kendi ajanlarını, çalışmalarını, görevlerini ve otomasyonlarını görür."""

import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from test_agent_runner import AGENT_TEST_SECONDS, finish, response
from test_agent_runner import runtime as runtime  # noqa: F401

from rpa_orkestrai.agents.automations import AutomationInput, AutomationService, AutomationTrigger
from rpa_orkestrai.agents.models import AgentInput, AgentLimits, AgentRunRequest
from rpa_orkestrai.agents.organization import OrganizationError
from rpa_orkestrai.agents.providers import ScriptedProvider
from rpa_orkestrai.agents.runner import AgentServiceError

CLAIMS, LOGISTICS = "c" * 32, "d" * 32


def work_in(runtime, office, user_id=1, name="Claim & İade Departmanı"):
    runtime.state["actor"] = runtime.owner.model_copy(update={"office_id": office, "office_name": name,
                                                              "user_id": user_id})


def new_agent(runtime, name="Ajan", **values):
    return runtime.service.create_agent(AgentInput(name=name, model="test", **values,
                                                   limits=AgentLimits(max_seconds=AGENT_TEST_SECONDS)))


def editable(agent):
    return AgentInput(**agent.model_dump(include=set(AgentInput.model_fields)))


def test_each_office_sees_only_its_own_agents_runs_and_tasks(runtime):
    work_in(runtime, CLAIMS)
    claims = new_agent(runtime, "İade ajanı")
    assert claims.office_id == CLAIMS
    runtime.state["provider"] = ScriptedProvider([response(finish("İade incelendi"))])
    run = runtime.done(runtime.service.start(claims.id, AgentRunRequest(task="İadeyi incele")))
    assert run.office_id == CLAIMS and runtime.service.get_task(run.task_id).office_id == CLAIMS
    stored = json.loads(runtime.service.agent_store.path("agent_runs", run.id).read_text())
    assert stored["office_id"] == CLAIMS and "office_id" not in stored["actor"]
    work_in(runtime, LOGISTICS, user_id=5, name="Lojistik Planlama ve Süreç Geliştirme Departmanı")
    logistics = new_agent(runtime, "Rota ajanı")
    service = runtime.service
    assert [agent.id for agent in service.agents()] == [logistics.id]
    assert service.runs() == [] and service.tasks() == [] and service.team()["agents"][0]["id"] == logistics.id
    for call in (lambda: service.get_agent(claims.id), lambda: service.get_run(run.id),
                 lambda: service.get_task(run.task_id), lambda: service.delete_task(run.task_id),
                 lambda: service.start(claims.id, AgentRunRequest(task="Başka ofisin işi"))):
        with pytest.raises(AgentServiceError) as error:
            call()
        assert error.value.status_code == 404
    work_in(runtime, CLAIMS)
    assert [agent.id for agent in service.agents()] == [claims.id]
    assert [item.id for item in service.runs()] == [run.id]


def test_agents_from_before_offices_move_with_the_person_who_created_them(runtime):
    legacy = new_agent(runtime, "Önceki ajan")
    assert legacy.office_id is None
    assert "office_id" not in json.loads(runtime.service.agent_store.path("agents", legacy.id).read_text())
    work_in(runtime, LOGISTICS, user_id=5, name="Lojistik")
    assert runtime.service.agents() == []
    work_in(runtime, CLAIMS)
    assert [agent.id for agent in runtime.service.agents()] == [legacy.id]
    updated = runtime.service.update_agent(legacy.id, editable(legacy))
    assert updated.office_id == CLAIMS
    runtime.state["actor"] = runtime.owner  # A single-team session no longer sees an office's agent.
    assert runtime.service.agents() == []


def test_every_office_has_its_own_manager_and_departments(runtime):
    work_in(runtime, CLAIMS)
    claims_manager = new_agent(runtime, "İade yöneticisi", role="manager")
    with pytest.raises(OrganizationError, match="Bir ofiste yalnız bir yönetici"):
        new_agent(runtime, "İkinci yönetici", role="manager")
    work_in(runtime, LOGISTICS, user_id=5, name="Lojistik")
    logistics_manager = new_agent(runtime, "Lojistik yöneticisi", role="manager")
    with pytest.raises(OrganizationError, match="aynı ofisin yönetici"):
        new_agent(runtime, "Rota", manager_id=claims_manager.id)
    assert new_agent(runtime, "Rota", manager_id=logistics_manager.id).manager_id == logistics_manager.id


def test_a_move_to_another_office_stops_running_work(runtime):
    work_in(runtime, CLAIMS)
    agent = new_agent(runtime)

    def moved(request):
        work_in(runtime, LOGISTICS)
        return response(finish())

    runtime.state["provider"] = ScriptedProvider([], callback=moved)
    run = runtime.done(runtime.service.start(agent.id, AgentRunRequest(task="İşi yap")))
    assert run.status == "cancelled" and "oturumu değiştiği" in run.error


def test_automations_belong_to_the_office_that_created_them(runtime):
    service = AutomationService(runtime.service, runtime.settings.data_dir, clock=lambda: datetime(2026, 10, 18, 8, 0))
    work_in(runtime, CLAIMS)
    agent = new_agent(runtime)
    created = service.create(AutomationInput(name="Sabah", agent_id=agent.id, task="Özetle",
                                             trigger=AutomationTrigger(kind="schedule", schedule_kind="daily",
                                                                       time="09:00")))
    assert "office_id" not in created
    stored = json.loads((runtime.settings.data_dir / "agent_automations.json").read_text())
    assert stored["automations"][0]["office_id"] == CLAIMS
    work_in(runtime, LOGISTICS, user_id=5, name="Lojistik")
    assert service.automations() == []
    for call in (lambda: service.run_now(created["id"]), lambda: service.delete(created["id"])):
        with pytest.raises(AgentServiceError):
            call()
    work_in(runtime, CLAIMS)
    assert [item["id"] for item in service.automations()] == [created["id"]]


def test_single_team_files_stay_readable_by_earlier_versions(runtime):
    agent = new_agent(runtime)
    service = AutomationService(runtime.service, runtime.settings.data_dir, clock=lambda: datetime(2026, 10, 18, 8, 0))
    service.create(AutomationInput(name="Sabah", agent_id=agent.id, task="Özetle",
                                   trigger=AutomationTrigger(kind="schedule", schedule_kind="daily", time="09:00")))
    runtime.state["provider"] = ScriptedProvider([response(finish())])
    run = runtime.done(runtime.service.start(agent.id, AgentRunRequest(task="İşi yap")))
    files = [runtime.service.agent_store.path("agents", agent.id), runtime.service.agent_store.path("agent_runs", run.id),
             runtime.service.agent_store.path("agent_tasks", run.task_id), runtime.settings.data_dir / "agent_automations.json"]
    assert not any("office_id" in path.read_text() for path in files)
    assert SimpleNamespace(**runtime.service.get_task(run.task_id).model_dump()).office_id is None
