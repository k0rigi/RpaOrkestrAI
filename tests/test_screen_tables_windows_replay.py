"""Replay every observed Windows OCR failure without a native Windows runtime.

The fixture preserves the three preparation results, including incorrect text,
from the 24 synthetic table cases on an English-only Windows CI runner.
"""

import json
from pathlib import Path

import pytest
from PIL import Image

from rpa_orkestrai.desktop import screen_tables
from rpa_orkestrai.desktop.ocr import OcrWord
from rpa_orkestrai.desktop.windows import WindowError

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "windows_table_ocr.json").read_text(encoding="utf-8"))
CASES = FIXTURE["cases"]


def table_for(case):
    rows = ["A125\tMotor\tARIZALILAR\t1"]
    if case["row_count"] == 2:
        rows.append("A126\tMotor\tARIZALILAR\t1")
    return screen_tables.TableText.parse("Kod\tAçıklama\tİade Sonrası\tMiktar\n" + "\n".join(rows))


def contains(word, point):
    return word.x <= point[0] <= word.x + word.width and word.y <= point[1] <= word.y + word.height


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_observed_windows_english_ocr_locates_each_record(monkeypatch, case):
    preparations = [[OcrWord(*word) for word in words] for words in case["preparations"]]
    calls = []

    def measured(image, preparation, **kwargs):
        calls.append(preparation)
        return preparations[preparation]

    monkeypatch.setattr(screen_tables, "measured_words", measured)
    image = Image.new("RGB", (900, 210))
    table = table_for(case)
    focus = screen_tables.table_focus_point(image, "İade Sonrası")
    observed = [word for words in preparations for word in words]
    first_row_words = [word for word in observed if word.text in table.rows[0] and 70 < word.y < 100]
    assert any(contains(word, focus) for word in first_row_words), (case["id"], focus)
    for row in range(case["row_count"]):
        location = screen_tables.locate_image(image, table, row, 2, reference_point=focus)
        expected_values = [word for word in observed if word.text == "ARIZALILAR"
                           and 70 + row * 28 < word.y < 100 + row * 28]
        assert any(contains(word, location.point) for word in expected_values), (case["id"], row, location)
        assert case["target_x"] - 2 <= location.text.x <= case["target_x"] + 5
        assert location.text.width > 40
        if case["row_count"] == 2:
            # Both target values/descriptions/quantities are identical. Only the
            # actual code text can distinguish the two records in this fixture.
            expected_codes = [word for word in observed if word.text == table.rows[row][0]]
            assert any(contains(word, location.witness_text.center) for word in expected_codes)
    assert calls and all(preparation in range(3) for preparation in calls)


def test_replay_keeps_observed_malformed_cell_value_unmatched(monkeypatch):
    case = CASES[0]
    words = [OcrWord(*word) for word in case["preparations"][1]]
    assert any(word.text == "ARIZA-II-AR" for word in words)
    assert not any(word.text == "ARIZALILAR" for word in words)
    monkeypatch.setattr(screen_tables, "measured_words", lambda *args, **kwargs: words)
    image = Image.new("RGB", (900, 210))
    focus = screen_tables.table_focus_point(image, "İade Sonrası")
    with pytest.raises(WindowError):
        screen_tables.locate_image(image, table_for(case), 0, 2, reference_point=focus)


def test_windows_replay_covers_all_original_native_fixture_variations():
    assert FIXTURE["recognizer_language"] == "en-US" and FIXTURE["turkish_ocr_installed"] is False
    actual = {(case["font_size"], case["target_x"], case["row_count"], case["selected"]) for case in CASES}
    assert actual == {(font, x, count, selected) for font in (12, 14, 16) for x in (330, 490)
                      for count in (1, 2) for selected in (False, True)}
    assert len(CASES) == 24 and all(len(case["preparations"]) == 3 for case in CASES)
