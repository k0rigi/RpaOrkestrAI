import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_agent_runner import (
    AGENT_TEST_SECONDS,
    approval_wait,
    finish,
    response,
    run_call,
    wait_for,
    write_flow,
)
from test_agent_runner import runtime as runtime

from rpa_orkestrai.agents.models import AgentInput, AgentLimits, AgentRunRequest, WorkflowGrant
from rpa_orkestrai.agents.organization import BudgetExceeded, OrganizationError, TeamBudget
from rpa_orkestrai.agents.providers import ScriptedProvider, ToolCall, Usage
from rpa_orkestrai.agents.runner import AgentServiceError
from rpa_orkestrai.models import Step, uid


def make_team(runtime, *, manager_limits=None, child_limits=None, grants=None):
    manager = runtime.service.create_agent(AgentInput(name="Yönetici", role="manager", model="test",
        limits=manager_limits or AgentLimits(max_seconds=AGENT_TEST_SECONDS)))
    child = runtime.service.create_agent(AgentInput(name="Departman", department="İnceleme", manager_id=manager.id,
        model="test", workflows=grants or [], limits=child_limits or AgentLimits(max_seconds=AGENT_TEST_SECONDS)))
    return manager, child


def delegate(agent, title="İncele"):
    return ToolCall(uid(), "delegate_task", {"agent_id": agent.id, "title": title,
                                             "instructions": "Görevi kendi yetkilerinle tamamla."})


def providers(runtime, mapping):
    runtime.service._provider_factory = lambda agent: mapping[agent.id]


def test_one_manager_per_company_and_parent_must_be_same_company_manager(runtime):
    manager, child = make_team(runtime)
    with pytest.raises(OrganizationError):
        runtime.service.create_agent(AgentInput(name="İkinci", role="manager"))
    with pytest.raises(OrganizationError):
        runtime.service.create_agent(AgentInput(name="Alt yönetici", manager_id=child.id))
    with pytest.raises(OrganizationError):
        runtime.service.update_agent(manager.id, AgentInput(name="Artık departman"))
    with pytest.raises(AgentServiceError):
        runtime.service.delete_agent(manager.id)
    with pytest.raises(OrganizationError):
        runtime.service.update_agent(child.id, AgentInput(name="Döngü", manager_id=child.id))
    runtime.state["actor"] = runtime.owner.model_copy(update={"company_id": 3})
    with pytest.raises(OrganizationError):
        runtime.service.create_agent(AgentInput(name="Yabancı", manager_id=manager.id))
    assert runtime.service.create_agent(AgentInput(name="Başka firma", role="manager")).company_id == 3


def test_manager_delegates_and_combines_completed_children_without_elevating_permissions(runtime):
    allowed = runtime.workflow(Step(action="core.set", params={"name": "result", "value": "Özet"}))
    forbidden = runtime.workflow(Step(action="core.set", params={"name": "private", "value": "Gizli"}))
    manager, child = make_team(runtime, grants=[WorkflowGrant(workflow_id=allowed.id)])
    manager_provider = ScriptedProvider([response(ToolCall(uid(), "list_team", {}), delegate(child)),
                                         response(finish()), response(finish("Ekip işi tamamladı"))])
    child_provider = ScriptedProvider([response(run_call(forbidden)), response(run_call(allowed)), response(finish())])
    providers(runtime, {manager.id: manager_provider, child.id: child_provider})
    run = runtime.service.start(manager.id, AgentRunRequest(task="Ekibi koordine et"))
    saved = runtime.done(run)
    assert saved.status == "succeeded" and saved.workflow_count == 0
    assert len(saved.delegated_task_ids) == 1
    child_task = runtime.service.get_task(saved.delegated_task_ids[0])
    assert child_task.status == "succeeded" and child_task.parent_task_id == saved.task_id
    assert child_task.root_run_id == run.id and len(child_task.workflow_run_ids) == 1
    assert runtime.store.run(child_task.workflow_run_ids[0]).workflow_id == allowed.id
    assert saved.team_usage["workflow_count"] == 1 and saved.team_usage["task_count"] == 1
    assert saved.team_usage["turns"] == 6
    result = manager_provider.requests[-1]["messages"]
    assert any("children_completed" in message.get("content", "") for message in result)
    assert runtime.service.get_task(saved.task_id).summary == "Ekip işi tamamladı"
    tools = {tool["name"] for tool in manager_provider.requests[0]["tools"]}
    assert tools == {"list_team", "delegate_task", "get_task", "list_tasks", "wait_tasks", "answer_department",
                     "ask_user", "suggest_note", "finish"}
    child_tools = {tool["name"] for tool in child_provider.requests[0]["tools"]}
    assert "ask_manager" in child_tools and not child_tools & {"delegate_task", "answer_department", "wait_tasks"}


