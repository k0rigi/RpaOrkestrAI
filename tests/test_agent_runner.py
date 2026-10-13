import json
import threading
import time
from types import SimpleNamespace

import pytest

from rpa_orkestrai.agents.models import Actor, AgentInput, AgentLimits, AgentRunRequest, WorkflowGrant
from rpa_orkestrai.agents.providers import ProviderResponse, ScriptedProvider, ToolCall, Usage
from rpa_orkestrai.agents.runner import AgentService, AgentServiceError
from rpa_orkestrai.config import Settings
from rpa_orkestrai.engine import RunManager
from rpa_orkestrai.models import Run, Step, Workflow, now, uid
from rpa_orkestrai.storage import Store


def response(*calls, text="", usage=None):
    return ProviderResponse(text=text, tool_calls=list(calls), usage=usage or Usage())


def finish(summary="Tamamlandı"):
    return ToolCall(uid(), "finish", {"summary": summary, "result": {"ok": True}})


def run_call(workflow, *, inputs=None, identity=None):
    return ToolCall(identity or uid(), "run_workflow", {"workflow_id": workflow.id,
                                                       "inputs": inputs or {}, "reason": "Görevi tamamla"})


def wait_for(get, predicate, timeout=4):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = get()
        if predicate(value):
            return value
        threading.Event().wait(0.01)
    pytest.fail(f"Beklenen duruma ulaşılmadı: {get()}")


@pytest.fixture
def runtime(tmp_path):
    settings = Settings(tmp_path / "data", dotenv=False)
    store = Store(settings.data_dir)
    manager = RunManager(settings, store)
    owner = Actor(user_id=1, company_id=2, name="Yetkili", session_id="session",
                  permissions=["agents.use", "agents.manage", "agents.approve"])
    state = {"actor": owner, "gate": True, "provider": ScriptedProvider([])}
    service = AgentService(settings, store, manager, actor=lambda: state["actor"],
                           gate=lambda: state["gate"], provider_factory=lambda agent: state["provider"])
    business = tmp_path / "business"
    business.mkdir()

    def workflow(*steps):
        item = Workflow(name="İş akışı", steps=list(steps))
        store.save_workflow(item)
        return item

    def agent(flow=None, *, limits=None, bypass=False, grants=None):
        permissions = grants if grants is not None else ([WorkflowGrant(
            workflow_id=flow.id, allow_without_approval=bypass, allowed_roots=[str(business)])] if flow else [])
        return service.create_agent(AgentInput(name="Ajan", model="test", workflows=permissions,
                                               limits=limits or AgentLimits(max_seconds=5)))

    def start(item, *replies):
        state["provider"] = ScriptedProvider(list(replies))
        return service.start(item.id, AgentRunRequest(task="İşi tamamla"))

    def done(run):
        return wait_for(lambda: service.agent_store.run(run.id), lambda value: value.finished_at is not None)

    yield SimpleNamespace(settings=settings, store=store, manager=manager, service=service, state=state,
                          owner=owner, business=business, workflow=workflow, agent=agent, start=start, done=done)
    service.close()
    manager.close()


def test_read_flow_returns_masked_variables_and_preserves_legacy_trigger(runtime):
    flow = runtime.workflow(Step(action="core.set", params={"name": "answer", "value": "${input_value}"}))
    item = runtime.agent(flow)
    run = runtime.start(item, response(run_call(flow, inputs={"input_value": "Değer"})), response(finish()))
    saved = runtime.done(run)
    assert saved.status == "succeeded" and saved.workflow_count == 1
    child = runtime.store.run(saved.workflow_run_ids[0])
    assert child.variables["answer"] == "Değer" and child.trigger == "manual"
    history = runtime.state["provider"].requests[1]["messages"]
    result = json.loads(next(entry["content"] for entry in history if entry["role"] == "tool"))
    assert result["untrusted_data"]["variables"]["answer"] == "Değer"
    assert "sistem" not in result["untrusted_data"]["variables"]
    audited = [event.data["payload"] for event in saved.events if event.kind == "provider_request"]
    assert audited == runtime.state["provider"].requests


def test_direct_and_indirect_unauthorized_flows_are_not_started(runtime):
    private = runtime.workflow(Step(action="core.set", params={"name": "private", "value": 1}))
    parent = runtime.workflow(Step(action="control.run_workflow", params={"workflow": private.id}))
    item = runtime.agent(parent)
    run = runtime.start(item, response(run_call(private)), response(run_call(parent)), response(finish()))
    saved = runtime.done(run)
    assert saved.workflow_count == 0 and not runtime.store.runs()
    assert any(event.kind == "tool_result" and "izni yok" in json.dumps(event.data, ensure_ascii=False)
               for event in saved.events)


