import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from rpa_orkestrai.agents.models import Actor, Agent, AgentEvent, AgentRun, AgentTask
from rpa_orkestrai.agents.storage import AgentStore
from rpa_orkestrai.models import now, uid


@pytest.fixture
def records(tmp_path):
    store = AgentStore(tmp_path)
    agent = Agent(name="Analiz", company_id=2, user_id=1)
    actor = Actor(company_id=2, user_id=1, session_id="oturum")
    return store, agent, actor


def link_or_skip(source, target):
    try:
        source.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("Bu test ortamı sembolik bağlantı oluşturmaya izin vermiyor.")


def test_save_load_and_delete_are_independent_copies(records):
    store, definition, actor = records
    saved = store.save_agent(definition)
    saved.name = "Değişti"
    definition.name = "Bellekte değişti"
    assert store.agent(definition.id).name == "Analiz"
    loaded = store.agents()[0]
    loaded.limits.max_turns = 100
    assert store.agent(definition.id).limits.max_turns == 20
    run = AgentRun(agent_id=definition.id, actor=actor, agent_revision=1, task="İncele",
                   events=[AgentEvent(kind="message", data={"nested": [1]})])
    store.save_run(run)
    run.events[0].data["nested"].append(2)
    assert store.run(run.id).events[0].data["nested"] == [1]
    store.delete_agent(definition.id)
    with pytest.raises(KeyError):
        store.agent(definition.id)
    # Deleting a definition must not erase the audit trail.
    assert store.run(run.id).agent_id == definition.id


@pytest.mark.parametrize("key", ["../other", "/tmp/record", "a" * 31, "A" * 32, "z" * 32, ""])
def test_traversal_and_invalid_record_ids_are_rejected(records, key):
    store, _, _ = records
    with pytest.raises(KeyError):
        store.agent(key)
    with pytest.raises(KeyError):
        store.path("other", uid())


def test_symlinked_folder_and_record_are_rejected(tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    root = tmp_path / "data"
    root.mkdir()
    link_or_skip(root / "agents", external)
    with pytest.raises(ValueError):
        AgentStore(root)
    (root / "agents").unlink()
    store = AgentStore(root)
    target = external / "private.json"
    target.write_text("private", encoding="utf-8")
    key = uid()
    link_or_skip(root / "agents" / f"{key}.json", target)
    with pytest.raises(ValueError):
        store.agent(key)
    with pytest.raises(ValueError):
        store.agents()
    assert target.read_text(encoding="utf-8") == "private"


def test_atomic_temp_file_cannot_redirect_a_write(records, tmp_path):
    store, definition, _ = records
    target = tmp_path / "unrelated.txt"
    target.write_text("Korunmalı", encoding="utf-8")
    link_or_skip(store.path("agents", definition.id).with_suffix(".tmp"), target)
    with pytest.raises(ValueError):
        store.save_agent(definition)
    assert target.read_text(encoding="utf-8") == "Korunmalı"


def test_saved_identity_must_match_its_filename(records):
    store, definition, _ = records
    path = store.path("agents", uid())
    path.write_text(definition.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError):
        store.agent(path.stem)


def test_invalid_file_contents_are_not_echoed_in_errors(records):
    store, definition, _ = records
    path = store.path("agents", definition.id)
    path.write_text('{"unexpected":"private-value"}', encoding="utf-8")
    with pytest.raises(ValueError) as captured:
        store.agent(definition.id)
    assert "private-value" not in str(captured.value)


def test_save_revalidates_mutated_models(records):
    store, definition, actor = records
    definition.limits.max_turns = -1
    with pytest.raises(ValidationError):
        store.save_agent(definition)
    run = AgentRun(agent_id=definition.id, actor=actor, agent_revision=1, task="İncele")
    run.inputs = {"sifre": {}}
    with pytest.raises(ValidationError):
        store.save_run(run)


def test_stores_share_a_lock_and_atomic_writes_leave_valid_json(records):
    store, definition, _ = records
    other = AgentStore(store.root)
    assert store._lock is other._lock

    def save(index):
        local = definition.model_copy(update={"description": str(index)})
        (store if index % 2 else other).save_agent(local)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(save, range(20)))
    content = json.loads(store.path("agents", definition.id).read_text(encoding="utf-8"))
    assert content["description"] in {str(index) for index in range(20)}
    assert not list((store.root / "agents").glob("*.tmp"))


@pytest.mark.parametrize("status", ["queued", "running", "waiting_user", "waiting_approval"])
def test_restart_invalidates_pending_approvals_and_does_not_replay(records, status):
    store, definition, actor = records
    run = AgentRun(agent_id=definition.id, actor=actor, agent_revision=1, task="İncele", status=status,
                   pending_approval={"id": uid()}, pending_question={"question": "Devam?"})
    store.save_run(run)
    store.recover_runs()
    recovered = store.run(run.id)
    assert recovered.status == "failed" and recovered.finished_at
    assert recovered.pending_approval is None and recovered.pending_question is None
    assert recovered.events[-1].kind == "interrupted"
    store.recover_runs()
    assert len(store.run(run.id).events) == 1


@pytest.mark.parametrize("status", ["succeeded", "failed", "cancelled"])
def test_restart_preserves_terminal_runs(records, status):
    store, definition, actor = records
    run = AgentRun(agent_id=definition.id, actor=actor, agent_revision=1, task="İncele", status=status)
    store.save_run(run)
    store.recover_runs()
    assert store.run(run.id) == run


def test_restart_repairs_task_metrics_from_run_after_interrupted_dual_write(records):
    store, definition, actor = records
    task = AgentTask(company_id=2, created_by=actor, assignee_id=definition.id,
                     assigned_agent_id=definition.id, title="İncele")
    run = AgentRun(agent_id=definition.id, actor=actor, agent_revision=1, task="İncele", task_id=task.id,
                   status="succeeded", finished_at=now(), summary="Bitti", tokens_in=5, tokens_out=7,
                   total_tokens=12, approval_wait_seconds=3, workflow_run_ids=[uid()])
    task.run_id = run.id
    store.save_task(task)
    store.save_run(run)
    store.recover_runs()
    repaired = store.task(task.id)
    assert repaired.status == "succeeded" and repaired.finished_at == run.finished_at
    assert repaired.summary == "Bitti" and repaired.total_tokens == 12
    assert repaired.workflow_run_ids == run.workflow_run_ids and repaired.approval_wait_seconds == 3


def test_task_from_before_provider_snapshots_loads_with_empty_defaults(records):
    store, definition, actor = records
    task = AgentTask(company_id=2, created_by=actor, assignee_id=definition.id, title="Eski görev")
    legacy = task.model_dump()
    legacy.pop("provider_connection_id")
    legacy.pop("model")
    store.path("agent_tasks", task.id).write_text(json.dumps(legacy), encoding="utf-8")
    loaded = store.task(task.id)
    assert loaded.provider_connection_id is None and loaded.model == ""


def test_restart_preserves_human_tasks_but_interrupts_local_agent_tasks(records):
    store, definition, actor = records
    human = AgentTask(company_id=2, created_by=actor, assignee_type="human", assignee_id="1", title="İncele")
    agent = AgentTask(company_id=2, created_by=actor, assignee_id=definition.id, title="Özetle")
    store.save_task(human)
    store.save_task(agent)
    store.recover_runs()
    assert store.task(human.id).status == "queued"
    assert store.task(agent.id).status == "failed"
