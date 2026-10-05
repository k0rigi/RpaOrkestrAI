"""Named connections selected per step (n8n-style credentials); secrets never leave the workspace."""

import json
import threading

import pytest
from fastapi.testclient import TestClient

from rpa_orkestrai.app import create_app
from rpa_orkestrai.config import Settings
from rpa_orkestrai.connections import Connections
from rpa_orkestrai.engine import Executor, WorkflowError
from rpa_orkestrai.integrations.apps_script import AppsScriptSheets
from rpa_orkestrai.models import Run, Step, Workflow
from rpa_orkestrai.storage import Store

URL_A = "https://script.google.com/macros/s/AKfycbA" + "a" * 40 + "/exec"
URL_B = "https://script.google.com/macros/s/AKfycbB" + "b" * 40 + "/exec"
TOKEN_A, TOKEN_B = "A" * 32, "B" * 32
SHEET = "https://docs.google.com/spreadsheets/d/1" + "x" * 30 + "/edit"


def test_old_settings_become_default_profiles(tmp_path):
    settings = Settings(tmp_path, dotenv=False)
    settings.update({"database_url": "postgresql+psycopg://reader:GIZLI@db/erp", "google_credentials_path": "/k.json",
                     "sheets_connection": "apps_script", "sheets_script_url": URL_A, "sheets_script_token": TOKEN_A})
    connections = Connections(tmp_path, settings)
    listed = {item["type"]: item for item in connections.list()}
    assert listed["google_sheets"]["method"] == "apps_script" and listed["google_sheets"]["default"]
    assert listed["database"]["allowed_tables"] and listed["database"]["engine"] == "url"
    assert listed["database"]["url_kind"] == "postgresql"
    assert "GIZLI" not in json.dumps(connections.list()) and TOKEN_A not in json.dumps(connections.list())
    # Migration runs once; later settings changes do not recreate profiles.
    settings.update({"database_url": ""})
    assert len(Connections(tmp_path, settings).list()) == 2


def test_profiles_are_named_validated_and_keep_secrets(tmp_path):
    connections = Connections(tmp_path)
    first = connections.create({"type": "google_sheets", "name": "Satış",
                                "config": {"method": "apps_script", "script_url": URL_A, "script_token": TOKEN_A}})
    assert first["default"] and first["ready"] and first["has_token"] and "script_token" not in first
    second = connections.create({"type": "google_sheets", "name": "İade",
                                 "config": {"method": "apps_script", "script_url": URL_B, "script_token": TOKEN_B}})
    assert not second["default"]
    with pytest.raises(ValueError, match="zaten var"):
        connections.create({"type": "google_sheets", "name": "satış", "config": {}})
    with pytest.raises(ValueError, match="ad"):
        connections.create({"type": "database", "name": " ", "config": {}})
    with pytest.raises(ValueError):
        connections.create({"type": "google_sheets", "name": "Kötü", "config": {"script_url": "https://example.com"}})
    # A blank token in an update keeps the stored one.
    connections.update(first["id"], {"name": "Satış tablosu", "config": {"script_url": URL_A, "script_token": ""}})
    assert connections.get(first["id"])["config"]["script_token"] == TOKEN_A
    connections.update(second["id"], {"default": True})
    assert connections.resolve(None, "google_sheets")["id"] == second["id"]
    connections.delete(second["id"])
    assert connections.resolve(None, "google_sheets")["id"] == first["id"]
    with pytest.raises(WorkflowError, match="bu bilgisayarda yok"):
        connections.resolve("f" * 32, "google_sheets")
    with pytest.raises(WorkflowError, match="tanımlı değil"):
        connections.resolve(None, "database")
    incomplete = connections.create({"type": "database", "name": "ERP", "config": {"allowed_tables": "public.A"}})
    with pytest.raises(WorkflowError, match="eksik"):
        connections.resolve(incomplete["id"], "database")


