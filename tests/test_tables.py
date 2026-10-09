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

    def write_available(self):
        return True

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
    desktop.screenshot.return_value.size = (800, 600)
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


def test_point_column_names_match_the_inspected_structure():
    assert column_index(["Status", "Status"], "Status (2)", canonical=True) == 1
    assert column_index(["", "sutun_1"], "sutun_1", canonical=True) == 0
    assert column_index(["", "sutun_1"], "sutun_1 (2)", canonical=True) == 1


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


def test_native_provider_error_is_reported_without_retry(setup):
    window, grid, _, _, _, ctx = setup
    cell = grid.cells[0][1]
    cell.write = Mock(side_effect=RuntimeError("provider unavailable"))
    with pytest.raises(WindowError, match="hücresine erişilemedi"):
        write_table(ctx, dict(window=window.result(), column="Tutar", value="99"))
    assert cell.write.call_count == 1


def set_grid_bounds(grid, x=120, y=120, width=250, height=150):
    grid.info = Mock(return_value=ElementInfo("DataGrid", "", "", "", x, y, width, height))


def test_point_automatically_uses_native_structure_without_clipboard(setup):
    window, grid, _, windows, desktop, _ = setup
    set_grid_bounds(grid)
    windows.screen_table_cell = Mock()
    result = windows.point_table_cell(window.result(), desktop, targeting=dict(x=70, y=70),
                                     selection={**SELECTION, "column": "sutun_2", "row": 2}, value="NEW")
    assert result == {"row": 2, "column": 2, "value": "NEW"}
    assert grid.cells[1][1].writes == ["NEW"]
    windows.screen_table_cell.assert_not_called()
    desktop.click.assert_not_called()


@pytest.mark.parametrize("problem", ["readonly", "provider", "duplicate"])
def test_point_never_falls_back_after_native_write_or_ambiguity(setup, problem):
    window, grid, backend, windows, desktop, _ = setup
    set_grid_bounds(grid)
    windows.screen_table_cell = Mock()
    if problem == "readonly":
        grid.cells[0][1].readonly = True
    elif problem == "provider":
        grid.cells[0][1].write = Mock(side_effect=RuntimeError("unknown outcome"))
    else:
        backend.tables.return_value = [grid, grid]
    with pytest.raises(WindowError):
        windows.point_table_cell(window.result(), desktop, targeting=dict(x=70, y=70),
                                 selection=SELECTION, value="NEW")
    windows.screen_table_cell.assert_not_called()
    desktop.click.assert_not_called()


@pytest.mark.parametrize("has_structure", [False, True])
def test_point_selects_clipboard_before_writing_when_native_cells_unavailable(setup, has_structure):
    window, grid, backend, windows, desktop, _ = setup
    set_grid_bounds(grid)
    if has_structure:
        grid.cells[0][1].write_available = Mock(return_value=False)
    else:
        backend.tables.return_value = []
    windows.screen_table_cell = Mock(return_value="result")
    assert windows.point_table_cell(window.result(), desktop, targeting=dict(x=70, y=70),
                                    selection=SELECTION, value="NEW") == "result"
    passed = windows.screen_table_cell.call_args.kwargs
    assert passed["region"] == ((20, 40, 250, 150) if has_structure else None)
    assert passed["copy_shape"] == ((2, 2) if has_structure else None)
    assert passed["selection"]["column"] == ("2" if has_structure else "Tutar")
    assert not any(cell.writes for row in grid.cells for cell in row)


def test_point_inspection_returns_entire_table_structure_without_writes(setup):
    window, grid, _, windows, desktop, _ = setup
    set_grid_bounds(grid)
    assert windows.inspect_table(window.result(), desktop, x=70, y=70) == {
        "rows": 2, "columns": ["Fatura No", "Tutar"]}
    desktop.click.assert_not_called()
    assert not any(cell.writes for row in grid.cells for cell in row)


@pytest.mark.parametrize("mode", ["coordinates", "image", "element"])
def test_reference_selects_only_the_table_containing_the_point(setup, tmp_path, monkeypatch, mode):
    from rpa_orkestrai.desktop.vision import Match, Vision

    window, grid, backend, windows, desktop, ctx = setup
    other = Grid()
    set_grid_bounds(grid)
    set_grid_bounds(other, x=500)
    backend.tables.return_value = [other, grid]  # Wrong table deliberately first.
    targeting = {"target_mode": "coordinates", "x": 70, "y": 70}
    if mode == "image":
        template = tmp_path / "table.png"
        template.write_bytes(b"mock image decoder")
        targeting = {"target_mode": "image", "template": template, "offset_x": 0, "offset_y": 0}
        monkeypatch.setattr(Vision, "match_template", Mock(return_value=Match(60, 60, 20, 20, .99)))
    elif mode == "element":
        import platform
        windows._elements = SimpleNamespace(find=Mock(return_value=ElementInfo(
            "DataGrid", "table1", "", "", 160, 140, 20, 20)))
        targeting = {"target_mode": "element", "element": {"platform": platform.system(), "automation_id": "table1"}}
    ctx.window_target = Mock(return_value=targeting)
    result = write_table(ctx, dict(window=window.result(), target_mode=mode, table="obsolete-id", column="2", value="7"))
    assert result["value"] == "7" and grid.cells[0][1].writes == ["7"]
    assert not any(cell.writes for row in other.cells for cell in row)
    desktop.click.assert_not_called()
    desktop.write.assert_not_called()


@pytest.mark.parametrize("problem", ["outside", "ambiguous", "hidden", "moved", "missing_image"])
def test_bad_reference_never_falls_back_to_another_table(setup, tmp_path, monkeypatch, problem):
    from rpa_orkestrai.desktop.vision import Vision

    window, grid, backend, windows, desktop, _ = setup
    set_grid_bounds(grid)
    targeting = {"target_mode": "coordinates", "x": 70, "y": 70}
    if problem == "outside":
        set_grid_bounds(grid, x=500)
    elif problem == "ambiguous":
        other = Grid()
        set_grid_bounds(other)
        backend.tables.return_value.append(other)
    elif problem == "hidden":
        grid.info.return_value = replace(grid.info.return_value, offscreen=True)
    elif problem == "moved":
        grid.info.side_effect = [grid.info.return_value, replace(grid.info.return_value, x=500)]
    else:
        path = tmp_path / "table.png"
        path.write_bytes(b"mock image decoder")
        targeting = {"target_mode": "image", "template": path, "timeout": 0}
        monkeypatch.setattr(Vision, "match_template", Mock(return_value=None))
    with pytest.raises((WindowError, TimeoutError)):
        windows.table_cell(window.result(), desktop, value="7", targeting=targeting, **SELECTION)
    assert not any(cell.writes for row in grid.cells for cell in row)
    desktop.click.assert_not_called()
    desktop.write.assert_not_called()


def test_legacy_table_steps_keep_automatic_lookup(setup):
    from rpa_orkestrai.catalog import defaults
    window, grid, _, _, _, ctx = setup
    ctx.window_target = Mock(side_effect=AssertionError("Legacy step must not require a reference"))
    params = {**defaults("window.write_table"), "window": window.result(), "column": "2", "value": "8"}
    assert write_table(ctx, params)["value"] == "8"
    ctx.window_target.assert_not_called()
    assert grid.cells[0][1].writes == ["8"]
