"""Named Sheets records and bounded nested conditions without real ERP input."""

import json
import threading
from pathlib import Path
from unittest.mock import Mock, call

import pytest

from rpa_orkestrai.config import Settings
from rpa_orkestrai.engine import (
    UNKNOWN,
    Cancelled,
    Executor,
    WorkflowError,
    compare,
    validate_workflow,
)
from rpa_orkestrai.integrations.sheets import SheetsService
from rpa_orkestrai.models import Run, Step, Workflow
from rpa_orkestrai.storage import Store


@pytest.fixture
def runner(tmp_path):
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "verified-result.png").write_bytes(b"mocked-image-match")
    settings = Settings(tmp_path, dotenv=False)
    settings.update({"google_credentials_path": "test-credentials.json", "template_dir": str(templates)})
    run = Run(workflow_id="test", workflow_name="Conditional rows", department="Test")
    executor = Executor(settings, Store(tmp_path), run, threading.Event(), lambda: None)
    executor._desktop = Mock()
    executor._windows = Mock()
    executor._windows.find.return_value = {"found": True, "title": "ERP"}
    service = SheetsService("unused.json", "sheet-id", "Sayfa1")
    service._worksheet = Mock()
    executor._sheets[("sheet-id", "Sayfa1")] = service
    return executor, service._worksheet


def read_cell(**params):
    return Step(action="sheets.read_cell", params={
        "spreadsheet_id": "sheet-id", "worksheet": "Sayfa1", "cell": "C2", **params,
    })


def pending_workflow():
    return Workflow(steps=[
        Step(action="desktop.find_window", params={"title": "ERP"}),
        Step(action="sheets.read_rows", params={
            "spreadsheet_id": "https://docs.google.com/spreadsheets/d/sheet-id/edit", "worksheet": "Sayfa1",
            "columns": {"form_id": "B", "status": "C"}, "start_row": 2, "max_rows": 5,
            "empty_policy": "skip",
        }),
        Step(action="control.for_each", params={"items": "${sheet_rows}", "item_name": "row"}, children=[
            Step(action="control.if", params={
                "left": "${row.status}", "operator": "empty_or_eq", "right": "Bekliyor",
            }, children=[
                Step(action="desktop.window_fill", params={"x": 120, "y": 80, "text": "${row.form_id}"}),
                Step(action="desktop.window_wait_image", params={"template": "verified-result.png"}),
                Step(action="sheets.write_cell", params={"spreadsheet_id": "sheet-id"}),
            ]),
        ]),
    ])


def test_blank_or_pending_rows_only_fill_and_write_success_to_original_rows(runner):
    executor, worksheet = runner
    worksheet.get.return_value = [
        ["000142", ""], ["000143", "Tamamlandı"], ["", "Bekliyor"],
        ["000144", "Bekliyor"], ["000145"],
    ]
    events = []
    executor._windows.fill_target.side_effect = lambda *args, **kwargs: events.append(("fill", args[1]))
    executor._windows.wait_image.side_effect = lambda *args, **kwargs: events.append(("verified",))
    worksheet.update.side_effect = lambda **kwargs: events.append(("write", kwargs["range_name"]))
    workflow = pending_workflow()
    validate_workflow(workflow)
    executor.execute(workflow)

    assert events == [
        ("fill", "000142"), ("verified",), ("write", "C2"),
        ("fill", "000144"), ("verified",), ("write", "C5"),
        ("fill", "000145"), ("verified",), ("write", "C6"),
    ]
    worksheet.get.assert_called_once_with("B2:C6", value_render_option="FORMATTED_VALUE")
    assert worksheet.update.call_args_list == [
        call(values=[["Tamamlandı"]], range_name=f"C{row}", raw=True) for row in (2, 5, 6)
    ]
    assert "row" not in executor.variables and "loop_index" not in executor.variables


def test_failed_erp_verification_never_writes_status_or_processes_next_row(runner):
    executor, worksheet = runner
    worksheet.get.return_value = [["000142", ""], ["000143", "Bekliyor"]]
    executor._windows.wait_image.side_effect = TimeoutError("result never appeared")
    with pytest.raises(TimeoutError):
        executor.execute(pending_workflow())
    executor._windows.fill_target.assert_called_once()
    worksheet.update.assert_not_called()
    assert "row" not in executor.variables


