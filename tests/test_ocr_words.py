"""Positioned OCR must preserve screen coordinates, never estimate missing boxes."""

import platform
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image, ImageDraw, ImageFont

from rpa_orkestrai.desktop import ocr


def mac_rect(x, y, width, height):
    bounds = SimpleNamespace(origin=SimpleNamespace(x=x, y=y),
                             size=SimpleNamespace(width=width, height=height))
    return SimpleNamespace(boundingBox=lambda: bounds)


def mac_candidate(text, rectangles):
    candidate = Mock()
    candidate.string.return_value = text
    candidate.confidence.return_value = 0.97
    candidate.boundingBoxForRange_error_.side_effect = rectangles
    return candidate


def test_mac_word_boxes_use_utf16_ranges_and_top_left_pixels(monkeypatch):
    image = Image.new("RGB", (1000, 400))
    candidate = mac_candidate("🔎 İade Sonrası", [
        (None, "No word bounds"),
        (mac_rect(0.2, 0.7, 0.1, 0.1), None),
        (mac_rect(0.35, 0.7, 0.2, 0.1), None),
    ])
    monkeypatch.setattr(ocr, "_mac_observations", lambda *_: [
        SimpleNamespace(topCandidates_=lambda _: [candidate]),
    ])
    words = ocr._mac_words(image, "tur")
    assert [(word.text, word.x, word.width) for word in words] == [
        ("İade", 200, 100), ("Sonrası", 350, 200),
    ]
    assert all(word.y == pytest.approx(80) and word.height == pytest.approx(40) for word in words)
    assert candidate.boundingBoxForRange_error_.call_args_list == [
        (((0, 2), None),), (((3, 4), None),), (((8, 7), None),),
    ]
    with pytest.raises(FrozenInstanceError):
        words[0].x = 0


@pytest.mark.parametrize("bounds", [
    (float("nan"), 0.7, 0.1, 0.1), (0.2, float("inf"), 0.1, 0.1),
    (0.2, 0.7, -0.1, 0.1), (0.2, 0.7, 0, 0.1),
    (-0.1, 0.7, 0.1, 0.1), (0.9, 0.7, 0.2, 0.1),
    (0.2, 0.95, 0.1, 0.1), (0.2, -0.1, 0.1, 0.1),
])
def test_mac_rejects_malformed_word_bounds(monkeypatch, bounds):
    candidate = mac_candidate("Value", [(mac_rect(*bounds), None)])
    monkeypatch.setattr(ocr, "_mac_observations", lambda *_: [
        SimpleNamespace(topCandidates_=lambda _: [candidate]),
    ])
    assert ocr._mac_words(Image.new("RGB", (1000, 400)), "eng") == []


def test_roundoff_tolerance_does_not_create_negative_box():
    assert ocr._word("edge", 100 + 1e-7, 10, 1e-7, 10, 1, (100, 100)) is None


def test_mac_does_not_replace_failed_word_bounds_with_line_bounds(monkeypatch):
    candidate = mac_candidate("Missing Failed", [(None, None), AttributeError("unavailable")])
    observation = Mock()
    observation.topCandidates_.return_value = [candidate]
    monkeypatch.setattr(ocr, "_mac_observations", lambda *_: [observation])
    assert ocr._mac_words(Image.new("RGB", (1000, 400)), "eng") == []
    observation.boundingBox.assert_not_called()


def test_vocabulary_is_recognition_hint_not_text_replacement(monkeypatch):
    candidate = mac_candidate("lade", [(mac_rect(0.2, 0.7, 0.1, 0.1), None)])
    recognize = Mock(return_value=[SimpleNamespace(topCandidates_=lambda _: [candidate])])
    monkeypatch.setattr(ocr, "_mac_observations", recognize)
    monkeypatch.setattr(ocr.platform, "system", lambda: "Darwin")
    image = Image.new("RGB", (1000, 400))
    words = ocr.read_words(image, engine="system", vocabulary=("İade", "Sonrası"))
    recognize.assert_called_once_with(image, "tur+eng", ("İade", "Sonrası"))
    assert [word.text for word in words] == ["lade"]


def windows_result(*, angle=0, box=(10, 20, 40, 10)):
    word = SimpleNamespace(text="Amount", bounding_rect=SimpleNamespace(
        x=box[0], y=box[1], width=box[2], height=box[3],
    ))
    return SimpleNamespace(text_angle=angle, lines=[SimpleNamespace(words=[word])])


def test_windows_undoes_resizing_separately_per_axis(monkeypatch):
    monkeypatch.setattr(ocr, "_windows_result", lambda *_: (windows_result(), (100, 60)))
    words = ocr._windows_words(Image.new("RGB", (1003, 607)), "eng")
    assert len(words) == 1
    word = words[0]
    assert (word.x, word.y, word.width, word.height) == pytest.approx((100.3, 607 / 3, 401.2, 607 / 6))
    assert word.confidence == 1


def test_windows_rotates_deskewed_box_around_image_center(monkeypatch):
    result = windows_result(angle=90, box=(20, 40, 10, 20))
    monkeypatch.setattr(ocr, "_windows_result", lambda *_: (result, (100, 100)))
    words = ocr._windows_words(Image.new("RGB", (100, 100)), "eng")
    assert len(words) == 1
    assert (words[0].x, words[0].y, words[0].width, words[0].height) == pytest.approx((40, 20, 20, 10))


