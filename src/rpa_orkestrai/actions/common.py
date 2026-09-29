"""Argument checks shared by step handlers; messages are shown to the user."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

from ..errors import WorkflowError


def number(value: Any, label: str, low: float, high: float) -> float:
    if isinstance(value, str) and value.strip():
        try:
            value = float(value.replace(",", "."))
        except ValueError:
            pass
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or not low <= value <= high:
        raise WorkflowError(f"{label} {low:g}–{high:g} arasında bir sayı olmalıdır.")
    return float(value)


def integer(value: Any, label: str, low: int, high: int) -> int:
    result = number(value, label, low, high)
    if result != int(result):
        raise WorkflowError(f"{label} tam sayı olmalıdır.")
    return int(result)


def optional_integer(value: Any, label: str, low: int, high: int) -> int | None:
    return None if value is None or value == "" else integer(value, label, low, high)


def text(value: Any, label: str, *, required: bool = True, limit: int = 100_000) -> str:
    if value is None:
        value = ""
    if isinstance(value, (dict, list)):
        raise WorkflowError(f"{label} bir metin olmalıdır.")
    value = str(value)
    if required and not value.strip():
        raise WorkflowError(f"{label} boş olamaz.")
    if len(value) > limit:
        raise WorkflowError(f"{label} en fazla {limit:,} karakter olabilir.".replace(",", "."))
    return value


def choice(value: Any, label: str, allowed: set[str] | dict) -> str:
    if value not in allowed:
        raise WorkflowError(f"{label} seçimi geçersiz.")
    return value


def path(value: Any, label: str = "Dosya yolu") -> Path:
    """~, %USERPROFILE% and $HOME forms work on both platforms."""
    raw = text(value, label, limit=4096).strip().strip('"')
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def region(value: Any) -> tuple[int, int, int, int] | None:
    if value in (None, "", []):
        return None
    if isinstance(value, dict) and {"x", "y", "width", "height"} <= set(value):
        value = [value["x"], value["y"], value["width"], value["height"]]
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise WorkflowError("Ekran bölgesi [x, y, genişlik, yükseklik] biçiminde dört sayı olmalıdır.")
    x, y, width, height = (integer(item, "Bölge değeri", -100_000, 100_000) for item in value)
    if width <= 0 or height <= 0:
        raise WorkflowError("Ekran bölgesinin genişliği ve yüksekliği sıfırdan büyük olmalıdır.")
    return x, y, width, height


def fold(value: Any) -> str:
    """Case-insensitive form that treats i, İ, ı and I alike (Turkish and English text)."""
    return str(value).replace("İ", "i").replace("I", "i").replace("ı", "i").casefold()


def jsonable(value: Any, *, depth: int = 0) -> Any:
    """Copy of a value that can be stored in run records."""
    if depth > 20:
        return "…"
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, dict):
        return {str(key): jsonable(item, depth=depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item, depth=depth + 1) for item in value]
    return str(value)
