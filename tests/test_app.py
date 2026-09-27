import time

import pytest
from fastapi.testclient import TestClient

from rpa_orkestrai.app import create_app
from rpa_orkestrai.config import Settings
from rpa_orkestrai.demo import demo_workflow


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
    assert bootstrap["workflows"] == []
    assert {a["type"] for a in bootstrap["catalog"]} == {
        "desktop.find_window", "desktop.window_click", "desktop.window_write", "sheets.read_cell", "control.if",
    }
    assert bootstrap["favorites"] == []
    assert client.get("/api/catalog").json() == bootstrap["catalog"]
    assert any(a["type"] == "control.for_each" for a in bootstrap["action_definitions"])
    assert client.get("/app.js").status_code == 200


def test_native_instance_metadata_identifies_workspace_without_exposing_path(client):
    from rpa_orkestrai.instance import identity

    response = client.get("/api/instance")
    assert response.status_code == 200
    assert response.json() == identity(client.app.state.settings.data_dir)
    assert str(client.app.state.settings.data_dir) not in response.text


def test_opening_studio_from_a_link_is_allowed_but_cross_site_api_is_not(client):
    headers = {"sec-fetch-site": "cross-site", "sec-fetch-mode": "navigate"}
    assert client.get("/", headers=headers).status_code == 200
    assert client.get("/api/bootstrap", headers=headers).status_code == 403
    assert client.post("/api/workflows", json={"name": "Unexpected"}, headers=headers).status_code == 403


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
    workflow = client.post("/api/workflows/import", json=demo_workflow().model_dump()).json()
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


def test_favorites_persist_across_restart_without_changing_workflows(tmp_path, monkeypatch):
    from rpa_orkestrai import catalog

    # Future published actions use the same favorite API and storage.
    monkeypatch.setattr(catalog, "CATALOG", [catalog.BY_TYPE[k] for k in ("core.log", "core.wait")])
    settings = Settings(tmp_path, dotenv=False)
    with TestClient(create_app(settings)) as client:
        workflow = client.post("/api/workflows/import", json=demo_workflow().model_dump()).json()
        assert client.put("/api/favorites/core.log", json={"favorite": True}).json() == ["core.log"]
        assert client.put("/api/favorites/core.log", json={"favorite": True}).json() == ["core.log"]
        assert client.put("/api/favorites/core.wait", json={"favorite": True}).json() == [
            "core.log", "core.wait",
        ]
        assert client.get(f"/api/workflows/{workflow['id']}").json() == workflow
        assert "favorites" not in client.get(f"/api/workflows/{workflow['id']}/export").json()
    with TestClient(create_app(settings)) as client:
        bootstrap = client.get("/api/bootstrap").json()
        assert bootstrap["favorites"] == ["core.log", "core.wait"]
        assert bootstrap["workflows"] == [workflow]
        assert client.put("/api/favorites/core.log", json={"favorite": False}).json() == ["core.wait"]
        assert client.put("/api/favorites/core.log", json={"favorite": False}).json() == ["core.wait"]
    with TestClient(create_app(Settings(tmp_path / "other", dotenv=False))) as client:
        assert client.get("/api/bootstrap").json()["favorites"] == []


def test_favorites_reject_unpublished_actions_and_invalid_requests(client, monkeypatch):
    from rpa_orkestrai import catalog

    assert client.put("/api/favorites/core.log", json={"favorite": True}).status_code == 404
    assert client.put("/api/favorites/unknown", json={"favorite": True}).status_code == 404
    monkeypatch.setattr(catalog, "CATALOG", [catalog.BY_TYPE["core.log"]])
    for payload in ({}, {"favorite": "false"}, {"favorite": True, "extra": 1}):
        assert client.put("/api/favorites/core.log", json=payload).status_code == 422
    assert client.get("/api/bootstrap").json()["favorites"] == []


def test_retired_favorites_are_not_displayed(client, monkeypatch):
    from rpa_orkestrai import catalog

    monkeypatch.setattr(catalog, "CATALOG", [catalog.BY_TYPE["core.log"]])
    assert client.put("/api/favorites/core.log", json={"favorite": True}).status_code == 200
    monkeypatch.setattr(catalog, "CATALOG", [])
    assert client.get("/api/bootstrap").json()["favorites"] == []


