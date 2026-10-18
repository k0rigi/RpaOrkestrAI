"""Ofis özetinde iş verisi yoktur; paket bütün yerel Three.js kaynaklarını taşır."""

import base64
import hashlib
import json
import re
import shutil
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_agent_api import api as agent_api  # noqa: F401

from rpa_orkestrai.agents.models import Actor, Agent, AgentEvent, AgentRun
from rpa_orkestrai.agents.office import human_snapshot, remember_completion, snapshot
from rpa_orkestrai.agents.redaction import Redactor
from rpa_orkestrai.agents.storage import AgentStore
from rpa_orkestrai.package_check import _check_office_assets


def test_office_snapshot_uses_explicit_safe_fields_and_company_scope(tmp_path):
    actor = Actor(user_id=1, company_id=1, name="Kişi", session_id="session-secret", permissions=("agents.use",))
    store = AgentStore(tmp_path)
    ours = store.save_agent(Agent(name="Yerel gizli", department="Operasyon", company_id=1, user_id=1))
    foreign = store.save_agent(Agent(name="Diğer firma", company_id=2, user_id=2))
    for index, state in enumerate(("succeeded", "running", "queued", "queued")):
        store.save_run(AgentRun(agent_id=ours.id, agent_revision=1, actor=actor, task="müşteri ve tutar",
                               title="özel başlık", inputs={"private": "girdi"}, status=state,
                               task_id="a" * 32, created_at=f"2026-10-13T10:0{index}:00+00:00",
                               result={"data": "sonuç"}, error="gizli hata", summary="iş özeti"))
    store.save_run(AgentRun(agent_id=foreign.id, agent_revision=1, actor=actor.model_copy(update={"company_id": 2}),
                           task="diğer görev", status="waiting_approval"))
    contexts = {run.id: SimpleNamespace(run=run, thread=None if run.status == "queued" else object()) for run in store.runs()}
    def forbid_history_reads():
        raise AssertionError("Ofis geçmiş çalışma kayıtlarını okumamalıdır.")

    store.runs = forbid_history_reads
    service = SimpleNamespace(agent_store=store, _authorize=lambda: actor, _new_redactor=lambda: Redactor(["gizli"]),
                              _contexts=contexts, _lock=threading.RLock())
    result = snapshot(service)
    assert set(result) == {"agents", "departments", "totals", "office_name"}
    item = result["agents"][0]
    assert set(item) == {"id", "name", "department", "role", "status", "task_id", "task_label", "queue_count",
                         "kind", "manager_id", "run_id", "activity", "event"}
    assert item["id"] == ours.id and item["name"] == "Yerel [gizlendi]" and item["status"] == "running"
    assert item["queue_count"] == 2 and item["task_label"] == "Görev üzerinde çalışıyor"
    assert result["departments"] == [{"name": "Operasyon", "agent_count": 1}]
    assert result["totals"] == {"agents": 1, "running": 1, "queued": 2, "waiting": 0}
    encoded = json.dumps(result, ensure_ascii=False)
    for hidden in ("müşteri", "özel başlık", "private", "girdi", "sonuç", "iş özeti", "session-secret", "Diğer firma", foreign.id):
        assert hidden not in encoded


def test_activity_delegation_and_short_lived_completion_are_metadata_only(tmp_path, monkeypatch):
    actor = Actor(user_id=1, company_id=1, session_id="session", permissions=("agents.use",))
    store = AgentStore(tmp_path)
    manager = store.save_agent(Agent(name="Yönetici", role="manager", company_id=1, user_id=1))
    child = store.save_agent(Agent(name="Ajan", department="İşler", company_id=1, user_id=1, manager_id=manager.id))
    run = AgentRun(agent_id=manager.id, agent_revision=1, actor=actor, task="ÖZEL İŞ", status="running",
                   events=[AgentEvent(kind="task_delegated", message="GİZLİ", data={"agent_id": child.id, "secret": "SIR"})])
    context = SimpleNamespace(run=run, agent=manager, thread=object(), active_workflow_id=None)
    service = SimpleNamespace(agent_store=store, _authorize=lambda: actor, _new_redactor=Redactor,
                              _contexts={run.id: context}, _lock=threading.RLock())
    item = next(row for row in snapshot(service)["agents"] if row["id"] == manager.id)
    assert item["activity"] == "thinking" and item["event"]["to_agent_id"] == child.id
    context.active_workflow_id = "c" * 32
    assert next(row for row in snapshot(service)["agents"] if row["id"] == manager.id)["activity"] == "workflow"
    run = AgentRun(agent_id=child.id, agent_revision=1, actor=actor, task="ÖZEL İŞ", status="succeeded", summary="SIR")
    context = SimpleNamespace(run=run, agent=child)
    monkeypatch.setattr("rpa_orkestrai.agents.office.time.monotonic", lambda: 100)
    remember_completion(service, context)
    value = snapshot(service)
    completed = next(row for row in value["agents"] if row["id"] == child.id)
    assert completed["status"] == "succeeded" and completed["event"]["to_agent_id"] == manager.id
    assert all(text not in json.dumps(value, ensure_ascii=False) for text in ("SIR", "ÖZEL İŞ", "GİZLİ"))
    monkeypatch.setattr("rpa_orkestrai.agents.office.time.monotonic", lambda: 161)
    assert next(row for row in snapshot(service)["agents"] if row["id"] == child.id)["status"] == "idle"
    assert service._office_recent == {}


