"""Sheets rows, ERP targeting, and result cells compose without external access."""

import json
import threading
from pathlib import Path
from unittest.mock import Mock, call

import pytest

from rpa_orkestrai.config import Settings
from rpa_orkestrai.engine import Cancelled, Executor, RunManager, WorkflowError, validate_workflow
from rpa_orkestrai.integrations.sheets import SheetsService
from rpa_orkestrai.models import Run, Step, Workflow
from rpa_orkestrai.storage import Store


@pytest.fixture
def row_runner(tmp_path):
    templates = tmp_path / "templates"
    templates.mkdir()
    # Image matching is mocked; only template-path validation uses this file.
    (templates / "result-ready.png").write_bytes(b"image-placeholder")
    settings = Settings(tmp_path, dotenv=False)
    settings.update({"google_credentials_path": "credentials/test.json", "template_dir": str(templates)})
    run = Run(workflow_id="test", workflow_name="Rows", department="Test")
    runner = Executor(settings, Store(tmp_path), run, threading.Event(), lambda: None)
    runner._desktop = Mock()
    runner._windows = Mock()
    runner._windows.find.return_value = {"found": True, "title": "ERP FormID"}
    sheets = SheetsService("unused.json", "sheet-id", "Sayfa1")
    worksheet = Mock()
    worksheet.get.return_value = [["000142"], [], [0]]
    sheets._worksheet = worksheet
    runner._sheets[("sheet-id", "Sayfa1")] = sheets
    return runner, worksheet


def row_workflow():
    return Workflow(steps=[
        Step(action="desktop.find_window", params={"title": "ERP FormID"}),
        Step(action="sheets.read_column", params={
            "spreadsheet_id": "https://docs.google.com/spreadsheets/d/sheet-id/edit#gid=0",
            "worksheet": "Sayfa1", "start_cell": "B2", "max_rows": 3, "empty_policy": "skip",
        }),
        Step(action="control.for_each", params={"items": "${sheet_rows}", "item_name": "row"}, children=[
            Step(action="desktop.window_fill", params={"x": 125, "y": 70}),
            Step(action="desktop.window_key", params={"key": "enter"}),
            Step(action="desktop.window_wait_image", params={"template": "result-ready.png"}),
            Step(action="sheets.write_cell", params={"spreadsheet_id": "sheet-id"}),
        ]),
    ])


def test_column_snapshot_fills_formids_in_order_and_marks_original_rows_after_success(row_runner):
    runner, worksheet = row_runner
    events = []

    def fill(window, text, desktop, **kwargs):
        assert kwargs == {"clear": True, "target_mode": "coordinates", "x": 125, "y": 70}
        events.append(("fill", text))
        # A changed worksheet during processing must not replace the snapshot.
        worksheet.get.return_value = [["CHANGED"]]

    runner._windows.fill_target.side_effect = fill
    runner._windows.press_key.side_effect = lambda *args: events.append(("key", args[1]))
    runner._windows.wait_image.side_effect = lambda *args, **kwargs: events.append(("ready",))
    worksheet.update.side_effect = lambda **kwargs: events.append(("write", kwargs["range_name"]))
    workflow = row_workflow()
    validate_workflow(workflow)
    runner.execute(workflow)

    assert events == [
        ("fill", "000142"), ("key", "enter"), ("ready",), ("write", "C2"),
        ("fill", "0"), ("key", "enter"), ("ready",), ("write", "C4"),
    ]
    worksheet.get.assert_called_once_with("B2:B4", value_render_option="FORMATTED_VALUE")
    assert worksheet.update.call_args_list == [
        call(values=[["Tamamlandı"]], range_name="C2", raw=True),
        call(values=[["Tamamlandı"]], range_name="C4", raw=True),
    ]
    assert runner.variables["sheet_rows"] == [
        {"row_number": 2, "cell": "B2", "value": "000142"},
        {"row_number": 4, "cell": "B4", "value": "0"},
    ]
    assert "row" not in runner.variables
    assert "loop_index" not in runner.variables


def test_failed_erp_confirmation_prevents_success_write_and_next_row(row_runner):
    runner, worksheet = row_runner
    runner._windows.wait_image.side_effect = TimeoutError("result did not appear")
    with pytest.raises(TimeoutError, match="result did not appear"):
        runner.execute(row_workflow())
    runner._windows.fill_target.assert_called_once()
    assert runner._windows.fill_target.call_args.args[1] == "000142"
    worksheet.update.assert_not_called()
    assert "row" not in runner.variables


def test_empty_column_stops_before_any_erp_input(row_runner):
    runner, worksheet = row_runner
    worksheet.get.return_value = [[], [" "], [None]]
    with pytest.raises(WorkflowError, match="boş|bulunamadı"):
        runner.execute(row_workflow())
    runner._windows.fill_target.assert_not_called()
    runner._windows.press_key.assert_not_called()
    runner._windows.wait_image.assert_not_called()
    worksheet.update.assert_not_called()


def test_dry_run_does_not_query_sheets_or_control_the_desktop(row_runner):
    runner, worksheet = row_runner
    runner.run.dry_run = True
    workflow = row_workflow()
    validate_workflow(workflow)
    runner.execute(workflow)
    assert runner._windows.mock_calls == []
    assert runner._desktop.mock_calls == []
    assert worksheet.mock_calls == []


def test_cancel_after_first_completed_row_prevents_second_row_and_restores_scope(row_runner):
    runner, worksheet = row_runner
    runner.variables.update(row="outer row", loop_index=91)
    worksheet.update.side_effect = lambda **kwargs: runner.cancel.set()
    with pytest.raises(Cancelled):
        runner.execute(row_workflow())
    runner._windows.fill_target.assert_called_once()
    worksheet.update.assert_called_once_with(values=[["Tamamlandı"]], range_name="C2", raw=True)
    assert runner.variables["row"] == "outer row"
    assert runner.variables["loop_index"] == 91


@pytest.mark.parametrize("dry_run", [False, True])
def test_example_requires_target_configuration_before_a_run_can_start(tmp_path, dry_run):
    path = Path(__file__).resolve().parents[1] / "examples" / "sheets-formid-loop.json"
    workflow = Workflow.model_validate(json.loads(path.read_text(encoding="utf-8")))
    validate_workflow(workflow, ready=False)
    manager = RunManager(Settings(tmp_path, dotenv=False), Store(tmp_path))
    try:
        with pytest.raises(WorkflowError, match="Pencere içi X gereklidir"):
            manager.start(workflow, dry_run=dry_run)
        assert manager._active is None
    finally:
        manager.close()


def test_image_target_does_not_require_inactive_coordinate_fields(row_runner):
    runner, _worksheet = row_runner
    workflow = row_workflow()
    fill_step = workflow.steps[-1].children[0]
    fill_step.params = {"target_mode": "image", "template": "result-ready.png", "offset_x": 120}
    validate_workflow(workflow)
    runner.execute(workflow)
    kwargs = runner._windows.fill_target.call_args.kwargs
    assert kwargs["target_mode"] == "image"
    assert kwargs["offset_x"] == 120
    assert kwargs["template"].name == "result-ready.png"
    assert "x" not in kwargs and "y" not in kwargs
