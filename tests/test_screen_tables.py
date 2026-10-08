"""Moving columns must move the write target; ambiguity must never cause input."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from rpa_orkestrai.actions.windows import table_operation, write_table
from rpa_orkestrai.desktop.ocr import OcrWord
from rpa_orkestrai.desktop.screen_tables import (
    AmbiguousTable,
    Phrases,
    TableText,
    locate_cell,
    locate_image,
    screen_table_cell,
    table_focus_point,
)
from rpa_orkestrai.desktop.windows import WindowError, WindowInfo, WindowService
from rpa_orkestrai.errors import WorkflowError

TEXT = "Kod\tİade Sonrası\tMiktar\nA125\tARIZALILAR\t1\nA126\tARIZALILAR\t2"
TABLE = TableText.parse(TEXT)
SELECTION = dict(row_mode="index", row=1, column="İade Sonrası", match_column="", match_value="")


def word(text, x, y, width=None):
    return OcrWord(text, x, y, width or len(text) * 7, 12, .99)


def grid_words(x=200, *, offset=0, y=20, old="ARIZALILAR"):
    return [word("Kod", 20 + offset, y), word("İade", x + offset, y),
            word("Sonrası", x + 35 + offset, y), word("Miktar", x + 180 + offset, y),
            word("A125", 20 + offset, y + 30), word(old, x + offset, y + 30),
            word("1", x + 180 + offset, y + 30), word("A126", 20 + offset, y + 75),
            word("ARIZALILAR", x + offset, y + 75), word("2", x + 180 + offset, y + 75)]


@pytest.mark.parametrize("column_x", [120, 250, 500])
def test_current_heading_and_row_witness_follow_changed_column_width(column_x):
    cell = locate_cell(grid_words(column_x), TABLE, 0, 1, reference_point=(30, 55))
    assert column_x <= cell.point[0] <= column_x + 70
    assert cell.point[1] == 56
    second = locate_cell(grid_words(column_x), TABLE, 1, 1, reference_point=(30, 55))
    assert second.point[1] == 101  # Variable row spacing, no fixed row-height estimate.


def test_single_row_uses_another_visible_cell_to_confirm_identity():
    table = TableText(TABLE.headers, TABLE.rows[:1])
    result = locate_cell(grid_words()[:7], table, 0, 1, reference_point=(30, 55))
    assert result.point[1] == 56


@pytest.mark.parametrize("title", ["İade", "Jade", "lade"])
def test_heading_optical_aliases_do_not_relax_cell_text_matching(title):
    words = [replace(w, text=title) if w.text == "İade" else
             replace(w, text="Sonrasl") if w.text == "Sonrası" else w for w in grid_words()]
    assert locate_cell(words, TABLE, 0, 1, reference_point=(30, 55)).point[1] == 56
    # The same optical substitutions are not allowed in a record's actual value.
    words = [replace(w, text="ARIZAJILAR") if w.text == "ARIZALILAR" else w for w in words]
    with pytest.raises(WindowError):
        locate_cell(words, TABLE, 0, 1, reference_point=(30, 55))


@pytest.mark.parametrize("titles", [("Alan I", "Alan l"), ("İade", "Jade")])
def test_optically_colliding_clipboard_headers_rejected_even_when_exact_visible(titles):
    table = TableText(("Kod", *titles), (("A125", "ESKI", "ESKI"),))
    words = [word("Kod", 20, 20), word(titles[0], 150, 20), word(titles[1], 350, 20),
             word("A125", 20, 50), word("ESKI", 150, 50), word("ESKI", 350, 50)]
    with pytest.raises(AmbiguousTable, match="ayırt edilemeyen"):
        locate_cell(words, table, 0, 1, reference_point=(30, 55))


def test_heading_cache_cannot_supply_a_cell_value_match():
    phrases = Phrases([word("Sonrasl", 20, 20)])
    assert phrases.find("Sonrası", heading=True)
    assert phrases.find("Sonrası") == []
    assert phrases.find("Sonrasl")
    assert Phrases([word("Proje", 20, 20)]).find("Proie", heading=True) == []
    assert Phrases([word("Alan1", 20, 20)]).find("AlanI", heading=True) == []


def test_focus_rejects_exact_and_optical_heading_candidates_together(monkeypatch):
    words = grid_words() + [word("Jade", 550, 20), word("Sonrasl", 585, 20)]
    monkeypatch.setattr("rpa_orkestrai.desktop.screen_tables.measured_words", lambda *a, **kw: words)
    with pytest.raises(AmbiguousTable):
        table_focus_point(Image.new("RGB", (900, 500)), "İade Sonrası")


def test_reference_binds_to_source_table_not_identical_neighbor():
    left = grid_words(120)
    right = grid_words(120, offset=450)
    assert locate_cell(left + right, TABLE, 0, 1, reference_point=(30, 55)).point[0] < 400
    # OCR missed the source value; an identical copy to the right is not a fallback.
    left = [w for w in left if not (w.text == "ARIZALILAR" and w.y == 50)]
    with pytest.raises(WindowError):
        locate_cell(left + right, TABLE, 0, 1, reference_point=(30, 55))


def test_reference_binds_to_source_table_not_identical_table_below():
    top = [w for w in grid_words() if not (w.text == "ARIZALILAR" and w.y == 50)]
    with pytest.raises(WindowError):
        locate_cell(top + grid_words(y=200), TABLE, 0, 1, reference_point=(30, 55))


def test_neighbor_cells_cannot_combine_into_wrong_record_witness():
    table = TableText.parse("Kod\tDurum\tNot\tEk\nA1\tESKI\tKIRMIZI MAVI\tX\nA2\tESKI\tKIRMIZI\tMAVI")
    words = [word("Kod", 20, 20), word("Durum", 100, 20), word("Not", 200, 20), word("Ek", 265, 20),
             word("A2", 20, 50), word("ESKI", 100, 50), word("KIRMIZI", 200, 50), word("MAVI", 265, 50)]
    with pytest.raises(WindowError):
        locate_cell(words, table, 0, 1, reference_point=(25, 55))


@pytest.mark.parametrize("problem", ["header", "offscreen", "clipped", "same_rows", "duplicate_header", "confidence"])
def test_uncertain_cell_is_rejected(problem):
    words, table = grid_words(), TABLE
    if problem == "header":
        words = [w for w in words if w.text != "Sonrası"]
    elif problem == "offscreen":
        words = [w for w in words if w.y != 50]
    elif problem == "clipped":
        words = [replace(w, text="ARIZA…") if w.y == 50 and w.text == "ARIZALILAR" else w for w in words]
    elif problem == "same_rows":
        table = TableText(table.headers, (table.rows[0], table.rows[0]))
    elif problem == "duplicate_header":
        table = TableText(("İade Sonrası", "İade Sonrası", "Miktar"), table.rows)
    else:
        words = [replace(w, confidence=.4) if w.y == 50 else w for w in words]
    with pytest.raises(WindowError):
        locate_cell(words, table, 0, 1, reference_point=(30, 55))


@pytest.mark.parametrize("text", ["a", "A\tB", "A\tB\n1", "\t\n1\t2", "A\tB\n1\t2\t3"])
def test_not_a_complete_table_rejected(text):
    with pytest.raises(WindowError):
        TableText.parse(text)


def test_selection_uses_copied_column_names_and_unique_row_key():
    assert TABLE.select(**{**SELECTION, "row_mode": "match", "match_column": "Kod", "match_value": "A126"}) == (1, 1)
    assert TABLE.select(**{**SELECTION, "column": "İADE SONRASI"}) == (0, 1)
    with pytest.raises(WindowError):
        TABLE.select(**{**SELECTION, "row_mode": "match", "match_column": "İade Sonrası", "match_value": "ARIZALILAR"})
    with pytest.raises(WindowError):
        TableText.parse("Kod\tDurum\nA1\t").select(**{**SELECTION, "column": "Durum"})


@pytest.fixture
def runtime(monkeypatch):
    import pyperclip

    window = WindowInfo(11, 42, "Application", "Records", 100, 80, 900, 500)
    backend = SimpleNamespace(list_windows=Mock(return_value=[window]), activate=Mock(), is_active=Mock(return_value=True))
    service = WindowService(backend=backend)
    service.cancel.wait = Mock(return_value=False)
    desktop = Mock()
    desktop.size.return_value = (1920, 1080)
    desktop.screenshot.return_value = Image.new("RGB", (900, 500), "white")
    state = {"clipboard": "previous clipboard", "editor": False, "value": "ARIZALILAR", "copied": 0,
             "editor_opens": True, "activation": "double_click", "after_write": None, "layout": 200, "ocr_calls": 0}
    monkeypatch.setattr(pyperclip, "paste", lambda: state["clipboard"])
    monkeypatch.setattr(pyperclip, "copy", lambda v: state.__setitem__("clipboard", v))

    def current_table():
        return TEXT.replace("A125\tARIZALILAR", "A125\t" + state["value"])

    def click(x, y, *, clicks, button):
        state["editor"] = state["editor_opens"] and (clicks == 2 or
            (state["activation"] == "single_click" and state["copied"] == 2))

    def hotkey(*keys):
        if keys == ("mod", "c"):
            state["copied"] += 1
            state["clipboard"] = state["value"] if state["editor"] else current_table()

    def paste(value):
        assert state["editor"]
        state["value"] = value
        if state["after_write"]:
            state["after_write"]()

    def words(image, **options):
        state["ocr_calls"] += 1
        measured = grid_words(state["layout"], old=state["value"])
        if state["editor"]:
            measured = [replace(w, x=w.x + .5, y=w.y + .5) if w.y == 50 else w for w in measured]
        return [replace(w, x=w.x * 2, y=w.y * 2, width=w.width * 2, height=w.height * 2) for w in measured
                if w.x + w.width <= image.width / 2 and w.y + w.height <= image.height / 2]

    desktop.click.side_effect = click
    desktop.hotkey.side_effect = hotkey
    desktop.paste.side_effect = paste
    desktop.press.side_effect = lambda key: state.__setitem__("editor", key == "f2" and state["editor_opens"])
    monkeypatch.setattr("rpa_orkestrai.desktop.screen_tables.read_words", words)
    options = dict(region=(0, 0, 900, 500), selection=SELECTION)
    return service, window, desktop, state, options


def test_write_checks_editor_pastes_once_and_verifies_new_width(runtime):
    service, window, desktop, state, options = runtime
    state["after_write"] = lambda: state.__setitem__("layout", 380)
    result = screen_table_cell(service, window.result(), desktop, value="YENI", **options)
    assert result == {"row": 1, "column": 2, "value": "YENI"}
    desktop.paste.assert_called_once_with("YENI")
    desktop.write.assert_not_called()
    assert state["clipboard"] == "previous clipboard"
    assert state["copied"] == 4
    writes = [c for c in desktop.click.call_args_list if c.kwargs["clicks"] == 2]
    assert len(writes) == 1 and 300 <= writes[0].args[0] <= 370


def test_show_target_copies_table_without_editing(runtime):
    service, window, desktop, state, options = runtime
    point = screen_table_cell(service, window.result(), desktop, **options)
    assert point[0] >= window.x + 200
    desktop.paste.assert_not_called()
    assert not any(c.kwargs["clicks"] == 2 for c in desktop.click.call_args_list)
    assert state["clipboard"] == "previous clipboard"


@pytest.mark.parametrize("edit_mode", ["single_click", "f2"])
def test_edit_mode_still_checks_old_text_before_pasting(runtime, edit_mode):
    service, window, desktop, state, options = runtime
    state["activation"] = edit_mode
    result = screen_table_cell(service, window.result(), desktop, value="YENI", edit_mode=edit_mode, **options)
    assert result["value"] == "YENI"
    desktop.paste.assert_called_once_with("YENI")
    assert state["copied"] == 4
    assert not any(c.kwargs["clicks"] == 2 for c in desktop.click.call_args_list)
    if edit_mode == "f2":
        assert desktop.press.call_args_list[0].args == ("f2",)


def test_grid_does_not_open_editor_never_pastes(runtime):
    service, window, desktop, state, options = runtime
    state["editor_opens"] = False
    with pytest.raises(WindowError, match="düzenlemeye açılamadı"):
        screen_table_cell(service, window.result(), desktop, value="YENI", **options)
    desktop.paste.assert_not_called()
    assert state["clipboard"] == "previous clipboard"


@pytest.mark.parametrize("area", [(0, 0, 900, 35), (0, 0, 60, 500), (-1, 0, 900, 500), (0, 0, 950, 500)])
def test_missing_data_header_or_invalid_scope_is_not_clicked(runtime, area):
    service, window, desktop, state, options = runtime
    options["region"] = area
    with pytest.raises(WindowError):
        screen_table_cell(service, window.result(), desktop, value="YENI", **options)
    desktop.click.assert_not_called()
    desktop.paste.assert_not_called()
    assert state["clipboard"] == "previous clipboard"


def test_ocr_receives_only_selected_table_not_neighbor(runtime, monkeypatch):
    service, window, desktop, state, options = runtime
    options["region"] = (10, 15, 80, 140)
    received = []

    def partial_source(image, **kwargs):
        received.append(image.size)
        # A neighboring table's Status header/value must not be in this image.
        return [word("Kod", 10, 10), word("A125", 10, 50)]

    monkeypatch.setattr("rpa_orkestrai.desktop.screen_tables.read_words", partial_source)
    with pytest.raises(WindowError, match="başlığı"):
        screen_table_cell(service, window.result(), desktop, value="YENI", **options)
    assert received and set(received) == {(160, 280)}
    desktop.click.assert_not_called()
    desktop.paste.assert_not_called()


def test_region_offset_is_added_to_freshly_measured_cell(runtime):
    service, window, desktop, state, options = runtime
    options["region"] = (40, 25, 750, 400)
    point = screen_table_cell(service, window.result(), desktop, **options)
    measured = locate_cell(grid_words(), TABLE, 0, 1).point
    assert point == (round(window.x + 40 + measured[0]), round(window.y + 25 + measured[1]))


def test_table_changes_between_copy_and_edit_never_pastes(runtime):
    service, window, desktop, state, options = runtime
    original = desktop.click.side_effect

    def click(*args, **kwargs):
        original(*args, **kwargs)
        if state["copied"] == 1:
            state["value"] = "CHANGED"

    desktop.click.side_effect = click
    with pytest.raises(WindowError, match="içeriği"):
        screen_table_cell(service, window.result(), desktop, value="YENI", **options)
    desktop.paste.assert_not_called()
    assert not any(c.kwargs["clicks"] == 2 for c in desktop.click.call_args_list)


def test_layout_changes_while_editor_opens_never_pastes(runtime):
    service, window, desktop, state, options = runtime
    original = desktop.click.side_effect

    def click(*args, **kwargs):
        original(*args, **kwargs)
        if kwargs["clicks"] == 2:
            state["layout"] = 380

    desktop.click.side_effect = click
    with pytest.raises(WindowError, match="hücre veya satır değişti"):
        screen_table_cell(service, window.result(), desktop, value="YENI", **options)
    desktop.paste.assert_not_called()


def test_focus_loss_before_write_never_pastes(runtime):
    service, window, desktop, state, options = runtime
    original = desktop.click.side_effect

    def click(*args, **kwargs):
        original(*args, **kwargs)
        if kwargs["clicks"] == 2:
            service.backend.is_active.return_value = False

    desktop.click.side_effect = click
    with pytest.raises(WindowError, match="odağı"):
        screen_table_cell(service, window.result(), desktop, value="YENI", **options)
    desktop.paste.assert_not_called()
    assert state["clipboard"] == "previous clipboard"


def test_verification_failure_after_write_never_retries(runtime):
    service, window, desktop, state, options = runtime
    state["after_write"] = lambda: state.__setitem__("value", "REJECTED")
    with pytest.raises(WindowError, match="yazma denendi"):
        screen_table_cell(service, window.result(), desktop, value="YENI", **options)
    desktop.paste.assert_called_once()
    assert state["clipboard"] == "previous clipboard"


def test_screen_action_validates_before_desktop_input():
    ctx = SimpleNamespace(windows=Mock(), desktop=Mock())
    with pytest.raises(WorkflowError, match="Tablo alanını çiz"):
        table_operation(ctx, dict(write_method="screen", column="Durum", row=1))
    ctx.windows.assert_not_called()
    for changed in [dict(value=""), dict(value="x\n"), dict(write_method="unknown"), dict(row=0)]:
        with pytest.raises(WorkflowError):
            write_table(ctx, {"write_method": "screen", "column": "Durum", "value": "Yeni", **changed})
    ctx.desktop.assert_not_called()


def test_enhanced_ocr_cannot_hide_observed_ambiguity(monkeypatch):
    words = grid_words() + [replace(w, y=w.y + 160) for w in grid_words() if w.y == 50]
    read = Mock(return_value=[replace(w, x=w.x * 2, y=w.y * 2, width=w.width * 2, height=w.height * 2) for w in words])
    monkeypatch.setattr("rpa_orkestrai.desktop.screen_tables.read_words", read)
    with pytest.raises(AmbiguousTable):
        locate_image(Image.new("RGB", (900, 500)), TABLE, 0, 1, reference_point=(30, 55))
    assert read.call_count == 1


def test_heading_order_follows_reordered_clipboard_columns():
    table = TableText.parse("Kod\tMiktar\tİade Sonrası\nA125\t1\tARIZALILAR")
    words = [word("Kod", 20, 20), word("Miktar", 120, 20), word("İade", 350, 20),
             word("Sonrası", 385, 20), word("A125", 20, 50), word("1", 120, 50), word("ARIZALILAR", 350, 50)]
    row, column = table.select(**SELECTION)
    assert column == 2
    assert locate_cell(words, table, row, column, reference_point=(30, 55)).point[0] >= 350
