"""Native table addressing never guesses a coordinate or writes an ambiguous cell."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rpa_orkestrai.actions.windows import write_table
from rpa_orkestrai.desktop.elements import ElementInfo
from rpa_orkestrai.desktop.tables import AxCell, AxGrid, column_index, resolve_cell
from rpa_orkestrai.desktop.windows import WindowError, WindowInfo, WindowService
from rpa_orkestrai.errors import WorkflowError

SELECTION = dict(table="", row_mode="index", row=1, column="Tutar", match_column="", match_value="")


class Cell:
    def __init__(self, value, row, column):
        self.value, self.row, self.column = value, row, column
        self.writes = []
        self.visible = True
        self.readonly = False

    def read(self):
        return self.value

    def info(self):
        return ElementInfo("DataItem", f"{self.row}-{self.column}", "", "", 150 + self.column * 90,
                           150 + self.row * 40, 80, 30, self.value, not self.visible)

    def write(self, value, guard):
        if self.readonly:
            raise WindowError("salt okunur")
        guard()
        self.writes.append(value)
        self.value = value


class Grid:
    name, identifier = "Faturalar", "invoiceGrid"

    def __init__(self):
        self.cells = [[Cell(value, r, c) for c, value in enumerate(row)]
                      for r, row in enumerate([["INV-2", "10"], ["INV-1", "20"]])]

    def shape(self):
        return len(self.cells), 2

    def headers(self, count):
        return ["Fatura No", "Tutar"]

    def cell(self, row, column):
        return self.cells[row][column]


@pytest.fixture
def setup(monkeypatch):
    window = WindowInfo(11, 42, "ERP", "Invoices", 100, 80, 800, 600)
    grid = Grid()
    backend = SimpleNamespace(tables=Mock(return_value=[grid]))
    monkeypatch.setattr("rpa_orkestrai.desktop.tables.native_backend", lambda: backend)
    windows = WindowService(backend=SimpleNamespace(list_windows=Mock(return_value=[window]),
                                                   activate=Mock(), is_active=Mock(return_value=True)))
    desktop = Mock()
    desktop.size.return_value = (1920, 1080)
    ctx = SimpleNamespace(windows=Mock(return_value=windows), desktop=Mock(return_value=desktop))
    return window, grid, backend, windows, desktop, ctx


def test_writes_cell_by_unique_key_and_verifies_value(setup):
    window, grid, _, _, desktop, ctx = setup
    result = write_table(ctx, dict(window=window.result(), table="invoiceGrid", row_mode="match",
                                   match_column="Fatura No", match_value="INV-1", column="Tutar", value="42,50"))
    assert result == {"row": 2, "column": 2, "value": "42,50"}
    assert grid.cells[1][1].writes == ["42,50"] and grid.cells[0][1].writes == []
    desktop.click.assert_not_called()
    desktop.write.assert_not_called()


def test_show_target_only_locates_cell_at_current_bounds(setup):
    window, grid, _, windows, _, ctx = setup
    point = windows.table_cell(window.result(), ctx.desktop(), **SELECTION)
    assert point == grid.cells[0][1].info().center
    assert not any(cell.writes for row in grid.cells for cell in row)


@pytest.mark.parametrize("changes", [dict(value=""), dict(value="x\tSave"), dict(value="x\n"),
    dict(row=0), dict(row=1.5), dict(column=""), dict(row_mode="bad"),
    dict(row_mode="match", match_column="Fatura No", match_value="")])
def test_invalid_parameters_never_activate_or_write(setup, changes):
    window, _, _, windows, desktop, ctx = setup
    with pytest.raises(WorkflowError):
        write_table(ctx, dict(dict(window=window.result(), column="Tutar", value="15"), **changes))
    windows.backend.activate.assert_not_called()
    desktop.write.assert_not_called()


@pytest.mark.parametrize("problem", ["duplicate", "missing", "two_tables", "no_tables", "offscreen", "readonly",
                                    "lost_focus", "moved_window", "column", "row", "changed_shape", "cancel"])
def test_no_writes_when_cell_cannot_be_safely_identified(setup, problem):
    window, grid, backend, windows, desktop, ctx = setup
    params = dict(window=window.result(), column="Tutar", value="99")
    if problem in {"duplicate", "missing"}:
        params.update(row_mode="match", match_column="Fatura No", match_value="INV-1")
        grid.cells[0][0].value = "INV-1" if problem == "duplicate" else "INV-2"
        if problem == "missing":
            grid.cells[1][0].value = "INV-3"
    elif problem in {"two_tables", "no_tables"}:
        backend.tables.return_value = [grid, Grid()] if problem == "two_tables" else []
    elif problem == "offscreen":
        grid.cells[0][1].visible = False
    elif problem == "readonly":
        grid.cells[0][1].readonly = True
    elif problem == "lost_focus":
        windows.backend.is_active.side_effect = [True, False]
    elif problem == "moved_window":
        windows.backend.list_windows.side_effect = [[window], [window], [replace(window, x=200)]]
    elif problem == "column":
        params["column"] = "Missing"
    elif problem == "row":
        params["row"] = 3
    elif problem == "changed_shape":
        grid.shape = Mock(side_effect=[(2, 2), (3, 2)])
    else:
        windows.cancel.set()
    with pytest.raises((WindowError, InterruptedError)):
        write_table(ctx, params)
    assert not any(cell.writes for row in grid.cells for cell in row)
    desktop.write.assert_not_called()
    desktop.click.assert_not_called()


def test_verification_failure_stops_after_one_write(setup):
    window, grid, _, _, _, ctx = setup
    grid.cells[0][1].read = Mock(return_value="ERP rejected value")
    with pytest.raises(WindowError, match="doğrulanamadı"):
        write_table(ctx, dict(window=window.result(), column="Tutar", value="99"))
    assert grid.cells[0][1].writes == ["99"]


def test_duplicate_headers_require_explicit_column_number():
    with pytest.raises(WindowError, match="Birden fazla"):
        column_index(["Tutar", "TUTAR"], "tutar")
    assert column_index(["Tutar", "Tutar"], "2") == 1


def test_cancel_checked_during_key_search(setup):
    window, grid, backend, *_ = setup
    check = Mock(side_effect=InterruptedError)
    with pytest.raises(InterruptedError):
        resolve_cell(backend, window, **{**SELECTION, "row_mode": "match", "match_column": "1", "match_value": "x"},
                     check=check)
    assert not any(cell.writes for row in grid.cells for cell in row)


def test_mac_table_uses_column_row_order_and_settable_value():
    cell_element = object()
    attrs = {"AXRows": [1, 2], "AXColumns": [3, 4], "AXValue": "old", "AXEnabled": True}
    backend = SimpleNamespace(_attribute=lambda element, key: attrs.get(key), ax=Mock(), _info=Mock())
    backend.ax.AXUIElementCopyParameterizedAttributeValue.return_value = (0, cell_element)
    backend.ax.AXUIElementIsAttributeSettable.return_value = (0, True)
    backend.ax.AXUIElementSetAttributeValue.return_value = 0
    grid = AxGrid(backend, "table", SimpleNamespace(name="Invoices", automation_id="grid"))
    assert grid.shape() == (2, 2)
    cell = grid.cell(1, 0)
    backend.ax.AXUIElementCopyParameterizedAttributeValue.assert_called_once_with(
        "table", "AXCellForColumnAndRow", [0, 1], None)
    assert cell.read() == "old"
    guard = Mock()
    cell.write("new", guard)
    guard.assert_called_once()
    backend.ax.AXUIElementSetAttributeValue.assert_called_once_with(cell_element, "AXValue", "new")
    backend.ax.AXUIElementSetAttributeValue.reset_mock()
    backend.ax.AXUIElementIsAttributeSettable.return_value = (0, False)
    with pytest.raises(WindowError, match="salt okunur"):
        cell.write("blocked", guard)
    backend.ax.AXUIElementSetAttributeValue.assert_not_called()


def test_mac_ambiguous_cell_children_never_written():
    backend = SimpleNamespace(_attribute=lambda element, key: [1, 2] if key == "AXChildren" else None,
                              _text=lambda element, key: "AXTextField", ax=Mock())
    with pytest.raises(WindowError):
        AxCell(backend, "cell").write("bad", Mock())
    backend.ax.AXUIElementSetAttributeValue.assert_not_called()


def test_resorting_between_resolution_and_write_stops_input(setup):
    window, grid, _, _, _, ctx = setup
    cell = grid.cells[1][1]
    original_write = cell.write

    def race(value, guard):
        grid.cells.reverse()
        original_write(value, guard)

    cell.write = race
    with pytest.raises(WindowError, match="değişti"):
        write_table(ctx, dict(window=window.result(), column="Tutar", value="99", row_mode="match",
                              match_column="Fatura No", match_value="INV-1"))
    assert cell.writes == []