class FakeScript:
    calls = []

    def __init__(self, url, token, spreadsheet, sheet, **kwargs):
        self.url, self.token = url, token

    def update_cell(self, cell, value, raw=True):
        FakeScript.calls.append((self.url, self.token, cell, value))

    def get_range(self, a1):
        return [["x"]]

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def test_each_step_uses_its_own_connection_and_logs_hide_secrets(tmp_path, monkeypatch):
    settings = Settings(tmp_path, dotenv=False)
    connections = Connections(tmp_path)
    a = connections.create({"type": "google_sheets", "name": "A",
                            "config": {"method": "apps_script", "script_url": URL_A, "script_token": TOKEN_A}})
    b = connections.create({"type": "google_sheets", "name": "B",
                            "config": {"method": "apps_script", "script_url": URL_B, "script_token": TOKEN_B}})
    monkeypatch.setattr("rpa_orkestrai.integrations.apps_script.AppsScriptSheets", FakeScript)
    FakeScript.calls = []
    store = Store(tmp_path)
    run = Run(workflow_id="0" * 32, workflow_name="T", department="Genel")
    runner = Executor(settings, store, run, threading.Event(), lambda: store.save_run(run))
    runner.execute(Workflow(steps=[
        Step(action="sheets.write_cell", params={"spreadsheet_id": SHEET, "worksheet": "S", "cell": "A1", "value": "1"}),
        Step(action="sheets.write_cell", params={"connection": b["id"], "spreadsheet_id": SHEET, "worksheet": "S",
                                                 "cell": "A2", "value": "2"}),
        Step(action="core.log", params={"message": f"anahtar {TOKEN_B}"}),
    ]))
    assert FakeScript.calls == [(URL_A, TOKEN_A, "A1", "1"), (URL_B, TOKEN_B, "A2", "2")]
    assert a["default"]
    assert all(TOKEN_B not in event.message for event in run.events)


def test_connections_api(tmp_path, monkeypatch):
    with TestClient(create_app(Settings(tmp_path, dotenv=False))) as api:
        code = api.post("/api/connections/apps-script-code", json={}).json()
        assert code["token"] in code["code"]
        created = api.post("/api/connections", json={"type": "google_sheets", "name": "Satış", "config": {
            "method": "apps_script", "script_url": URL_A, "script_token": code["token"]}})
        assert created.status_code == 201
        profile = created.json()
        listed = api.get("/api/connections").text
        assert code["token"] not in listed and "Satış" in listed
        again = api.post("/api/connections/apps-script-code", json={"id": profile["id"]}).json()
        assert again["token"] == code["token"]
        renewed = api.post("/api/connections/apps-script-code", json={"id": profile["id"], "renew": True}).json()
        assert renewed["token"] != code["token"]
        monkeypatch.setattr(AppsScriptSheets, "ping", lambda self: {"ok": True, "spreadsheet": "Faturalar"})
        tested = api.post("/api/connections/test", json={"type": "google_sheets", "id": profile["id"], "config": {}})
        assert tested.json()["message"] == "Bağlantı çalışıyor: Faturalar."
        key = tmp_path / "anahtar.json"
        key.write_text(json.dumps({"client_email": "rpa@proje.iam.gserviceaccount.com"}), encoding="utf-8")
        service = api.post("/api/connections/test", json={"type": "google_sheets", "config": {
            "method": "service_account", "credentials_path": str(key)}}).json()
        assert "rpa@proje.iam.gserviceaccount.com" in service["message"]
        assert api.post("/api/connections", json={"type": "ftp", "name": "x"}).status_code == 422
        workflow = api.post("/api/workflows", json={"name": "A", "steps": [
            {"action": "sheets.write_cell", "params": {"connection": profile["id"], "spreadsheet_id": SHEET,
                                                        "worksheet": "S", "cell": "A1", "value": "x"}}]}).json()
        exported = api.get(f"/api/workflows/{workflow['id']}/export").text
        assert profile["id"] in exported and renewed["token"] not in exported and URL_A not in exported
        assert api.delete(f"/api/connections/{profile['id']}").status_code == 204
        assert api.get("/api/connections").json() == []