def write_flow(runtime):
    target = runtime.business / "result.txt"
    flow = runtime.workflow(Step(action="file.write_text", params={"path": str(target), "text": "Yazıldı",
                                                                   "mode": "append"}))
    return flow, target


def approval_wait(runtime, run):
    return wait_for(lambda: runtime.service.get_run(run.id), lambda value: value.status == "waiting_approval")


def test_risky_flow_waits_for_single_use_approval(runtime):
    flow, target = write_flow(runtime)
    run = runtime.start(runtime.agent(flow), response(run_call(flow)), response(finish()))
    pending = approval_wait(runtime, run)
    assert not target.exists() and not runtime.store.runs() and not runtime.manager.busy()
    key = pending.pending_approval["id"]
    runtime.service.approve(run.id, key, True)
    with pytest.raises(AgentServiceError):
        runtime.service.approve(run.id, key, True)
    saved = runtime.done(run)
    assert saved.status == "succeeded" and target.read_text(encoding="utf-8") == "Yazıldı"
    assert len([event for event in saved.events if event.kind == "approval_consumed"]) == 1


@pytest.mark.parametrize("decision", ["reject", "expire"])
def test_rejected_or_expired_approval_never_runs(runtime, decision):
    flow, target = write_flow(runtime)
    item = runtime.agent(flow, limits=AgentLimits(max_seconds=5, approval_timeout_seconds=0.15))
    run = runtime.start(item, response(run_call(flow)), response(finish()))
    pending = approval_wait(runtime, run)
    if decision == "reject":
        runtime.service.approve(run.id, pending.pending_approval["id"], False)
    saved = runtime.done(run)
    assert not target.exists() and saved.workflow_count == 0


def test_approval_cannot_cover_a_changed_workflow(runtime):
    flow, target = write_flow(runtime)
    run = runtime.start(runtime.agent(flow), response(run_call(flow)), response(finish()))
    pending = approval_wait(runtime, run)
    flow.steps[0].params["text"] = "Değişti"
    runtime.store.save_workflow(flow)
    runtime.service.approve(run.id, pending.pending_approval["id"], True)
    saved = runtime.done(run)
    assert saved.status == "failed" and "değişti" in saved.error and not target.exists()


def test_only_claimed_owner_can_approve(runtime):
    flow, target = write_flow(runtime)
    run = runtime.start(runtime.agent(flow), response(run_call(flow)), response(finish()))
    pending = approval_wait(runtime, run)
    runtime.state["actor"] = runtime.owner.model_copy(update={"permissions": ("agents.use", "agents.manage")})
    with pytest.raises(AgentServiceError) as denied:
        runtime.service.approve(run.id, pending.pending_approval["id"], True)
    assert denied.value.status_code == 403 and not target.exists()
    runtime.service.cancel(run.id)
    assert runtime.done(run).status == "cancelled"


def test_bypass_is_revision_bound_and_retry_still_requires_approval(runtime):
    flow, target = write_flow(runtime)
    item = runtime.agent(flow, bypass=True)
    run = runtime.start(item, response(run_call(flow)), response(run_call(flow)), response(finish()))
    pending = approval_wait(runtime, run)
    assert target.read_text(encoding="utf-8") == "Yazıldı"
    runtime.service.approve(run.id, pending.pending_approval["id"], False)
    assert runtime.done(run).workflow_count == 1
    flow.steps[0].params["text"] = "Yeni tanım"
    runtime.store.save_workflow(flow)
    run = runtime.start(item, response(run_call(flow)), response(finish()))
    pending = approval_wait(runtime, run)
    runtime.service.approve(run.id, pending.pending_approval["id"], False)
    assert runtime.done(run).workflow_count == 0


def test_unprivileged_editor_cannot_grant_bypass(runtime):
    flow, _ = write_flow(runtime)
    runtime.state["actor"] = runtime.owner.model_copy(update={"permissions": ("agents.use", "agents.manage")})
    with pytest.raises(AgentServiceError) as denied:
        runtime.agent(flow, bypass=True)
    assert denied.value.status_code == 403


