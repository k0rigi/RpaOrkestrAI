from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from rpa_orkestrai.agents.models import Actor
from rpa_orkestrai.agents.providers import ProviderResponse, ScriptedProvider, ToolCall
from rpa_orkestrai.app import create_app
from rpa_orkestrai.config import Settings
from rpa_orkestrai.models import uid


class AgentLicense:
    def __init__(self):
        self.rpa = True
        self.agents = True
        self.actor = Actor(user_id=1, company_id=2, name="Yetkili", session_id="session",
                           permissions=["agents.use", "agents.manage", "agents.approve"])

    def allowed(self):
        return self.rpa

    def agent_allowed(self):
        return self.agents

    def agent_actor(self):
        return self.actor

    def status(self):
        return {"state": "valid" if self.rpa else "denied", "message": "", "online": True,
                "license": None, "remembered": True, "detail": None}

    def start(self):
        pass

    def stop(self):
        pass


@pytest.fixture
def api(tmp_path):
    licensing = AgentLicense()
    app = create_app(Settings(tmp_path, dotenv=False), licensing=licensing)
    provider = ScriptedProvider([ProviderResponse(tool_calls=[
        ToolCall(uid(), "finish", {"summary": "Bitti", "result": {"ok": True}}),
    ])])
    app.state.agents._provider_factory = lambda agent: provider
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, licensing=licensing, app=app)


def create(api):
    response = api.client.post("/api/agents", json={"name": "Analiz", "model": "test"})
    assert response.status_code == 201, response.text
    return response.json()


def test_agent_crud_and_run_routes_are_behind_real_studio_middleware(api):
    agent = create(api)
    identity = agent["id"]
    assert api.client.get("/api/agents").json()[0]["id"] == identity
    assert api.client.get(f"/api/agents/{identity}").status_code == 200
    changed = api.client.put(f"/api/agents/{identity}", json={"name": "Yeni ad", "model": "test"})
    assert changed.status_code == 200 and changed.json()["revision"] == 2
    started = api.client.post(f"/api/agents/{identity}/runs", json={"task": "Özetle"})
    assert started.status_code == 202, started.text
    run_id = started.json()["id"]
    assert api.client.get(f"/api/agents/runs/{run_id}").status_code == 200
    assert api.client.get("/api/agents/runs").json()[0]["id"] == run_id
    assert api.client.delete(f"/api/agents/{identity}").status_code == 204
    assert api.client.get(f"/api/agents/{identity}").status_code == 404


@pytest.mark.parametrize("which", ["rpa", "agents"])
def test_both_license_modules_are_required(api, which):
    setattr(api.licensing, which, False)
    assert api.client.get("/api/agents").status_code == 403
    assert api.client.post("/api/agents", json={"name": "Analiz"}).status_code == 403
    if which == "agents":
        # Separate entitlement must not lock regular RPA operation.
        assert api.client.get("/api/workflows").status_code == 200


def test_server_owned_fields_and_embedded_secrets_are_not_echoed(api):
    secret = "never-echo-this-private-value"
    result = api.client.post("/api/agents", json={"name": "Analiz", "api_key": secret,
                                               "company_id": 99, "revision": 20})
    assert result.status_code == 422 and secret not in result.text
    assert api.client.get("/api/agents").json() == []


def test_user_without_management_permission_cannot_edit_agents(api):
    agent = create(api)
    api.licensing.actor = api.licensing.actor.model_copy(update={"permissions": ("agents.use",)})
    assert api.client.post("/api/agents", json={"name": "Başka"}).status_code == 403
    assert api.client.put(f"/api/agents/{agent['id']}", json={"name": "Yeni"}).status_code == 403
    assert api.client.delete(f"/api/agents/{agent['id']}").status_code == 403


def test_company_boundary_is_enforced_for_reads_and_mutations(api):
    agent = create(api)
    api.licensing.actor = Actor(user_id=3, company_id=4, session_id="other",
                               permissions=["agents.use", "agents.manage", "agents.approve"])
    assert api.client.get("/api/agents").json() == []
    assert api.client.get(f"/api/agents/{agent['id']}").status_code == 404
    assert api.client.delete(f"/api/agents/{agent['id']}").status_code == 404
    assert api.client.post(f"/api/agents/{agent['id']}/runs", json={"task": "İş"}).status_code == 404


def test_cross_origin_and_oversized_agent_requests_are_blocked(api):
    result = api.client.post("/api/agents", json={"name": "Analiz"}, headers={"Origin": "https://outside.example"})
    assert result.status_code == 403
    result = api.client.post("/api/agents", content="x" * 2_000_001,
                             headers={"Content-Type": "application/json"})
    assert result.status_code == 413


def test_approval_is_strict_boolean_and_actor_cannot_be_forged(api):
    result = api.client.post(f"/api/agents/runs/{uid()}/approvals/{uid()}/decision",
                             json={"approved": "true", "actor": {"user_id": 1}})
    assert result.status_code == 422
    api.licensing.actor = api.licensing.actor.model_copy(update={"permissions": ("agents.use",)})
    result = api.client.post(f"/api/agents/runs/{uid()}/approvals/{uid()}/decision", json={"approved": True})
    assert result.status_code == 403


def test_reserved_inputs_are_blocked_before_any_work_starts(api):
    agent = create(api)
    result = api.client.post(f"/api/agents/{agent['id']}/runs", json={"task": "İş", "inputs": {"sifre": {}}})
    assert result.status_code == 422
    assert api.client.get("/api/agents/runs").json() == []


def test_tasks_team_and_queue_are_company_scoped_and_license_gated(api):
    agent = create(api)
    response = api.client.post(f"/api/agents/{agent['id']}/runs", json={"task": "İşi yap"})
    assert response.status_code == 202
    task_id = response.json()["task_id"]
    assert api.client.get("/api/agents/tasks").json()[0]["id"] == task_id
    assert api.client.get(f"/api/agents/tasks/{task_id}").status_code == 200
    assert api.client.get("/api/agents/team").json()["agents"][0]["id"] == agent["id"]
    assert api.client.get("/api/agents/queue").status_code == 200
    api.licensing.actor = api.licensing.actor.model_copy(update={"company_id": 99})
    assert api.client.get("/api/agents/tasks").json() == []
    assert api.client.get(f"/api/agents/tasks/{task_id}").status_code == 404
    assert api.client.get("/api/agents/team").json() == {"agents": []}
    assert api.client.get("/api/agents/queue").json() == []
    api.licensing.agents = False
    for path in ("tasks", "team", "queue"):
        assert api.client.get(f"/api/agents/{path}").status_code == 403


def test_note_routes_are_license_gated_and_reject_unknown_fields(api):
    identity = create(api)["id"]
    assert api.client.get("/api/agents/notes").json() == {identity: []}
    added = api.client.post(f"/api/agents/{identity}/notes", json={"text": "Raporlar haftalık hazırlanır."})
    assert added.status_code == 201, added.text
    note = added.json()["id"]
    assert api.client.post(f"/api/agents/{identity}/notes", json={"text": "X", "user_id": 99}).status_code == 422
    assert api.client.put(f"/api/agents/{identity}/notes/{note}", json={"text": "Raporlar aylık hazırlanır."}).status_code == 200
    assert api.client.get("/api/agents/notes").json()[identity][0]["text"] == "Raporlar aylık hazırlanır."
    api.licensing.agents = False
    assert api.client.get("/api/agents/notes").status_code == 403
    api.licensing.agents = True
    assert api.client.delete(f"/api/agents/{identity}/notes/{note}").status_code == 204
    assert api.client.delete(f"/api/agents/{identity}/notes/{note}").status_code == 404
