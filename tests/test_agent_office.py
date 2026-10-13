"""Ofis özetinde iş verisi yoktur; paket bütün yerel Three.js kaynaklarını taşır."""

import base64
import hashlib
import json
import re
import shutil
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_agent_api import api as agent_api  # noqa: F401

from rpa_orkestrai.agents.models import Actor, Agent, AgentRun
from rpa_orkestrai.agents.office import snapshot
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
    assert set(result) == {"agents", "departments", "totals"}
    item = result["agents"][0]
    assert set(item) == {"id", "name", "department", "role", "status", "task_id", "task_label", "queue_count"}
    assert item["id"] == ours.id and item["name"] == "Yerel [gizlendi]" and item["status"] == "running"
    assert item["queue_count"] == 2 and item["task_label"] == "Görev üzerinde çalışıyor"
    assert result["departments"] == [{"name": "Operasyon", "agent_count": 1}]
    assert result["totals"] == {"agents": 1, "running": 1, "queued": 2, "waiting": 0}
    encoded = json.dumps(result, ensure_ascii=False)
    for hidden in ("müşteri", "özel başlık", "private", "girdi", "sonuç", "iş özeti", "session-secret", "Diğer firma", foreign.id):
        assert hidden not in encoded


def test_office_snapshot_requires_current_license_and_user_permission(tmp_path):
    def deny():
        raise PermissionError("Ajan modülü kapalı.")

    with pytest.raises(PermissionError):
        snapshot(SimpleNamespace(_authorize=deny, agent_store=AgentStore(tmp_path)))


def test_empty_office_has_only_zero_totals(tmp_path):
    actor = Actor(user_id=1, company_id=1, session_id="session", permissions=("agents.use",))
    value = snapshot(SimpleNamespace(agent_store=AgentStore(tmp_path), _authorize=lambda: actor, _new_redactor=Redactor,
                                     _contexts={}, _lock=threading.RLock()))
    assert value == {"agents": [], "departments": [], "totals": {"agents": 0, "queued": 0, "running": 0, "waiting": 0}}


@pytest.mark.parametrize("module", ["rpa", "agents"])
def test_office_endpoint_is_behind_both_license_gates(agent_api, module):  # noqa: F811
    response = agent_api.client.get("/api/agents/office")
    assert response.status_code == 200 and set(response.json()) == {"agents", "departments", "totals"}
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


@pytest.mark.parametrize("name", ["vendor/three/three.module.js", "vendor/three/addons/controls/OrbitControls.js",
                                  "vendor/three/LICENSE", "office.js"])
def test_packaged_office_check_detects_missing_or_changed_files(tmp_path, name):
    root = Path(__file__).resolve().parents[1] / "src" / "rpa_orkestrai" / "static"
    shutil.copytree(root / "vendor" / "three", tmp_path / "vendor" / "three")
    for item in ("office.js", "office.css", "agents.js", "agents.css"):
        (tmp_path / item).write_text("test", encoding="utf-8")
    if name == "office.js":
        (tmp_path / name).unlink()
    else:
        (tmp_path / name).write_text("değiştirilmiş dosya", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Three.js"):
        _check_office_assets(tmp_path)
