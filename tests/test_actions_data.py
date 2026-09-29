"""Data, text, date, list and flow-control steps; no desktop access."""

import threading
from datetime import datetime

import pytest

from rpa_orkestrai.config import Settings
from rpa_orkestrai.engine import Executor, RunManager, WorkflowError, validate_workflow
from rpa_orkestrai.models import Run, Step, Workflow
from rpa_orkestrai.storage import Store


def executor(tmp_path, variables=None, *, dry_run=False):
    settings = Settings(tmp_path, dotenv=False)
    store = Store(tmp_path)
    run = Run(workflow_id="0" * 32, workflow_name="Test", department="Genel", dry_run=dry_run)
    return Executor(settings, store, run, threading.Event(), lambda: store.save_run(run), variables)


def run_steps(tmp_path, steps, variables=None, **kwargs):
    runner = executor(tmp_path, variables, **kwargs)
    runner.execute(Workflow(steps=steps))
    return runner


def step(action, children=(), otherwise=(), **params):
    return Step(action=action, params=params, children=list(children), otherwise=list(otherwise))


@pytest.mark.parametrize("expression,variables,expected", [
    ("${sayac} + 1", {"sayac": 4}, 5),
    ("sayac + 1", {"sayac": "41"}, 42),
    ("round(tutar * 1.2, 2)", {"tutar": "1.234,50"}, 1481.4),
    ("row.adet > 0 and row.durum == 'Bekliyor'", {"row": {"adet": "3", "durum": "Bekliyor"}}, True),
    ("'INV-' + no", {"no": "42"}, "INV-42"),
    ("liste[1]", {"liste": [10, 20]}, 20),
    ("len(liste)", {"liste": [1, 2, 3]}, 3),
    ("10 // 3 + 10 % 3", {}, 4),
    ("'evet' if puan >= 50 else 'hayır'", {"puan": 70}, "evet"),
    ("max(a, b, 3)", {"a": 1, "b": 7}, 7),
    ("${ad} + ' Bey'", {"ad": "Çağrı Öztürk"}, "Çağrı Öztürk Bey"),
    ("${row.not} == 'Ödendi \"tam\"'", {"row": {"not": 'Ödendi "tam"'}}, True),
])
def test_calculate(tmp_path, expression, variables, expected):
    runner = run_steps(tmp_path, [step("data.calculate", expression=expression, output="result")], variables)
    assert runner.variables["result"] == expected


@pytest.mark.parametrize("expression", [
    "__import__('os').system('echo x')", "liste.__class__", "open('x')", "(lambda: 1)()",
    "a" * 1001, "2 ** 1000", "1 / 0", "tanimsiz + 1", "'x' * 3",
])
def test_calculate_rejects_unsafe_or_invalid_expressions(tmp_path, expression):
    with pytest.raises(WorkflowError):
        run_steps(tmp_path, [step("data.calculate", expression=expression, output="result")], {"liste": [1]})


@pytest.mark.parametrize("operation,params,expected", [
    ("trim", {}, "istanbul ılık"),
    ("upper", {}, "İSTANBUL ILIK"),
    ("upper", {"turkish": False}, "ISTANBUL ILIK"),
    ("title", {}, "İstanbul Ilık"),
    ("replace", {"find": "ılık", "replace_with": "sıcak"}, "istanbul sıcak"),
    ("split", {"find": " "}, ["istanbul", "ılık"]),
    ("substring", {"start": 0, "length": 8}, "istanbul"),
    ("length", {}, 13),
    ("contains", {"find": "İSTANBUL"}, True),
    ("pad_left", {"find": "0", "length": 15}, "  istanbul ılık  ".strip().rjust(15, "0")),
])
def test_text_operations(tmp_path, operation, params, expected):
    runner = run_steps(tmp_path, [step("text.transform", text="  istanbul ılık  " if operation == "trim" else
                                       "istanbul ılık", operation=operation, output="out", **params)])
    assert runner.variables["out"] == expected


