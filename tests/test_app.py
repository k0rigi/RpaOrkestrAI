import time

import pytest
from fastapi.testclient import TestClient

from rpa_orkestrai.app import create_app
from rpa_orkestrai.config import Settings


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(Settings(tmp_path, dotenv=False))) as instance:
        yield instance


def test_studio_bootstrap_and_static(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "RpaOrkestrAI" in response.text
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    bootstrap = client.get("/api/bootstrap").json()
    assert len(bootstrap["workflows"]) == 1
    assert any(a["type"] == "control.for_each" for a in bootstrap["catalog"])
    assert client.get("/app.js").status_code == 200


def test_workflow_crud_duplicate_import_export(client):
    body = {"name": "Test akışı", "department": "Satış", "steps": [{"action": "core.log"}]}
    response = client.post("/api/workflows", json=body)
    assert response.status_code == 201
    created = response.json()
    wid = created["id"]
    assert client.put(f"/api/workflows/{wid}", json={**body, "name": "Günlük rapor"}).status_code == 200
    duplicate = client.post(f"/api/workflows/{wid}/duplicate").json()
    assert duplicate["id"] != wid
    exported = client.get(f"/api/workflows/{wid}/export")
    assert "attachment" in exported.headers["content-disposition"]
    imported = client.post("/api/workflows/import", json=exported.json()).json()
    assert imported["id"] != wid
    assert client.delete(f"/api/workflows/{wid}").status_code == 204
    assert client.get(f"/api/workflows/{wid}").status_code == 404


def test_demo_run_and_report_download(client):
    workflow = client.get("/api/workflows").json()[0]
    response = client.post(f"/api/workflows/{workflow['id']}/run", json={"dry_run": False})
    assert response.status_code == 202
    run_id = response.json()["id"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()
        if run["status"] not in {"queued", "running"}:
            break
        time.sleep(0.02)
    assert run["status"] == "succeeded", run
    artifact = run["artifacts"][0]
    assert artifact["rows"] == 3
    report = client.get(artifact["url"])
    assert report.status_code == 200
    assert "SIP-1001" in report.text
    assert "SIP-1002" not in report.text
    assert client.get(f"/api/runs/{run_id}/artifacts/unknown").status_code == 404


def test_cross_origin_and_dns_rebinding_are_blocked(client):
    assert client.post("/api/workflows", json={"name": "Unexpected"},
                       headers={"origin": "https://malicious.example"}).status_code == 403
    assert client.post("/api/workflows", json={"name": "Unexpected"},
                       headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert client.get("/api/bootstrap", headers={"host": "malicious.example"}).status_code == 400
    assert client.post("/api/workflows", json={"name": "Allowed"},
                       headers={"origin": "http://testserver"}).status_code == 201


def test_settings_never_expose_secrets(client):
    secret = "postgresql+psycopg://reader:VERY_SECRET@localhost/erp"
    response = client.put("/api/settings", json={"database_url": secret,
                                                "google_credentials_path": "/private/credentials.json"})
    assert response.status_code == 200
    assert response.json()["database_configured"]
    assert "VERY_SECRET" not in response.text
    assert "credentials.json" not in response.text
    assert "VERY_SECRET" not in client.get("/api/bootstrap").text
    assert client.put("/api/settings", json={"invalid": secret}).status_code == 422


def test_invalid_workflows_rejected_before_execution(client):
    assert client.post("/api/workflows", json={"steps": [{"action": "os.system"}]}).status_code == 422
    assert client.post("/api/workflows", json={"steps": [
        {"id": "same", "action": "core.log"}, {"id": "same", "action": "core.log"},
    ]}).status_code == 422
    assert client.post("/api/workflows", json={"steps": [
        {"action": "core.log", "children": [{"action": "core.log"}]},
    ]}).status_code == 422
    workflow = client.post("/api/workflows", json={"name": "Boş"}).json()
    assert client.post(f"/api/workflows/{workflow['id']}/run", json={}).status_code == 422


def test_chunked_request_limit_and_malformed_origin(client):
    response = client.put("/api/settings", content=(b"x" * 100000 for _ in range(21)),
                          headers={"content-type": "application/json"})
    assert response.status_code == 413
    assert client.get("/api/bootstrap", headers={"origin": "http://[broken"}).status_code == 403
