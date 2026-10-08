"""Text recognition with the operating system's own OCR; Tesseract is the fallback.

macOS uses the Vision framework and Windows uses Windows.Media.Ocr, so installed
apps can read screen text without extra software. Turkish is requested first
and English second; each engine uses what the computer supports.
"""

from __future__ import annotations

import io
import math
import platform
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LANGUAGES = {"tur": ("tr-TR", "tr"), "eng": ("en-US", "en")}


class OcrUnavailable(RuntimeError):
    """No OCR engine can run on this computer."""


@dataclass(frozen=True)
class OcrWord:
    """A word in original image pixels, from the top left; confidence is 0..1."""

    text: str
    x: float
    y: float
    width: float
    height: float
    confidence: float


def _word(text: str, x: float, y: float, width: float, height: float,
          confidence: float, size: tuple[int, int]) -> OcrWord | None:
    """Discard unusable geometry; never estimate a word's position from its text."""
    try:
        x, y, width, height, confidence = map(float, (x, y, width, height, confidence))
    except (TypeError, ValueError, OverflowError):
        return None
    if not isinstance(text, str) or not text.strip():
        return None
    if not all(math.isfinite(value) for value in (x, y, width, height, confidence)):
        return None
    if width <= 0 or height <= 0 or not 0 <= confidence <= 1:
        return None
    # Allow only arithmetic roundoff from normalized native coordinates.
    epsilon = 1e-6
    if x < -epsilon or y < -epsilon or x + width > size[0] + epsilon or y + height > size[1] + epsilon:
        return None
    x, y = max(0.0, x), max(0.0, y)
    width, height = min(width, size[0] - x), min(height, size[1] - y)
    if width <= 0 or height <= 0:
        return None
    return OcrWord(text.strip(), x, y, width, height, confidence)


def _requested(language: str) -> list[str]:
    codes = [code for code in re.split(r"[+,\s]+", language or "") if code]
    return [code for code in codes if code in LANGUAGES] or ["tur", "eng"]


def _mac_observations(image: Any, language: str, vocabulary: Iterable[str] = ()) -> list[Any]:
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
    custom_words = list(dict.fromkeys(token for text in vocabulary if isinstance(text, str)
                                     for token in [text.strip(), *text.split()] if 0 < len(token) <= 256))
    if custom_words:
        request.setCustomWords_(custom_words[:4000])
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
    return sorted(request.results() or [], key=lambda item: (-item.boundingBox().origin.y,
                                                              item.boundingBox().origin.x))


def _mac(image: Any, language: str) -> str:
    lines = []
    for observation in _mac_observations(image, language):
        candidates = observation.topCandidates_(1)
        if candidates:
            lines.append(str(candidates[0].string()))
    return "\n".join(lines)


def _mac_words(image: Any, language: str, vocabulary: Iterable[str] = ()) -> list[OcrWord]:
    words = []
    for observation in _mac_observations(image, language, vocabulary):
        candidates = observation.topCandidates_(1)
        if not candidates:
            continue
        candidate = candidates[0]
        text = str(candidate.string())
        for match in re.finditer(r"\S+", text):
            # NSString/NSRange counts UTF-16 units, not Python's Unicode code points.
            start = len(text[:match.start()].encode("utf-16-le")) // 2
            length = len(match.group().encode("utf-16-le")) // 2
            try:
                rectangle, error = candidate.boundingBoxForRange_error_((start, length), None)
                if rectangle is None or error is not None:
                    continue
                box = rectangle.boundingBox()
                word = _word(match.group(), box.origin.x * image.width,
                             (1 - box.origin.y - box.size.height) * image.height,
                             box.size.width * image.width, box.size.height * image.height,
                             candidate.confidence(), image.size)
            except (AttributeError, TypeError, ValueError, OverflowError):
                continue
            if word is not None:
                words.append(word)
    return words


def _windows_result(image: Any, language: str) -> tuple[Any, tuple[int, int]]:
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

    return asyncio.run(recognize()), gray.size


def _windows(image: Any, language: str) -> str:
    result, _ = _windows_result(image, language)
    return "\n".join(line.text for line in result.lines)


