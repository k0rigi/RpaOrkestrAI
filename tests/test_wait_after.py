"""Sonraki adıma geçmeden bekle: every step can pause before the flow moves on."""

import threading
import time

import pytest

from rpa_orkestrai.catalog import BY_TYPE, CATALOG, NO_WAIT_AFTER
from rpa_orkestrai.config import Settings
from rpa_orkestrai.engine import Executor, WorkflowError, validate_workflow
from rpa_orkestrai.errors import Cancelled
from rpa_orkestrai.models import Run, Step, Workflow
from rpa_orkestrai.storage import Store


def run_flow(tmp_path, steps, *, dry_run=False, cancel=None):
    settings = Settings(tmp_path, dotenv=False)
    store = Store(tmp_path)
    workflow = Workflow(name="Bekleme", steps=steps)
    validate_workflow(workflow)
    run = Run(workflow_id=workflow.id, workflow_name=workflow.name, department=workflow.department, dry_run=dry_run)
    executor = Executor(settings, store, run, cancel or threading.Event(), lambda: store.save_run(run))
    started = time.monotonic()
    executor.execute(workflow)
    return executor, run, time.monotonic() - started


def note(step_id, **params):
    return Step(id=step_id, action="data.append", params={"name": "seen", "value": step_id, **params})


def test_every_step_that_hands_over_to_a_next_step_can_wait():
    for entry in CATALOG:
        names = [field["name"] for field in entry["fields"]]
        if entry["type"] in NO_WAIT_AFTER:
            assert "wait_after" not in names, entry["type"]
        else:
            # The last field, default 0: an existing flow keeps running without pauses.
            assert names[-1] == "wait_after", entry["type"]
            assert entry["fields"][-1]["default"] == 0 and entry["fields"][-1].get("help")


def test_the_flow_waits_after_the_step_and_says_so(tmp_path):
    executor, run, elapsed = run_flow(tmp_path, [note("a", wait_after=0.3), note("b")])
    assert executor.variables["seen"] == ["a", "b"]
    assert elapsed >= 0.3
    messages = [event.message for event in run.events]
    assert "Sonraki adıma geçmeden 0,3 saniye bekleniyor." in messages
    # The pause comes after the step is done and before the next one starts.
    assert messages.index("Tamamlandı: Listeye ekle") < messages.index("Sonraki adıma geçmeden 0,3 saniye bekleniyor.")


def test_a_block_waits_once_after_all_its_turns(tmp_path):
    loop = Step(id="rows", action="control.repeat", params={"count": 3, "wait_after": 0.2},
                children=[note("inside")])
    executor, run, elapsed = run_flow(tmp_path, [loop, note("after")])
    assert executor.variables["seen"] == ["inside"] * 3 + ["after"]
    assert sum("bekleniyor" in event.message for event in run.events) == 1
    assert 0.2 <= elapsed < 2


def test_a_preview_does_not_wait(tmp_path):
    _, run, elapsed = run_flow(tmp_path, [note("a", wait_after=30)], dry_run=True)
    assert elapsed < 5 and not any("bekleniyor" in event.message for event in run.events)


def test_stopping_the_run_ends_the_pause(tmp_path):
    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()
    started = time.monotonic()
    with pytest.raises(Cancelled):
        run_flow(tmp_path, [note("a", wait_after=60), note("b")], cancel=cancel)
    assert time.monotonic() - started < 5


def test_the_pause_is_checked_before_the_run(tmp_path):
    for value in (-1, 3601):
        with pytest.raises(WorkflowError, match="Sonraki adıma geçmeden bekle"):
            validate_workflow(Workflow(steps=[note("a", wait_after=value)]))
    # Steps that end a path have no next step to wait for.
    with pytest.raises(WorkflowError, match="bilinmeyen parametre"):
        validate_workflow(Workflow(steps=[Step(action="control.stop", params={"wait_after": 1})]))
    assert BY_TYPE["core.wait"]["fields"][-1]["name"] == "seconds"