def test_conditional_table_dry_run_never_reads_or_controls_external_applications(runner):
    executor, worksheet = runner
    executor.run.dry_run = True
    executor.execute(pending_workflow())
    assert worksheet.mock_calls == []
    assert executor._windows.mock_calls == []
    assert executor._desktop.mock_calls == []
    assert executor.variables["sheet_rows"] is UNKNOWN


@pytest.mark.parametrize("blank", [None, ""])
def test_empty_cell_can_feed_an_empty_condition_when_explicitly_allowed(runner, blank):
    executor, worksheet = runner
    worksheet.acell.return_value.value = blank
    executor.execute(Workflow(steps=[
        read_cell(allow_empty=True),
        Step(action="control.if", params={
            "left": "${cell_value}", "operator": "empty", "right": "${irrelevant_missing_value}",
        }, children=[Step(action="core.set", params={"name": "branch", "value": "empty"})]),
    ]))
    assert executor.variables["cell_value"] == ""
    assert executor.variables["branch"] == "empty"


@pytest.mark.parametrize("blank", [None, ""])
def test_empty_single_cell_still_errors_in_legacy_workflows(runner, blank):
    executor, worksheet = runner
    worksheet.acell.return_value.value = blank
    with pytest.raises(WorkflowError, match="hücresi boş"):
        executor.execute(Workflow(steps=[read_cell()]))


@pytest.mark.parametrize("value, expected", [(None, True), ("", True), (" \t ", True),
                                           (0, False), (False, False), ("0", False), ([], False)])
def test_empty_predicates_distinguish_blanks_from_zero_false_and_collections(value, expected):
    assert compare(value, "empty", None) is expected
    assert compare(value, "not_empty", None) is not expected


@pytest.mark.parametrize("value, expected", [
    (None, True), (" \t ", True), ("Bekliyor", True), ("Tamamlandı", False), ("bekliyor", False),
])
def test_empty_or_equal_preserves_explicit_equality_semantics(value, expected):
    assert compare(value, "empty_or_eq", "Bekliyor") is expected


@pytest.mark.parametrize("operator, right", [
    ("one_of", "Bekliyor"), ("one_of", {"status": "Bekliyor"}),
    ("one_of", [""] * 1001), ("not-an-operator", ""), ("gt", 3),
    ([], "Bekliyor"), ({"operator": "eq"}, "Bekliyor"),
])
def test_invalid_comparisons_raise_actionable_workflow_errors(operator, right):
    with pytest.raises(WorkflowError):
        compare("Bekliyor", operator, right)


def test_one_of_checks_whole_values_and_accepts_bounded_empty_list():
    assert compare("Bekliyor", "one_of", ["", "Bekliyor"])
    assert not compare("Bek", "one_of", ["Bekliyor"])
    assert not compare("Bekliyor", "one_of", [])


@pytest.mark.parametrize("invalid_operator", [[], {"operator": "eq"}])
def test_if_rejects_nonstring_dynamic_operator_before_executing_either_branch(runner, invalid_operator):
    executor, _ = runner
    executor.variables["dynamic_op"] = invalid_operator
    workflow = Workflow(steps=[Step(action="control.if", params={
        "left": "Bekliyor", "operator": "${dynamic_op}", "right": "Bekliyor",
    }, children=[Step(action="core.set", params={"name": "yes_branch", "value": True})],
        otherwise=[Step(action="core.set", params={"name": "no_branch", "value": True})])])
    validate_workflow(workflow)
    with pytest.raises(WorkflowError, match="[Kk]arşılaştırma"):
        executor.execute(workflow)
    assert "yes_branch" not in executor.variables
    assert "no_branch" not in executor.variables


def while_step(*, children=None, **params):
    return Step(action="control.while", params={
        "left": "${status}", "operator": "ne", "right": "Tamamlandı",
        "max_iterations": 3, "max_seconds": 30, **params,
    }, children=children or [])


def test_while_rereads_sheet_status_and_exits_when_it_changes(runner):
    executor, worksheet = runner
    worksheet.acell.side_effect = [
        Mock(value="Bekliyor"), Mock(value="Bekliyor"), Mock(value="Tamamlandı"),
    ]
    workflow = Workflow(steps=[read_cell(output="status"), while_step(children=[
        Step(action="data.append", params={"name": "indices", "value": "${loop_index}"}),
        read_cell(output="status", allow_empty=True),
    ])])
    validate_workflow(workflow)
    executor.execute(workflow)
    assert executor.variables["status"] == "Tamamlandı"
    assert executor.variables["indices"] == [0, 1]
    assert worksheet.acell.call_count == 3
    assert "loop_index" not in executor.variables


