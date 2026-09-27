"""OpenCV template matching and Tesseract OCR over RGB/Pillow images."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Match:
    x: int
    y: int
    width: int
    height: int
    confidence: float

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


class Vision:
    @staticmethod
    def _gray(image: Any) -> Any:
        import cv2
        import numpy as np

        if isinstance(image, (str, Path)):
            path = Path(image).expanduser()
            if not path.is_file():
                raise FileNotFoundError(f"Image not found: {path.name}")
            # imdecode works with non-ASCII paths on Windows.
            pixels = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_GRAYSCALE)
            if pixels is None:
                raise ValueError("The image could not be decoded.")
            return pixels
        if hasattr(image, "convert"):
            image = image.convert("RGB")
        pixels = np.asarray(image)
        if pixels.size == 0:
            raise ValueError("Image cannot be empty.")
        if pixels.ndim == 2:
            return pixels
        if pixels.ndim == 3 and pixels.shape[2] in (3, 4):
            code = cv2.COLOR_RGBA2GRAY if pixels.shape[2] == 4 else cv2.COLOR_RGB2GRAY
            return cv2.cvtColor(pixels, code)
        raise ValueError("Expected a grayscale or RGB/RGBA image.")

    @staticmethod
    def match_template(image: Any, template: Any, threshold: float = 0.85, *, template_scale: float = 1.0) -> Match | None:
        import cv2
        import numpy as np

        if not 0 < threshold <= 1:
            raise ValueError("Template threshold must be in (0, 1].")
        if not 0.1 <= template_scale <= 4:
            raise ValueError("Template scale must be between 0.1 and 4.")
        screen, target = Vision._gray(image), Vision._gray(template)
        if template_scale != 1:
            target = cv2.resize(target, None, fx=template_scale, fy=template_scale, interpolation=cv2.INTER_AREA)
        height, width = target.shape[:2]
        if height > screen.shape[0] or width > screen.shape[1]:
            return None
        # Constant images give misleading perfect CCOEFF scores at every pixel.
        if float(np.std(target)) < 1:
            raise ValueError("Template must contain visible detail; a flat color is ambiguous.")
        result = cv2.matchTemplate(screen, target, cv2.TM_CCOEFF_NORMED)
        _, score, _, location = cv2.minMaxLoc(result)
        if not np.isfinite(score) or score < threshold:
            return None
        return Match(int(location[0]), int(location[1]), width, height, float(score))

    @staticmethod
    def preprocess(image: Any) -> Any:
        import cv2

        gray = Vision._gray(image)
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        gray = cv2.GaussianBlur(gray, (3, 3), 0)
        return cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

    @staticmethod
    def read_text(
        image: Any, language: str = "eng", *, tesseract_cmd: str | None = None,
        psm: int = 6, timeout: float = 10,
    ) -> str:
        """Read OCR text; install Tesseract and requested language data separately."""
        import re

        import pytesseract

        if not re.fullmatch(r"[A-Za-z_]+(?:\+[A-Za-z_]+)*", language):
            raise ValueError("Invalid Tesseract language identifier.")
        if type(psm) is not int or not 0 <= psm <= 13:
            raise ValueError("Tesseract page segmentation mode must be 0–13.")
        if timeout <= 0:
            raise ValueError("OCR timeout must be positive.")
        previous_command = pytesseract.pytesseract.tesseract_cmd
        try:
            if tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = str(Path(tesseract_cmd).expanduser())
            return pytesseract.image_to_string(
                Vision.preprocess(image), lang=language, config=f"--psm {psm}", timeout=timeout,
            ).strip()
        except pytesseract.TesseractNotFoundError as exc:
            raise RuntimeError("Tesseract is missing. Install it and configure its executable path.") from exc
        finally:
            pytesseract.pytesseract.tesseract_cmd = previous_command

    @staticmethod
    def read_lines(image: Any, language: str = "eng", **kwargs: Any) -> list[str]:
        return [line.strip() for line in Vision.read_text(image, language, **kwargs).splitlines() if line.strip()]