def test_editing_name_does_not_reapprove_changed_workflows_and_bypass_has_audit(runtime):
    flow, _ = write_flow(runtime)
    item = runtime.agent(flow, bypass=True)
    assert item.permission_audit[0].user_id == runtime.owner.user_id
    assert item.permission_audit[0].allow_without_approval
    original = item.grant_revisions[flow.id]
    flow.steps[0].params["text"] = "Yeni işlem"
    runtime.store.save_workflow(flow)
    body = AgentInput(name="Yeni ad", model="test", workflows=item.workflows)
    updated = runtime.service.update_agent(item.id, body)
    assert updated.grant_revisions[flow.id] == original
    body.workflows[0].allow_without_approval = False
    updated = runtime.service.update_agent(item.id, body)
    assert updated.permission_audit[-1].allow_without_approval is False
    body.workflows[0].allow_without_approval = True
    updated = runtime.service.update_agent(item.id, body)
    assert updated.permission_audit[-1].allow_without_approval is True
    assert updated.grant_revisions[flow.id] != original


def test_question_answer_is_audited_and_cannot_be_replayed(runtime):
    item = runtime.agent()
    run = runtime.start(item, response(ToolCall(uid(), "ask_user", {"question": "Hangisi?", "options": ["A", "B"]})),
                        response(finish()))
    pending = wait_for(lambda: runtime.service.get_run(run.id), lambda value: value.status == "waiting_user")
    runtime.service.answer(run.id, pending.pending_question["id"], "A")
    with pytest.raises(AgentServiceError):
        runtime.service.answer(run.id, pending.pending_question["id"], "B")
    saved = runtime.done(run)
    assert saved.status == "succeeded" and any(event.kind == "user_answer" for event in saved.events)


def test_question_expiry_fails_without_fabricating_an_answer(runtime):
    item = runtime.agent(limits=AgentLimits(max_seconds=5, question_timeout_seconds=0.05))
    run = runtime.start(item, response(ToolCall(uid(), "ask_user", {"question": "Eksik değer?"})))
    saved = runtime.done(run)
    assert saved.status == "failed" and "yanıt süresi" in saved.error


@pytest.mark.parametrize("change", ["gate", "session"])
def test_license_and_session_change_cancel_waiting_agent(runtime, change):
    run = runtime.start(runtime.agent(), response(ToolCall(uid(), "ask_user", {"question": "Devam?"})))
    wait_for(lambda: runtime.service.get_run(run.id), lambda value: value.status == "waiting_user")
    if change == "gate":
        runtime.state["gate"] = False
    else:
        runtime.state["actor"] = runtime.owner.model_copy(update={"session_id": "another"})
    assert runtime.done(run).status == "cancelled"


def test_closed_license_prevents_start(runtime):
    item = runtime.agent()
    runtime.state["gate"] = False
    with pytest.raises(AgentServiceError) as denied:
        runtime.service.start(item.id, AgentRunRequest(task="İş"))
    assert denied.value.status_code == 403 and not runtime.service.agent_store.runs()


def test_cancel_stops_only_the_owned_running_workflow(runtime):
    flow = runtime.workflow(Step(action="core.wait", params={"seconds": 10}))
    run = runtime.start(runtime.agent(flow), response(run_call(flow)))
    active = wait_for(lambda: runtime.service.get_run(run.id), lambda value: bool(value.workflow_run_ids))
    runtime.service.cancel(run.id)
    assert runtime.done(run).status == "cancelled"
    child = wait_for(lambda: runtime.store.run(active.workflow_run_ids[0]), lambda value: value.finished_at is not None)
    assert child.status == "cancelled"


def test_busy_result_does_not_cancel_unrelated_work(runtime):
    manual_flow = runtime.workflow(Step(action="core.wait", params={"seconds": 1}))
    manual = runtime.manager.start(manual_flow)
    allowed = runtime.workflow(Step(action="core.set", params={"name": "value", "value": 1}))
    item = runtime.agent(allowed, limits=AgentLimits(max_seconds=5, busy_wait_seconds=0.05))
    run = runtime.start(item, response(run_call(allowed)), response(finish()))
    saved = runtime.done(run)
    assert saved.status == "succeeded" and not saved.workflow_run_ids
    assert runtime.store.run(manual.id).status != "cancelled"
    assert any(event.kind == "tool_result" and "busy" in json.dumps(event.data) for event in saved.events)
    runtime.manager.stop_run(manual.id, "Test tamamlandı.")