def test_manager_cannot_delegate_to_self_unrelated_or_other_company(runtime):
    manager, child = make_team(runtime)
    unrelated = runtime.agent()
    parent_provider = ScriptedProvider([response(delegate(manager), delegate(unrelated)), response(finish())])
    providers(runtime, {manager.id: parent_provider})
    run = runtime.service.start(manager.id, AgentRunRequest(task="Görev dağıt"))
    saved = runtime.done(run)
    assert saved.status == "succeeded" and saved.delegated_task_ids == []
    assert len(runtime.service.tasks()) == 1
    errors = [event.data["untrusted_data"] for event in saved.events if event.kind == "tool_result"]
    assert sum(item.get("status") == "error" for item in errors) == 2
    # A child cannot delegate back to its manager or to a sibling.
    runtime.service._provider_factory = lambda agent: runtime.state["provider"]
    run = runtime.start(child, response(delegate(manager)), response(finish()))
    saved = runtime.done(run)
    assert saved.status == "succeeded" and saved.delegated_task_ids == []


def test_child_risky_work_still_waits_for_owner_approval(runtime):
    flow, target = write_flow(runtime)
    manager, child = make_team(runtime, grants=[WorkflowGrant(workflow_id=flow.id,
                                                             allowed_roots=[str(runtime.business)])])
    providers(runtime, {manager.id: ScriptedProvider([response(delegate(child)), response(finish()), response(finish())]),
                        child.id: ScriptedProvider([response(run_call(flow)), response(finish())])})
    run = runtime.service.start(manager.id, AgentRunRequest(task="İşi devret"))
    task = wait_for(lambda: runtime.service.tasks(child.id), lambda items: bool(items))[0]
    pending = approval_wait(runtime, runtime.service.get_run(task.run_id))
    assert not target.exists()
    runtime.service.approve(task.run_id, pending.pending_approval["id"], False)
    assert runtime.done(run).status == "succeeded"
    child_task = runtime.service.get_task(task.id)
    assert child_task.workflow_run_ids == [] and child_task.approval_wait_seconds > 0
    assert any(event.kind == "approval_decision" for event in child_task.approvals)


@pytest.mark.parametrize("clock_moves_back", [False, True])
def test_same_agent_jobs_are_fifo_and_queue_is_only_metadata(runtime, clock_moves_back):
    agent = runtime.agent()
    provider = ScriptedProvider([response(ToolCall(uid(), "ask_user", {"question": "Devam?"})),
                                  response(finish("Bir")), response(finish("İki")), response(finish("Üç"))])
    runtime.service._provider_factory = lambda _: provider
    first = runtime.service.start(agent.id, AgentRunRequest(task="Birinci gizli iş"))
    wait_for(lambda: runtime.service.get_run(first.id), lambda run: run.status == "waiting_user")
    with runtime.service._lock:
        second = runtime.service.start(agent.id, AgentRunRequest(task="İkinci gizli iş"))
        third = runtime.service.start(agent.id, AgentRunRequest(task="Üçüncü gizli iş"))
        if clock_moves_back:
            runtime.service._contexts[third.id].run.created_at = "2000-01-01T00:00:00+00:00"
    queue = runtime.service.queue()
    assert [(item["run_id"], item["position"]) for item in queue] == [(first.id, 0), (second.id, 1), (third.id, 2)]
    assert "gizli" not in json.dumps(queue)
    pending = runtime.service.get_run(first.id)
    runtime.service.answer(first.id, pending.pending_question["id"], "Evet")
    runs = [runtime.done(item) for item in (first, second, third)]
    assert [item.summary for item in runs] == ["Bir", "İki", "Üç"]
    assert runs[0].finished_at <= runs[1].started_at <= runs[2].started_at
    assert runtime.service.queue() == []
    assert {task.status for task in runtime.service.tasks()} == {"succeeded"}


