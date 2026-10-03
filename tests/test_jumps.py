"""Adıma git: a path continues at another step, back or ahead, without copying steps."""

import threading
import time

import pytest

from rpa_orkestrai.config import Settings
from rpa_orkestrai.engine import Executor, RunManager, WorkflowError, validate_workflow
from rpa_orkestrai.models import Run, Step, Workflow
from rpa_orkestrai.storage import Store


def run_flow(tmp_path, steps, **variables):
    settings = Settings(tmp_path, dotenv=False)
    store = Store(tmp_path)
    workflow = Workflow(name="Bağlantılar", steps=steps)
    validate_workflow(workflow)
    run = Run(workflow_id=workflow.id, workflow_name=workflow.name, department=workflow.department)
    executor = Executor(settings, store, run, threading.Event(), lambda: store.save_run(run), variables)
    executor.execute(workflow)
    return executor, run


def note(step_id, value=None):
    """Records that the step ran (its id, or the given value) in ${seen}."""
    return Step(id=step_id, action="data.append", params={"name": "seen", "value": step_id if value is None else value})


def goto(step_id, target, **params):
    return Step(id=step_id, action="control.goto", params={"target": target, **params})


def condition(step_id, left, operator, right, yes=(), no=()):
    return Step(id=step_id, action="control.if", params={"left": left, "operator": operator, "right": right},
                children=list(yes), otherwise=list(no))


def test_a_jump_ahead_skips_the_steps_in_between(tmp_path):
    executor, run = run_flow(tmp_path, [
        note("a", None), goto("jump", "c"), note("b", None), note("c", None)])
    assert executor.variables["seen"] == ["a", "c"]
    assert "b" not in run.step_stats and run.step_stats["jump"]["ok"] == 1
    assert any("«Listeye ekle» adımına gidiliyor." in event.message for event in run.events)


def test_going_back_repeats_steps_until_the_condition_changes(tmp_path):
    executor, run = run_flow(tmp_path, [
        Step(id="count", action="data.calculate", params={"expression": "${tries} + 1", "output": "tries"}),
        condition("check", "${tries}", "lt", 3, yes=[goto("again", "count")]),
        note("done", "${tries}"),
    ], tries=0)
    assert executor.variables["seen"] == [3]
    assert run.step_stats["count"]["ok"] == 3 and run.step_stats["again"]["ok"] == 2


def test_an_endless_jump_stops_at_its_limit(tmp_path):
    with pytest.raises(WorkflowError, match="«Listeye ekle» adımına 3 kez gidildi; sonsuz döngüye"):
        run_flow(tmp_path, [note("a", None), goto("back", "a", max_jumps=3)])


def test_within_a_loop_the_limit_counts_each_turn(tmp_path):
    def rows(times):
        # Every row is added, then the path goes back to add it again until it is in ${seen} `times` times.
        return [Step(id="rows", action="control.for_each", params={"items": [1, 2, 3], "item_name": "row"}, children=[
            Step(id="reset", action="core.set", params={"name": "added", "value": 0}),
            Step(id="add", action="data.append", params={"name": "seen", "value": "${row}"}),
            Step(id="count", action="data.calculate", params={"expression": "${added} + 1", "output": "added"}),
            condition("more", "${added}", "lt", times, yes=[goto("again", "add", max_jumps=1)]),
        ])]

    # Going back once for every row uses the jump three times in all, once per turn.
    executor, _ = run_flow(tmp_path / "a", rows(2))
    assert executor.variables["seen"] == [1, 1, 2, 2, 3, 3]
    # Twice within one turn is more than allowed.
    with pytest.raises(WorkflowError, match="adımına bu turda 1 kez gidildi"):
        run_flow(tmp_path / "b", rows(3))


def test_connecting_back_to_the_loop_box_starts_the_next_turn(tmp_path):
    executor, run = run_flow(tmp_path, [Step(id="rows", action="control.for_each", params={
        "items": [1, 2, 3], "item_name": "row"}, children=[
            condition("skip", "${row}", "eq", 2, yes=[goto("next", "rows")]),
            Step(id="add", action="data.append", params={"name": "seen", "value": "${row}"}),
        ]), note("after", "son")])
    assert executor.variables["seen"] == [1, 3, "son"]
    assert run.step_stats["rows"]["runs"] == 1


def test_a_jump_out_of_a_loop_ends_it_and_restores_its_variables(tmp_path):
    executor, _ = run_flow(tmp_path, [Step(id="rows", action="control.for_each", params={
        "items": [1, 2, 3], "item_name": "row"}, children=[
            condition("found", "${row}", "eq", 2, yes=[goto("leave", "report")]),
            Step(id="add", action="data.append", params={"name": "seen", "value": "${row}"}),
        ]), note("skipped", "atlandı"), note("report", "rapor")])
    assert executor.variables["seen"] == [1, "rapor"]
    assert "row" not in executor.variables and "loop_index" not in executor.variables


