"""Ajan otomasyonları: zaman, akış ve klasör tetikleyicileri elle verilen görevle aynı sınırlarla çalışır."""

import threading
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from test_agent_runner import AGENT_TEST_SECONDS, finish, response, run_call, wait_for
from test_agent_runner import runtime as runtime  # noqa: F401

from rpa_orkestrai.agents.automations import AutomationInput, AutomationService, AutomationTrigger
from rpa_orkestrai.agents.models import AgentRunRequest
from rpa_orkestrai.agents.providers import ScriptedProvider
from rpa_orkestrai.agents.runner import AgentServiceError
from rpa_orkestrai.models import Step


@pytest.fixture
def auto(runtime):
    clock = [datetime(2026, 10, 16, 8, 0)]
    service = AutomationService(runtime.service, runtime.settings.data_dir, clock=lambda: clock[0])
    runtime.state["provider"] = ScriptedProvider([], callback=lambda request: response(finish()))
    return SimpleNamespace(runtime=runtime, service=service, clock=clock)


def body(agent, **trigger):
    return AutomationInput(name="Sabah özeti", agent_id=agent.id, task="Günün özetini hazırla",
                           inputs={"bolum": "İade"}, trigger=AutomationTrigger(**trigger))


def runs(runtime):
    return sorted(runtime.service.agent_store.runs(), key=lambda run: run.created_at)


def settle(runtime):
    return [runtime.done(run) for run in runs(runtime)]


def test_daily_schedule_starts_once_with_the_same_agent_rules_and_skips_missed_times(auto):
    agent = auto.runtime.agent()
    created = auto.service.create(body(agent, kind="schedule", schedule_kind="daily", time="09:00"))
    assert created["next_run_at"] == "2026-10-16T09:00" and created["summary"] == "Her gün 09:00"
    auto.clock[0] = datetime(2026, 10, 16, 8, 59)
    auto.service.tick()
    assert runs(auto.runtime) == []
    auto.clock[0] = datetime(2026, 10, 16, 9, 1)
    auto.service.tick()
    auto.service.tick()  # The same due time never starts twice.
    started = settle(auto.runtime)
    assert len(started) == 1 and started[0].title == "Otomatik: Sabah özeti"
    assert started[0].inputs == {"bolum": "İade", "tetikleme_zamani": "2026-10-16T09:00"}
    assert any(event.kind == "automation" and event.data["automation_id"] == created["id"] for event in started[0].events)
    current = auto.service.automations()[0]
    assert current["last_status"] == "started" and current["next_run_at"] == "2026-10-17T09:00"
    # The Studio was closed past the allowed delay: recorded as missed, nothing is started late.
    auto.clock[0] = datetime(2026, 10, 17, 10, 30)
    auto.service.tick()
    assert len(runs(auto.runtime)) == 1
    current = auto.service.automations()[0]
    assert current["last_status"] == "missed" and current["next_run_at"] == "2026-10-18T09:00"


def test_running_previous_task_and_hourly_limit_skip_new_starts(auto):
    gate = threading.Event()
    auto.runtime.state["provider"] = ScriptedProvider([], callback=lambda request: (gate.wait(AGENT_TEST_SECONDS), response(finish()))[1])
    agent = auto.runtime.agent()
    created = auto.service.create(body(agent, kind="schedule", schedule_kind="interval", time="08:00", every_minutes=5,
                                       days=list(range(7))))
    auto.clock[0] = datetime(2026, 10, 16, 8, 5)
    auto.service.tick()
    auto.clock[0] = datetime(2026, 10, 16, 8, 10)
    auto.service.tick()
    assert len(runs(auto.runtime)) == 1
    assert auto.service.automations()[0]["last_status"] == "skipped"
    with pytest.raises(AgentServiceError) as error:
        auto.service.run_now(created["id"])
    assert error.value.status_code == 409
    gate.set()
    settle(auto.runtime)
    book = auto.service._read()
    book.automations[0].recent_starts = [datetime(2026, 10, 16, 8, 11).isoformat(timespec="seconds")] * 30
    auto.service._write(book)
    auto.clock[0] = datetime(2026, 10, 16, 8, 15)
    auto.service.tick()
    assert len(runs(auto.runtime)) == 1 and "en fazla 30" in auto.service.automations()[0]["last_message"]