@pytest.mark.parametrize("kind", ["turns", "tokens", "duration", "flows", "loop"])
def test_limits_stop_before_additional_work(runtime, kind):
    flow = runtime.workflow(Step(action="core.set", params={"name": "value", "value": 1}))
    limits = AgentLimits(max_seconds=5)
    replies = []
    if kind == "turns":
        limits.max_turns = 1
        replies = [response(text="Devam"), response(finish())]
    elif kind == "tokens":
        limits.max_tokens = 10
        replies = [response(run_call(flow), usage=Usage(8, 8))]
    elif kind == "duration":
        limits.max_seconds = 0.05
        replies = [response(ToolCall(uid(), "ask_user", {"question": "Bekle"}))]
    elif kind == "flows":
        limits.max_workflow_runs = 0
        replies = [response(run_call(flow))]
    else:
        replies = [response(ToolCall(uid(), "list_workflows", {})) for _ in range(3)]
    run = runtime.start(runtime.agent(flow, limits=limits), *replies)
    saved = runtime.done(run)
    assert saved.status == "failed" and saved.workflow_count == 0


def test_failed_flow_cannot_be_blindly_retried(runtime):
    flow = runtime.workflow(Step(action="control.stop", params={"status": "failure", "message": "Hedef yok"}))
    run = runtime.start(runtime.agent(flow), response(run_call(flow)), response(run_call(flow)))
    saved = runtime.done(run)
    assert saved.status == "failed" and saved.workflow_count == 1 and "aynı girdilerle" in saved.error


def test_duplicate_tool_call_id_is_not_executed_twice(runtime):
    flow = runtime.workflow(Step(action="core.set", params={"name": "value", "value": 1}))
    call = run_call(flow, identity="same-call")
    run = runtime.start(runtime.agent(flow), response(call), response(call), response(finish()))
    saved = runtime.done(run)
    assert saved.status == "succeeded" and saved.workflow_count == 1


def test_old_run_snapshot_and_error_are_never_sent_to_model(runtime):
    flow = runtime.workflow()
    old = Run(workflow_id=flow.id, workflow_name=flow.name, department=flow.department, status="failed",
              finished_at=now(), error="old-secret-value", variables={"unsafe": "old-secret-value"})
    runtime.store.save_run(old)
    run = runtime.start(runtime.agent(flow), response(ToolCall(uid(), "get_run", {"run_id": old.id})),
                        response(finish()))
    saved = runtime.done(run)
    assert saved.status == "succeeded"
    assert "old-secret-value" not in json.dumps(runtime.state["provider"].requests)
    assert "old-secret-value" not in saved.model_dump_json()


def test_settings_secrets_are_removed_from_prompts_timeline_and_result(runtime):
    secret = "private-script-token"
    runtime.settings.update({"sheets_script_token": secret})
    item = runtime.agent()
    provider = ScriptedProvider([response(finish(secret))])
    runtime.state["provider"] = provider
    run = runtime.service.start(item.id, AgentRunRequest(task=f"Bu veriyi özetle: {secret}"))
    saved = runtime.done(run)
    assert saved.status == "succeeded"
    assert secret not in saved.model_dump_json() and secret not in json.dumps(provider.requests)
    assert secret not in runtime.service.agent_store.path("agent_runs", run.id).read_text(encoding="utf-8")


def test_vault_secret_and_derived_variables_never_reach_the_model(runtime, monkeypatch):
    secret = "vault-private-unique-value"
    monkeypatch.setattr("rpa_orkestrai.vault.Vault.get", lambda self, name: secret)
    flow = runtime.workflow(
        Step(action="core.set", params={"name": "copied", "value": "${sifre.saved}"}),
        Step(action="core.set", params={"name": "derived", "value": {"inner": "${copied}"}}),
        Step(action="core.log", params={"message": "${copied}"}),
    )
    run = runtime.start(runtime.agent(flow), response(run_call(flow)), response(finish()))
    saved = runtime.done(run)
    assert saved.status == "succeeded"
    child = runtime.store.run(saved.workflow_run_ids[0])
    assert "copied" not in child.variables and "derived" not in child.variables
    assert secret not in child.model_dump_json()
    assert secret not in saved.model_dump_json() and secret not in json.dumps(runtime.state["provider"].requests)


def test_provider_audit_preserves_complete_payload_larger_than_tool_result_limit(runtime):
    item = runtime.service.create_agent(AgentInput(name="Analiz", model="test", instructions="Kural " * 2500))
    run = runtime.start(item, response(finish()))
    saved = runtime.done(run)
    request = runtime.state["provider"].requests[0]
    assert len(json.dumps(request).encode()) > 16_000
    recorded = next(event.data["payload"] for event in saved.events if event.kind == "provider_request")
    assert recorded == request