def test_human_office_strips_new_fields_and_hidden_task_metadata():
    raw = {"success": True, "people": [{"id": "human-10", "user_id": 10, "name": "Çalışan",
           "status": "running", "task_id": "a" * 32, "queue_count": 4, "can_view_tasks": False,
           "instructions": "ÖZEL", "task_label": "SIR", "department": "ÖZEL", "api_key": "SIR"}]}
    value = human_snapshot(raw)
    item = value["people"][0]
    assert item["status"] == "unknown" and item["task_id"] is None and item["queue_count"] == 0
    assert "SIR" not in json.dumps(value) and "ÖZEL" not in json.dumps(value, ensure_ascii=False)
    raw["people"][0]["can_view_tasks"] = True
    assert human_snapshot(raw)["people"][0]["task_id"] == "a" * 32
    raw["people"][0]["task_id"] = "https://evil.invalid"
    with pytest.raises(ValueError):
        human_snapshot(raw)


def test_human_office_endpoint_is_readonly_masked_and_license_gated(agent_api, monkeypatch):  # noqa: F811
    calls = []

    def respond(method, path, body, **kwargs):
        calls.append((method, path, body, kwargs["expected_actor"].company_id))
        return {"success": True, "people": [{"id": "human-10", "user_id": 10, "name": "Çalışan SIR",
                "status": "idle", "task_id": None, "queue_count": 0, "can_view_tasks": True,
                "instructions": "ÖZEL"}]}

    monkeypatch.setattr(agent_api.app.state.agent_central, "request", respond)
    monkeypatch.setattr(agent_api.app.state.agents, "_new_redactor", lambda: Redactor(["SIR"]))
    response = agent_api.client.get("/api/agents/central/office")
    assert response.status_code == 200 and response.json()["people"][0]["name"] == "Çalışan [gizlendi]"
    assert "ÖZEL" not in response.text and calls == [("GET", "/ofis", None, 2)]
    assert agent_api.client.post("/api/agents/central/office", json={}).status_code == 405
    agent_api.licensing.agents = False
    assert agent_api.client.get("/api/agents/central/office").status_code == 403
    assert len(calls) == 1


def test_office_snapshot_requires_current_license_and_user_permission(tmp_path):
    def deny():
        raise PermissionError("Ajan modülü kapalı.")

    with pytest.raises(PermissionError):
        snapshot(SimpleNamespace(_authorize=deny, agent_store=AgentStore(tmp_path)))


def test_empty_office_has_only_zero_totals(tmp_path):
    actor = Actor(user_id=1, company_id=1, session_id="session", permissions=("agents.use",))
    value = snapshot(SimpleNamespace(agent_store=AgentStore(tmp_path), _authorize=lambda: actor, _new_redactor=Redactor,
                                     _contexts={}, _lock=threading.RLock()))
    assert value == {"agents": [], "departments": [], "office_name": "",
                     "totals": {"agents": 0, "queued": 0, "running": 0, "waiting": 0}}


def test_office_shows_only_the_departments_own_agents_and_its_name(tmp_path):
    claims, logistics = "c" * 32, "d" * 32
    actor = Actor(user_id=1, company_id=1, session_id="session", permissions=("agents.use", "agents.manage"),
                  office_id=claims, office_name="Claim & İade Departmanı")
    store = AgentStore(tmp_path)
    ours = store.save_agent(Agent(name="İade ajanı", company_id=1, user_id=1, office_id=claims))
    legacy = store.save_agent(Agent(name="Önceki ajan", company_id=1, user_id=1))
    store.save_agent(Agent(name="Lojistik ajanı", company_id=1, user_id=5, office_id=logistics))
    store.save_agent(Agent(name="Başkasının eski ajanı", company_id=1, user_id=5))
    value = snapshot(SimpleNamespace(agent_store=store, _authorize=lambda: actor, _new_redactor=Redactor,
                                     _contexts={}, _lock=threading.RLock()))
    assert {item["id"] for item in value["agents"]} == {ours.id, legacy.id}
    assert value["office_name"] == "Claim & İade Departmanı"