def test_text_regex_and_numbers(tmp_path):
    runner = run_steps(tmp_path, [
        step("text.transform", text="Fatura No: INV-2026-0042 Tutar 1.250,75 TL", operation="regex_extract",
             pattern=r"Fatura No: (\S+)", output="invoice"),
        step("text.transform", text="1.250,75", operation="number", output="amount"),
        step("text.transform", text="A1 B22 C333", operation="regex_extract", pattern=r"\d+", all_matches=True,
             output="numbers"),
        step("text.transform", text="Tel: 0532 111 22 33", operation="regex_replace", pattern=r"\D",
             replace_with="", output="digits"),
    ])
    assert runner.variables["invoice"] == "INV-2026-0042"
    assert runner.variables["amount"] == 1250.75
    assert runner.variables["numbers"] == ["1", "22", "333"]
    assert runner.variables["digits"] == "05321112233"
    with pytest.raises(WorkflowError, match="Düzenli ifade"):
        run_steps(tmp_path, [step("text.transform", text="x", operation="regex_extract", pattern="(", output="o")])


def test_dates(tmp_path):
    runner = run_steps(tmp_path, [
        step("data.date", operation="add", value="31.01.2026", amount=1, unit="months", format="%d.%m.%Y",
             output="next_month"),
        step("data.date", operation="add", value="2026-09-28 10:00", amount=-2, unit="days",
             format="%Y-%m-%d %H:%M", output="before"),
        step("data.date", operation="difference", value="01.09.2026", other="28.09.2026", unit="days",
             output="days"),
        step("data.date", operation="weekday", value="28.09.2026", output="weekday"),
        step("data.date", operation="now", format="%Y", output="year"),
    ])
    assert runner.variables["next_month"] == "28.02.2026"
    assert runner.variables["before"] == "2026-09-26 10:00"
    assert runner.variables["days"] == 27
    assert runner.variables["weekday"] == "Pazartesi"
    assert runner.variables["year"] == str(datetime.now().year)
    with pytest.raises(WorkflowError, match="anlaşılamadı"):
        run_steps(tmp_path, [step("data.date", operation="format", value="dün değil", output="x")])


def test_lists(tmp_path):
    rows = [{"no": "A", "tutar": "10,5", "durum": "Bekliyor"}, {"no": "B", "tutar": "4", "durum": "Tamam"},
            {"no": "A", "tutar": "2", "durum": "Bekliyor"}]
    runner = run_steps(tmp_path, [
        step("data.list", list="${rows}", operation="length", output="count"),
        step("data.list", list="${rows}", operation="filter", field="durum", operator="eq", value="Bekliyor",
             output="pending"),
        step("data.list", list="${rows}", operation="sum", field="tutar", output="total"),
        step("data.list", list="${rows}", operation="unique", field="no", output="unique"),
        step("data.list", list="${rows}", operation="sort", field="tutar", descending=True, output="sorted"),
        step("data.list", list="${rows}", operation="join", field="no", separator="-", output="joined"),
        step("data.list", list="${rows}", operation="last", output="last"),
    ], {"rows": rows})
    assert runner.variables["count"] == 3
    assert [row["tutar"] for row in runner.variables["pending"]] == ["10,5", "2"]
    assert runner.variables["total"] == 16.5
    assert [row["no"] for row in runner.variables["unique"]] == ["A", "B"]
    assert runner.variables["sorted"][0]["no"] == "A" and runner.variables["sorted"][0]["tutar"] == "10,5"
    assert runner.variables["joined"] == "A-B-A"
    assert runner.variables["last"]["tutar"] == "2"
    with pytest.raises(WorkflowError, match="boş"):
        run_steps(tmp_path, [step("data.list", list=[], operation="first", output="x")])


def test_repeat_break_continue_and_loop_index(tmp_path):
    runner = run_steps(tmp_path, [
        step("core.set", name="seen", value=[]),
        step("control.repeat", count=10, children=[
            step("control.if", left="${loop_index}", operator="eq", right=1, children=[step("control.continue")]),
            step("control.if", left="${loop_index}", operator="eq", right=4, children=[step("control.break")]),
            step("data.append", name="seen", value="${loop_index}"),
        ]),
    ])
    assert runner.variables["seen"] == [0, 2, 3]
    assert "loop_index" not in runner.variables


