import json
import threading
import time
from types import SimpleNamespace

import pytest
from test_vault import MemoryStore

from rpa_orkestrai import vault as vault_module
from rpa_orkestrai.agents.connections import ProviderConnectionStore
from rpa_orkestrai.agents.models import Actor, Agent, ProviderConnection, WorkflowGrant
from rpa_orkestrai.agents.policy import prepare_workflow
from rpa_orkestrai.agents.providers import ProviderResponse, ScriptedProvider, ToolCall, Usage
from rpa_orkestrai.agents.schema import compile_schema
from rpa_orkestrai.agents.workflow_ai import WorkflowAIService
from rpa_orkestrai.config import Settings
from rpa_orkestrai.engine import UNKNOWN, Executor, RunManager, step_reads, step_test_plan
from rpa_orkestrai.errors import AgentPolicyStop, Cancelled, WorkflowError
from rpa_orkestrai.models import Run, Step, Workflow, uid
from rpa_orkestrai.package_check import _check_ai_schema
from rpa_orkestrai.storage import Store
from rpa_orkestrai.vault import Vault


@pytest.fixture
def ai(tmp_path, monkeypatch):
    memory = MemoryStore()
    monkeypatch.setattr(vault_module, "system_store", lambda: memory)
    settings = Settings(tmp_path / "data", dotenv=False)
    store = Store(settings.data_dir)
    connections = ProviderConnectionStore(settings.data_dir)
    connection = ProviderConnection(name="Yerel model", provider="ollama", model="yerel-test", company_id=2)
    connections.save(connection, 2)
    actor = Actor(user_id=1, company_id=2, session_id="session", permissions=["agents.use"])
    state = {"actor": actor, "gate": True, "provider": ScriptedProvider([ProviderResponse(text="Tamam")])}
    service = WorkflowAIService(settings, connections, actor=lambda: state["actor"], gate=lambda: state["gate"],
                                 provider_factory=lambda connection, actor: state["provider"])
    run = Run(workflow_id=uid(), workflow_name="Analiz", department="Genel")
    executor = Executor(settings, store, run, threading.Event(), lambda: store.save_run(run), ai_service=service)

    def step(**changes):
        return Step(action="ai.ask", params={"connection": connection.id, "instructions": "Veriyi analiz et.",
                                            "input": "Veri", "output": "result", **changes})

    yield SimpleNamespace(settings=settings, store=store, connections=connections, connection=connection,
                          actor=actor, state=state, service=service, executor=executor, memory=memory, step=step)
    executor.cancel.set()


def execute(ai, step=None):
    ai.executor.execute(Workflow(steps=[step or ai.step()]))
    return ai.executor.variables.get("result")


def test_ai_step_uses_saved_model_without_tools_and_saves_masked_request(ai):
    assert execute(ai) == "Tamam"
    request = ai.state["provider"].requests[0]
    assert request["model"] == "yerel-test" and request["tools"] == []
    artifact = ai.executor.run.artifacts[0]
    content = next((ai.settings.data_dir / "artifacts" / ai.executor.run.id).glob(f"{artifact.id}.*")).read_text()
    assert json.loads(content) == request


@pytest.mark.parametrize("available", [0, 384])
def test_shared_context_limit_is_applied_before_audit_and_provider_call(ai, available):
    provider = ai.state["provider"]
    provider.request_limits = lambda model, **kwargs: SimpleNamespace(
        output_budget=lambda messages, tools, requested: available)
    if not available:
        with pytest.raises(WorkflowError, match="bağlam"):
            execute(ai)
        assert not provider.requests and not ai.executor.run.artifacts
    else:
        assert execute(ai) == "Tamam"
        request = provider.requests[0]
        assert request["max_tokens"] == available
        content = next((ai.settings.data_dir / "artifacts" / ai.executor.run.id).glob("*.json")).read_text()
        assert json.loads(content) == request


def test_bounded_input_is_never_silently_truncated_for_decision(ai):
    value = "x" * 20_000
    execute(ai, ai.step(input=value))
    request = ai.state["provider"].requests[0]
    assert json.loads(request["messages"][1]["content"])["untrusted_data"] == value


def test_valid_json_schema_output_drives_workflow_branch(ai):
    ai.state["provider"] = ScriptedProvider([ProviderResponse(text='{"karar":"evet","adet":2}')])
    schema = {"type": "object", "properties": {"karar": {"enum": ["evet", "hayır"]}, "adet": {"type": "integer"}},
              "required": ["karar", "adet"], "additionalProperties": False}
    branch = Step(action="control.if", params={"left": "${result.karar}", "operator": "eq", "right": "evet"},
                  children=[Step(action="core.set", params={"name": "branch", "value": "Evet"})])
    ai.executor.execute(Workflow(steps=[ai.step(schema=schema), branch]))
    assert ai.executor.variables["result"] == {"karar": "evet", "adet": 2}
    assert ai.executor.variables["branch"] == "Evet"


