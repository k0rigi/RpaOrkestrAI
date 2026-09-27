"""Bounded dropdown discovery and per-value execution."""

from __future__ import annotations

import math
import time
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from .controller import DesktopController, Region
from .vision import Vision


def _normalized(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


class DropdownScanLimitError(RuntimeError):
    """Scan reached its bound before proving that the list stopped moving."""

    def __init__(self, values: list[str]) -> None:
        super().__init__("Dropdown scan limit reached; refine the region or increase max_scrolls.")
        self.values = values


@dataclass(frozen=True)
class DropdownResult:
    value: str
    result: Any = None
    error: str | None = None


class DropdownIterator:
    def __init__(self, controller: DesktopController | None = None) -> None:
        self.controller = controller

    def scan(
        self,
        read_visible: Callable[[], Iterable[str]] | None = None,
        scroll: Callable[[], None] | None = None,
        *, region: Region | None = None, language: str = "eng",
        max_scrolls: int = 30, stable_passes: int = 2, max_items: int = 1_000,
        settle_seconds: float = 0.2, tesseract_cmd: str | None = None,
        ocr_timeout: float = 10,
    ) -> list[str]:
        """Read an already-open dropdown, deduplicate, scroll until stable.

        A region is mandatory for built-in OCR so unrelated screen text is not
        accidentally treated as list items. OCR is heuristic: ERP workflows
        should prefer an authoritative known-values list when available.
        """
        if type(max_scrolls) is not int or not 1 <= max_scrolls <= 1_000:
            raise ValueError("max_scrolls must be between 1 and 1,000.")
        if type(stable_passes) is not int or not 1 <= stable_passes <= max_scrolls:
            raise ValueError("stable_passes must be between 1 and max_scrolls.")
        if type(max_items) is not int or not 1 <= max_items <= 10_000:
            raise ValueError("max_items must be between 1 and 10,000.")
        if not 0 <= settle_seconds <= 10:
            raise ValueError("settle_seconds must be between 0 and 10.")
        if isinstance(ocr_timeout, bool) or not math.isfinite(ocr_timeout) or ocr_timeout <= 0:
            raise ValueError("ocr_timeout must be positive and finite.")
        if read_visible is None:
            if self.controller is None or region is None:
                raise ValueError("Provide read_visible or a controller and dropdown region.")
            def read_visible() -> list[str]:
                return Vision.read_lines(
                    self.controller.screenshot(region), language,
                    tesseract_cmd=tesseract_cmd, timeout=ocr_timeout,
                )
        if scroll is None:
            if self.controller is None or region is None:
                raise ValueError("Provide scroll or a controller and dropdown region.")
            x, y, width, height = region
            def scroll() -> None:
                self.controller.scroll(-3, x=x + width // 2, y=y + height // 2)
        values: list[str] = []
        seen: set[str] = set()
        previous_page: tuple[str, ...] | None = None
        stable = 0
        for step in range(max_scrolls + 1):
            if self.controller:
                self.controller._check_cancelled()
            raw_page = read_visible()
            if isinstance(raw_page, str):
                raw_page = raw_page.splitlines()
            page = tuple(_normalized(str(value)) for value in raw_page if str(value).strip())
            canonical_page = tuple(value.casefold() for value in page)
            for value in page:
                key = value.casefold()
                if key not in seen:
                    if len(values) >= max_items:
                        raise DropdownScanLimitError(values)
                    seen.add(key)
                    values.append(value)
            stable = stable + 1 if canonical_page == previous_page else 0
            if stable >= stable_passes:
                return values
            previous_page = canonical_page
            if step < max_scrolls:
                scroll()
                if settle_seconds:
                    time.sleep(settle_seconds)
        raise DropdownScanLimitError(values)

    def iterate(
        self, values: Iterable[str], select: Callable[[str], Any],
        process: Callable[[str], Any], *, max_items: int = 1_000,
        continue_on_error: bool = False,
    ) -> list[DropdownResult]:
        """Select every unique value, then perform the caller's search/action.

        select must reopen a dropdown if selection closes it. Exceptions stop
        the workflow by default; explicit continue_on_error records failures.
        """
        if isinstance(values, (str, bytes)):
            raise ValueError("values must be a sequence of dropdown values, not text.")
        if type(max_items) is not int or not 1 <= max_items <= 10_000:
            raise ValueError("max_items must be between 1 and 10,000.")
        results: list[DropdownResult] = []
        seen: set[str] = set()
        for index, raw in enumerate(values):
            # Also bound repeated/infinite iterables, not only unique values.
            if index >= max_items:
                raise ValueError("Dropdown input exceeds max_items.")
            if self.controller:
                self.controller._check_cancelled()
            value = _normalized(str(raw))
            if not value or value.casefold() in seen:
                continue
            seen.add(value.casefold())
            try:
                select(value)
                result = process(value)
                results.append(DropdownResult(value, result))
            except (InterruptedError, KeyboardInterrupt):
                raise
            except Exception as exc:
                # PyAutoGUI failsafe must never be swallowed by continue mode.
                if type(exc).__name__ == "FailSafeException" or not continue_on_error:
                    raise
                results.append(DropdownResult(value, error=type(exc).__name__))
        return results