def test_workflow_trigger_reacts_to_person_runs_but_never_to_the_agents_own_flow(auto):
    flow = auto.runtime.workflow(Step(action="core.set", params={"name": "value", "value": 1}))
    agent = auto.runtime.agent(flow)
    auto.service.create(body(agent, kind="workflow", workflow_id=flow.id, outcome="failed"))
    auto.runtime.manager.finished_listeners.append(auto.service.workflow_finished)
    manual = auto.runtime.manager.start(flow)
    wait_for(lambda: auto.runtime.store.run(manual.id), lambda run: run.finished_at is not None)
    wait_for(lambda: list(auto.service._events), lambda events: len(events) == 1)
    auto.service.tick()
    assert runs(auto.runtime) == []  # The flow succeeded; the trigger asks for failures.
    auto.service.workflow_finished(SimpleNamespace(workflow_id=flow.id, status="failed", id="f" * 32,
                                                   workflow_name="İş akışı", error="Hedef bulunamadı"))
    auto.service.tick()
    started = settle(auto.runtime)
    assert started[0].inputs["akis_durumu"] == "failed" and started[0].inputs["akis_hatasi"] == "Hedef bulunamadı"
    # A flow started by an agent is never reported, so an automation cannot trigger itself in a loop.
    auto.runtime.state["provider"] = ScriptedProvider([response(run_call(flow)), response(finish())])
    agent_run = auto.runtime.done(auto.runtime.service.start(agent.id, AgentRunRequest(task="Akışı çalıştır")))
    assert agent_run.workflow_count == 1
    assert list(auto.service._events) == []


def test_folder_trigger_waits_for_complete_new_files_and_ignores_existing_and_temporary_ones(auto, tmp_path):
    folder = tmp_path / "gelen"
    folder.mkdir()
    (folder / "eski.pdf").write_bytes(b"1")
    agent = auto.runtime.agent()
    auto.service.create(body(agent, kind="folder", folder=str(folder), pattern="*.pdf"))
    (folder / "yeni.pdf").write_bytes(b"12")
    for name in ("~$kilit.pdf", ".gizli.pdf", "indiriliyor.pdf.crdownload", "not.txt"):
        (folder / name).write_bytes(b"x")
    auto.service.tick()
    assert runs(auto.runtime) == []  # First sighting: the file may still be copying.
    auto.service.tick()
    started = settle(auto.runtime)
    assert len(started) == 1 and started[0].inputs["dosya_adi"] == "yeni.pdf"
    assert started[0].inputs["dosya_yolu"] == str(folder / "yeni.pdf")
    auto.service.tick()
    assert len(runs(auto.runtime)) == 1


def test_only_managers_change_automations_and_secrets_or_bad_triggers_are_refused(auto, tmp_path):
    agent = auto.runtime.agent()
    with pytest.raises(ValueError):
        AutomationTrigger(kind="workflow")
    with pytest.raises(ValueError):
        AutomationTrigger(kind="folder", folder="göreli/klasör")
    with pytest.raises(AgentServiceError):
        auto.service.create(body(agent, kind="folder", folder=str(tmp_path / "olmayan-klasor")))
    with pytest.raises(AgentServiceError, match="geçmişte"):
        auto.service.create(body(agent, kind="schedule", schedule_kind="once", date="2026-10-15", time="09:00"))
    created = auto.service.create(body(agent))
    auto.runtime.state["actor"] = auto.runtime.owner.model_copy(update={"user_id": 7, "permissions": ("agents.use",)})
    assert len(auto.service.automations()) == 1
    for action in (lambda: auto.service.create(body(agent)), lambda: auto.service.delete(created["id"]),
                   lambda: auto.service.run_now(created["id"])):
        with pytest.raises(AgentServiceError) as error:
            action()
        assert error.value.status_code == 403
    auto.runtime.state["actor"] = auto.runtime.owner
    auto.runtime.state["gate"] = False
    auto.clock[0] = datetime(2026, 10, 16, 9, 5)
    auto.service.tick()  # No licensed session: nothing starts.
    assert runs(auto.runtime) == []
    auto.runtime.state["gate"] = True
    updated = auto.service.update(created["id"], body(agent, kind="schedule", schedule_kind="daily", time="18:00"))
    assert updated["next_run_at"] == "2026-10-16T18:00"
    auto.service.delete(created["id"])
    assert auto.service.automations() == []


