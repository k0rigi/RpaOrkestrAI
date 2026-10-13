"""Ajan sınırlarının gerçek motorun kontrol dallarında da korunması."""

import json
import threading
import time

import pytest

from rpa_orkestrai.agents.models import Actor, Agent, WorkflowGrant
from rpa_orkestrai.agents.policy import AgentExecutionPolicy, prepare_workflow
from rpa_orkestrai.config import Settings
from rpa_orkestrai.engine import Executor, RunManager
from rpa_orkestrai.errors import AgentPolicyStop
from rpa_orkestrai.models import Run, Step, Workflow
from rpa_orkestrai.storage import Store


def context(tmp_path, workflow, *, children=(), check=None):
    store = Store(tmp_path)
    for item in (workflow, *children):
        store.save_workflow(item)
    actor = Actor(user_id=1, company_id=1, session_id="oturum")
    agent = Agent(name="Analiz", user_id=1, company_id=1,
                  workflows=[WorkflowGrant(workflow_id=item.id) for item in (workflow, *children)])
    prepared = prepare_workflow(agent, workflow.id, store, {}, actor=actor)
    return store, AgentExecutionPolicy(prepared, check_callback=check, protected_roots=(tmp_path,))


def finished(store, run_id):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        run = store.run(run_id)
        if run.finished_at:
            return run
        time.sleep(0.01)
    pytest.fail("Ajan akışı süresinde tamamlanmadı.")


def test_agent_result_is_masked_and_keeps_legacy_run_format(tmp_path, monkeypatch):
    workflow = Workflow(steps=[
        Step(action="core.set", params={"name": "secret_copy", "value": "${sifre.test}"}),
        Step(action="text.transform", params={"text": "${secret_copy}", "operation": "upper", "output": "derived"}),
        Step(action="core.log", params={"message": "${derived}"}),
        Step(action="core.set", params={"name": "safe", "value": 7}),
    ])
    store, policy = context(tmp_path, workflow)
    monkeypatch.setattr("rpa_orkestrai.vault.Vault.get", lambda self, name: "gizli-sir")
    manager = RunManager(Settings(tmp_path, dotenv=False), store)
    try:
        run = finished(store, manager.start(workflow, agent_context=policy).id)
        assert run.status == "succeeded"
        assert run.variables == {"safe": 7}
        assert run.trigger == "manual"
        saved = store.path("runs", run.id).read_text()
        assert "gizli-sir" not in saved and "GIZLI-SIR" not in saved
        assert "agent_context" not in saved
        Run.model_validate_json(saved)
    finally:
        manager.close()


def test_policy_error_cannot_be_caught_by_try_even_inside_a_child(tmp_path, monkeypatch):
    child = Workflow(steps=[Step(action="core.set", params={"name": "changed", "value": True})])
    workflow = Workflow(steps=[Step(action="control.try", children=[
        Step(action="control.run_workflow", params={"workflow": child.id}),
    ], otherwise=[Step(action="core.set", params={"name": "recovered", "value": True})])])
    store, policy = context(tmp_path, workflow, children=(child,))

    def deny(identity):
        raise AgentPolicyStop("Alt akış yetkisi geri çekildi.")

    monkeypatch.setattr(policy, "authorize_workflow", deny)
    run = Run(workflow_id=workflow.id, workflow_name=workflow.name, department=workflow.department)
    executor = Executor(Settings(tmp_path, dotenv=False), store, run, threading.Event(), lambda: None,
                        agent_context=policy)
    with pytest.raises(AgentPolicyStop):
        executor.execute(workflow)
    assert "changed" not in executor.variables and "recovered" not in executor.variables


def test_subworkflow_uses_prepared_definition(tmp_path):
    child = Workflow(steps=[Step(action="core.set", params={"name": "value", "value": "onaylanan"})])
    workflow = Workflow(steps=[Step(action="control.run_workflow", params={"workflow": child.id})])
    store, policy = context(tmp_path, workflow, children=(child,))
    child.steps[0].params["value"] = "sonradan değiştirilen"
    store.save_workflow(child)
    manager = RunManager(Settings(tmp_path, dotenv=False), store)
    try:
        run = finished(store, manager.start(workflow, agent_context=policy).id)
        assert run.variables["value"] == "onaylanan"
    finally:
        manager.close()


def test_wait_observes_agent_gate_and_does_not_run_next_step(tmp_path):
    allowed = threading.Event()
    allowed.set()

    def check():
        if not allowed.is_set():
            raise AgentPolicyStop("Ajan lisansı doğrulanamadı.")

    workflow = Workflow(steps=[Step(action="core.wait", params={"seconds": 30}),
                               Step(action="core.set", params={"name": "changed", "value": True})])
    store, policy = context(tmp_path, workflow, check=check)
    manager = RunManager(Settings(tmp_path, dotenv=False), store)
    try:
        run = manager.start(workflow, agent_context=policy)
        allowed.clear()
        result = finished(store, run.id)
        assert result.status == "failed" and "changed" not in result.variables
        assert "lisansı" in result.error
    finally:
        manager.close()


def test_agent_text_artifact_redacts_before_writing(tmp_path):
    workflow = Workflow(steps=[])
    store, policy = context(tmp_path, workflow)
    policy.remember_secret("tiny")
    run = Run(workflow_id=workflow.id, workflow_name=workflow.name, department=workflow.department)
    executor = Executor(Settings(tmp_path, dotenv=False), store, run, threading.Event(), lambda: None,
                        agent_context=policy)
    artifact = executor.save_artifact("rapor.json", json.dumps({"value": "tiny"}).encode())
    assert "tiny" not in artifact.read_text()
    with pytest.raises(AgentPolicyStop):
        executor.save_artifact("ekran.png", b"tiny")


@pytest.mark.parametrize("failure_at", ["setup", "finish"])
def test_policy_failure_releases_worker_without_recording_exception(tmp_path, monkeypatch, failure_at):
    workflow = Workflow(steps=[Step(action="core.set", params={"name": "safe", "value": 7})])
    store, policy = context(tmp_path, workflow)

    def fail(*args, **kwargs):
        raise RuntimeError("asla-kaydedilmemesi-gereken-sir")

    if failure_at == "setup":
        monkeypatch.setattr("rpa_orkestrai.engine.Executor", fail)
    else:
        monkeypatch.setattr(policy, "finish", fail)
    manager = RunManager(Settings(tmp_path, dotenv=False), store)
    try:
        run = finished(store, manager.start(workflow, agent_context=policy).id)
        assert run.status == "failed"
        assert not manager.busy()
        assert run.variables == {}
        assert "asla-kaydedilmemesi-gereken-sir" not in store.path("runs", run.id).read_text()
    finally:
        manager.close()
