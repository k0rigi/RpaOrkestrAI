"""İzin, onay bağlama, masaüstü ve dosya sınırlarının ağsız saldırı testleri."""

import os
from types import SimpleNamespace

import pytest

from rpa_orkestrai.agents.models import Actor, Agent, WorkflowGrant
from rpa_orkestrai.agents.policy import AgentExecutionPolicy, prepare_workflow, workflow_fingerprint
from rpa_orkestrai.agents.risk import READ, STEP_RISKS, WRITE, step_risk, workflow_risk
from rpa_orkestrai.catalog import BY_TYPE, defaults
from rpa_orkestrai.errors import AgentPolicyStop, WorkflowError
from rpa_orkestrai.models import Step, Workflow


def setup_policy(*workflows, grants=None, actor=None, inputs=None):
    records = {workflow.id: workflow for workflow in workflows}
    store = SimpleNamespace(workflow=records.__getitem__)
    agent = Agent(name="Test ajanı", company_id=1, user_id=2,
                  workflows=grants if grants is not None else [WorkflowGrant(workflow_id=w.id) for w in workflows])
    prepared = prepare_workflow(agent, workflows[0].id, store, inputs or {}, actor=actor)
    return agent, store, prepared


def test_every_catalog_type_has_explicit_risk():
    assert set(STEP_RISKS) == set(BY_TYPE)
    assert set(STEP_RISKS.values()) == {READ, WRITE}
    assert step_risk("future.unknown") == WRITE
    assert step_risk("window.read_table") == WRITE


def test_unauthorized_root_and_transitive_child_are_rejected():
    child = Workflow(steps=[Step(action="core.wait")])
    root = Workflow(steps=[Step(action="control.run_workflow", params={"workflow": child.id})])
    with pytest.raises(WorkflowError, match="izni yok"):
        setup_policy(root, child, grants=[])
    with pytest.raises(WorkflowError, match="alt akışı"):
        setup_policy(root, child, grants=[WorkflowGrant(workflow_id=root.id)])


def test_dynamic_child_and_cycles_rejected():
    dynamic = Workflow(steps=[Step(action="control.run_workflow", params={"workflow": "${chosen}"})])
    with pytest.raises(WorkflowError, match="sabit"):
        setup_policy(dynamic)
    loop = Workflow()
    loop.steps = [Step(action="control.run_workflow", params={"workflow": loop.id})]
    with pytest.raises(WorkflowError, match="döngü"):
        setup_policy(loop)


def test_subflow_depth_limit():
    flows = [Workflow() for _ in range(8)]
    for parent, child in zip(flows, flows[1:]):
        parent.steps = [Step(action="control.run_workflow", params={"workflow": child.id})]
    with pytest.raises(WorkflowError, match="derinlik"):
        setup_policy(*flows)


def test_snapshot_is_stable_and_inputs_are_copied():
    child = Workflow(steps=[Step(action="core.set", params={"name": "value", "value": 7})])
    root = Workflow(steps=[Step(action="control.run_workflow", params={"workflow": child.id})])
    supplied = {"item": {"count": 1}}
    _, _, prepared = setup_policy(root, child, inputs=supplied)
    child.steps[0].params["value"] = 99
    supplied["item"]["count"] = 10
    context = AgentExecutionPolicy(prepared)
    assert context.authorize_workflow(child.id).steps[0].params["value"] == 7
    assert prepared.inputs == {"item": {"count": 1}}
    loaded = context.authorize_workflow(child.id)
    loaded.steps.clear()
    assert context.authorize_workflow(child.id).steps


def test_approval_exemption_requires_current_transitive_revision():
    child = Workflow(steps=[Step(action="sheets.write_cell")])
    root = Workflow(steps=[Step(action="control.run_workflow", params={"workflow": child.id})])
    grants = [WorkflowGrant(workflow_id=w.id, allow_without_approval=True) for w in (root, child)]
    agent, store, prepared = setup_policy(root, child, grants=grants)
    assert prepared.risk == WRITE and prepared.approval_required
    agent.grant_revisions = {w.id: workflow_fingerprint(w.id, store) for w in (root, child)}
    assert not prepare_workflow(agent, root.id, store, {}).approval_required
    child.steps[0].params["value"] = "Değişti"
    assert prepare_workflow(agent, root.id, store, {}).approval_required


