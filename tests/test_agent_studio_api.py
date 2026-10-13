"""Ajan ayarları API'sinin firma, anahtar ve girdi sınırları."""

import pytest
from test_agent_api import api as agent_api  # noqa: F401
from test_agent_connections import MemorySecrets

from rpa_orkestrai.models import Step, Workflow
from rpa_orkestrai.vault import Vault


@pytest.fixture
def client(agent_api, tmp_path):  # noqa: F811
    store = agent_api.app.state.agent_connections
    store.vault = Vault(tmp_path, store=MemorySecrets(), purpose="agent_provider")
    return agent_api


def connection(client):
    result = client.client.post("/api/agents/connections", json={"name": "Yerel", "provider": "ollama",
                                                               "model": "deneme"})
    assert result.status_code == 201, result.text
    return result.json()


def test_session_summary_omits_session_tokens(client):
    response = client.client.get("/api/agents/session")
    assert response.status_code == 200
    assert response.json() == {"actor": {"user_id": 1, "company_id": 2, "name": "Yetkili"},
                               "can_manage": True, "can_approve": True}


def test_write_only_key_is_not_in_metadata_validation_or_record(client, tmp_path):
    item = connection(client)
    path = f"/api/agents/connections/{item['id']}/key"
    secret = "sakli-api-anahtari"
    assert client.client.put(path, json={"key": secret}).json() == {"has_key": True}
    assert client.client.get(path).status_code == 404
    public = client.client.get("/api/agents/connections")
    assert secret not in public.text and public.json()[0]["has_key"] is True
    invalid = client.client.put(path, json={"key": {"bad": secret}})
    assert invalid.status_code == 422 and secret not in invalid.text
    invalid = client.client.put(path, json={"key": secret, secret: "fazla alan"})
    assert invalid.status_code == 422 and secret not in invalid.text
    for file in tmp_path.rglob("*.json"):
        assert secret not in file.read_text()
    assert client.client.delete(path).json() == {"has_key": False}


def test_only_manager_can_change_connection_or_test_it(client, monkeypatch):
    item = connection(client)
    called = []
    monkeypatch.setattr(client.app.state.agent_connections, "test_connection", lambda *a, **kw: called.append(1))
    client.licensing.actor = client.licensing.actor.model_copy(update={"permissions": ("agents.use",)})
    path = f"/api/agents/connections/{item['id']}"
    assert client.client.get("/api/agents/connections").status_code == 200
    assert client.client.put(path, json={"name": "Yeni", "provider": "ollama"}).status_code == 403
    assert client.client.put(path + "/key", json={"key": "sakli"}).status_code == 403
    assert client.client.delete(path).status_code == 403
    assert client.client.post(path + "/test", json={}).status_code == 403
    assert not called


def test_connection_test_is_explicit_and_uses_selected_model(client, monkeypatch):
    item = connection(client)
    seen = []

    def test(identity, company_id, *, model):
        seen.append((identity, company_id, model))
        return {"ok": True}

    monkeypatch.setattr(client.app.state.agent_connections, "test_connection", test)
    assert not seen
    response = client.client.post(f"/api/agents/connections/{item['id']}/test", json={"model": "baska-model"})
    assert response.json() == {"ok": True}
    assert seen == [(item["id"], 2, "baska-model")]


def test_connection_scope_and_unknown_fields_are_enforced(client):
    item = connection(client)
    client.licensing.actor = client.licensing.actor.model_copy(update={"company_id": 9})
    assert client.client.get("/api/agents/connections").json() == []
    assert client.client.delete(f"/api/agents/connections/{item['id']}").status_code == 404
    response = client.client.post("/api/agents/connections", json={"name": "Deneme", "provider": "ollama",
                                                                 "company_id": 2})
    assert response.status_code == 422


@pytest.mark.parametrize("body", [
    {"name": "Deneme", "provider": "openai", "base_url": "https://baska.example"},
    {"name": "Deneme", "provider": "ollama", "base_url": "http://169.254.169.254"},
    {"name": "Deneme", "provider": "fake"},
])
def test_arbitrary_endpoint_and_fake_provider_are_rejected(client, body):
    assert client.client.post("/api/agents/connections", json=body).status_code == 422


def test_workflow_metadata_hides_parameters_and_allows_configuring_file_grant(client):
    first = Workflow(name="Dosya oku", steps=[Step(action="file.read_text", params={"path": "${dosya}", "output": "metin"})])
    second = Workflow(name="Komut", steps=[Step(action="system.command", params={"command": "gizli-komut-metni"})])
    for workflow in (first, second):
        client.app.state.store.save_workflow(workflow)
    response = client.client.get("/api/agents/workflows")
    assert response.status_code == 200, response.text
    items = {item["id"]: item for item in response.json()}
    assert items[first.id]["agent_supported"] is True and items[first.id]["requires_roots"] is True
    assert items[first.id]["inputs"] == [{"name": "dosya", "required": True}]
    assert items[second.id]["agent_supported"] is False
    assert "gizli-komut-metni" not in response.text