def test_terminal_status_without_finished_timestamp_does_not_advance_agent(runtime, monkeypatch):
    flow = runtime.workflow(Step(action="core.set", params={"name": "answer", "value": "Hazır"}))
    original = runtime.store.run
    observed = []

    def delayed(identity):
        run = original(identity)
        if run.status == "succeeded" and len(observed) < 4:
            observed.append(run.id)
            return run.model_copy(update={"finished_at": None, "variables": None})
        return run

    monkeypatch.setattr(runtime.store, "run", delayed)
    run = runtime.start(runtime.agent(flow), response(run_call(flow)), response(finish()))
    saved = runtime.done(run)
    assert saved.status == "succeeded" and len(observed) == 4
    result = next(message for message in runtime.state["provider"].requests[1]["messages"]
                  if message["role"] == "tool")
    assert json.loads(result["content"])["untrusted_data"]["variables"]["answer"] == "Hazır"


@pytest.mark.parametrize("mode", ["read", "other_run", "symlink"])
def test_artifact_access_is_own_run_only_and_rejects_symlinks(runtime, mode):
    flow = runtime.workflow(Step(action="core.set", params={"name": "rows", "value": [{"value": "Güvenli"}]}),
                            Step(action="data.export_csv", params={"rows": "${rows}", "filename": "sonuc.csv"}))
    item = runtime.agent(flow, bypass=True)
    stage = [0]

    def reply(request):
        stage[0] += 1
        if stage[0] == 1:
            return response(run_call(flow))
        if stage[0] == 2:
            child = runtime.store.runs()[0]
            artifact = child.artifacts[0]
            if mode == "symlink":
                path = runtime.store.root / "artifacts" / child.id / f"{artifact.id}.csv"
                private = runtime.business / "private.txt"
                private.write_text("private-artifact-content", encoding="utf-8")
                path.unlink()
                try:
                    path.symlink_to(private)
                except (OSError, NotImplementedError):
                    # The assertion below still checks ownership on Windows without symlink privilege.
                    return response(ToolCall(uid(), "read_artifact", {"run_id": uid(), "artifact_id": artifact.id}))
            return response(ToolCall(uid(), "read_artifact", {
                "run_id": uid() if mode == "other_run" else child.id, "artifact_id": artifact.id,
            }))
        return response(finish())

    runtime.state["provider"] = ScriptedProvider([], callback=reply)
    started = runtime.service.start(item.id, AgentRunRequest(task="Çıktıyı incele"))
    saved = runtime.done(started)
    assert saved.status == "succeeded"
    results = [event.data for event in saved.events if event.kind == "tool_result"
               and event.data.get("name") == "read_artifact"]
    assert len(results) == 1
    result = results[0]["untrusted_data"]
    if mode == "read":
        assert "Güvenli" in result["content"]
    else:
        assert result["status"] == "error"
        assert "private-artifact-content" not in json.dumps(runtime.state["provider"].requests)


def test_manager_cannot_start_a_workflow_loop(runtime):
    flow = runtime.workflow(Step(action="core.set", params={"name": "value", "value": 1}))
    item = runtime.service.create_agent(AgentInput(name="Yönetici", role="manager"))
    run = runtime.start(item, response(run_call(flow)), response(finish()))
    saved = runtime.done(run)
    assert saved.status == "succeeded" and saved.workflow_count == 0
    assert not runtime.store.runs()
    assert "run_workflow" not in {tool["name"] for tool in runtime.state["provider"].requests[0]["tools"]}
    assert any(event.kind == "tool_result" and event.data["untrusted_data"].get("status") == "error"
               for event in saved.events)


def test_other_company_cannot_read_edit_or_cancel(runtime):
    item = runtime.agent()
    run = runtime.start(item, response(finish()))
    runtime.done(run)
    runtime.state["actor"] = Actor(user_id=3, company_id=4, session_id="other",
                                   permissions=["agents.use", "agents.manage", "agents.approve"])
    assert runtime.service.agents() == [] and runtime.service.runs() == []
    for operation in (lambda: runtime.service.get_agent(item.id), lambda: runtime.service.get_run(run.id),
                      lambda: runtime.service.cancel(run.id), lambda: runtime.service.delete_agent(item.id)):
        with pytest.raises(AgentServiceError) as denied:
            operation()
        assert denied.value.status_code == 404