@pytest.mark.parametrize("box", [(-1, 20, 40, 10), (10, 20, 0, 10),
                                  (10, 20, -5, 10), (10, 20, 40, -10),
                                  (10, 20, float("nan"), 10), (90, 20, 40, 10)])
def test_windows_rejects_invalid_boxes(monkeypatch, box):
    monkeypatch.setattr(ocr, "_windows_result", lambda *_: (windows_result(box=box), (100, 100)))
    assert ocr._windows_words(Image.new("RGB", (100, 100)), "eng") == []


def test_windows_rejects_nonfinite_angle(monkeypatch):
    monkeypatch.setattr(ocr, "_windows_result", lambda *_: (windows_result(angle=float("nan")), (100, 100)))
    with pytest.raises(ocr.OcrUnavailable, match="yönünü"):
        ocr._windows_words(Image.new("RGB", (100, 100)), "eng")


def test_tesseract_word_data_restores_command_and_preprocessed_scale(monkeypatch):
    import pytesseract

    before = pytesseract.pytesseract.tesseract_cmd
    requested = []

    def data(image, **kwargs):
        requested.append((image.shape, kwargs, pytesseract.pytesseract.tesseract_cmd))
        return {"level": [4, 5, 5, 5], "text": ["whole line", "Amount", "Value", "Invalid"],
                "left": [0, 20, 100, -2], "top": [0, 40, 40, 40], "width": [200, 60, 80, 40],
                "height": [20, 20, 20, 20], "conf": [-1, 98.5, -1, 99]}

    monkeypatch.setattr(pytesseract, "image_to_data", data)
    words = ocr.read_words(Image.new("RGB", (100, 80)), language="eng", timeout=3,
                           tesseract_cmd="~/bin/tesseract", engine="tesseract")
    assert words == [ocr.OcrWord("Amount", 10, 20, 30, 10, 0.985)]
    assert requested == [((160, 200), {"lang": "eng", "config": "--psm 11",
                                      "output_type": pytesseract.Output.DICT, "timeout": 3},
                          str(Path("~/bin/tesseract").expanduser()))]
    assert pytesseract.pytesseract.tesseract_cmd == before


def test_tesseract_timeout_restores_command(monkeypatch):
    import pytesseract

    before = pytesseract.pytesseract.tesseract_cmd
    monkeypatch.setattr(pytesseract, "image_to_data", Mock(side_effect=RuntimeError("timeout")))
    with pytest.raises(ocr.OcrUnavailable):
        ocr.read_words(Image.new("RGB", (20, 20)), tesseract_cmd="custom", engine="tesseract")
    assert pytesseract.pytesseract.tesseract_cmd == before


def test_auto_uses_fallback_but_system_reports_unavailable(monkeypatch):
    monkeypatch.setattr(ocr.platform, "system", lambda: "Windows")
    monkeypatch.setattr(ocr, "_windows_words", Mock(side_effect=ocr.OcrUnavailable("missing")))
    fallback = Mock(return_value=[ocr.OcrWord("Value", 2, 3, 4, 5, 0.95)])
    monkeypatch.setattr(ocr, "_tesseract_words", fallback)
    image = Image.new("RGB", (100, 100))
    assert ocr.read_words(image) == fallback.return_value
    with pytest.raises(ocr.OcrUnavailable, match="missing"):
        ocr.read_words(image, engine="system")
    assert fallback.call_count == 1


@pytest.mark.parametrize("kwargs", [{"engine": "unknown"}, {"timeout": 0}, {"timeout": float("inf")},
                                    {"engine": "tesseract", "language": "eng --inject"}])
def test_bad_options_fail_before_ocr(kwargs):
    with pytest.raises(ValueError):
        ocr.read_words(Image.new("RGB", (100, 100)), **kwargs)


@pytest.mark.skipif(platform.system() not in {"Darwin", "Windows"}, reason="Native system OCR")
@pytest.mark.parametrize("column_x", [180, 430])
def test_native_word_positions_follow_moved_column_from_worker(column_x):
    """Run on both platform CI jobs; verifies coordinates, not just recognized text."""
    if platform.system() == "Darwin":
        font_path = "/System/Library/Fonts/Supplemental/Arial.ttf"
    else:
        font_path = "arial.ttf"
    font = ImageFont.truetype(font_path, 32)
    image = Image.new("RGB", (900, 240), "white")
    draw = ImageDraw.Draw(image)
    draw.text((20, 24), "Code", fill="black", font=font)
    draw.text((20, 110), "A123", fill="black", font=font)
    draw.text((column_x, 24), "Amount", fill="black", font=font)
    draw.text((column_x, 110), "42.50", fill="black", font=font)
    with ThreadPoolExecutor(max_workers=1) as pool:
        words = pool.submit(ocr.read_words, image, engine="system", language="eng").result(timeout=45)
    header = [word for word in words if word.text.lower() == "amount"]
    assert len(header) == 1, words
    word = header[0]
    assert column_x - 5 <= word.x <= column_x + 12
    assert 20 <= word.y <= 45
    assert 80 <= word.width <= 140
    assert 15 <= word.height <= 42
    values = [word for word in words if word.text == "42.50"]
    assert len(values) == 1, words
    assert values[0].x == pytest.approx(column_x, abs=12)
    assert 105 <= values[0].y <= 132