def test_fifo_survives_running_job_finishing_between_two_queue_candidates(runtime, monkeypatch):
    agent = runtime.agent()
    provider = ScriptedProvider([response(ToolCall(uid(), "ask_user", {"question": "Devam?"})),
                                response(finish("Bir")), response(finish("İki")), response(finish("Üç"))])
    runtime.service._provider_factory = lambda _: provider
    first = runtime.service.start(agent.id, AgentRunRequest(task="Birinci"))
    pending = wait_for(lambda: runtime.service.get_run(first.id), lambda run: run.status == "waiting_user")
    original_check = runtime.service._check
    candidates = {}
    saw_second, forced_completion = threading.Event(), threading.Event()

    def check(context):
        if threading.current_thread() is runtime.service._queue_thread:
            if context.run.id == candidates.get("second"):
                saw_second.set()
            if context.run.id == candidates.get("third") and not forced_completion.is_set():
                assert saw_second.is_set()
                forced_completion.set()
                # The earlier candidate was skipped because the first job was
                # running. Finish that job before checking the later candidate.
                runtime.service.answer(first.id, pending.pending_question["id"], "Evet")
                runtime.done(first)
                with runtime.service._lock:
                    assert first.id not in runtime.service._contexts
        return original_check(context)

    monkeypatch.setattr(runtime.service, "_check", check)
    # Both candidates must belong to the same scheduler pass.
    with runtime.service._lock:
        second = runtime.service.start(agent.id, AgentRunRequest(task="İkinci"))
        third = runtime.service.start(agent.id, AgentRunRequest(task="Üçüncü"))
        candidates.update(second=second.id, third=third.id)
    runs = [runtime.done(item) for item in (first, second, third)]
    assert forced_completion.is_set()
    assert [item.summary for item in runs] == ["Bir", "İki", "Üç"]
    assert all(item.status == "succeeded" for item in runs)
    assert runs[0].finished_at <= runs[1].started_at <= runs[2].started_at
    assert runtime.service.queue() == []


def test_cancelling_root_cancels_running_and_queued_children(runtime):
    manager, child = make_team(runtime)
    providers(runtime, {manager.id: ScriptedProvider([response(delegate(child, "Bir"), delegate(child, "İki")),
                                                       response(finish())]),
                        child.id: ScriptedProvider([response(ToolCall(uid(), "ask_user", {"question": "Bekle?"}))])})
    run = runtime.service.start(manager.id, AgentRunRequest(task="İki görev"))
    wait_for(lambda: runtime.service.tasks(child.id), lambda tasks: len(tasks) == 2)
    runtime.service.cancel(run.id)
    assert runtime.done(run).status == "cancelled"
    tasks = wait_for(lambda: runtime.service.tasks(child.id), lambda tasks: all(task.finished_at for task in tasks))
    assert {task.status for task in tasks} == {"cancelled"}
    assert not runtime.service.queue()


@pytest.mark.parametrize("kind", ["tasks", "turns", "tokens", "workflows", "seconds"])
def test_root_budget_bounds_the_whole_team(runtime, kind):
    limits = AgentLimits(max_seconds=AGENT_TEST_SECONDS)
    if kind == "tasks":
        limits.max_tasks = 1
    elif kind == "turns":
        limits.max_turns = 1
    elif kind == "tokens":
        limits.max_tokens = 5
    elif kind == "workflows":
        limits.max_workflow_runs = 1
    else:
        limits.max_seconds = 0.12
    flow = runtime.workflow(Step(action="core.set", params={"name": "value", "value": 1}))
    manager, child = make_team(runtime, manager_limits=limits, grants=[WorkflowGrant(workflow_id=flow.id)])
    calls = [delegate(child, "Bir"), delegate(child, "İki")] if kind in {"tasks", "workflows"} else [delegate(child)]
    parent_provider = ScriptedProvider([response(*calls), response(finish()), response(finish())])
    if kind == "tokens":
        child_provider = ScriptedProvider([response(finish(), usage=Usage(4, 4))])
    elif kind == "seconds":
        child_provider = ScriptedProvider([response(ToolCall(uid(), "ask_user", {"question": "Bekle?"}))])
    else:
        child_provider = ScriptedProvider([response(run_call(flow)), response(finish()),
                                           response(run_call(flow)), response(finish())])
    providers(runtime, {manager.id: parent_provider, child.id: child_provider})
    run = runtime.service.start(manager.id, AgentRunRequest(task="Ekibin bütçesini aşmayı dene"))
    saved = runtime.done(run)
    assert saved.status == "failed"
    assert len(runtime.store.runs()) <= limits.max_workflow_runs
    wait_for(lambda: runtime.service.tasks(), lambda tasks: all(task.finished_at for task in tasks))
    assert runtime.service.queue() == []