@pytest.mark.parametrize("answer", ['{"adet":"2"}', '{"adet":2,"fazla":true}', '```json\n{"adet":2}\n```',
                                    '{"adet":1,"adet":2}', '{"adet":NaN}', '{"adet":Infinity}', 'tahmin', ''])
def test_invalid_json_or_schema_result_never_assigns_output(ai, answer):
    ai.state["provider"] = ScriptedProvider([ProviderResponse(text=answer)])
    schema = {"type": "object", "properties": {"adet": {"type": "integer"}},
              "required": ["adet"], "additionalProperties": False}
    with pytest.raises(WorkflowError):
        execute(ai, ai.step(schema=schema))
    assert "result" not in ai.executor.variables


@pytest.mark.parametrize("schema", [
    {"type": "not-a-type"}, {"type": "object", "required": "name"}, {"typ": "string"},
    {"$ref": "https://example.test/private-schema.json"}, {"$ref": "file:///etc/passwd"},
    {"$dynamicRef": "http://127.0.0.1/schema"}, {"properties": {"value": {"$ref": "../other.json"}}},
    {"pattern": "(a+)+$"}, {"patternProperties": {"(a+)+$": {"type": "string"}}},
    {"format": "unknown-format"}, {"format": []},
    {"$schema": "https://json-schema.org/draft-07/schema#"},
    {"$ref": "#/$defs/missing"}, {"$ref": "#/description", "description": "Şema değil"},
    {"$id": "https://example.test/schema", "$ref": "#/$defs/type", "$defs": {"type": {"type": "string"}}},
])
def test_invalid_or_external_schema_fails_before_model_or_artifact(ai, schema, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: pytest.fail("Şema ağ isteği yapamaz."))
    with pytest.raises(WorkflowError):
        execute(ai, ai.step(schema=schema))
    assert not ai.state["provider"].requests and not ai.executor.run.artifacts


def test_local_schema_refs_work_and_recursive_refs_are_bounded():
    validator = compile_schema({"$defs": {"count": {"type": "integer", "minimum": 1}},
                                "type": "object", "properties": {"n": {"$ref": "#/$defs/count"}}})
    validator.validate({"n": 1})
    with pytest.raises(WorkflowError):
        validator.validate({"n": 0})
    with pytest.raises(WorkflowError):
        compile_schema({"$ref": "#"}).validate({})


def test_preview_skips_service_license_vault_and_schema_and_propagates_unknown(ai):
    ai.executor.run.dry_run = True
    ai.executor.ai_service = None
    ai.state["gate"] = False
    branch = Step(action="control.if", params={"left": "${result}", "operator": "truthy"},
                  children=[Step(action="core.set", params={"name": "decision", "value": "Tahmin"})])
    ai.executor.execute(Workflow(steps=[ai.step(connection="f" * 32,
                                               schema={"$ref": "https://forbidden.test"}), branch]))
    assert ai.executor.variables["result"] is UNKNOWN and ai.executor.variables["decision"] is UNKNOWN
    assert not ai.state["provider"].requests and not ai.executor.run.artifacts


def test_input_dependencies_and_safe_test_preparation(ai):
    step = ai.step(input="${rows}", instructions="${instruction}")
    assert set(step_reads(step)[0]) == {"rows", "instruction"}
    consumer = Step(action="core.log", params={"message": "${result}"})
    workflow = Workflow(steps=[ai.step(), consumer])
    plan = step_test_plan(workflow, consumer.id)
    assert plan["prepare"][0]["step"].action == "ai.ask"


def test_registered_unread_vault_and_provider_secrets_never_escape(ai):
    password, key = "unread-vault-private", "private-provider-key"
    Vault(ai.settings.data_dir).set("password", password)
    ai.connections.set_key(ai.connection.id, key, 2)
    ai.state["provider"] = ScriptedProvider([ProviderResponse(text=f"Sonuç {password} / {key}")])
    result = execute(ai, ai.step(input={"text": password, "key": key}))
    encoded = json.dumps(ai.state["provider"].requests)
    all_files = "".join(path.read_text(encoding="utf-8") for path in
                        (ai.settings.data_dir / "artifacts" / ai.executor.run.id).glob("*.json"))
    for secret in (password, key):
        assert secret not in encoded and secret not in all_files and secret not in result
        assert secret not in ai.executor.run.model_dump_json()


def test_explicit_secret_variable_is_masked_and_whole_vault_is_rejected(ai):
    Vault(ai.settings.data_dir).set("password", "read-vault-private")
    execute(ai, ai.step(input="${sifre.password}"))
    assert "read-vault-private" not in json.dumps(ai.state["provider"].requests)
    ai.state["provider"] = ScriptedProvider([])
    with pytest.raises(WorkflowError):
        execute(ai, ai.step(input="${sifre}"))
    assert not ai.state["provider"].requests