@pytest.mark.parametrize("changed, new_value", [("left", 0), ("right", 10), ("op", "lt")])
def test_while_resolves_each_comparison_operand_again_after_children(runner, changed, new_value):
    executor, _ = runner
    executor.variables.update(left=5, right=1, op="gt")
    executor.execute(Workflow(steps=[while_step(
        left="${left}", operator="${op}", right="${right}", children=[
            Step(action="data.append", params={"name": "indices", "value": "${loop_index}"}),
            Step(action="core.set", params={"name": changed, "value": new_value}),
        ],
    )]))
    assert executor.variables["indices"] == [0]


@pytest.mark.parametrize("invalid_operator", [[], {"operator": "eq"}])
def test_while_rejects_child_changed_nonstring_operator_and_restores_scope(runner, invalid_operator):
    executor, _ = runner
    executor.variables.update(dynamic_op="eq", loop_index=64)
    workflow = Workflow(steps=[while_step(
        left="Bekliyor", operator="${dynamic_op}", right="Bekliyor", children=[
            Step(action="data.append", params={"name": "indices", "value": "${loop_index}"}),
            Step(action="core.set", params={"name": "dynamic_op", "value": invalid_operator}),
        ],
    )])
    validate_workflow(workflow)
    with pytest.raises(WorkflowError, match="[Kk]arşılaştırma"):
        executor.execute(workflow)
    assert executor.variables["indices"] == [0]
    assert executor.variables["loop_index"] == 64
    assert executor._deadlines == []


def test_false_while_never_executes_children(runner):
    executor, _ = runner
    executor.variables["status"] = "Tamamlandı"
    executor.execute(Workflow(steps=[while_step(children=[
        Step(action="core.set", params={"name": "touched", "value": True}),
    ])]))
    assert "touched" not in executor.variables


def test_while_repeat_limit_errors_and_restores_outer_index(runner):
    executor, _ = runner
    executor.variables.update(status="Bekliyor", loop_index=91)
    with pytest.raises(WorkflowError, match="tekrar sınırına"):
        executor.execute(Workflow(steps=[while_step(max_iterations=2, children=[
            Step(action="data.append", params={"name": "indices", "value": "${loop_index}"}),
        ])]))
    assert executor.variables["indices"] == [0, 1]
    assert executor.variables["loop_index"] == 91


def test_while_accepts_false_condition_exactly_at_iteration_limit(runner):
    executor, _ = runner
    executor.variables["status"] = "Bekliyor"
    executor.execute(Workflow(steps=[while_step(max_iterations=1, children=[
        Step(action="core.set", params={"name": "status", "value": "Tamamlandı"}),
    ])]))
    assert executor.variables["status"] == "Tamamlandı"


def test_while_timeout_stops_before_later_child_steps(runner, monkeypatch):
    executor, _ = runner
    executor.variables.update(status="Bekliyor", loop_index=19)
    clock = {"now": 0}
    monkeypatch.setattr("rpa_orkestrai.engine.time.monotonic", lambda: clock["now"])
    perform = executor.perform

    def advance_clock(action, params):
        if action == "core.set":
            clock["now"] = 2
        return perform(action, params)

    monkeypatch.setattr(executor, "perform", advance_clock)
    with pytest.raises(WorkflowError, match="süre sınırı"):
        executor.execute(Workflow(steps=[while_step(max_seconds=1, children=[
            Step(action="core.set", params={"name": "first_child", "value": True}),
            Step(action="data.append", params={"name": "must_not_run", "value": "late write"}),
        ])]))
    assert executor.variables["first_child"] is True
    assert "must_not_run" not in executor.variables
    assert executor.variables["loop_index"] == 19
    assert executor._deadlines == []


def test_nested_while_honors_shorter_outer_deadline_and_cleans_all_scopes(runner, monkeypatch):
    executor, _ = runner
    executor.variables.update(status="Bekliyor", loop_index=28)
    clock = {"now": 0}
    monkeypatch.setattr("rpa_orkestrai.engine.time.monotonic", lambda: clock["now"])
    perform = executor.perform

    def advance_clock(action, params):
        if action == "core.set":
            clock["now"] = 2
        return perform(action, params)

    monkeypatch.setattr(executor, "perform", advance_clock)
    with pytest.raises(WorkflowError, match="süre sınırı"):
        executor.execute(Workflow(steps=[while_step(max_seconds=1, children=[
            while_step(max_seconds=30, children=[
                Step(action="core.set", params={"name": "first_child", "value": True}),
                Step(action="data.append", params={"name": "must_not_run", "value": True}),
            ]),
        ])]))
    assert executor.variables["first_child"] is True
    assert "must_not_run" not in executor.variables
    assert executor.variables["loop_index"] == 28
    assert executor._deadlines == []