def test_token_reservations_are_atomic_across_parallel_children():
    budget = TeamBudget(AgentLimits(max_tokens=10), time.monotonic() + 5)
    barrier = threading.Barrier(3)

    def reserve(identity):
        barrier.wait()
        return budget.reserve_turn(identity, 10)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(reserve, identity) for identity in ("one", "two")]
        barrier.wait()
        allowances = [future.result() for future in futures]
    assert sorted(value or 0 for value in allowances) == [0, 10]
    used = next(identity for identity in ("one", "two") if identity in budget.reserved)
    budget.release_turn(used, Usage(8, 2))
    with pytest.raises(BudgetExceeded):
        budget.reserve_turn("next", 1)


def test_model_default_is_resolved_without_mutating_saved_agent(runtime):
    connection_id = uid()
    item = runtime.service.create_agent(AgentInput(name="Varsayılan bağlantı", model="",
                                                  provider_connection_id=connection_id))
    runtime.service.model_resolver = lambda agent: "yerel-model"
    run = runtime.start(item, response(finish()))
    assert runtime.done(run).status == "succeeded"
    assert runtime.state["provider"].requests[0]["model"] == "yerel-model"
    assert runtime.service.get_agent(item.id).model == ""
    task_id = runtime.service.get_run(run.id).task_id
    task = runtime.service.get_task(task_id)
    assert task.model == "yerel-model" and task.provider_connection_id == connection_id
    runtime.service.model_resolver = lambda agent: "başka-model"
    runtime.service.update_agent(item.id, AgentInput(name="Değişti", model="yeni-model",
                                                     provider_connection_id=uid()))
    assert runtime.service.get_task(task_id).model == "yerel-model"
    assert runtime.service.get_task(task_id).provider_connection_id == connection_id


def test_provider_key_source_is_masked_in_all_task_and_run_records(runtime):
    secret = "provider-only-private-key"
    runtime.service.secret_source = lambda: [secret]
    item = runtime.agent()
    runtime.state["provider"] = ScriptedProvider([response(finish(secret))])
    run = runtime.service.start(item.id, AgentRunRequest(task=secret, inputs={"value": secret}))
    saved = runtime.done(run)
    assert secret not in json.dumps(runtime.state["provider"].requests)
    assert secret not in saved.model_dump_json()
    assert secret not in runtime.service.get_task(saved.task_id).model_dump_json()
    runtime.service.secret_source = lambda: (_ for _ in ()).throw(RuntimeError(secret))
    with pytest.raises(AgentServiceError) as denied:
        runtime.service.start(item.id, AgentRunRequest(task="İş"))
    assert secret not in str(denied.value)


def test_provider_key_accidentally_pasted_in_agent_definition_is_not_saved(runtime):
    secret = "provider-only-private-key"
    runtime.service.secret_source = lambda: [secret]
    item = runtime.service.create_agent(AgentInput(name=secret, description=secret, instructions=secret))
    assert secret not in runtime.service.agent_store.agent(item.id).model_dump_json()
    with pytest.raises(AgentServiceError):
        runtime.service.update_agent(item.id, AgentInput(name="Ajan", model=secret))


def ask_manager(question="Hangi dönemi kullanayım?"):
    return ToolCall(uid(), "ask_manager", {"question": question, "options": ["Mart", "Nisan"]})


def last_tool_data(request):
    message = request["messages"][-1]
    return json.loads(message["content"])["untrusted_data"] if message.get("role") == "tool" else {}


