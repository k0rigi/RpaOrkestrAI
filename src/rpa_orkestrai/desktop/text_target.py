"""Find a click point from text read inside one window area.

The point is measured on a fresh capture each run: the centre of one OCR text
phrase, or a column heading's horizontal centre on a row text's line. Nothing
is saved as a screen coordinate; missing or repeated text never clicks.
"""
from __future__ import annotations

from .ocr import OcrUnavailable
from .screen_tables import Box, Phrases, measured_words, overlap_x
from .windows import WindowError


def single(phrases, text, label, *, heading=False):
    found = phrases.find(text, heading=heading)
    if len(found) > 1:
        raise WindowError(f"{label} “{text}” alanda {len(found)} yerde bulundu; tıklanmadı. "
                          "Alanı daraltın veya daha ayırt edici bir metin yazın.")
    return found[0] if found else None


def text_point(words, *, mode, text="", column_text="", row_text=""):
    """Return (x, y) inside the area, None if any text is not visible."""
    phrases = Phrases(words)
    if mode == "text":
        box = single(phrases, text, "Aranacak metin")
        return None if box is None else box.center
    # Headings are matched with the OCR i/l aliases; the row value is exact.
    column = single(phrases, column_text, "Sütun metni", heading=True)
    row = single(phrases, row_text, "Satır metni")
    if column is None or row is None:
        return None
    if row.y <= column.bottom:
        raise WindowError("Satır metni sütun metninin altında olmalıdır; tıklanmadı.")
    if overlap_x(column, row) > 0:
        raise WindowError("Satır metni yazılacak sütunun içinde bulundu; satırı başka bir sütundaki "
                          "değerle belirtin. Tıklanmadı.")
    return Box(column.x, row.y, column.width, row.height).center


def locate_text(image, *, mode, text="", column_text="", row_text="", ocr_options=None):
    """Bounded OCR preparations; ambiguity in any of them stops at once."""
    if mode not in {"text", "cross"}:
        raise WindowError("Tıklama konumu metnin üzeri veya sütun ve satır kesişimi olmalıdır.")
    wanted = (text,) if mode == "text" else (column_text, row_text)
    if not all(isinstance(value, str) and value.strip() for value in wanted):
        raise WindowError("Aranacak metni yazın.")
    for preparation in range(3):
        try:
            words = measured_words(image, preparation, vocabulary=wanted, ocr_options=ocr_options)
        except OcrUnavailable as exc:
            raise WindowError(str(exc)) from exc
        point = text_point(words, mode=mode, text=text, column_text=column_text, row_text=row_text)
        if point is not None:
            return point
    missing = f"“{text}”" if mode == "text" else f"“{column_text}” sütunu veya “{row_text}” satırı"
    raise WindowError(f"{missing} seçilen alanda okunamadı; tıklanmadı. Metnin ekranda tam göründüğünü "
                      "ve alanın içinde kaldığını kontrol edin.")


def text_write(service, target, desktop, *, region=None, mode, text="", column_text="", row_text="",
               value=None, clicks=1, clear=False, after="none", ocr_options=None):
    """Capture -> locate -> click -> optional clear -> write -> optional key.

    With value None the measured point is returned and nothing is clicked.
    """
    if clicks not in {1, 2} or type(clicks) is not int:
        raise WindowError("Tıklama sayısı 1 veya 2 olmalıdır.")
    if type(clear) is not bool or after not in {"none", "tab", "enter"}:
        raise WindowError("Yazma sonrası seçimi geçersiz.")
    if value is not None and (not isinstance(value, str) or not value or len(value) > 10_000
                              or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise WindowError("Yazılacak değer boş olmamalı; Enter, Tab veya kontrol karakteri içeremez. "
                          "Sonrasında basılacak tuşu ayrıca seçin.")
    window = service.focus(target)
    captured, image = service._capture_window(target, desktop)
    if captured != window:
        raise WindowError("Pencere değişti; tıklanmadı.")
    if region is None:
        region = (0, 0, image.width, image.height)
    left, top, width, height = region
    if left < 0 or top < 0 or left + width > image.width or top + height > image.height:
        raise WindowError("Arama alanı pencerenin dışına taşıyor; alanı pencere içinden yeniden çizin.")
    x, y = locate_text(image.crop((left, top, left + width, top + height)), mode=mode, text=text,
                       column_text=column_text, row_text=row_text, ocr_options=ocr_options)
    point = service._point_in_window(window, left + x, top + y, desktop)
    service._guard(target, window)
    if value is None:
        return point
    desktop.click(*point, clicks=clicks, button="left")
    service._guard(target, window)
    if clear:
        desktop.hotkey("mod", "a")
        service._guard(target, window)
        desktop.press("backspace")
        service._guard(target, window)
    desktop.write(value)
    if after != "none":
        service._guard(target, window)
        desktop.press(after)
    return {"x": point[0], "y": point[1], "value": value}