def test_window_picker_and_check_are_read_only(client, monkeypatch):
    from unittest.mock import Mock

    from rpa_orkestrai.desktop.windows import WindowInfo

    window = WindowInfo(12, 42, 'ERP', 'İade Faturası', 100, 80, 800, 600)
    listing = Mock(return_value=[window])
    monkeypatch.setattr('rpa_orkestrai.desktop.windows.WindowService.list_windows', listing)
    assert client.get('/api/desktop/windows').json() == [window.result()]
    body = {'application': 'ERP', 'title': 'İade Faturası', 'match': 'exact'}
    assert client.post('/api/desktop/windows/check', json=body).json() == window.result()
    assert client.post('/api/desktop/windows/check', json={**body, 'title': 'Missing'}).json() == {'found': False}
    assert client.post('/api/desktop/windows/check', json={**body, 'match': 'invalid'}).status_code == 422
    assert client.post('/api/desktop/windows/check', json={**body, 'title': ' '}).status_code == 422
    assert client.get('/api/bootstrap').json()['workflows'] == []
    assert client.get('/api/runs').json() == []


def test_window_permissions_and_ambiguity_are_actionable(client, monkeypatch):
    from unittest.mock import Mock

    from rpa_orkestrai.desktop.windows import WindowError, WindowInfo

    monkeypatch.setattr('rpa_orkestrai.desktop.windows.WindowService.list_windows',
                        Mock(side_effect=WindowError('Ekran Kaydı izni gerekli.')))
    response = client.get('/api/desktop/windows')
    assert response.status_code == 422
    assert response.json()['detail'] == 'Ekran Kaydı izni gerekli.'
    window = WindowInfo(12, 42, 'ERP', 'Title', 0, 0, 800, 600)
    monkeypatch.setattr('rpa_orkestrai.desktop.windows.WindowService.list_windows', Mock(return_value=[window, window]))
    response = client.post('/api/desktop/windows/check', json={'title': 'Title'})
    assert response.status_code == 422
    assert 'Birden fazla' in response.json()['detail']


def test_new_window_flow_validation_and_public_run_error(client, monkeypatch):
    from unittest.mock import Mock

    from rpa_orkestrai.desktop.windows import WindowError

    created = client.post('/api/workflows', json={'steps': [{'action': 'desktop.find_window'}]}).json()
    assert client.post(f"/api/workflows/{created['id']}/run", json={}).status_code == 422
    body = {'steps': [{'action': 'desktop.find_window', 'params': {'title': 'ERP', 'timeout': -1}}]}
    client.put(f"/api/workflows/{created['id']}", json=body)
    assert client.post(f"/api/workflows/{created['id']}/run", json={}).status_code == 422
    body['steps'][0]['params']['timeout'] = 0
    client.put(f"/api/workflows/{created['id']}", json=body)
    monkeypatch.setattr('rpa_orkestrai.desktop.windows.WindowService.find',
                        Mock(side_effect=WindowError('ERP penceresi bulunamadı.')))
    run = client.post(f"/api/workflows/{created['id']}/run", json={}).json()
    deadline = time.monotonic() + 3
    while run['status'] in {'queued', 'running'} and time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run['id']}").json()
        time.sleep(0.01)
    assert run['status'] == 'failed'
    assert run['error'] == 'ERP penceresi bulunamadı.'


def test_update_status_and_checks_do_not_allow_cross_site_requests(tmp_path):
    from unittest.mock import Mock

    settings = Settings(tmp_path, dotenv=False)
    updater = Mock()
    updater.status.return_value = {"enabled": True, "status": "ready", "version": "0.2.0",
                                   "available_version": "0.2.1", "message": "Yeni sürüm hazır."}
    settings.desktop_updates = updater
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/bootstrap").json()["updates"]["status"] == "ready"
        assert client.get("/api/updates").json()["available_version"] == "0.2.1"
        assert client.post("/api/updates/check", headers={"origin": "https://evil.example"}).status_code == 403
        updater.start.assert_not_called()
        assert client.post("/api/updates/check", headers={"origin": "http://testserver"}).status_code == 200
        updater.start.assert_called_once()