@pytest.mark.parametrize("module", ["rpa", "agents"])
def test_office_endpoint_is_behind_both_license_gates(agent_api, module):  # noqa: F811
    response = agent_api.client.get("/api/agents/office")
    assert response.status_code == 200 and set(response.json()) == {"agents", "departments", "totals", "office_name"}
    setattr(agent_api.licensing, module, False)
    assert agent_api.client.get("/api/agents/office").status_code == 403


def test_actual_studio_csp_allows_only_local_office_import_map(agent_api):  # noqa: F811
    response = agent_api.client.get("/")
    content = re.search(r'<script type="importmap">(.*?)</script>', response.text).group(1)
    digest = base64.b64encode(hashlib.sha256(content.encode()).digest()).decode()
    policy = response.headers["Content-Security-Policy"]
    script_policy = next(part for part in policy.split(";") if part.strip().startswith("script-src"))
    assert f"'sha256-{digest}'" in script_policy and "unsafe-inline" not in script_policy
    assert all(value.startswith("/vendor/three/") for value in json.loads(content)["imports"].values())
    assert agent_api.client.get("/vendor/three/LICENSE").status_code == 200


def test_three_files_license_and_revision_are_bundled():
    _check_office_assets()
    from scripts.build_desktop import office_assets

    assert office_assets().name == "static"


def test_windows_checkout_preserves_upstream_vendor_bytes(tmp_path):
    project = Path(__file__).resolve().parents[1]
    relative = Path("src/rpa_orkestrai/static/vendor/three")
    vendor = tmp_path / relative
    shutil.copytree(project / relative, vendor)
    shutil.copyfile(project / ".gitattributes", tmp_path / ".gitattributes")
    original = {str(path.relative_to(vendor)): path.read_bytes() for path in vendor.rglob("*") if path.is_file()}

    def git(*args):
        return subprocess.run(["git", "-c", "core.autocrlf=true", *args], cwd=tmp_path,
                              check=True, capture_output=True)

    git("init", "--quiet")
    git("add", ".gitattributes", relative.as_posix())
    shutil.rmtree(vendor)
    git("checkout-index", "--all", "--force")
    assert {str(path.relative_to(vendor)): path.read_bytes() for path in vendor.rglob("*") if path.is_file()} == original
    root = vendor.parent.parent
    for name in ("office.js", "office.css", "agents.js", "agents.css", "native-office-check.js"):
        shutil.copyfile(project / "src/rpa_orkestrai/static" / name, root / name)
    _check_office_assets(root)


@pytest.mark.parametrize("name", ["three.module.js", "addons/controls/OrbitControls.js", "addons/loaders/GLTFLoader.js",
                                  "addons/utils/BufferGeometryUtils.js", "LICENSE"])
def test_office_integrity_rejects_changed_line_endings(tmp_path, name):
    root = Path(__file__).resolve().parents[1] / "src" / "rpa_orkestrai" / "static"
    vendor = tmp_path / "vendor" / "three"
    shutil.copytree(root / "vendor" / "three", vendor)
    for item in ("office.js", "office.css", "agents.js", "agents.css", "native-office-check.js"):
        shutil.copyfile(root / item, tmp_path / item)
    target = vendor / name
    original = target.read_bytes()
    changed = original.replace(b"\n", b"\r\n")
    assert changed != original
    target.write_bytes(changed)
    with pytest.raises(RuntimeError, match="Three.js"):
        _check_office_assets(tmp_path)


@pytest.mark.parametrize("name", ["vendor/three/three.module.js", "vendor/three/addons/controls/OrbitControls.js",
                                  "vendor/three/addons/loaders/GLTFLoader.js", "vendor/three/addons/utils/BufferGeometryUtils.js",
                                  "vendor/three/LICENSE", "office.js", "native-office-check.js"])
def test_packaged_office_check_detects_missing_or_changed_files(tmp_path, name):
    root = Path(__file__).resolve().parents[1] / "src" / "rpa_orkestrai" / "static"
    shutil.copytree(root / "vendor" / "three", tmp_path / "vendor" / "three")
    for item in ("office.js", "office.css", "agents.js", "agents.css", "native-office-check.js"):
        (tmp_path / item).write_text("test", encoding="utf-8")
    if name in {"office.js", "native-office-check.js"}:
        (tmp_path / name).unlink()
    else:
        (tmp_path / name).write_text("değiştirilmiş dosya", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Three.js"):
        _check_office_assets(tmp_path)