def test_approval_digest_binds_input_actor_session_and_policy():
    workflow = Workflow(steps=[Step(action="sheets.write_cell")])
    actor = Actor(user_id=2, company_id=1, session_id="ilk")
    agent, store, baseline = setup_policy(workflow, actor=actor, inputs={"value": 1})
    variants = [
        prepare_workflow(agent, workflow.id, store, {"value": 2}, actor=actor),
        prepare_workflow(agent, workflow.id, store, {"value": 1},
                         actor=actor.model_copy(update={"session_id": "ikinci"})),
        prepare_workflow(agent.model_copy(update={"revision": 2}), workflow.id, store, {"value": 1}, actor=actor),
    ]
    assert all(item.digest != baseline.digest for item in variants)
    assert baseline.approval_required
    with pytest.raises(WorkflowError, match="Başka firmanın"):
        prepare_workflow(agent, workflow.id, store, {}, actor=actor.model_copy(update={"company_id": 9}))


def test_manager_has_no_workflow_tool_and_unknown_descendant_risk_is_high():
    workflow = Workflow(steps=[Step(action="core.wait")])
    agent, store, prepared = setup_policy(workflow)
    assert not prepared.approval_required
    with pytest.raises(WorkflowError, match="Yönetici ajan"):
        prepare_workflow(agent.model_copy(update={"role": "manager"}), workflow.id, store, {})
    root = Workflow(steps=[Step(action="control.run_workflow", params={"workflow": workflow.id})])
    assert workflow_risk(root) == WRITE


@pytest.mark.parametrize("action", ["system.command", "system.open", "web.script", "web.open", "input.hotkey", "ai.ask",
                                    "file.zip", "screen.screenshot"])
def test_a_granted_flow_runs_every_step_and_risky_ones_wait_for_approval(action):
    # The person gave this flow to the agent: all its steps are allowed; risky ones need an approval each time.
    _, _, prepared = setup_policy(Workflow(steps=[Step(action=action)]))
    assert prepared.risk == WRITE and prepared.approval_required


def test_api_requests_of_a_granted_flow_run_as_written_after_approval():
    from rpa_orkestrai.agents.policy import AgentExecutionPolicy

    for params in ({"url": "https://ornek.com/v1"}, {"connection": "a" * 32, "url": "https://baska.com/v1"},
                   {"connection": "a" * 32, "url": "/v1/siparis/${no}"}):
        step = Step(action="http.request", params=params)
        _, _, prepared = setup_policy(Workflow(steps=[step]))
        assert prepared.risk == WRITE and prepared.approval_required
        AgentExecutionPolicy(prepared).before_step(step, params, {})


def test_reading_mail_is_a_read_until_it_marks_messages_or_saves_attachments(tmp_path):
    assert step_risk("mail.read", {}) == READ
    assert step_risk("mail.read", {"mark_read": True}) == WRITE
    assert step_risk("mail.read", {"attachment_folder": str(tmp_path)}) == WRITE
    assert step_risk("ftp.transfer", {"operation": "list"}) == READ
    assert step_risk("ftp.transfer", {"operation": "upload"}) == WRITE
    reading = Workflow(steps=[Step(action="mail.read", params={"connection": "b" * 32})])
    _, _, prepared = setup_policy(reading)
    assert prepared.risk == READ and not prepared.approval_required
    saving = Workflow(steps=[Step(action="mail.read", params={"connection": "b" * 32, "attachment_folder": str(tmp_path)})])
    assert setup_policy(saving)[2].risk == WRITE  # folders are optional; named ones are enforced
    assert setup_policy(saving, grants=[WorkflowGrant(workflow_id=saving.id, allowed_roots=[str(tmp_path)])])[2].risk == WRITE


def test_file_scope_and_protected_directories(tmp_path):
    allowed = tmp_path / "isler"
    allowed.mkdir()
    protected = allowed / "studio"
    protected.mkdir()
    step = Step(action="file.write_text", params={"path": "${path}", "text": "Değer"})
    flow = Workflow(steps=[step])
    grant = WorkflowGrant(workflow_id=flow.id, allowed_roots=[str(allowed)])
    _, _, prepared = setup_policy(flow, grants=[grant], inputs={"path": str(allowed / "a.txt")})
    context = AgentExecutionPolicy(prepared, protected_roots=[protected])
    context.before_step(step, {"path": str(allowed / "a.txt")}, {})
    context.after_step(step, None, {})
    for bad in (tmp_path / "diger.txt", protected / "agents.json", allowed / "credentials" / "anahtar.pem"):
        with pytest.raises(AgentPolicyStop):
            context.before_step(step, {"path": str(bad)}, {})
        context.after_step(step, None, {})
    link = allowed / "link"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Bu sistemde sembolik bağlantı oluşturma izni yok.")
    with pytest.raises(AgentPolicyStop):
        context.before_step(step, {"path": str(link / "diger.txt")}, {})