def test_an_inner_loop_can_continue_the_outer_loop(tmp_path):
    executor, _ = run_flow(tmp_path, [Step(id="outer", action="control.for_each", params={
        "items": ["a", "b"], "item_name": "letter"}, children=[
            Step(id="inner", action="control.for_each", params={"items": [1, 2], "item_name": "digit"}, children=[
                Step(id="add", action="data.append", params={"name": "seen", "value": "${letter}${digit}"}),
                goto("next-letter", "outer"),
            ]),
            note("never", "x"),
        ])])
    assert executor.variables["seen"] == ["a1", "b1"]


def test_one_branch_can_continue_in_the_middle_of_the_other(tmp_path):
    # Değilse does its own first step, then shares the rest of the Doğruysa branch.
    flow = [condition("check", "${kind}", "eq", "iade", yes=[note("open", None), note("fill", None)],
                      no=[note("search", None), goto("join", "fill")]), note("save", None)]
    executor, _ = run_flow(tmp_path / "a", flow, kind="satis")
    assert executor.variables["seen"] == ["search", "fill", "save"]
    executor, _ = run_flow(tmp_path / "b", flow, kind="iade")
    assert executor.variables["seen"] == ["open", "fill", "save"]


def test_a_jump_into_a_try_block_keeps_its_error_handler(tmp_path):
    executor, _ = run_flow(tmp_path, [
        goto("retry", "fail"),
        Step(id="guard", action="control.try", params={"error_name": "problem"}, children=[
            note("start", None),
            Step(id="fail", action="core.set", params={"name": "x", "value": "${missing}"}),
        ], otherwise=[note("handled", "${problem}")]),
    ])
    # The jump skipped the first step of the block, and the failing step was still caught.
    [message] = executor.variables["seen"]
    assert "missing" in message


def test_impossible_connections_are_named_before_the_run(tmp_path):
    loop = Step(id="rows", action="control.for_each", params={"items": [1], "item_name": "row"},
                children=[note("inside", None)])
    guard = Step(id="guard", action="control.try", params={}, children=[note("try", None)],
                 otherwise=[note("handler", None)])
    cases = {
        "missing": ([goto("j", "nowhere")], "akışta yok"),
        "self": ([goto("j", "j")], "kendisine"),
        "into-loop": ([loop.model_copy(deep=True), goto("j", "inside")], "«Her satır için» döngüsünün içindeki"),
        "into-handler": ([guard.model_copy(deep=True), goto("j", "handler")], "Hata olursa dalındaki"),
    }
    for name, (steps, message) in cases.items():
        with pytest.raises(WorkflowError, match=message):
            validate_workflow(Workflow(steps=steps))
        validate_workflow(Workflow(steps=steps), ready=False)  # an unfinished draft can still be saved
    # These are fine: the loop box itself, a step of the same loop, a condition branch, the Dene block.
    validate_workflow(Workflow(steps=[loop.model_copy(deep=True), goto("j", "rows")]))
    validate_workflow(Workflow(steps=[Step(id="rows", action="control.for_each", params={"items": [1]},
                                           children=[note("inside", None), goto("j", "inside")])]))
    validate_workflow(Workflow(steps=[guard.model_copy(deep=True), goto("j", "try")]))
    validate_workflow(Workflow(steps=[condition("c", 1, "eq", 1, yes=[note("y", None)]), goto("j", "y")]))
    with pytest.raises(WorkflowError, match="Gidilecek adım gereklidir"):
        validate_workflow(Workflow(steps=[note("a", None), Step(id="j", action="control.goto")]))


def test_testing_a_jump_alone_tells_where_the_flow_would_go(tmp_path):
    settings = Settings(tmp_path, dotenv=False)
    store = Store(tmp_path)
    manager = RunManager(settings, store)
    workflow = store.save_workflow(Workflow(name="Test", steps=[
        Step(id="search", title="Ara", action="core.log", params={"message": "ara"}),
        condition("found", "${found}", "eq", False, yes=[goto("again", "search")]),
    ]))
    try:
        run = manager.start_step(workflow, "again", {})
        deadline = time.monotonic() + 5
        while store.run(run.id).status in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(0.01)
        finished = store.run(run.id)
        assert finished.status == "succeeded", finished.error
        assert any("«Ara» adımına gidilir" in event.message for event in finished.events)
    finally:
        manager.close()


def test_jumps_in_a_preview_follow_the_same_path(tmp_path):
    settings = Settings(tmp_path, dotenv=False)
    store = Store(tmp_path)
    workflow = Workflow(steps=[note("a", None), goto("skip", "c"), note("b", None), note("c", None)])
    run = Run(workflow_id=workflow.id, workflow_name=workflow.name, department=workflow.department, dry_run=True)
    executor = Executor(settings, store, run, threading.Event(), lambda: store.save_run(run))
    executor.execute(workflow)
    assert executor.variables["seen"] == ["a", "c"]
