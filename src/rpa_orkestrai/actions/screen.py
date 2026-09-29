"""Screen reading: images, OCR text, pixel colors and screenshots.

Regions are either primary-screen coordinates or relative to a recognized window,
so a moved ERP window keeps the same region.
"""

from __future__ import annotations

import io
import shutil
import time
from pathlib import Path
from typing import Any

from ..desktop.vision import AmbiguousMatchError, Vision
from ..errors import WorkflowError
from . import handler
from .common import choice, fold, integer, number, path, region, text


def capture(ctx, p) -> tuple[Any, int, int]:
    """Image of the requested area and its screen origin."""
    area = region(p.get("region"))
    desktop = ctx.desktop()
    if p.get("relative_to", "screen") == "window":
        target = p.get("window")
        if not isinstance(target, dict) or target.get("found") is not True:
            raise WorkflowError("Pencereye göre bölge için bulunan bir pencere değişkeni seçin.")
        window, image = ctx.windows().screenshot_window(target, desktop)
        if area is None:
            return image, window.x, window.y
        x, y, width, height = area
        if x < 0 or y < 0 or x + width > image.width or y + height > image.height:
            raise WorkflowError("Bölge pencerenin dışına taşıyor. Bölgeyi pencere içinden yeniden seçin.")
        return image.crop((x, y, x + width, y + height)), window.x + x, window.y + y
    try:
        return desktop.screenshot(area), (area or (0, 0))[0], (area or (0, 0))[1]
    except ValueError as exc:
        raise WorkflowError("Bölge ana ekranın dışına taşıyor. Bölgeyi yeniden seçin.") from exc


def _find(ctx, p, image, template):
    try:
        return Vision.match_template(image, template, threshold=number(p.get("confidence", 0.9), "Eşleşme eşiği",
                                                                      0.5, 1))
    except AmbiguousMatchError as exc:
        raise WorkflowError("Görsel birden fazla yerde bulundu. Daha ayırt edici bir görsel seçin.") from exc
    except (ValueError, OSError) as exc:
        raise WorkflowError("Referans görsel okunamadı veya ayırt edici ayrıntı içermiyor.") from exc


def search(ctx, p, *, visible: bool = True) -> dict:
    template = ctx.template_path(p.get("template"))
    timeout = number(p.get("timeout", 5), "Bekleme süresi", 0, 600)
    deadline = time.monotonic() + timeout
    while True:
        ctx.check_cancelled()
        image, left, top = capture(ctx, p)
        match = _find(ctx, p, image, template)
        if (match is not None) == visible:
            if match is None:
                return {"found": False}
            x, y = match.x + left, match.y + top
            return {"found": True, "x": x, "y": y, "width": match.width, "height": match.height,
                    "center_x": x + match.width // 2, "center_y": y + match.height // 2,
                    "confidence": round(match.confidence, 3)}
        if time.monotonic() >= deadline:
            return {"found": match is not None, "timed_out": True}
        ctx.wait(min(0.25, max(0.0, deadline - time.monotonic())))


@handler("screen.find_image")
def find_image(ctx, p):
    state = choice(p.get("state", "visible"), "Beklenen durum", {"visible", "hidden"})
    result = search(ctx, p, visible=state == "visible")
    if result.pop("timed_out", False):
        if p.get("on_missing", "stop") == "stop":
            raise WorkflowError("Görsel ekranda görünmedi." if state == "visible" else "Görsel ekrandan kaybolmadı.")
        return {"found": result["found"]}
    return result


@handler("screen.click_image")
def click_image(ctx, p):
    result = search(ctx, p)
    if result.pop("timed_out", False) or not result["found"]:
        raise WorkflowError("Tıklanacak görsel bekleme süresi içinde ekranda bulunamadı.")
    x = result["center_x"] + number(p.get("offset_x", 0), "Yatay fark", -10_000, 10_000)
    y = result["center_y"] + number(p.get("offset_y", 0), "Dikey fark", -10_000, 10_000)
    try:
        ctx.desktop().click(x, y, clicks=integer(p.get("clicks", 1), "Tıklama sayısı", 1, 3),
                            button=choice(p.get("button", "left"), "Fare düğmesi", {"left", "right", "middle"}))
    except ValueError as exc:
        raise WorkflowError("Tıklanacak nokta ana ekranın dışında. Yatay/dikey farkı kontrol edin.") from exc
    return result


def ocr(ctx, image) -> str:
    from ..desktop.ocr import OcrUnavailable, read_text

    try:
        return read_text(image, language=ctx.config.get("ocr_language") or "tur+eng",
                         tesseract_cmd=ctx.config.get("tesseract_cmd") or None,
                         timeout=ctx.settings.action_timeout)
    except OcrUnavailable as exc:
        raise WorkflowError(str(exc)) from exc


@handler("screen.read_text")
def read_text(ctx, p):
    image, _, _ = capture(ctx, p)
    return ocr(ctx, image)


@handler("screen.wait_text")
def wait_text(ctx, p):
    wanted = " ".join(fold(text(p.get("text"), "Aranacak metin", limit=500)).split())
    timeout = number(p.get("timeout", 10), "Bekleme süresi", 0, 600)
    deadline = time.monotonic() + timeout
    while True:
        image, _, _ = capture(ctx, p)
        if wanted in " ".join(fold(ocr(ctx, image)).split()):
            return True
        if time.monotonic() >= deadline:
            if p.get("on_missing", "stop") == "stop":
                raise WorkflowError(f"“{p.get('text')}” metni ekranda görünmedi.")
            return False
        ctx.wait(min(0.5, max(0.0, deadline - time.monotonic())))


@handler("screen.pixel")
def pixel(ctx, p):
    try:
        red, green, blue = ctx.desktop().pixel(number(p.get("x"), "X", 0, 100_000), number(p.get("y"), "Y", 0, 100_000))
    except ValueError as exc:
        raise WorkflowError("Nokta ana ekranın dışında.") from exc
    return f"#{red:02X}{green:02X}{blue:02X}"


@handler("screen.screenshot")
def screenshot(ctx, p):
    image, _, _ = capture(ctx, p)
    name = text(p.get("filename") or "ekran.png", "Dosya adı", limit=120).strip()
    if not name.lower().endswith(".png"):
        name += ".png"
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    stored = ctx.save_artifact(name, buffer.getvalue())
    folder = p.get("folder")
    if folder:
        destination = path(folder, "Kayıt klasörü")
        try:
            destination.mkdir(parents=True, exist_ok=True)
            target = destination / Path(name).name
            shutil.copyfile(stored, target)
            return str(target)
        except OSError as exc:
            raise WorkflowError("Ekran görüntüsü klasöre kaydedilemedi. Klasör yolunu ve izinleri kontrol edin.") from exc
    return str(stored)
