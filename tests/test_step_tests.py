"""A single-step test prepares what it needs by itself; every step explains how it is used."""

import time

import pytest

from rpa_orkestrai.catalog import CATALOG, LOCATABLE
from rpa_orkestrai.config import Settings
from rpa_orkestrai.engine import Executor, RunManager, WorkflowError, step_test_plan
from rpa_orkestrai.guide import QUICK_GUIDE
from rpa_orkestrai.models import Step, Workflow
from rpa_orkestrai.storage import Store

plan_for = step_test_plan


def step(action, children=(), otherwise=(), title="", **params):
    return Step(action=action, title=title, params=params, children=list(children), otherwise=list(otherwise))


def finished(store, run_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        run = store.run(run_id)
        if run.status not in {"queued", "running"}:
            return run
        time.sleep(0.02)
    pytest.fail("run did not finish")


def test_every_step_has_a_guide_and_every_field_is_explained():
    for entry in CATALOG:
        guide = entry.get("guide")
        assert guide and guide["how"] and all(isinstance(line, str) and line for line in guide["how"]), entry["type"]
        for field in entry["fields"]:
            assert field.get("help"), f'{entry["type"]}.{field["name"]}'
    assert len(QUICK_GUIDE) >= 4 and all(len(item) == 2 for item in QUICK_GUIDE)


def build(tmp_path):
    fill = step("desktop.window_fill", title="Form ID yaz", window="${erp}", target_mode="coordinates", x=10, y=20,
                text="${row.form_id}", clear=True)
    skip = step("control.if", [step("control.continue")], title="Atla", left="${row.durum}", operator="ne",
                right="BEKLIYOR")
    report = step("core.log", title="Rapor", message="${durum} ${cevap} ${loop_index}")
    workflow = Workflow(steps=[
        step("core.set", title="Tablo", name="tablo", value="adres"),
        Step(action="desktop.find_window", title="Pencere", params={"application": "", "title": "ERP",
                                                                      "output": "erp"}),
        step("core.set", title="Satırlar", name="satirlar", value=[{"form_id": "A-1", "durum": "TAMAM"},
                                                                 {"form_id": "A-2", "durum": "BEKLIYOR"}]),
        step("ui.input", title="Sor", prompt="?", output="cevap"),
        step("control.for_each", [skip, fill, step("core.set", name="durum", value="işlendi"), report],
             title="Her satır", items="${satirlar}", item_name="row"),
    ])
    return workflow, {"fill": fill, "skip": skip, "report": report}


def test_plan_prepares_from_earlier_read_only_steps_and_asks_only_for_the_rest(tmp_path):
    workflow, steps = build(tmp_path)
    plan = plan_for(workflow, steps["fill"].id)
    assert [(entry["variable"], entry["kind"]) for entry in plan["prepare"]] == [
        ("erp", "step"), ("satirlar", "step"), ("row", "item")]
    assert plan["manual"] == [] and plan["in_loop"] and plan["locatable"] and plan["external"]
    # A value the user typed is not prepared again, and what an acting step produces is asked for.
    assert [e["variable"] for e in plan_for(workflow, steps["fill"].id, {"row"})["prepare"]] == ["erp"]
    report = plan_for(workflow, steps["report"].id)
    assert report["manual"] == ["cevap"] and not report["locatable"] and not report["external"]
    assert [(e["variable"], e["kind"]) for e in report["prepare"]] == [("durum", "step"), ("loop_index", "index")]
    with pytest.raises(KeyError):
        plan_for(workflow, "missing")


def test_step_test_runs_without_typed_values_and_handles_loop_steps(tmp_path):
    settings, store = Settings(tmp_path, dotenv=False), Store(tmp_path)
    workflow, steps = build(tmp_path)
    workflow = store.save_workflow(workflow)
    manager = RunManager(settings, store)
    try:
        # "Sonraki tura geç" inside a tested loop step is an expected result, not an error.
        run = finished(store, manager.start_step(workflow, steps["skip"].id, {}).id)
        assert run.status == "succeeded" and run.variables["row"] == {"form_id": "A-1", "durum": "TAMAM"}
        assert any("sonraki satıra geçilir" in event.message for event in run.events)
        # The second row is used when the user supplies it; preparation then skips the list.
        run = finished(store, manager.start_step(workflow, steps["skip"].id,
                                                 {"row": {"durum": "BEKLIYOR"}}).id)
        assert run.status == "succeeded" and "satirlar" not in run.variables
        run = finished(store, manager.start_step(workflow, steps["report"].id, {"cevap": "evet"}).id)
        assert run.status == "succeeded" and any("işlendi evet 0" in event.message for event in run.events)
        with pytest.raises(WorkflowError, match="Yeri göster"):
            manager.start_step(workflow, steps["report"].id, {"cevap": "x"}, locate=True)
    finally:
        manager.close()


def test_an_empty_list_or_a_failing_preparation_is_explained(tmp_path):
    settings, store = Settings(tmp_path, dotenv=False), Store(tmp_path)
    inner = step("core.log", message="${row}")
    broken = step("core.log", message="${sonuc}")
    workflow = store.save_workflow(Workflow(steps=[
        step("core.set", name="liste", value=[]),
        step("control.for_each", [inner], title="Boş döngü", items="${liste}", item_name="row"),
        step("data.calculate", title="Böl", expression="1 / 0", output="sonuc"),
        broken,
    ]))
    manager = RunManager(settings, store)
    try:
        run = finished(store, manager.start_step(workflow, inner.id, {}).id)
        assert run.status == "failed" and "Boş döngü" in run.error and "hiç öğe yok" in run.error
        run = finished(store, manager.start_step(workflow, broken.id, {}).id)
        assert run.status == "failed" and run.error.startswith("Test hazırlığı tamamlanamadı (Böl)")
    finally:
        manager.close()


class Pointer:
    def __init__(self):
        self.calls = []

    def move(self, x, y, duration=0):
        self.calls.append(("move", x, y))

    def click(self, *args, **kwargs):
        self.calls.append(("click", *args))

    def write(self, *args, **kwargs):
        self.calls.append(("write", *args))

    def hotkey(self, *args):
        self.calls.append(("hotkey", *args))

    def press(self, *args):
        self.calls.append(("press", *args))


class Windows:
    def __init__(self):
        self.located = []

    def find(self, application, title, match, timeout, on_missing):
        return {"found": True, "title": title, "platform": "Test"}

    def locate_target(self, target, desktop, **targeting):
        self.located.append((target["title"], targeting["x"], targeting["y"]))
        return 110, 220

    def fill_target(self, *args, **kwargs):
        raise AssertionError("locating must not type")

    def click_target(self, *args, **kwargs):
        raise AssertionError("locating must not click")


def test_show_target_moves_the_pointer_without_clicking_or_typing(tmp_path, monkeypatch):
    settings, store = Settings(tmp_path, dotenv=False), Store(tmp_path)
    workflow, steps = build(tmp_path)
    workflow = store.save_workflow(workflow)
    pointer, windows = Pointer(), Windows()
    monkeypatch.setattr(Executor, "desktop", lambda self: pointer)
    monkeypatch.setattr(Executor, "windows", lambda self: windows)
    manager = RunManager(settings, store)
    try:
        run = finished(store, manager.start_step(workflow, steps["fill"].id, {}, locate=True).id)
        assert run.status == "succeeded", run.error
        assert windows.located == [("ERP", 10, 20)] and pointer.calls == [("move", 110, 220)]
        assert any("Tıklama veya yazma yapılmadı" in event.message for event in run.events)
    finally:
        manager.close()
    assert {"desktop.window_click", "desktop.window_fill", "screen.click_image"} <= LOCATABLE


def test_box_positions_are_saved_with_the_step_and_bounded(tmp_path):
    store = Store(tmp_path)
    moved = Step(action="core.log", params={"message": "x"}, offset=(40, -25))
    saved = store.save_workflow(Workflow(steps=[moved, Step(action="core.log", params={"message": "y"})]))
    again = store.workflow(saved.id)
    assert again.steps[0].offset == (40, -25) and again.steps[1].offset is None
    for bad in ((6000, 0), (0, float("nan"))):
        with pytest.raises(ValueError):
            Step(action="core.log", params={}, offset=bad)


def test_every_color_in_the_stylesheet_is_a_theme_token():
    """A literal color would not follow the dark theme."""
    import re
    from pathlib import Path

    css = (Path(__file__).parents[1] / "src/rpa_orkestrai/static/styles.css").read_text(encoding="utf-8")
    themes = re.findall(r":root(?:\[data-theme=\"dark\"\])? \{[^}]*\}", css)
    assert len(themes) == 2
    light, dark = (set(re.findall(r"(--[a-z0-9-]+):", block)) for block in themes)
    colors = {name for name in light if not name.startswith(("--r-", "--font", "--shadow:")) and name != "--shadow"}
    assert colors <= dark, sorted(colors - dark)
    rest = css
    for block in themes:
        rest = rest.replace(block, "")
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b|rgba?\(", rest)
    assert not re.findall(r":\s*(?:white|black)\s*;", rest)