def _windows_words(image: Any, language: str) -> list[OcrWord]:
    result, size = _windows_result(image, language)
    scale_x, scale_y = image.width / size[0], image.height / size[1]
    try:
        angle = float(result.text_angle or 0)
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        raise OcrUnavailable("Windows OCR metin yönünü belirleyemedi.") from exc
    if not math.isfinite(angle):
        raise OcrUnavailable("Windows OCR metin yönünü belirleyemedi.")
    sine, cosine = math.sin(math.radians(angle)), math.cos(math.radians(angle))
    words = []
    for line in result.lines:
        for item in line.words:
            try:
                box = item.bounding_rect
                # Windows boxes refer to the deskewed image. Rotate clockwise around
                # its center to overlay the original image, then undo input resizing.
                corners = [(box.x, box.y), (box.x + box.width, box.y),
                           (box.x, box.y + box.height), (box.x + box.width, box.y + box.height)]
                if box.width <= 0 or box.height <= 0:
                    continue
                rotated = [((x - size[0] / 2) * cosine - (y - size[1] / 2) * sine + size[0] / 2,
                            (x - size[0] / 2) * sine + (y - size[1] / 2) * cosine + size[1] / 2)
                           for x, y in corners]
                left, top = min(x for x, _ in rotated), min(y for _, y in rotated)
                right, bottom = max(x for x, _ in rotated), max(y for _, y in rotated)
                word = _word(item.text, left * scale_x, top * scale_y,
                             (right - left) * scale_x, (bottom - top) * scale_y, 1.0, image.size)
            except (AttributeError, TypeError, ValueError, OverflowError):
                continue
            if word is not None:
                words.append(word)
    return words


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


def _tesseract_words(image: Any, language: str, tesseract_cmd: str | None,
                     timeout: float) -> list[OcrWord]:
    from .vision import Vision

    try:
        import pytesseract
    except ImportError as exc:
        raise OcrUnavailable("OCR için kullanılabilir bir motor bulunamadı.") from exc
    language = language or "tur+eng"
    if not re.fullmatch(r"[A-Za-z_]+(?:\+[A-Za-z_]+)*", language):
        raise ValueError("Invalid Tesseract language identifier.")
    prepared = Vision.preprocess(image)
    scale_x, scale_y = image.width / prepared.shape[1], image.height / prepared.shape[0]
    previous_command = pytesseract.pytesseract.tesseract_cmd
    try:
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = str(Path(tesseract_cmd).expanduser())
        data = pytesseract.image_to_data(prepared, lang=language, config="--psm 11",
                                        output_type=pytesseract.Output.DICT, timeout=timeout)
    except (OSError, RuntimeError) as exc:
        raise OcrUnavailable("OCR için kullanılabilir bir motor bulunamadı.") from exc
    finally:
        pytesseract.pytesseract.tesseract_cmd = previous_command
    words = []
    for index, text in enumerate(data.get("text", [])):
        try:
            if int(data["level"][index]) != 5:
                continue
            word = _word(text, float(data["left"][index]) * scale_x,
                         float(data["top"][index]) * scale_y,
                         float(data["width"][index]) * scale_x,
                         float(data["height"][index]) * scale_y,
                         float(data["conf"][index]) / 100, image.size)
        except (KeyError, IndexError, TypeError, ValueError, OverflowError):
            continue
        if word is not None:
            words.append(word)
    return words


def read_words(image: Any, *, language: str = "tur+eng", tesseract_cmd: str | None = None,
               timeout: float = 10, engine: str = "auto", vocabulary: Iterable[str] = ()) -> list[OcrWord]:
    """Recognize word boxes in input image pixels, using the OS or Tesseract.

    Invalid/missing boxes are omitted rather than estimated from a line. Windows
    does not expose word confidence, so its words use 1.0. Native engines control
    their own execution time; ``timeout`` limits the Tesseract fallback.
    ``vocabulary`` supplies recognition hints on macOS; engines without a custom
    lexicon ignore it. Recognized words are never replaced by these hints.
    """
    if engine not in {"auto", "system", "tesseract"}:
        raise ValueError("OCR engine must be auto, system or tesseract.")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("OCR timeout must be positive and finite.")
    if image.width <= 0 or image.height <= 0:
        raise ValueError("OCR image must have positive dimensions.")
    if engine == "tesseract":
        return _tesseract_words(image, language, tesseract_cmd, timeout)
    system = platform.system()
    native = _mac_words if system == "Darwin" else _windows_words if system == "Windows" else None
    if native is not None:
        try:
            return _mac_words(image, language, vocabulary) if system == "Darwin" else native(image, language)
        except OcrUnavailable:
            if engine == "system":
                raise
    elif engine == "system":
        raise OcrUnavailable("Sistem OCR'ı macOS ve Windows'ta kullanılabilir.")
    return _tesseract_words(image, language, tesseract_cmd, timeout)