def test_locked_vault_stops_before_model_request(ai, monkeypatch):
    Vault(ai.settings.data_dir).set("password", "unread-vault-private")
    monkeypatch.setattr(ai.memory, "load", lambda name: (_ for _ in ()).throw(RuntimeError("private-error")))
    with pytest.raises(WorkflowError) as denied:
        execute(ai)
    assert "private-error" not in str(denied.value) and not ai.state["provider"].requests


@pytest.mark.parametrize("kind", ["gate", "actor", "company", "session", "permission", "scheduled"])
def test_license_identity_scope_and_manual_trigger_enforced(ai, kind):
    if kind == "gate":
        ai.state["gate"] = False
    elif kind == "actor":
        ai.state["actor"] = None
    elif kind == "company":
        ai.state["actor"] = ai.actor.model_copy(update={"company_id": 99})
    elif kind == "permission":
        ai.state["actor"] = ai.actor.model_copy(update={"permissions": ()})
    elif kind == "session":
        ai.state["provider"] = ScriptedProvider([], callback=lambda request: (
            ai.state.update(actor=ai.actor.model_copy(update={"session_id": "new"})) or ProviderResponse(text="Yanıt")))
    else:
        ai.executor.run.trigger = "schedule"
    with pytest.raises(WorkflowError):
        execute(ai)
    assert "result" not in ai.executor.variables
    if kind != "session":
        assert not ai.state["provider"].requests


@pytest.mark.parametrize("change", ["cancel", "gate", "timeout"])
def test_inflight_request_is_cancellable_and_never_writes_late_result(ai, change):
    entered, cancelled = threading.Event(), threading.Event()

    class WaitingProvider:
        def complete(self, messages, tools, *, model, max_tokens, cancel, deadline):
            entered.set()
            assert cancel.wait(2)
            cancelled.set()
            return ProviderResponse(text="Çok geç gelen yanıt")

    ai.state["provider"] = WaitingProvider()
    failures = []

    def work():
        try:
            execute(ai, ai.step(timeout=0.12 if change == "timeout" else 2))
        except Exception as exc:
            failures.append(exc)

    worker = threading.Thread(target=work)
    worker.start()
    assert entered.wait(2)
    if change == "cancel":
        ai.executor.cancel.set()
    elif change == "gate":
        ai.state["gate"] = False
    worker.join(2)
    assert not worker.is_alive() and cancelled.wait(1)
    assert isinstance(failures[0], Cancelled if change == "cancel" else WorkflowError)
    assert "result" not in ai.executor.variables


@pytest.mark.parametrize("kind", ["tool", "tokens", "total", "size", "input", "schema", "reserved"])
def test_ai_limits_and_unexpected_tools_fail_closed(ai, kind):
    step = ai.step()
    if kind == "tool":
        ai.state["provider"] = ScriptedProvider([ProviderResponse(tool_calls=[ToolCall(uid(), "run_workflow", {})])])
    elif kind == "tokens":
        ai.state["provider"] = ScriptedProvider([ProviderResponse(text="Yanıt", usage=Usage(1, 1025))])
    elif kind == "total":
        ai.state["provider"] = ScriptedProvider([ProviderResponse(text="Yanıt", usage=Usage(16_384, 1))])
    elif kind == "size":
        ai.state["provider"] = ScriptedProvider([ProviderResponse(text="x" * 32_001)])
    elif kind == "input":
        step.params["input"] = "x" * 32_001
    elif kind == "schema":
        step.params["schema"] = {"type": "string", "description": "x" * 16_001}
    else:
        step.params["output"] = "sifre"
    with pytest.raises(WorkflowError):
        execute(ai, step)
    assert "result" not in ai.executor.variables


def test_agent_cannot_call_ai_step_directly_or_via_subworkflow(ai):
    child = Workflow(steps=[ai.step()])
    parent = Workflow(steps=[Step(action="control.run_workflow", params={"workflow": child.id})])
    for item in (child, parent):
        ai.store.save_workflow(item)
    agent = Agent(name="Analiz", company_id=2, user_id=1,
                  workflows=[WorkflowGrant(workflow_id=item.id) for item in (child, parent)])
    for item in (child, parent):
        with pytest.raises(WorkflowError):
            prepare_workflow(agent, item.id, ai.store, {}, actor=ai.actor)
    ai.executor.agent_context = object()
    with pytest.raises(AgentPolicyStop):
        ai.service.complete(ai.executor, ai.step().params)


def test_schema_package_self_check_and_run_manager_service_hook(ai):
    _check_ai_schema()
    manager = RunManager(ai.settings, ai.store, ai_service=ai.service)
    try:
        step = ai.step()
        run = manager.start_step(Workflow(steps=[step]), step.id, {})
        deadline = time.monotonic() + 3
        while not ai.store.run(run.id).finished_at and time.monotonic() < deadline:
            threading.Event().wait(0.01)
        saved = ai.store.run(run.id)
        assert saved.status == "succeeded" and saved.variables["result"] == "Tamam"
    finally:
        manager.close()
