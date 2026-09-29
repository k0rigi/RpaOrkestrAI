"""Text recognition with the operating system's own OCR; Tesseract is the fallback.

macOS uses the Vision framework and Windows uses Windows.Media.Ocr, so installed
apps can read screen text without extra software. Turkish is requested first
and English second; each engine uses what the computer supports.
"""

from __future__ import annotations

import io
import platform
import re
from typing import Any

LANGUAGES = {"tur": ("tr-TR", "tr"), "eng": ("en-US", "en")}


class OcrUnavailable(RuntimeError):
    """No OCR engine can run on this computer."""


def _requested(language: str) -> list[str]:
    codes = [code for code in re.split(r"[+,\s]+", language or "") if code]
    return [code for code in codes if code in LANGUAGES] or ["tur", "eng"]


def _mac(image: Any, language: str) -> str:
    try:
        import Quartz
        import Vision
        from Foundation import NSData
    except ImportError as exc:
        raise OcrUnavailable("macOS Vision OCR yüklenemedi.") from exc
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    raw = buffer.getvalue()
    source = Quartz.CGImageSourceCreateWithData(NSData.dataWithBytes_length_(raw, len(raw)), None)
    picture = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None) if source is not None else None
    if picture is None:
        raise OcrUnavailable("Ekran görüntüsü OCR için hazırlanamadı.")
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(True)
    wanted = [LANGUAGES[code][0] for code in _requested(language)]
    try:
        supported, _ = request.supportedRecognitionLanguagesAndReturnError_(None)
        available = [code for code in wanted if code in set(supported or [])]
    except (AttributeError, TypeError):
        available = []
    if available:
        request.setRecognitionLanguages_(available)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(picture, None)
    success, error = handler.performRequests_error_([request], None)
    if not success:
        raise OcrUnavailable(f"macOS OCR çalışmadı: {error}")
    observations = sorted(request.results() or [], key=lambda item: (-item.boundingBox().origin.y,
                                                                      item.boundingBox().origin.x))
    lines = []
    for observation in observations:
        candidates = observation.topCandidates_(1)
        if candidates:
            lines.append(str(candidates[0].string()))
    return "\n".join(lines)


def _windows(image: Any, language: str) -> str:
    try:
        import asyncio

        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter
    except ImportError as exc:
        raise OcrUnavailable("Windows OCR bileşenleri yüklenemedi.") from exc
    try:
        import ctypes

        # Workflow threads start without COM; WinRT needs the multithreaded apartment.
        ctypes.windll.ole32.CoInitializeEx(None, 0)
    except (OSError, AttributeError):
        pass
    engine = None
    for code in _requested(language):
        tag = LANGUAGES[code][1]
        if OcrEngine.is_language_supported(Language(tag)):
            engine = OcrEngine.try_create_from_language(Language(tag))
            break
    engine = engine or OcrEngine.try_create_from_user_profile_languages()
    if engine is None:
        raise OcrUnavailable("Windows'ta OCR dili yüklü değil. Ayarlar → Saat ve dil → Dil bölümünden "
                             "Türkçe veya İngilizce dil paketini (OCR) ekleyin.")
    gray = image.convert("L")
    try:
        limit = int(OcrEngine.max_image_dimension)
    except (AttributeError, TypeError, ValueError):
        limit = 10_000
    if max(gray.size) > limit:
        ratio = limit / max(gray.size)
        gray = gray.resize((max(1, int(gray.width * ratio)), max(1, int(gray.height * ratio))))
    writer = DataWriter()
    writer.write_bytes(gray.tobytes())
    bitmap = SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), BitmapPixelFormat.GRAY8,
                                                    gray.width, gray.height)

    async def recognize():
        return await engine.recognize_async(bitmap)

    result = asyncio.run(recognize())
    return "\n".join(line.text for line in result.lines)


def _tesseract(image: Any, language: str, tesseract_cmd: str | None, timeout: float) -> str:
    from .vision import Vision

    try:
        return Vision.read_text(image, language or "tur+eng", tesseract_cmd=tesseract_cmd, timeout=timeout)
    except (ImportError, RuntimeError) as exc:
        raise OcrUnavailable("OCR için kullanılabilir bir motor bulunamadı.") from exc


def read_text(image: Any, *, language: str = "tur+eng", tesseract_cmd: str | None = None,
              timeout: float = 10, engine: str = "auto") -> str:
    """Text in the image, top-to-bottom; `engine` is auto, system or tesseract."""
    if engine not in {"auto", "system", "tesseract"}:
        raise ValueError("OCR engine must be auto, system or tesseract.")
    if engine == "tesseract":
        return _tesseract(image, language, tesseract_cmd, timeout)
    system = platform.system()
    native = _mac if system == "Darwin" else _windows if system == "Windows" else None
    if native is not None:
        try:
            return native(image, language).strip()
        except OcrUnavailable:
            if engine == "system":
                raise
    elif engine == "system":
        raise OcrUnavailable("Sistem OCR'ı macOS ve Windows'ta kullanılabilir.")
    return _tesseract(image, language, tesseract_cmd, timeout)
