"""Real system OCR must locate a table cell as desktop column widths change."""

import platform
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image, ImageDraw, ImageFont

from rpa_orkestrai.desktop.screen_tables import TableText, locate_image, measured_words, table_focus_point
from rpa_orkestrai.desktop.windows import WindowError

pytestmark = pytest.mark.skipif(platform.system() not in {"Darwin", "Windows"},
                                reason="Windows/macOS native OCR integration")


def _failure_diagnostics(image):
    """Only synthetic fixture text is reported; never captures the desktop."""
    details = {"system": platform.system()}
    for preparation in range(3):
        try:
            words = measured_words(image, preparation, vocabulary=("İade Sonrası",),
                                   ocr_options={"engine": "system", "language": "tur+eng"})
            details[f"preparation_{preparation}"] = [
                (word.text, round(word.x, 3), round(word.y, 3), round(word.width, 3),
                 round(word.height, 3), word.confidence) for word in words
            ]
        except Exception as exc:
            details[f"preparation_{preparation}"] = f"{type(exc).__name__}: {exc}"
    if platform.system() == "Windows":
        try:
            from winrt.windows.globalization import Language
            from winrt.windows.media.ocr import OcrEngine

            details["available_languages"] = [language.language_tag
                                               for language in OcrEngine.available_recognizer_languages]
            supported = {tag: OcrEngine.is_language_supported(Language(tag)) for tag in ("tr", "en")}
            details["requested_languages_supported"] = supported
            requested = next((tag for tag, available in supported.items() if available), None)
            engine = (OcrEngine.try_create_from_language(Language(requested)) if requested is not None
                      else OcrEngine.try_create_from_user_profile_languages())
            details["chosen_recognizer_language"] = engine.recognizer_language.language_tag if engine else None
        except Exception as exc:
            details["language_diagnostics_error"] = f"{type(exc).__name__}: {exc}"
    return details


def table_image(*, target_x, font_size, row_count, selected=False):
    path = "/System/Library/Fonts/Supplemental/Arial.ttf" if platform.system() == "Darwin" else "arial.ttf"
    font = ImageFont.truetype(path, font_size)
    image = Image.new("RGB", (900, 210), "#f7f7f7")
    draw = ImageDraw.Draw(image)
    columns = [38, 140, target_x, target_x + 145]
    header_y, first_row_y, row_height = 45, 75, 28
    titles = ("Kod", "Açıklama", "İade Sonrası", "Miktar")
    rows = [("A125", "Motor", "ARIZALILAR", "1")]
    if row_count == 2:
        rows.append(("A126", "Motor", "ARIZALILAR", "1"))
    right = columns[-1] + 105
    draw.rectangle((26, header_y - 5, right, first_row_y - 4), fill="#e0e0e0")
    for x, title in zip(columns, titles):
        draw.text((x, header_y), title, font=font, fill="#202020")
    for index, row in enumerate(rows):
        y = first_row_y + index * row_height
        background = "#0078d7" if selected else "white" if index == 0 else "#f0f0f0"
        draw.rectangle((26, y - 3, right, y + row_height - 4), fill=background)
        for x, value in zip(columns, row):
            draw.text((x, y), value, font=font, fill="white" if selected else "#202020")
    for x in [26, 130, target_x - 10, columns[-1] - 10, right]:
        draw.line((x, header_y - 5, x, first_row_y + row_count * row_height - 4), fill="#c7c7c7")
    for y in [header_y - 5, first_row_y - 4, first_row_y + row_count * row_height - 4]:
        draw.line((26, y, right, y), fill="#c7c7c7")
    text = "\n".join("\t".join(row) for row in [titles, *rows])
    target_bounds = [draw.textbbox((target_x, first_row_y + index * row_height), row[2], font=font)
                     for index, row in enumerate(rows)]
    first_row_bounds = [draw.textbbox((x, first_row_y), value, font=font)
                        for x, value in zip(columns, rows[0])]
    return image, TableText.parse(text), target_bounds, first_row_bounds


@pytest.mark.parametrize("font_size", [12, 14, 16])
@pytest.mark.parametrize("target_x", [330, 490])
@pytest.mark.parametrize("row_count", [1, 2], ids=["one-record", "duplicate-values"])
@pytest.mark.parametrize("selected", [False, True], ids=["normal", "selected-blue"])
def test_native_ocr_addresses_turkish_header_despite_column_resize(font_size, target_x, row_count, selected):
    image, table, target_bounds, first_row_bounds = table_image(
        target_x=target_x, font_size=font_size, row_count=row_count, selected=selected,
    )
    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            reference_point = pool.submit(table_focus_point, image, "İade Sonrası",
                                          ocr_options={"engine": "system", "language": "tur+eng"}).result(timeout=45)
        except WindowError as exc:
            details = pool.submit(_failure_diagnostics, image).result(timeout=60)
            pytest.fail(f"table_focus_point failed: {exc}\nSynthetic OCR diagnostics: {details!r}", pytrace=False)
    focus_x, focus_y = reference_point
    assert any(left <= focus_x <= right and top <= focus_y <= bottom
               for left, top, right, bottom in first_row_bounds), (reference_point, first_row_bounds)
    for row, (left, top, right, bottom) in enumerate(target_bounds):
        # Exercise the production preprocessing, Turkish heading matcher,
        # confidence floor and unique row witness from a workflow-style thread.
        with ThreadPoolExecutor(max_workers=1) as pool:
            location = pool.submit(locate_image, image, table, row, 2, reference_point=reference_point,
                                   ocr_options={"engine": "system", "language": "tur+eng"}).result(timeout=45)
        x, y = location.point
        assert left <= x <= right, (location, target_bounds)
        assert top - 2 <= y <= bottom + 2, (location, target_bounds)
        assert location.witness_text.center[1] == pytest.approx(y, abs=font_size / 2)
        # Native OCR may include the selection edge in its word box. The click
        # horizontal click above must still lie inside the actual drawn text.
        assert location.text.x == pytest.approx(target_x, abs=font_size / 2)
        assert location.text.width > 40
