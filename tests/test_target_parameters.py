"""Resolve target modes and click counts without accessing the real desktop."""

import threading
from unittest.mock import Mock, create_autospec

import pytest

from rpa_orkestrai.config import Settings
from rpa_orkestrai.desktop.controller import DesktopController
from rpa_orkestrai.desktop.windows import WindowService
from rpa_orkestrai.engine import Executor, WorkflowError, validate_workflow
from rpa_orkestrai.models import Run, Step, Workflow
from rpa_orkestrai.storage import Store


@pytest.fixture
def runner(tmp_path):
    settings = Settings(tmp_path / "data", dotenv=False)
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    settings.update({"template_dir": str(template_dir)})
    (template_dir / "form-id.png").write_bytes(b"the adapter is mocked; no image is decoded")
    run = Run(workflow_id="targets", workflow_name="Targets", department="Test")
    executor = Executor(settings, Store(settings.data_dir), run, threading.Event(), lambda: None)
    executor._windows = create_autospec(WindowService, instance=True)
    executor._desktop = create_autospec(DesktopController, instance=True)
    executor.variables["erp"] = {"found": True, "window_id": 42}
    return executor


@pytest.mark.parametrize("action", ["desktop.window_click", "desktop.window_fill"])
@pytest.mark.parametrize("mode", ["coordinates", "image"])
def test_dynamic_mode_keeps_active_target_and_never_resolves_inactive_references(runner, action, mode):
    parameters = {"window": "${erp}", "target_mode": "${selected_mode}"}
    if mode == "coordinates":
        parameters.update(x=20, y=30, template="${old_missing_template}", confidence="${old_missing_confidence}",
                          timeout="${old_missing_timeout}", offset_x="${old_missing_offset}")
        expected_target = {"target_mode": "coordinates", "x": 20, "y": 30}
    else:
        parameters.update(x="${old_missing_x}", y="${old_missing_y}", template="form-id.png",
                          confidence=0.95, timeout=4, offset_x=18, offset_y=-2)
        expected_target = {"target_mode": "image", "template": runner.template_path("form-id.png"),
                           "confidence": 0.95, "timeout": 4, "offset_x": 18, "offset_y": -2}
    if action == "desktop.window_fill":
        parameters.update(text="INV-00042", clear=False)
    workflow = Workflow(steps=[
        Step(action="core.set", params={"name": "selected_mode", "value": mode}),
        Step(action=action, params=parameters),
    ])
    validate_workflow(workflow)

    runner.execute(workflow)

    if action == "desktop.window_click":
        runner._windows.click_target.assert_called_once_with(
            runner.variables["erp"], runner._desktop, **expected_target, clicks=1, button="left",
        )
    else:
        runner._windows.fill_target.assert_called_once_with(
            runner.variables["erp"], "INV-00042", runner._desktop, clear=False, **expected_target,
        )


@pytest.mark.parametrize("value", [True, False, 1.0, 2.9, "2.0", " 2", "02", 3, 0, None, [1]])
def test_invalid_resolved_click_count_stops_before_desktop_or_window_adapter(runner, value, monkeypatch):
    desktop = Mock(return_value=runner._desktop)
    windows = Mock(return_value=runner._windows)
    monkeypatch.setattr(runner, "desktop", desktop)
    monkeypatch.setattr(runner, "windows", windows)
    workflow = Workflow(steps=[
        Step(action="core.set", params={"name": "click_count", "value": value}),
        Step(action="desktop.window_click", params={
            "window": "${erp}", "x": 20, "y": 30, "clicks": "${click_count}",
        }),
    ])
    validate_workflow(workflow)

    with pytest.raises(WorkflowError, match="Tıklama sayısı 1 veya 2"):
        runner.execute(workflow)

    desktop.assert_not_called()
    windows.assert_not_called()
    runner._windows.click_target.assert_not_called()
    runner._desktop.click.assert_not_called()


@pytest.mark.parametrize("value,expected", [(1, 1), (2, 2), ("1", 1), ("2", 2)])
def test_supported_resolved_click_count_reaches_adapter_as_exact_integer(runner, value, expected):
    runner.variables["click_count"] = value
    workflow = Workflow(steps=[Step(action="desktop.window_click", params={
        "window": "${erp}", "x": 20, "y": 30, "clicks": "${click_count}",
    })])
    validate_workflow(workflow)

    runner.execute(workflow)

    actual = runner._windows.click_target.call_args.kwargs["clicks"]
    assert type(actual) is int and actual == expected
