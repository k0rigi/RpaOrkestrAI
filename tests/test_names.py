"""Names a step gives to its result: ${ad} typed in a name field means ad, and mistakes are explained."""

import time

import pytest
from fastapi.testclient import TestClient

from rpa_orkestrai.app import create_app
from rpa_orkestrai.catalog import ACTION_DEFINITIONS, BY_TYPE, CATALOG
from rpa_orkestrai.config import Settings
from rpa_orkestrai.engine import WorkflowError, step_test_plan, validate_workflow
from rpa_orkestrai.models import Step, Workflow


def test_a_name_typed_the_way_it_is_used_means_the_name():
    assert Step(action="desktop.find_window", params={"title": "x", "output": " ${ erp_window } "}).params[
        "output"] == "erp_window"
    loop = Step(action="control.for_each", params={"items": "${rows}", "item_name": "${row}"}, children=[
        Step(action="control.try", params={"error_name": "${hata}"}),
        Step(action="core.set", params={"name": "${sayac}", "value": "${row}"}),
        Step(action="data.append", params={"name": " sonuclar ", "value": "${row}"}),
    ])
    assert loop.params == {"items": "${rows}", "item_name": "row"}  # the list itself stays a reference
    assert loop.children[0].params == {"error_name": "hata"}
    assert loop.children[1].params == {"name": "sayac", "value": "${row}"}
    assert loop.children[2].params["name"] == "sonuclar"
    # Only whole, simple names are unwrapped; anything else is left for the validation message.
    assert Step(action="core.set", params={"name": "${a.b}", "value": 1}).params["name"] == "${a.b}"
    assert Step(action="core.log", params={"message": "${x}"}).params == {"message": "${x}"}


def test_a_bad_name_is_reported_with_its_step_and_field():
    window = Step(action="desktop.find_window", title="CaniasBsgt31", params={"title": "x", "output": "erp penceresi"})
    with pytest.raises(WorkflowError) as error:
        validate_workflow(Workflow(steps=[window]))
    message = str(error.value)
    assert message.startswith("CaniasBsgt31: “Pencereye verilecek ad”") and "erp penceresi" in message
    assert "erp_window" in message  # an example of a valid name
    guard = Step(action="control.try", title="Dene", params={"error_name": "hata mesajı"})
    with pytest.raises(WorkflowError, match="Dene: “Hata mesajı değişkeni”"):
        validate_workflow(Workflow(steps=[guard]))


def test_a_wrapped_name_no_longer_breaks_the_run_or_the_step_test(tmp_path):
    """The flow a user built: ${erp_window} typed as the window's name, then used by later steps."""
    with TestClient(create_app(Settings(tmp_path, dotenv=False))) as client:
        created = client.post("/api/workflows", json={"name": "deneme1", "steps": [
            {"id": "window", "action": "desktop.find_window", "title": "CaniasBsgt31", "params": {
                "application": "", "title": "CANIAS", "match": "contains", "output": "${erp_window}"}},
            {"id": "counter", "action": "core.set", "params": {"name": "${sayac}", "value": 41}},
            {"id": "sum", "action": "data.calculate", "params": {"expression": "${sayac} + 1", "output": "${toplam}"}},
            {"id": "click", "action": "desktop.window_click", "title": "Tıkla", "params": {
                "window": "${erp_window}", "target_mode": "coordinates", "x": 5, "y": 5}},
        ]})
        assert created.status_code == 201, created.text
        workflow = created.json()
        assert [step["params"].get("output", step["params"].get("name")) for step in workflow["steps"][:3]] == [
            "erp_window", "sayac", "toplam"]
        plan = client.get(f"/api/workflows/{workflow['id']}/steps/click/test-plan").json()
        assert plan["manual"] == [] and [entry["variable"] for entry in plan["prepare"]] == ["erp_window"]
        assert client.get(f"/api/workflows/{workflow['id']}/steps/window/test-plan").json()["manual"] == []
        test = client.post(f"/api/workflows/{workflow['id']}/steps/sum/test", json={"variables": {}})
        assert test.status_code == 202, test.text
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            run = client.get(f"/api/runs/{test.json()['id']}").json()
            if run["status"] not in {"queued", "running"}:
                break
            time.sleep(0.02)
        assert run["status"] == "succeeded" and run["variables"]["toplam"] == 42
        # A preview run passes validation: no "Değişken adı…" error for the whole flow.
        assert client.post(f"/api/workflows/{workflow['id']}/run", json={"dry_run": True}).status_code == 202


def test_the_plan_says_why_a_value_cannot_be_prepared():
    click = Step(action="desktop.window_click", title="Tıkla", params={
        "window": "${erp_windov}", "target_mode": "coordinates", "x": 1, "y": 1})
    ask = Step(action="ui.input", title="Tarihi sor", params={"prompt": "?", "output": "tarih"})
    note = Step(action="core.log", title="Yaz", params={"message": "${tarih} ${hic_yok}"})
    flow = Workflow(steps=[
        Step(action="desktop.find_window", title="Canias", params={"title": "x", "output": "erp_window"}), ask, click, note])
    assert step_test_plan(flow, click.id)["manual_details"] == [
        {"variable": "erp_windov", "reason": "missing", "suggestion": "erp_window"}]
    assert step_test_plan(flow, note.id)["manual_details"] == [
        {"variable": "tarih", "reason": "acting", "title": "Tarihi sor"},
        {"variable": "hic_yok", "reason": "missing", "suggestion": None}]
    # After "Başka akışı çalıştır" an unknown name may come from the called flow.
    call = Step(action="control.run_workflow", title="Giriş yap", params={"workflow": "0" * 32})
    later = Step(action="core.log", params={"message": "${oturum}"})
    assert step_test_plan(Workflow(steps=[call, later]), later.id)["manual_details"] == [
        {"variable": "oturum", "reason": "acting", "title": "Giriş yap"}]


def test_name_fields_and_window_fields_are_marked_and_labelled_apart():
    for entry in ACTION_DEFINITIONS + CATALOG:
        for field in entry["fields"]:
            name_field = field["name"] in {"output", "item_name", "error_name"} or (
                field["name"] == "name" and entry["type"] in {"core.set", "data.append"})
            assert bool(field.get("variable")) == name_field, (entry["type"], field["name"])
            assert (field.get("reference") == "window") == (field["name"] == "window"), (entry["type"], field["name"])
    # The window's name and the window a step uses must not share a label again.
    naming = next(f for f in BY_TYPE["desktop.find_window"]["fields"] if f["name"] == "output")
    using = next(f for f in BY_TYPE["desktop.window_click"]["fields"] if f["name"] == "window")
    assert naming["label"] != using["label"] and "${" not in naming["help"].split(".")[0]