def test_break_leaves_only_the_innermost_loop(tmp_path):
    runner = run_steps(tmp_path, [
        step("core.set", name="pairs", value=[]),
        step("control.for_each", items=[1, 2], item_name="outer", children=[
            step("control.for_each", items=["a", "b", "c"], item_name="inner", children=[
                step("control.if", left="${inner}", operator="eq", right="b", children=[step("control.break")]),
                step("data.append", name="pairs", value="${outer}${inner}"),
            ]),
        ]),
    ])
    assert runner.variables["pairs"] == ["1a", "2a"]


def test_break_outside_a_loop_is_rejected_before_running(tmp_path):
    with pytest.raises(WorkflowError, match="döngünün"):
        validate_workflow(Workflow(steps=[step("control.break")]))
    with pytest.raises(WorkflowError, match="döngünün"):
        validate_workflow(Workflow(steps=[step("control.try", children=[step("control.continue")])]))
    validate_workflow(Workflow(steps=[step("control.repeat", count=2, children=[
        step("control.try", children=[step("control.break")])])]))


def test_try_catches_errors_and_runs_recovery(tmp_path):
    runner = run_steps(tmp_path, [
        step("control.try", error_name="hata", children=[
            step("core.set", name="before", value=1),
            step("data.calculate", expression="1 / 0", output="x"),
            step("core.set", name="after", value=1),
        ], otherwise=[step("core.set", name="recovered", value="${hata}")]),
    ])
    assert runner.variables["before"] == 1 and "after" not in runner.variables
    assert runner.variables["recovered"] == "Sıfıra bölme yapılamaz."
    # A break inside try still leaves the loop instead of being treated as an error.
    runner = run_steps(tmp_path, [step("control.repeat", count=5, children=[
        step("control.try", children=[step("control.break")], otherwise=[step("core.set", name="caught", value=1)]),
        step("core.set", name="after_break", value=1),
    ])])
    assert "caught" not in runner.variables and "after_break" not in runner.variables


def wait_done(manager, store, run_id):
    import time

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        run = store.run(run_id)
        if run.status not in {"queued", "running"}:
            return run
        time.sleep(0.02)
    pytest.fail("run did not finish")


def test_stop_ends_run_with_chosen_result(tmp_path):
    settings, store = Settings(tmp_path, dotenv=False), Store(tmp_path)
    manager = RunManager(settings, store)
    try:
        ok = manager.start(Workflow(steps=[step("control.stop", status="success", message="Erken bitti"),
                                           step("core.set", name="x", value=1)]))
        assert wait_done(manager, store, ok.id).status == "succeeded"
        failed = manager.start(Workflow(steps=[step("control.stop", status="failure", message="Stok yok")]))
        result = wait_done(manager, store, failed.id)
        assert result.status == "failed" and result.error == "Stok yok"
    finally:
        manager.close()


def test_sub_workflow_shares_variables_and_refuses_recursion(tmp_path):
    runner = executor(tmp_path)
    child = runner.store.save_workflow(Workflow(name="Ortak giriş", steps=[
        step("data.calculate", expression="${sayi} * 2", output="iki_kat")]))
    runner.variables["sayi"] = 21
    runner.execute(Workflow(steps=[step("control.run_workflow", workflow=child.id)]))
    assert runner.variables["iki_kat"] == 42
    looping = runner.store.save_workflow(Workflow(name="Döngüsel", steps=[]))
    looping.steps = [step("control.run_workflow", workflow=looping.id)]
    runner.store.save_workflow(looping)
    with pytest.raises(WorkflowError, match="kendisini"):
        executor(tmp_path).execute(looping)
    with pytest.raises(WorkflowError, match="bulunamadı"):
        executor(tmp_path).execute(Workflow(steps=[step("control.run_workflow", workflow="f" * 32)]))