def test_cancel_during_child_prevents_following_child_and_restores_index(runner):
    executor, worksheet = runner
    executor.variables.update(status="Bekliyor", loop_index=52)

    def cancel_during_read(address):
        executor.cancel.set()
        return Mock(value="Bekliyor")

    worksheet.acell.side_effect = cancel_during_read
    with pytest.raises(Cancelled):
        executor.execute(Workflow(steps=[while_step(children=[
            read_cell(output="status"),
            Step(action="core.set", params={"name": "must_not_run", "value": True}),
        ])]))
    assert "must_not_run" not in executor.variables
    assert executor.variables["loop_index"] == 52
    assert executor._deadlines == []


def test_while_inside_for_each_restores_each_outer_index(runner):
    executor, _ = runner
    executor.variables.update(loop_index=77, row="original")
    executor.execute(Workflow(steps=[Step(
        action="control.for_each", params={"items": ["first", "second"], "item_name": "row"}, children=[
            Step(action="core.set", params={"name": "running", "value": True}),
            while_step(left="${running}", operator="truthy", right="${unused_missing}", children=[
                Step(action="data.append", params={"name": "inner_indices", "value": "${loop_index}"}),
                Step(action="core.set", params={"name": "running", "value": False}),
            ]),
            Step(action="data.append", params={"name": "outer_indices", "value": "${loop_index}"}),
        ],
    )]))
    assert executor.variables["inner_indices"] == [0, 0]
    assert executor.variables["outer_indices"] == [0, 1]
    assert executor.variables["loop_index"] == 77
    assert executor.variables["row"] == "original"


def test_while_unknown_external_status_skips_the_loop_in_preview(runner):
    executor, worksheet = runner
    executor.run.dry_run = True
    executor.execute(Workflow(steps=[read_cell(output="status"), while_step(children=[
        Step(action="desktop.window_key", params={"window": "${unresolved_erp}", "key": "enter"}),
    ])]))
    assert worksheet.mock_calls == []
    assert executor._windows.mock_calls == []
    assert executor.variables["status"] is UNKNOWN


def test_while_stops_preview_when_child_makes_next_condition_unknown(runner):
    executor, worksheet = runner
    executor.run.dry_run = True
    executor.variables.update(status="Bekliyor", loop_index=7)
    executor.execute(Workflow(steps=[while_step(children=[read_cell(output="status")])]))
    assert worksheet.mock_calls == []
    assert executor.variables["status"] is UNKNOWN
    assert executor.variables["loop_index"] == 7


@pytest.mark.parametrize("params", [
    {"max_iterations": 0}, {"max_iterations": 1001}, {"max_iterations": True},
    {"max_iterations": 1.5}, {"max_seconds": 0}, {"max_seconds": 3601},
    {"max_seconds": True}, {"max_seconds": float("inf")}, {"max_seconds": float("nan")},
])
def test_while_limits_validate_before_any_children(runner, params):
    executor, _ = runner
    executor.variables["status"] = "Bekliyor"
    with pytest.raises(WorkflowError):
        executor.execute(Workflow(steps=[while_step(**params, children=[
            Step(action="core.set", params={"name": "must_not_run", "value": True}),
        ])]))
    assert "must_not_run" not in executor.variables


def test_pending_example_requires_real_target_and_only_fills_one_record():
    path = Path(__file__).resolve().parents[1] / "examples" / "sheets-pending-formids.json"
    workflow = Workflow.model_validate(json.loads(path.read_text(encoding="utf-8")))
    validate_workflow(workflow, ready=False)
    assert workflow.steps[1].params["max_rows"] == 1
    condition = workflow.steps[2].children[0]
    assert condition.params["operator"] == "empty_or_eq"
    assert [step.action for step in condition.children] == ["desktop.window_fill"]
    with pytest.raises(WorkflowError, match="Pencere içi X gereklidir"):
        validate_workflow(workflow)