def test_routes_precede_agent_routes(tmp_path):
    from fastapi.testclient import TestClient
    from test_agent_api import AgentLicense

    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    app = create_app(Settings(tmp_path, dotenv=False), licensing=AgentLicense())
    with TestClient(app) as client:
        agent = client.post("/api/agents", json={"name": "Analiz", "model": "test"}).json()
        assert client.get("/api/agents/automations").json() == []
        created = client.post("/api/agents/automations", json={
            "name": "Haftalık", "agent_id": agent["id"], "task": "Raporu hazırla",
            "trigger": {"kind": "schedule", "schedule_kind": "weekly", "days": [0], "time": "08:30"}})
        assert created.status_code == 201, created.text
        assert created.json()["summary"] == "Pzt 08:30"
        assert client.post("/api/agents/automations", json={"name": "X", "agent_id": agent["id"], "task": "Y",
                                                              "unknown": 1}).status_code == 422
        identity = created.json()["id"]
        assert client.delete(f"/api/agents/automations/{identity}").status_code == 204
        assert app.state.automations.workflow_finished in app.state.manager.finished_listeners


def rows_body(agent, path, **trigger):
    return AutomationInput(name="Gelen siparişler", agent_id=agent.id, task="Yeni siparişi işle",
                           trigger=AutomationTrigger(kind="rows", source="file", file_path=str(path), key_column="No",
                                                     check_minutes=1, **trigger))


def test_new_table_rows_are_queued_one_by_one_and_existing_rows_are_left_alone(auto, tmp_path):
    gate = threading.Event()
    auto.runtime.state["provider"] = ScriptedProvider([], callback=lambda request: (gate.wait(AGENT_TEST_SECONDS), response(finish()))[1])
    table = tmp_path / "siparisler.csv"
    table.write_text("No;Müşteri;Durum\nS-1;Ege;Bekliyor\n", encoding="utf-8")
    agent = auto.runtime.agent()
    created = auto.service.create(rows_body(agent, table, filter_column="Durum", filter_value="bekliyor"))
    assert "anahtar: No" in created["summary"]
    auto.service.tick()
    assert runs(auto.runtime) == []  # S-1 was there when the automation was saved.
    table.write_text("No;Müşteri;Durum\nS-1;Ege;Bekliyor\nS-2;Kuzey;Bekliyor\nS-3;Güney;Bekliyor\nS-4;Batı;Tamam\n",
                     encoding="utf-8")
    auto.clock[0] += timedelta(minutes=1)
    auto.service.tick()
    started = runs(auto.runtime)
    assert len(started) == 1 and started[0].inputs["kayit_anahtari"] == "S-2"
    assert started[0].inputs["kayit"]["Musteri"] == "Kuzey"  # «Müşteri» is written ${kayit.Musteri} in a flow.
    assert auto.service.automations()[0]["queue_count"] == 1  # S-3 waits; S-4 does not match the filter.
    gate.set()
    settle(auto.runtime)
    auto.clock[0] += timedelta(seconds=20)
    auto.service.tick()
    finished = settle(auto.runtime)
    assert [run.inputs["kayit_anahtari"] for run in finished] == ["S-2", "S-3"]
    assert auto.service.automations()[0]["queue_count"] == 0


def test_rows_from_a_database_query_and_a_missing_key_column_is_explained(auto, tmp_path):
    import sqlite3

    from rpa_orkestrai.connections import Connections

    database = tmp_path / "erp.db"
    with sqlite3.connect(database) as connection:
        connection.executescript("CREATE TABLE siparis (id INTEGER, durum TEXT); INSERT INTO siparis VALUES (1, 'yeni');")
    connection.close()
    created = Connections(auto.runtime.settings.data_dir).create(
        {"name": "ERP", "type": "database", "config": {"engine": "sqlite", "path": str(database)}})
    agent = auto.runtime.agent()
    trigger = dict(kind="rows", source="database", connection_id=created["id"], query="SELECT id, durum FROM siparis",
                   check_minutes=1)
    with pytest.raises(AgentServiceError, match="“No” sütunu bulunamadı. Tablodaki sütunlar: id, durum"):
        auto.service.create(AutomationInput(name="DB", agent_id=agent.id, task="İşle",
                                            trigger=AutomationTrigger(key_column="No", **trigger)))
    with pytest.raises(ValueError, match="değişken"):
        AutomationTrigger(kind="rows", source="database", key_column="id", query="SELECT * FROM t WHERE a = ${x}")
    with pytest.raises(ValueError, match="okuma"):
        AutomationTrigger(kind="rows", source="database", key_column="id", query="DELETE FROM siparis WHERE id = 1")
    auto.service.create(AutomationInput(name="DB", agent_id=agent.id, task="İşle",
                                        trigger=AutomationTrigger(key_column="ID", process_existing=True, **trigger)))
    auto.service.tick()
    started = settle(auto.runtime)
    assert started[0].inputs == {"kayit": {"id": 1, "durum": "yeni"}, "kayit_anahtari": "1"}