def test_destination_directory_cannot_hide_symlink(tmp_path):
    source = tmp_path / "a.txt"
    source.write_text("test")
    destination = tmp_path / "hedef"
    destination.mkdir()
    try:
        (destination / source.name).symlink_to(tmp_path / "b.txt")
    except OSError:
        pytest.skip("Bu sistemde sembolik bağlantı oluşturma izni yok.")
    step = Step(action="file.operation", params={"operation": "copy", "source": str(source),
                                                "destination": str(destination)})
    flow = Workflow(steps=[step])
    _, _, prepared = setup_policy(flow, grants=[WorkflowGrant(workflow_id=flow.id, allowed_roots=[str(tmp_path)])])
    with pytest.raises(AgentPolicyStop, match="sembolik"):
        AgentExecutionPolicy(prepared).before_step(step, step.params, {})


def test_only_runtime_discovered_non_studio_window_is_accepted():
    find = Step(action="desktop.find_window", params={"output": "target", "application": "Test"})
    write = Step(action="desktop.window_fill", params={"window": "${target}"})
    _, _, prepared = setup_policy(Workflow(steps=[find, write]))
    validated = []
    context = AgentExecutionPolicy(prepared, window_validator=validated.append)
    target = {"found": True, "pid": os.getpid() + 100, "application": "Test", "window_id": 77}
    with pytest.raises(AgentPolicyStop, match="tanıtılmış"):
        context.before_step(write, {"window": target}, {})
    context.after_step(write, None, {})
    context.before_step(find, {**defaults(find.action), **find.params}, {})
    context.after_step(find, None, {"target": target})
    context.before_step(write, {"window": target}, {"target": target})
    context.after_step(write, None, {})
    assert validated == [target]
    context.before_step(find, {**defaults(find.action), **find.params}, {})
    with pytest.raises(AgentPolicyStop, match="Studio"):
        context.after_step(find, None, {"target": {**target, "pid": os.getpid()}})


def test_runtime_policy_checks_changes_and_unknown_steps():
    step = Step(action="core.wait")
    _, _, prepared = setup_policy(Workflow(steps=[step]))
    called = []
    context = AgentExecutionPolicy(prepared, check_callback=lambda: called.append(True))
    context.before_step(step, {}, {})
    assert called
    with pytest.raises(AgentPolicyStop, match="tanımında"):
        context.before_step(Step(action="core.wait"), {}, {})


@pytest.mark.parametrize("application", ["", "${app}", "Terminal", "powershell.exe", "Google Chrome"])
def test_any_window_of_a_granted_flow_is_allowed(application):
    setup_policy(Workflow(steps=[Step(action="desktop.find_window", params={"application": application})]))


@pytest.mark.parametrize("target", [{"application": "RpaOrkestrAI"}, {"application": "Uygulama", "title": "RpaOrkestrAI Studio"}])
def test_the_studio_itself_is_never_an_agents_window(target):
    with pytest.raises(WorkflowError, match="Studio"):
        setup_policy(Workflow(steps=[Step(action="desktop.find_window", params=target)]))


def test_secret_taint_survives_transformation_and_nested_branches():
    secret = Step(action="core.set", params={"name": "first", "value": "${sifre.key}"})
    transformed = Step(action="text.transform", params={"text": "${first}", "operation": "upper", "output": "changed"})
    nested = Step(action="core.set", params={"name": "answer", "value": "Veri"})
    branch = Step(action="control.if", params={"left": "${changed}", "operator": "truthy"}, children=[nested])
    _, _, prepared = setup_policy(Workflow(steps=[secret, transformed, branch]))
    context = AgentExecutionPolicy(prepared)
    variables = {}
    context.before_step(secret, {"name": "first", "value": "secret-123"}, variables)
    variables["first"] = "secret-123"
    context.after_step(secret, None, variables)
    context.before_step(transformed, {"text": variables["first"], "output": "changed"}, variables)
    variables["changed"] = "SECRET-123"
    context.after_step(transformed, None, variables)
    context.before_step(branch, {"left": variables["changed"]}, variables)
    context.before_step(nested, {"name": "answer", "value": "Veri"}, variables)
    assert "secret" not in context.mask("secret-123")
    variables["answer"] = "Veri"
    context.after_step(nested, None, variables)
    context.after_step(branch, None, variables)
    assert context.snapshot(variables) == {}
    assert "SECRET-123" not in context.mask("Hata: SECRET-123")
    assert "SECRET-123" not in context.artifact("x.csv", b"SECRET-123").decode()
    # A picture or a workbook cannot be masked: it is kept, unless a saved secret is written into it.
    assert context.artifact("x.png", b"\x89PNG resim") == b"\x89PNG resim"
    with pytest.raises(AgentPolicyStop, match="gizli değer"):
        context.artifact("x.png", b"SECRET-123")


@pytest.mark.parametrize("name", ["sistem", "sifre", "loop_index", "x_${choice}"])
def test_workflow_cannot_overwrite_reserved_or_dynamic_output(name):
    with pytest.raises(WorkflowError):
        setup_policy(Workflow(steps=[Step(action="core.set", params={"name": name, "value": 1})]))