def test_step_test_runs_only_that_step_with_sample_variables(tmp_path):
    settings, store = Settings(tmp_path, dotenv=False), Store(tmp_path)
    target = step("text.transform", text="${row.form_id}", operation="upper", output="upper_id")
    workflow = store.save_workflow(Workflow(steps=[step("core.set", name="must_not_run", value=1),
                                                   step("control.for_each", items="${rows}", item_name="row",
                                                        children=[target])]))
    manager = RunManager(settings, store)
    try:
        run = manager.start_step(workflow, target.id, {"row": {"form_id": "inv-ı"}})
        result = wait_done(manager, store, run.id)
        assert result.status == "succeeded" and result.test_step_id == target.id
        assert result.variables["upper_id"] == "İNV-I"  # Turkish rules: i → İ, ı → I
        assert "must_not_run" not in result.variables
        with pytest.raises(KeyError):
            manager.start_step(workflow, "missing", {})
        with pytest.raises(WorkflowError):
            manager.start_step(workflow, target.id, {"1bad": 1})
    finally:
        manager.close()


def test_preview_skips_screen_file_and_network_steps_but_evaluates_data(tmp_path):
    runner = run_steps(tmp_path, [
        step("input.mouse_click", x=10, y=10),
        step("file.read_text", path="/does/not/exist.txt", output="content"),
        step("data.calculate", expression="2 + 2", output="four"),
        step("data.calculate", expression="len(content) + 1", output="unknown_length"),
        step("text.transform", text="${content}", operation="upper", output="shouted"),
    ], dry_run=True)
    assert runner.variables["four"] == 4
    assert type(runner.variables["unknown_length"]).__name__ == "PreviewValue"
    assert any("atlandı" in event.message for event in runner.run.events)


def test_held_keys_are_released_when_a_run_fails(tmp_path, monkeypatch):
    from unittest.mock import Mock

    runner = executor(tmp_path)
    desktop = Mock()
    runner._desktop = desktop
    monkeypatch.setattr("rpa_orkestrai.actions.inputs.key_name", lambda value: value)
    with pytest.raises(WorkflowError):
        runner.execute(Workflow(steps=[step("input.key_state", key="shift", state="down"),
                                       step("data.calculate", expression="1/0", output="x")]))
    desktop.key_down.assert_called_once_with("shift")
    desktop.key_up.assert_called_once_with("shift")


def test_bundled_examples_are_valid_and_the_tour_runs(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    from rpa_orkestrai.models import WorkflowInput

    examples = Path(__file__).resolve().parents[1] / "examples"
    for name in ("adim-turu.json", "metin-editoru.json"):
        workflow = Workflow(**WorkflowInput(**json.loads((examples / name).read_text(encoding="utf-8"))).model_dump())
        validate_workflow(workflow)
    tour = Workflow(**WorkflowInput(**json.loads((examples / "adim-turu.json").read_text(encoding="utf-8"))).model_dump())
    from rpa_orkestrai import actions

    actions.get("ui.message")
    monkeypatch.setitem(actions.HANDLERS, "ui.message", lambda ctx, p: "ok")
    runner = executor(tmp_path)
    runner.variables["sistem"] = {**runner.variables["sistem"], "masaustu": str(tmp_path)}
    runner.execute(tour)
    assert runner.variables["toplam"] == round(3 * 12.5 + 5 * 8 + 2 * 95.9, 2)
    assert [row["Ürün"] for row in runner.variables["okunan"]] == ["ÇAY", "ŞEKER", "KAHVE"]
    assert (tmp_path / "rpa-adim-turu.xlsx").is_file()


def test_every_library_step_has_a_handler():
    import importlib

    from rpa_orkestrai import actions
    from rpa_orkestrai.catalog import CATALOG

    importlib.import_module("rpa_orkestrai.actions.files")  # an early partial import must not hide others
    engine_steps = {"desktop.find_window", "desktop.window_click", "desktop.window_fill", "desktop.window_key",
                    "desktop.window_wait_image", "core.wait", "core.set", "core.log", "data.append",
                    "data.export_csv"}
    flow = {entry["type"] for entry in CATALOG if entry["type"].startswith("control.")}
    missing = [entry["type"] for entry in CATALOG if entry["type"] not in engine_steps | flow
               and not entry["type"].startswith("sheets.") and actions.get(entry["type"]) is None]
    assert missing == []
