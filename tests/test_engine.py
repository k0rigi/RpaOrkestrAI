import csv
import threading
import time

import pytest

from rpa_orkestrai.config import Settings, modifier_key
from rpa_orkestrai.demo import demo_workflow
from rpa_orkestrai.engine import Executor, RunManager, WorkflowError, compare, resolve, validate_workflow
from rpa_orkestrai.locking import WorkspaceLock
from rpa_orkestrai.models import Run, Step, Workflow
from rpa_orkestrai.storage import Store


def setup_run(tmp_path, *, dry_run=False):
    settings = Settings(tmp_path, dotenv=False)
    store = Store(tmp_path)
    workflow = demo_workflow()
    run = Run(workflow_id=workflow.id, workflow_name=workflow.name, department=workflow.department,
              dry_run=dry_run)
    executor = Executor(settings, store, run, threading.Event(), lambda: store.save_run(run))
    return workflow, executor, run


def wait_done(manager, store, run_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        run = store.run(run_id)
        if run.status not in {"queued", "running"}:
            return run
        time.sleep(0.01)
    manager.close()
    pytest.fail("Run failed to finish within 5 seconds")


def test_demo_filters_rows_and_creates_department_report(tmp_path):
    workflow, executor, run = setup_run(tmp_path)
    executor.execute(workflow)
    assert len(run.artifacts) == 1
    artifact = run.artifacts[0]
    assert artifact.department == "Finans"
    assert artifact.rows == 3
    path = tmp_path / "artifacts" / run.id / f"{artifact.id}.csv"
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [r["order_id"] for r in rows] == ["SIP-1001", "SIP-1003", "SIP-1004"]
    assert "item" not in executor.variables


def test_template_resolution_preserves_types_and_never_evaluates_code():
    variables = {"items": [{"amount": 1200}], "name": "Ada"}
    assert resolve("${items.0.amount}", variables) == 1200
    assert resolve("Merhaba ${name}", variables) == "Merhaba Ada"
    assert resolve("${__import__('os').system('whoami')}", variables).startswith("${")
    with pytest.raises(WorkflowError, match="bulunamadı"):
        resolve("${missing}", variables)


def test_dry_run_skips_connections_and_does_not_fabricate_outputs(tmp_path, monkeypatch):
    _, executor, run = setup_run(tmp_path, dry_run=True)
    workflow = Workflow(steps=[
        Step(action="database.read", params={"output": "orders"}),
        Step(action="control.for_each", params={"items": "${orders}"}, children=[
            Step(action="data.append", params={"name": "results", "value": "${item}"}),
        ]),
        Step(action="data.export_csv", params={"rows": "${results}", "filename": "preview.csv"}),
    ])
    monkeypatch.setattr(executor, "perform", lambda *args: pytest.fail("External/dependent action executed"))
    executor.execute(workflow)
    assert run.artifacts == []
    assert len([event for event in run.events if event.level == "warning"]) == 3


def test_nested_loop_restores_parent_item_and_index(tmp_path):
    _, executor, _ = setup_run(tmp_path)
    executor.variables["results"] = []
    workflow = Workflow(steps=[Step(action="control.for_each", params={"items": ["outer"]}, children=[
        Step(action="control.for_each", params={"items": ["inner"]}, children=[
            Step(action="data.append", params={"name": "results", "value": "${item}"}),
        ]),
        Step(action="data.append", params={"name": "results", "value": "${item}"}),
    ])])
    executor.execute(workflow)
    assert executor.variables["results"] == ["inner", "outer"]
    assert "loop_index" not in executor.variables
    with pytest.raises(WorkflowError, match="ayrılmıştır"):
        validate_workflow(Workflow(steps=[Step(action="control.for_each", params={"item_name": "loop_index"})]))


def test_iteration_snapshots_source_and_has_bounds(tmp_path):
    _, executor, _ = setup_run(tmp_path)
    executor.variables["rows"] = [1, 2]
    executor.execute(Workflow(steps=[Step(action="control.for_each", params={"items": "${rows}"}, children=[
        Step(action="data.append", params={"name": "rows", "value": 3}),
    ])]))
    assert executor.variables["rows"] == [1, 2, 3, 3]
    with pytest.raises(WorkflowError, match="100.000"):
        executor.execute(Workflow(steps=[Step(action="control.for_each", params={"items": [1] * 100_001})]))


def test_single_run_lock_and_cancel_wait(tmp_path):
    settings = Settings(tmp_path, dotenv=False)
    store = Store(tmp_path)
    manager = RunManager(settings, store)
    try:
        workflow = Workflow(steps=[Step(action="core.wait", params={"seconds": 30})])
        run = manager.start(workflow)
        with pytest.raises(RuntimeError, match="çalışıyor"):
            manager.start(workflow)
        manager.cancel(run.id)
        assert wait_done(manager, store, run.id).status == "cancelled"
    finally:
        manager.close()


def test_report_blocks_path_traversal_and_escapes_formulas(tmp_path):
    _, executor, run = setup_run(tmp_path)
    with pytest.raises(WorkflowError):
        executor.export_csv([], "../../secret.csv")
    executor.export_csv([{"name": "=HYPERLINK(1)", "amount": -20}], "safe.csv")
    path = tmp_path / "artifacts" / run.id / f"{run.artifacts[0].id}.csv"
    text = path.read_text(encoding="utf-8-sig")
    assert "'=HYPERLINK(1)" in text
    assert ",-20" in text


def test_template_path_cannot_escape_allowed_directory(tmp_path):
    _, executor, _ = setup_run(tmp_path)
    root = tmp_path / "templates"
    root.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("secret")
    executor.config["template_dir"] = str(root)
    with pytest.raises(WorkflowError):
        executor.template_path("../secret.txt")


def test_recovery_and_platform_settings(tmp_path):
    _, executor, run = setup_run(tmp_path)
    run.status = "running"
    executor.store.save_run(run)
    executor.store.recover_runs()
    assert executor.store.run(run.id).status == "failed"
    assert modifier_key("Darwin") == "command"
    assert modifier_key("Windows") == "ctrl"
    assert compare("HATA: Başarısız", "contains", "hata")


def test_workspace_lock_is_exclusive_and_released(tmp_path):
    with WorkspaceLock(tmp_path):
        with pytest.raises(RuntimeError, match="başka"):
            with WorkspaceLock(tmp_path):
                pass
    with WorkspaceLock(tmp_path):
        pass