def test_new_mail_after_saving_reaches_the_agent_with_its_attachment(auto, tmp_path, monkeypatch):
    from email.message import EmailMessage

    from test_integrations_enterprise import FakeIMAP

    from rpa_orkestrai.connections import Connections
    from rpa_orkestrai.integrations import imap

    def mail(subject):
        message = EmailMessage()
        message["From"], message["Subject"] = "fatura@tedarikci.com", subject
        message.set_content("Fatura ekte.")
        message.add_attachment(b"%PDF", maintype="application", subtype="pdf", filename=f"{subject}.pdf")
        return message

    fake = FakeIMAP({5: mail("Eski")})
    monkeypatch.setattr(imap, "connect", lambda config, timeout: fake)
    box = Connections(auto.runtime.settings.data_dir).create(
        {"name": "Faturalar", "type": "imap", "config": {"host": "imap.x.com", "user": "fatura@firma.com",
                                                         "password": "uygulama-sifresi-9"}})
    agent = auto.runtime.agent()
    attachments = tmp_path / "ekler"
    created = auto.service.create(AutomationInput(name="Fatura postası", agent_id=agent.id, task="Faturayı işle",
                                                  trigger=AutomationTrigger(kind="email", connection_id=box["id"],
                                                                            subject_contains="fatura",
                                                                            attachment_folder=str(attachments))))
    assert "Faturalar (INBOX) yeni e-posta geldiğinde" in created["summary"]
    fake.messages[6] = mail("Fatura F-9")
    fake.messages[7] = mail("Toplantı")
    auto.service.tick()
    assert runs(auto.runtime) == []  # The mailbox is checked every 5 minutes by default.
    auto.clock[0] += timedelta(minutes=5)
    auto.service.tick()
    started = settle(auto.runtime)
    assert len(started) == 1
    message = started[0].inputs["eposta"]
    assert message["subject"] == "Fatura F-9" and message["attachments"][0]["path"] == str(attachments / "Fatura F-9.pdf")
    assert (attachments / "Fatura F-9.pdf").read_bytes() == b"%PDF" and fake.stored == []


def test_an_automation_can_run_a_flow_directly_and_that_flow_never_triggers_another_automation(auto, tmp_path):
    out = tmp_path / "isler"
    out.mkdir()
    flow = auto.runtime.workflow(Step(action="file.write_text", params={
        "path": str(out / "${kayit_anahtari}.txt"), "text": "${kayit.Musteri}"}))
    service = AutomationService(auto.runtime.service, auto.runtime.settings.data_dir, clock=lambda: auto.clock[0],
                                manager=auto.runtime.manager, dispatch=auto.runtime.service.dispatch)
    auto.runtime.manager.finished_listeners.append(service.workflow_finished)
    agent = auto.runtime.agent()
    table = tmp_path / "siparisler.csv"
    table.write_text("No,Müşteri\n", encoding="utf-8")
    with pytest.raises(ValueError, match="kendi bitişiyle"):
        AutomationInput(name="Döngü", target="workflow", target_workflow_id=flow.id,
                        trigger=AutomationTrigger(kind="workflow", workflow_id=flow.id))
    service.create(AutomationInput(name="Sipariş akışı", target="workflow", target_workflow_id=flow.id,
                                   trigger=AutomationTrigger(kind="rows", source="file", file_path=str(table),
                                                             key_column="No", check_minutes=1)))
    # A second automation listens for the flow; the automation's own run must not reach it.
    service.create(AutomationInput(name="İzleyici", agent_id=agent.id, task="Bildir",
                                   trigger=AutomationTrigger(kind="workflow", workflow_id=flow.id)))
    table.write_text("No,Müşteri\nS-7,Ege Üretim\n", encoding="utf-8")
    auto.clock[0] += timedelta(minutes=1)
    service.tick()
    wait_for(lambda: (out / "S-7.txt").exists() and service.automations()[0]["last_status"], lambda value: value == "started")
    assert (out / "S-7.txt").read_text(encoding="utf-8") == "Ege Üretim"
    run_id = service.automations()[0]["last_run_id"]
    wait_for(lambda: auto.runtime.store.run(run_id).finished_at, lambda value: value is not None)
    service.tick()
    assert list(service._events) == [] and runs(auto.runtime) == []
