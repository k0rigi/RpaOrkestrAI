"""Moving columns must move the write target; ambiguity must never cause input."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from rpa_orkestrai.actions.windows import table_operation, write_table
from rpa_orkestrai.desktop.elements import ElementInfo
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


@pytest.mark.parametrize("text", ["a", "A\tB", "A\tB\n1", "A\tB\n1\t2\t3"])
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
    service = WindowService(backend=backend, elements=SimpleNamespace(focused_editor=Mock(return_value=None)))
    service.cancel.wait = Mock(return_value=False)
    desktop = Mock()
    desktop.size.return_value = (1920, 1080)
    desktop.screenshot.return_value = Image.new("RGB", (900, 500), "white")
    state = {"clipboard": "previous clipboard", "editor": False, "value": "ARIZALILAR", "copied": 0,
             "editor_opens": True, "activation": "double_click", "after_write": None, "layout": 200, "ocr_calls": 0}
    monkeypatch.setattr(pyperclip, "paste", lambda: state["clipboard"])
    monkeypatch.setattr(pyperclip, "copy", lambda v: state.__setitem__("clipboard", v))

    def current_table():
        return state.get("prefix", "") + TEXT.replace("A125\tARIZALILAR", "A125\t" + state["value"])

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


@pytest.mark.parametrize("copy_shape", [None, (2, 3)])
def test_selected_header_after_empty_export_row_writes_first_record(runtime, copy_shape):
    service, window, desktop, state, options = runtime
    state["prefix"] = "\t\t\n"
    result = screen_table_cell(service, window.result(), desktop, value="YENI", header_row=2,
                               edit_mode="auto", copy_shape=copy_shape, **options)
    assert result == {"row": 1, "column": 2, "value": "YENI"}
    desktop.paste.assert_called_once_with("YENI")
    assert state["clipboard"] == "previous clipboard"


def test_changed_export_prefix_is_not_ignored_during_write_verification(runtime):
    service, window, desktop, state, options = runtime
    state["prefix"] = "\t\t\n"
    state["after_write"] = lambda: state.__setitem__("prefix", "CHANGED\t\t\n")
    with pytest.raises(WindowError):
        screen_table_cell(service, window.result(), desktop, value="YENI", header_row=2, **options)
    desktop.paste.assert_called_once_with("YENI")


@pytest.mark.parametrize("failure", [None, "no_response", "lost_focus"])
def test_slow_clipboard_retries_only_read_with_focus_guard(runtime, monkeypatch, failure):
    service, window, desktop, state, options = runtime
    clock, copies = [0.0], []
    original = desktop.hotkey.side_effect

    def hotkey(*keys):
        if keys == ("mod", "c"):
            copies.append(keys)
            if len(copies) == 1 or failure == "no_response":
                return
        original(*keys)

    def wait(seconds):
        clock[0] += seconds
        if copies and failure == "lost_focus":
            service.backend.is_active.return_value = False
        return False

    monkeypatch.setattr("rpa_orkestrai.desktop.screen_tables.time",
                        SimpleNamespace(monotonic=lambda: clock[0], monotonic_ns=lambda: round(clock[0] * 1e9)))
    desktop.hotkey.side_effect = hotkey
    service.cancel.wait.side_effect = wait
    if failure:
        with pytest.raises(WindowError, match="kopyalanamadı" if failure == "no_response" else "odağı"):
            screen_table_cell(service, window.result(), desktop, value="YENI", **options)
        desktop.paste.assert_not_called()
        assert len(copies) == (3 if failure == "no_response" else 1)
        assert desktop.click.call_count == 1
    else:
        assert screen_table_cell(service, window.result(), desktop, value="YENI", **options)["value"] == "YENI"
        assert len(copies) == 5
        desktop.paste.assert_called_once_with("YENI")
    assert state["clipboard"] == "previous clipboard"


def test_show_target_copies_table_without_editing(runtime):
    service, window, desktop, state, options = runtime
    point = screen_table_cell(service, window.result(), desktop, **options)
    assert point[0] >= window.x + 200
    desktop.paste.assert_not_called()
    assert not any(c.kwargs["clicks"] == 2 for c in desktop.click.call_args_list)
    assert state["clipboard"] == "previous clipboard"


@pytest.mark.parametrize("point", [(35, 56), (235, 56), (35, 101)])
def test_point_identifies_whole_table_without_a_rectangle(runtime, point):
    service, window, desktop, state, options = runtime
    options.pop("region")
    options["targeting"] = dict(target_mode="coordinates", x=point[0], y=point[1])
    assert screen_table_cell(service, window.result(), desktop, value="YENI", **options)["column"] == 2
    assert desktop.click.call_args_list[0].args == (window.x + point[0], window.y + point[1])
    desktop.paste.assert_called_once_with("YENI")
    assert state["clipboard"] == "previous clipboard"


def test_point_inspection_reads_all_structure_without_editing(runtime):
    service, window, desktop, state, options = runtime
    table = screen_table_cell(service, window.result(), desktop, selection={}, inspect=True,
                              targeting=dict(target_mode="coordinates", x=35, y=56))
    assert table == TABLE
    assert table.names == ["Kod", "İade Sonrası", "Miktar"]
    desktop.paste.assert_not_called()
    assert desktop.click.call_count == 1 and state["clipboard"] == "previous clipboard"


@pytest.mark.parametrize("problem", [None, "existing", "outside", "wrong_value", "unavailable", "stays_open"])
def test_point_click_opening_cell_editor_returns_to_grid_without_cancelling_prior_input(runtime, problem):
    service, window, desktop, state, options = runtime
    original_click, original_press = desktop.click.side_effect, desktop.press.side_effect
    editor = ElementInfo("Edit", "", "", "", 295, 125, 160, 28, value=state["value"])
    if problem == "outside":
        editor = replace(editor, x=700)
    elif problem == "wrong_value":
        editor = replace(editor, value="different")

    def click(*args, **kwargs):
        original_click(*args, **kwargs)
        if desktop.click.call_count == 1:
            state["editor"] = True

    def focused(window):
        return editor if problem != "unavailable" and (state["editor"] or problem == "existing") else None

    desktop.click.side_effect = click
    service.elements.focused_editor.side_effect = focused
    desktop.press.side_effect = lambda key: None if key == "esc" and problem == "stays_open" else original_press(key)
    options = dict(selection=SELECTION, targeting=dict(x=235, y=56))
    if problem:
        with pytest.raises(WindowError):
            screen_table_cell(service, window.result(), desktop, value="YENI", **options)
        desktop.paste.assert_not_called()
        if problem != "stays_open":
            desktop.press.assert_not_called()
    else:
        assert screen_table_cell(service, window.result(), desktop, value="YENI", **options)["value"] == "YENI"
        desktop.paste.assert_called_once_with("YENI")
        assert desktop.press.call_args_list[0].args == ("esc",)
    assert state["clipboard"] == "previous clipboard"


def test_point_does_not_resolve_a_duplicate_table_by_nearness(runtime, monkeypatch):
    service, window, desktop, state, options = runtime
    from rpa_orkestrai.desktop import screen_tables
    original = screen_tables.read_words

    def duplicate(*args, **kwargs):
        words = original(*args, **kwargs)
        return words + [replace(w, y=w.y + 320) for w in words]

    monkeypatch.setattr(screen_tables, "read_words", duplicate)
    with pytest.raises(WindowError, match="birden fazla"):
        screen_table_cell(service, window.result(), desktop, selection=SELECTION, value="YENI",
                          targeting=dict(target_mode="coordinates", x=35, y=56))
    desktop.paste.assert_not_called()


def test_provider_shape_detects_copied_header_without_user_setting(runtime):
    service, window, desktop, state, options = runtime
    options.update(header=False, copy_shape=(2, 3))  # Actual copied text includes titles.
    assert screen_table_cell(service, window.result(), desktop, value="YENI", **options)["row"] == 1
    desktop.paste.assert_called_once_with("YENI")


def test_provider_shape_rejects_partial_clipboard(runtime):
    service, window, desktop, state, options = runtime
    options["copy_shape"] = (20, 3)
    with pytest.raises(WindowError, match="tamamıyla"):
        screen_table_cell(service, window.result(), desktop, value="YENI", **options)
    desktop.paste.assert_not_called()


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


@pytest.fixture
def caret_editor(runtime, monkeypatch):
    from rpa_orkestrai.desktop import screen_tables

    service, window, desktop, state, options = runtime
    original = screen_tables.read_words

    def with_caret(*args, **kwargs):
        words = original(*args, **kwargs)
        if state["editor"]:
            return [replace(w, text=w.text + "|") if w.text == state["value"] else w for w in words]
        return words

    monkeypatch.setattr(screen_tables, "read_words", with_caret)
    editor = ElementInfo("Edit", "", "", "", 295, 125, 160, 28, value="ARIZALILAR")
    service.elements.focused_editor.return_value = editor
    return runtime, editor, with_caret, original


def test_caret_ocr_error_uses_actual_editor_and_fresh_row_witness(caret_editor):
    (service, window, desktop, state, options), _, _, _ = caret_editor
    result = screen_table_cell(service, window.result(), desktop, value="YENI", **options)
    assert result["value"] == "YENI"
    desktop.paste.assert_called_once_with("YENI")
    assert service.elements.focused_editor.call_count == 2


@pytest.mark.parametrize("changed", [dict(x=475), dict(y=170), dict(value="OTHER"),
                                     dict(x=110, width=345), dict(offscreen=True)])
def test_caret_never_hides_wrong_editor(caret_editor, changed):
    (service, window, desktop, state, options), editor, _, _ = caret_editor
    service.elements.focused_editor.return_value = replace(editor, **changed)
    with pytest.raises(WindowError, match="hücre veya satır değişti"):
        screen_table_cell(service, window.result(), desktop, value="YENI", **options)
    desktop.paste.assert_not_called()


def test_caret_editor_changes_during_witness_check_never_pastes(caret_editor):
    (service, window, desktop, state, options), editor, _, _ = caret_editor
    service.elements.focused_editor.side_effect = [editor, replace(editor, y=170)]
    with pytest.raises(WindowError, match="hücre veya satır değişti"):
        screen_table_cell(service, window.result(), desktop, value="YENI", **options)
    desktop.paste.assert_not_called()


def test_caret_row_witness_moves_never_pastes(caret_editor, monkeypatch):
    (service, window, desktop, state, options), _, caret, _ = caret_editor

    def moved(*args, **kwargs):
        return [replace(w, y=w.y + 50) if state["editor"] and w.text == "A125" else w
                for w in caret(*args, **kwargs)]

    monkeypatch.setattr("rpa_orkestrai.desktop.screen_tables.read_words", moved)
    with pytest.raises(WindowError, match="hücre veya satır değişti"):
        screen_table_cell(service, window.result(), desktop, value="YENI", **options)
    desktop.paste.assert_not_called()


def test_blinking_caret_without_accessibility_retries_fresh_screenshot(caret_editor, monkeypatch):
    (service, window, desktop, state, options), _, caret, original = caret_editor
    service.elements.focused_editor.return_value = None
    screenshots = []

    def blinking(*args, **kwargs):
        if service.elements.focused_editor.call_count > 1:
            assert desktop.screenshot.call_count > screenshots[0]
            return original(*args, **kwargs)
        if state["editor"] and not screenshots:
            screenshots.append(desktop.screenshot.call_count)
        return caret(*args, **kwargs)

    monkeypatch.setattr("rpa_orkestrai.desktop.screen_tables.read_words", blinking)
    assert screen_table_cell(service, window.result(), desktop, value="YENI", **options)["value"] == "YENI"
    desktop.paste.assert_called_once_with("YENI")


def test_permanent_ocr_error_without_editor_never_pastes(caret_editor):
    (service, window, desktop, state, options), _, _, _ = caret_editor
    service.elements.focused_editor.return_value = None
    with pytest.raises(WindowError):
        screen_table_cell(service, window.result(), desktop, value="YENI", **options)
    desktop.paste.assert_not_called()
    assert service.elements.focused_editor.call_count == 3


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


@pytest.mark.parametrize('header,raw', [
    (False, 'A125\tARIZALILAR\t1\nA126\tARIZALILAR\t2'),
    (True, 'Kod\t\tAdet\nA125\tARIZALILAR\t1\nA126\tARIZALILAR\t2'),
])
@pytest.mark.parametrize('selector', ['sutun_2', 'sütun_2', '2'])
def test_read_and_write_share_aliases_and_header_flag(header, raw, selector):
    from rpa_orkestrai.actions.windows import table_column, table_of

    names, rows = table_of(raw, header=header)
    table = TableText.parse(raw, header=header)
    assert table.names == names
    assert [list(row) for row in table.rows] == rows
    assert table.column(selector) == table_column(names, selector) == 1
    assert table.select(**{**SELECTION, 'column': selector}) == (0, 1)


def test_single_headerless_row_and_literal_alias_name():
    table = TableText.parse('A125\tARIZALILAR', header=False)
    assert table.rows == (('A125', 'ARIZALILAR'),)
    assert table.column('sutun_2') == 1
    # An actual copied name takes priority over an automatically interpreted alias.
    assert TableText.parse('sutun_2\tStatus\nA125\tOLD').column('sutun_2') == 0
    assert TableText.parse('\t\nA125\tOLD').names == ['sutun_1', 'sutun_2']


@pytest.mark.parametrize('column_x', [120, 250, 500])
def test_headerless_values_follow_resized_columns_with_unreadable_titles(column_x):
    from rpa_orkestrai.desktop.screen_tables import locate_by_values

    table = TableText(('', '', ''), TABLE.rows, False)
    words = [w for w in grid_words(column_x) if w.y != 20]
    assert locate_by_values(words, table, 0, 1).point == (column_x + 35, 56)
    assert locate_by_values(words, table, 1, 1).point == (column_x + 35, 101)


def test_blank_checkbox_columns_do_not_change_copied_column_number():
    from rpa_orkestrai.desktop.screen_tables import locate_by_values

    table = TableText.parse('A125\t\t1\tARIZALILAR\nA126\t\t1\tARIZALILAR', header=False)
    words = [word('A125', 20, 50), word('ARIZALILAR', 320, 50),
             word('A126', 20, 90), word('ARIZALILAR', 320, 90)]
    row, col = table.select(**{**SELECTION, 'column': 'sutun_4', 'row_mode': 'match',
                              'match_column': 'sutun_1', 'match_value': 'A126'})
    assert (row, col) == (1, 3)
    assert locate_by_values(words, table, row, col).point[1] == 96


def test_duplicate_cell_values_on_opposite_sides_of_record_key():
    from rpa_orkestrai.desktop.screen_tables import locate_by_values

    table = TableText.parse('OLD\tA125\tOLD', header=False)
    words = [word('OLD', 20, 50), word('A125', 140, 50), word('OLD', 320, 50)]
    assert locate_by_values(words, table, 0, 0).point[0] < 100
    assert locate_by_values(words, table, 0, 2).point[0] > 300


@pytest.mark.parametrize('raw,words', [
    ('A125\tOLD\tOLD', [word('A125', 20, 50), word('OLD', 140, 50), word('OLD', 320, 50)]),
    ('A125\tOLD\nPrefix A125\tOLD', [word('Prefix', 20, 50), word('A125', 70, 50), word('OLD', 320, 50)]),
    ('A125\tOLD\nA12599\tOLD', [word('A125', 20, 50), word('OLD', 320, 50)]),
    ('A125\tOLD\nA125\tPrefix OLD', [word('A125', 20, 50), word('Prefix', 250, 50), word('OLD', 320, 50)]),
    ('A1\tOLD\tKIRMIZI MAVI\tX\nA2\tOLD\tKIRMIZI\tMAVI',
     [word('A2', 20, 50), word('OLD', 100, 50), word('KIRMIZI', 200, 50), word('MAVI', 265, 50)]),
])
def test_headerless_does_not_guess_ambiguous_columns_or_word_fragments(raw, words):
    from rpa_orkestrai.desktop.screen_tables import locate_by_values

    with pytest.raises(WindowError):
        locate_by_values(words, TableText.parse(raw, header=False), 0, 1)


def test_headerless_runtime_pastes_once_and_reports_exact_read_settings(runtime):
    service, window, desktop, state, options = runtime
    original = desktop.hotkey.side_effect

    def copy_without_header(*keys):
        original(*keys)
        if keys == ('mod', 'c') and not state['editor']:
            state['clipboard'] = state['clipboard'].split('\n', 1)[1]

    desktop.hotkey.side_effect = copy_without_header
    reports = []
    options.update(header=False, report=reports.append,
                   selection={**SELECTION, 'column': 'sutun_2'})
    state['after_write'] = lambda: state.__setitem__('layout', 380)
    assert screen_table_cell(service, window.result(), desktop, value='YENI DURUM', **options) == {
        'row': 1, 'column': 2, 'value': 'YENI DURUM'}
    desktop.paste.assert_called_once_with('YENI DURUM')
    assert reports == [{'rows': 2, 'columns': ['sutun_1', 'sutun_2', 'sutun_3'], 'row': 1,
                        'column': 2, 'current_value': 'ARIZALILAR', 'header': False}]
    assert state['clipboard'] == 'previous clipboard'


@pytest.mark.parametrize('activation', ['single_click', 'f2', 'double_click'])
def test_auto_editor_activation_verifies_before_one_paste(runtime, activation):
    service, window, desktop, state, options = runtime
    options.update(targeting=dict(x=35, y=56), edit_mode='auto')
    state['activation'] = activation
    original_press = desktop.press.side_effect

    def press(key):
        if key != 'f2' or activation == 'f2':
            original_press(key)

    desktop.press.side_effect = press
    assert screen_table_cell(service, window.result(), desktop, value='YENI', **options)['value'] == 'YENI'
    desktop.paste.assert_called_once_with('YENI')
    doubles = [c for c in desktop.click.call_args_list if c.kwargs['clicks'] == 2]
    assert len(doubles) == int(activation == 'double_click')
    assert state['clipboard'] == 'previous clipboard'


def test_auto_editor_never_continues_after_unexpected_cell_text(runtime):
    service, window, desktop, state, options = runtime
    original = desktop.hotkey.side_effect

    def hotkey(*keys):
        original(*keys)
        if keys == ('mod', 'c') and state['copied'] == 3:
            state['clipboard'] = 'DIFFERENT CELL'

    desktop.hotkey.side_effect = hotkey
    with pytest.raises(WindowError, match='seçim veya tablo değişti'):
        screen_table_cell(service, window.result(), desktop, value='YENI', edit_mode='auto', **options)
    desktop.paste.assert_not_called()
    desktop.press.assert_not_called()
    assert not any(c.kwargs['clicks'] == 2 for c in desktop.click.call_args_list)


def test_written_long_variable_does_not_need_to_fit_onscreen(runtime):
    service, window, desktop, state, options = runtime
    state['after_write'] = lambda: state.__setitem__('layout', 890)
    value = ('Değişkenden gelen uzun açıklama ' * 8).strip()
    # Intentionally no longer visible to OCR, but copied intact by the table.
    assert screen_table_cell(service, window.result(), desktop, value=value, **options)['value'] == value
    desktop.paste.assert_called_once_with(value)


def test_point_flow_resolves_variable_then_writes_and_reports_all_phases(runtime, tmp_path, monkeypatch):
    import threading

    from rpa_orkestrai.config import Settings
    from rpa_orkestrai.engine import Executor
    from rpa_orkestrai.models import Run, Step, Workflow
    from rpa_orkestrai.storage import Store

    service, window, desktop, state, _ = runtime
    monkeypatch.setattr('rpa_orkestrai.desktop.tables.native_backend',
                        lambda: SimpleNamespace(tables=lambda *args: []))
    state['activation'] = 'single_click'
    workflow = Workflow(name='Değişkeni tabloya yaz', steps=[Step(action='window.write_table', params={
        'window': '${target}', 'write_method': 'point', 'target_mode': 'coordinates', 'x': 35, 'y': 56,
        'row': 1, 'column': 'sutun_2', 'value': '${row.deger}', 'output': 'written'})])
    run = Run(workflow_id=workflow.id, workflow_name=workflow.name, department=workflow.department)
    executor = Executor(Settings(tmp_path, dotenv=False), Store(tmp_path), run, threading.Event(), lambda: None,
                        variables={'target': window.result(), 'row': {'deger': 'İŞLENDİ'}})
    executor._windows, executor._desktop = service, desktop
    log = Mock(wraps=executor.log)
    executor.log = log
    executor.execute(workflow)
    assert executor.variables['written'] == {'row': 1, 'column': 2, 'value': 'İŞLENDİ'}
    desktop.paste.assert_called_once_with('İŞLENDİ')
    messages = [entry.args[0] for entry in log.call_args_list]
    assert any('Hedef bulundu' in text for text in messages)
    assert any('Tabloya yazma doğrulandı' in text for text in messages)


def test_auto_mode_exhausts_read_only_checks_without_paste(runtime):
    service, window, desktop, state, options = runtime
    state['editor_opens'] = False
    with pytest.raises(WindowError, match='uygulama hücreyi düzenlemeye açmadı'):
        screen_table_cell(service, window.result(), desktop, value='YENI', edit_mode='auto', **options)
    desktop.paste.assert_not_called()
    assert state['value'] == 'ARIZALILAR'


def test_missing_table_selection_explains_button_instead_of_hidden_coordinates():
    from rpa_orkestrai.engine import validate_workflow
    from rpa_orkestrai.models import Step, Workflow

    flow = Workflow(name='Tablo seçilmedi', steps=[Step(action='window.write_table', params={
        'write_method': 'point', 'target_mode': 'coordinates', 'column': 'sutun_2', 'value': 'YENI'})])
    with pytest.raises(WorkflowError, match='Tabloyu seç düğmesi'):
        validate_workflow(flow)


@pytest.mark.parametrize('settles', [True, False])
def test_post_write_focus_transition_retries_only_editor_read(runtime, settles):
    service, window, desktop, state, options = runtime
    options['targeting'] = dict(x=35, y=56)
    reads = []

    def editor():
        if state['value'] == 'YENI':
            reads.append(True)
            if not settles or len(reads) == 1:
                raise WindowError('Düzenleme alanının odağı değişti; yazılmadı.')
        return None

    service.elements.focused_editor.side_effect = lambda window: editor()
    if settles:
        assert screen_table_cell(service, window.result(), desktop, value='YENI', **options)['value'] == 'YENI'
        assert len(reads) == 2
    else:
        with pytest.raises(WindowError, match='yazma denendi'):
            screen_table_cell(service, window.result(), desktop, value='YENI', **options)
        assert len(reads) == 3
    desktop.paste.assert_called_once_with('YENI')
    assert [c.args for c in desktop.press.call_args_list] == [('tab',)]
