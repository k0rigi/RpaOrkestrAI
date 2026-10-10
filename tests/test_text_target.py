"""Metni bul, tıkla ve yaz: the point comes from fresh OCR text; doubt never clicks."""
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from PIL import Image

from rpa_orkestrai.actions.windows import text_write as handler
from rpa_orkestrai.desktop.ocr import OcrWord
from rpa_orkestrai.desktop.text_target import text_point, text_write
from rpa_orkestrai.desktop.windows import WindowError, WindowInfo
from rpa_orkestrai.errors import WorkflowError


def word(text, x, y):
    return OcrWord(text, x, y, len(text) * 7, 12, .99)


GRID = [word("Kod", 20, 20), word("İade", 200, 20), word("Sonrası", 235, 20), word("Miktar", 380, 20),
        word("A125", 20, 50), word("1", 380, 50), word("A126", 20, 80), word("ARIZALILAR", 200, 80),
        word("2", 380, 80)]


def test_text_mode_clicks_the_centre_of_the_one_matching_phrase():
    assert text_point(GRID, mode="text", text="a126") == (34, 86)
    assert text_point(GRID, mode="text", text="İADE SONRASI") == (242, 26)
    assert text_point(GRID, mode="text", text="B999") is None


@pytest.mark.parametrize("wanted", ["İad", "iad", "IAD", "ade"])
def test_part_of_a_word_is_enough_and_clicks_that_word_centre(wanted):
    assert text_point(GRID, mode="text", text=wanted) == (214, 26)  # Centre of the word "İade".


def test_part_spanning_words_clicks_the_centre_of_both():
    assert text_point(GRID, mode="text", text="ade Son") == (242, 26)
    assert text_point(GRID, mode="text", text="125") == (34, 56)


def test_part_in_two_places_is_ambiguous_and_never_joins_distant_cells():
    with pytest.raises(WindowError, match="2 yerde"):
        text_point(GRID, mode="text", text="A12")  # A125 and A126.
    assert text_point(GRID, mode="text", text="Kod İade") is None  # Separate cells on one line.


def test_cross_accepts_truncated_heading_and_part_of_row_value():
    x, y = text_point(GRID, mode="cross", column_text="İade Sonr", row_text="126")
    assert 200 <= x <= 284 and y == 86


@pytest.mark.parametrize("row_text,y", [("A125", 56), ("A126", 86)])
def test_cross_mode_is_heading_column_on_row_line_even_for_an_empty_cell(row_text, y):
    x, found_y = text_point(GRID, mode="cross", column_text="İade Sonrası", row_text=row_text)
    assert 200 <= x <= 284 and found_y == y


def test_heading_tolerates_ocr_dotless_i_but_row_value_is_exact():
    words = [word("Sonrasl", 235, 20) if w.text == "Sonrası" else w for w in GRID]
    assert text_point(words, mode="cross", column_text="İade Sonrası", row_text="A125")[1] == 56
    assert text_point(words, mode="cross", column_text="İade Sonrası", row_text="Al25") is None


@pytest.mark.parametrize("problem", ["repeated", "row_above", "same_column"])
def test_uncertain_point_raises(problem):
    words, row_text = GRID, "A125"
    if problem == "repeated":
        words = GRID + [word("A125", 20, 110)]
    elif problem == "row_above":
        words = GRID + [word("X9", 20, 2)]
        row_text = "X9"
    else:
        row_text = "ARIZALILAR"
    with pytest.raises(WindowError):
        text_point(words, mode="cross", column_text="İade Sonrası", row_text=row_text)


@pytest.fixture
def runtime(monkeypatch):
    window = WindowInfo(11, 42, "Application", "Records", 100, 80, 900, 500)
    service = SimpleNamespace(focus=Mock(return_value=window), _guard=Mock(return_value=window),
                              _capture_window=Mock(return_value=(window, Image.new("RGB", (900, 500)))),
                              _point_in_window=lambda w, x, y, d: (w.x + round(x), w.y + round(y)))
    words = {"value": GRID}
    monkeypatch.setattr("rpa_orkestrai.desktop.text_target.measured_words",
                        lambda image, preparation, **kw: [w for w in words["value"]
                                                          if w.x + w.width <= image.width
                                                          and w.y + w.height <= image.height])
    return service, window, Mock(), words


def test_write_clicks_measured_point_then_types_and_presses_tab(runtime):
    service, window, desktop, _ = runtime
    result = text_write(service, window.result(), desktop, region=(0, 0, 600, 300), mode="cross",
                        column_text="İade Sonrası", row_text="A125", value="YENI", clicks=2, after="tab")
    point = desktop.click.call_args.args
    assert window.x + 200 <= point[0] <= window.x + 284 and point[1] == window.y + 56
    assert desktop.mock_calls == [call.click(*point, clicks=2, button="left"), call.write("YENI"), call.press("tab")]
    assert result == {"x": point[0], "y": point[1], "value": "YENI"}


def test_clear_selects_and_deletes_before_typing(runtime):
    service, window, desktop, _ = runtime
    text_write(service, window.result(), desktop, mode="text", text="A126", value="Z", clear=True)
    assert [c[0] for c in desktop.mock_calls] == ["click", "hotkey", "press", "write"]
    assert desktop.hotkey.call_args == call("mod", "a")


def test_show_target_returns_point_without_input(runtime):
    service, window, desktop, _ = runtime
    assert text_write(service, window.result(), desktop, mode="text", text="A126") == (window.x + 34, window.y + 86)
    assert desktop.mock_calls == []


@pytest.mark.parametrize("case", ["missing", "repeated", "outside_region", "region_overflow", "bad_value",
                                  "window_changed"])
def test_doubt_never_clicks_or_types(runtime, case):
    service, window, desktop, words = runtime
    options = dict(mode="text", text="A126", value="YENI")
    if case == "missing":
        options["text"] = "B999"
    elif case == "repeated":
        words["value"] = GRID + [word("A126", 500, 80)]
    elif case == "outside_region":
        options["region"] = (0, 0, 150, 60)  # A126 is below this area.
    elif case == "region_overflow":
        options["region"] = (0, 0, 901, 100)
    elif case == "bad_value":
        options["value"] = "A\tB"
    else:
        service._capture_window.return_value = (WindowInfo(12, 42, "Application", "Records", 100, 80, 900, 500),
                                                Image.new("RGB", (900, 500)))
    with pytest.raises(WindowError):
        text_write(service, window.result(), desktop, **options)
    assert desktop.mock_calls == []


def test_handler_validates_before_touching_the_window(monkeypatch):
    write = Mock()
    monkeypatch.setattr("rpa_orkestrai.desktop.text_target.text_write", write)
    ctx = SimpleNamespace(windows=Mock(), desktop=Mock(), config={}, settings=SimpleNamespace(action_timeout=5))
    target = {"found": True, "window_id": 1}
    with pytest.raises(WorkflowError):
        handler(ctx, {"window": target, "position": "text", "text": "", "value": "X"})
    with pytest.raises(WorkflowError):
        handler(ctx, {"window": target, "position": "cross", "column_text": "Miktar", "value": "X"})
    write.assert_not_called()
    handler(ctx, {"window": target, "position": "text", "text": " A125 ", "value": 5, "clicks": "2",
                  "region": [1, 2, 300, 200]})
    assert write.call_args.kwargs | {"ocr_options": None} == {
        "region": (1, 2, 300, 200), "mode": "text", "value": "5", "clicks": 2, "clear": False, "after": "none",
        "ocr_options": None, "text": "A125"}