def test_department_asks_manager_and_gets_answer_without_user(runtime):
    from rpa_orkestrai.agents.office import snapshot

    manager, child = make_team(runtime)
    gate, office = threading.Event(), {}

    def manager_reply(request):
        data = last_tool_data(request)
        if data.get("status") != "department_question":
            return None
        office.update(snapshot(runtime.service))
        gate.set()
        question = data["questions"][0]
        assert question["agent_id"] == child.id and question["question"] == "Hangi dönemi kullanayım?"
        return response(ToolCall(uid(), "answer_department", {"question_id": question["question_id"], "answer": "Mart"}),
                        finish())

    manager_provider = ScriptedProvider([response(delegate(child)), response(finish()), response(finish("Ekip bitirdi"))],
                                        callback=manager_reply)
    child_provider = ScriptedProvider([response(ask_manager()), response(finish("Mart raporu hazır"))])
    providers(runtime, {manager.id: manager_provider, child.id: child_provider})
    run = runtime.service.start(manager.id, AgentRunRequest(task="Raporu hazırlat"))
    saved = runtime.done(run)
    assert gate.is_set() and saved.status == "succeeded"
    child_task = runtime.service.get_task(saved.delegated_task_ids[0])
    assert child_task.status == "succeeded" and child_task.summary == "Mart raporu hazır"
    answer = last_tool_data(child_provider.requests[1])
    assert answer == {"answer": "Mart", "from": "manager"}
    assert "ask_manager" in child_provider.requests[0]["messages"][0]["content"]
    assert {"department_question", "department_answered"} <= {event.kind for event in saved.events}
    child_run = runtime.service.get_run(child_task.run_id)
    assert {"manager_question", "manager_answer"} <= {event.kind for event in child_run.events}
    assert child_run.pending_question is None and not any(event.kind == "question" for event in child_run.events)
    # The office sees who asks whom, never the question text.
    people = {item["id"]: item for item in office["agents"]}
    assert people[child.id]["activity"] == "asking_manager"
    assert people[child.id]["event"]["kind"] == "question" and people[child.id]["event"]["to_agent_id"] == manager.id
    assert people[manager.id]["activity"] == "reviewing"
    assert "Hangi dönemi" not in json.dumps(office, ensure_ascii=False)


def test_ask_manager_is_only_for_delegated_work_and_answers_stay_scoped(runtime):
    manager, child = make_team(runtime)
    other = runtime.agent()
    run = runtime.start(child, response(ask_manager()), response(finish()))
    saved = runtime.done(run)
    assert saved.status == "succeeded"
    assert "ask_manager" not in {tool["name"] for tool in runtime.state["provider"].requests[0]["tools"]}
    error = next(event.data["untrusted_data"] for event in saved.events if event.kind == "tool_result")
    assert error["status"] == "error" and "ask_user" in error["error"]
    # A department agent cannot answer questions or wait for team tasks.
    run = runtime.start(other, response(ToolCall(uid(), "answer_department", {"question_id": uid(), "answer": "Evet"}),
                                        ToolCall(uid(), "wait_tasks", {})), response(finish()))
    saved = runtime.done(run)
    results = [event.data["untrusted_data"] for event in saved.events if event.kind == "tool_result"]
    assert [item.get("status") for item in results[:2]] == ["error", "error"]


def test_manager_waits_for_any_task_to_hand_results_to_next_department(runtime):
    manager = runtime.service.create_agent(AgentInput(name="Yönetici", role="manager", model="test",
                                                      limits=AgentLimits(max_seconds=AGENT_TEST_SECONDS)))
    first = runtime.service.create_agent(AgentInput(name="Muhasebe", department="Muhasebe", manager_id=manager.id,
                                                    model="test", limits=AgentLimits(max_seconds=AGENT_TEST_SECONDS)))
    second = runtime.service.create_agent(AgentInput(name="Satış", department="Satış", manager_id=manager.id,
                                                     model="test", limits=AgentLimits(max_seconds=AGENT_TEST_SECONDS)))

    def manager_reply(request):
        data = last_tool_data(request)
        if "tasks" in data and data.get("status") is None and all(task["status"] == "succeeded" for task in data["tasks"]):
            total = data["tasks"][0]["result"]["toplam"]
            return response(ToolCall(uid(), "delegate_task", {"agent_id": second.id, "title": "Teklif",
                                     "instructions": "Toplamı kullan", "inputs": {"toplam": total}}))
        return None

    manager_provider = ScriptedProvider([response(delegate(first)), response(ToolCall(uid(), "wait_tasks", {"until": "any"})),
                                         response(finish()), response(finish("Zincir tamam"))], callback=manager_reply)
    providers(runtime, {
        manager.id: manager_provider,
        first.id: ScriptedProvider([response(ToolCall(uid(), "finish", {"summary": "Toplam", "result": {"toplam": 42}}))]),
        second.id: ScriptedProvider([response(finish("Teklif hazır"))]),
    })
    saved = runtime.done(runtime.service.start(manager.id, AgentRunRequest(task="Zinciri yürüt")))
    assert saved.status == "succeeded" and len(saved.delegated_task_ids) == 2
    handed = runtime.service.get_task(saved.delegated_task_ids[1])
    assert handed.assigned_agent_id == second.id and runtime.service.get_run(handed.run_id).inputs == {"toplam": 42}
