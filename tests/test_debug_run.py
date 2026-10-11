"""Buraya kadar çalıştır: wait before a step, then step, continue or finish from the Studio."""
import time

import pytest

from rpa_orkestrai.config import Settings
from rpa_orkestrai.engine import RunManager, WorkflowError
from rpa_orkestrai.models import Run, Step, Workflow
from rpa_orkestrai.storage import Store


def setter(name, value, title=""):
    return Step(action="core.set", title=title, params={"name": name, "value": value})


@pytest.fixture
def runtime(tmp_path):
    settings, store = Settings(tmp_path, dotenv=False), Store(tmp_path)
    calls = []
    settings.prepare_run = lambda cancel: calls.append("minimize")
    settings.bring_to_front = lambda: calls.append("front")
    manager = RunManager(settings, store)
    yield manager, store, calls
    manager.close()


def wait_for(store, run_id, check):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        run = store.run(run_id)
        if check(run):
            return run
        time.sleep(0.01)
    pytest.fail(f"Run did not reach the expected state: {store.run(run_id)}")


def paused(store, run_id, step_id):
    return wait_for(store, run_id, lambda run: (run.paused or {}).get("step_id") == step_id)


def done(store, run_id):
    return wait_for(store, run_id, lambda run: run.status not in {"queued", "running"})


def test_runs_to_the_step_then_steps_one_at_a_time(runtime):
    manager, store, calls = runtime
    first, second, third = setter("a", 1), setter("b", 2, "İkinci"), setter("c", 3)
    run = manager.start(Workflow(steps=[first, second, third]), pause_at=second.id)
    state = paused(store, run.id, second.id)
    # Earlier steps ran; the paused step did not. Its values are shown, the Studio comes forward.
    assert state.paused == {"step_id": second.id, "title": "İkinci"}
    assert state.variables["a"] == 1 and "b" not in state.variables
    assert state.step_stats[first.id]["ok"] == 1 and state.step_stats[second.id]["runs"] == 0
    assert calls == ["minimize", "front"]
    manager.debug(run.id, "step")
    state = paused(store, run.id, third.id)
    assert state.variables["b"] == 2 and "c" not in state.variables
    assert calls == ["minimize", "front", "minimize", "front"]  # the screen is freed before each step
    manager.debug(run.id, "step")
    final = done(store, run.id)
    assert final.status == "succeeded" and final.paused is None and final.variables is None
    assert final.step_stats[third.id]["ok"] == 1
    # Older versions reject unknown fields: a finished run file does not carry the pause field.
    assert "paused" not in (store.root / "runs" / f"{run.id}.json").read_text(encoding="utf-8")


def test_continue_waits_again_at_the_same_step_in_the_next_loop_turn(runtime):
    manager, store, _ = runtime
    inner = setter("seen", "${loop_index}")
    loop = Step(action="control.repeat", params={"count": 3}, children=[inner])
    run = manager.start(Workflow(steps=[loop]), pause_at=inner.id)
    assert "seen" not in paused(store, run.id, inner.id).variables
    manager.debug(run.id, "continue")
    wait_for(store, run.id, lambda r: r.paused and r.variables.get("seen") == 0)
    manager.debug(run.id, "finish")  # no more pauses
    final = done(store, run.id)
    assert final.status == "succeeded" and final.step_stats[inner.id]["ok"] == 3


def test_stop_while_paused_cancels_without_running_the_step(runtime):
    manager, store, _ = runtime
    first, second = setter("a", 1), setter("b", 2)
    run = manager.start(Workflow(steps=[first, second]), pause_at=second.id)
    paused(store, run.id, second.id)
    manager.cancel(run.id)
    final = done(store, run.id)
    assert final.status == "cancelled" and final.paused is None and final.step_stats[second.id]["runs"] == 0


def test_commands_need_a_paused_run_and_a_known_step(runtime):
    manager, store, _ = runtime
    with pytest.raises(WorkflowError, match="bulunamadı"):
        manager.start(Workflow(steps=[setter("a", 1)]), pause_at="missing")
    step = Step(action="core.wait", params={"seconds": 30})
    run = manager.start(Workflow(steps=[step]))
    with pytest.raises(RuntimeError, match="duraklatılmış değil"):
        manager.debug(run.id, "step")
    manager.cancel(run.id)
    done(store, run.id)


def test_api_starts_a_paused_run_and_accepts_commands(tmp_path):
    from fastapi.testclient import TestClient

    from rpa_orkestrai.app import create_app

    settings = Settings(tmp_path, dotenv=False)
    app = create_app(settings)
    with TestClient(app) as client:
        first, second = setter("a", 1), setter("b", 2)
        workflow = client.post("/api/workflows", json={"name": "Hata ayıklama", "steps": [
            first.model_dump(), second.model_dump()]}).json()
        run = client.post(f"/api/workflows/{workflow['id']}/run", json={"pause_at": second.id}).json()

        class Api:
            # Read through the app (its store lock): Windows refuses to open a file being replaced.
            @staticmethod
            def run(run_id):
                return Run.model_validate(client.get(f"/api/runs/{run_id}").json())

        paused(Api, run["id"], second.id)
        assert client.post(f"/api/runs/{run['id']}/debug", json={"action": "jump"}).status_code == 422
        assert client.post(f"/api/runs/{run['id']}/debug", json={"action": "finish"}).status_code == 200
        assert done(Api, run["id"]).status == "succeeded"
        assert client.post(f"/api/runs/{run['id']}/debug", json={"action": "step"}).status_code == 409


def test_paused_values_stay_small_even_for_a_long_list(runtime):
    manager, store, _ = runtime
    rows = [{"kod": f"A{i}", "aciklama": "x" * 40} for i in range(2000)]
    first, second = setter("sheet_rows", rows), setter("b", 2)
    run = manager.start(Workflow(steps=[first, second]), pause_at=second.id)
    state = paused(store, run.id, second.id)
    shown = state.variables["sheet_rows"]
    # The run file is read on every poll while paused: a long value is shortened, not copied whole.
    assert isinstance(shown, str) and shown.endswith(" …") and len(shown) < 2100
    manager.debug(run.id, "finish")
    assert done(store, run.id).status == "succeeded"
