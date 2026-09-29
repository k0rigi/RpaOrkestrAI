"""Primary-display automation in logical coordinates, including macOS Retina."""

from __future__ import annotations

import math
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .vision import Match, Vision

Region = tuple[int, int, int, int]


class DesktopController:
    """Lazy, fail-safe-enabled screen control.

    Coordinates and regions are logical primary-monitor pixels. Screenshots are
    normalized to that size before matching. Capture templates with screenshot()
    or set template_scale for externally captured high-DPI templates.
    """

    def __init__(
        self, default_timeout: float = 10, confidence: float = 0.85, *,
        pause: float = 0.15, cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        if not math.isfinite(default_timeout) or default_timeout <= 0:
            raise ValueError("default_timeout must be positive and finite.")
        if not 0 < confidence <= 1 or not 0 <= pause <= 5:
            raise ValueError("Invalid desktop confidence or pause.")
        self.default_timeout = default_timeout
        self.confidence = confidence
        self.pause = pause
        self.cancel_check = cancel_check
        self._backend: Any = None

    @property
    def modifier(self) -> str:
        return "command" if sys.platform == "darwin" else "ctrl"

    def _check_cancelled(self) -> None:
        if self.cancel_check and self.cancel_check():
            raise InterruptedError("Desktop automation was cancelled.")

    def _gui(self) -> Any:
        self._check_cancelled()
        if self._backend is None:
            try:
                import pyautogui
            except (ImportError, KeyError) as exc:
                raise RuntimeError("Desktop automation requires PyAutoGUI and an interactive desktop session.") from exc
            self._backend = pyautogui
        self._backend.FAILSAFE = True
        self._backend.PAUSE = self.pause
        return self._backend

    @staticmethod
    def _point(x: float, y: float) -> tuple[int, int]:
        if isinstance(x, bool) or isinstance(y, bool) or not math.isfinite(x) or not math.isfinite(y):
            raise ValueError("Screen coordinates must be finite numbers.")
        return round(x), round(y)

    def size(self) -> tuple[int, int]:
        """Return the primary display's logical coordinate size."""
        width, height = self._gui().size()
        return int(width), int(height)

    def click(self, x: float, y: float, *, clicks: int = 1, button: str = "left") -> None:
        if type(clicks) is not int or not 1 <= clicks <= 3 or button not in {"left", "right", "middle"}:
            raise ValueError("Invalid click count or mouse button.")
        x, y = self._point(x, y)
        gui = self._gui()
        width, height = gui.size()
        if not 0 <= x < width or not 0 <= y < height:
            raise ValueError("Click lies outside the primary display.")
        gui.click(x=x, y=y, clicks=clicks, interval=0.1, button=button)

    def hotkey(self, *keys: str) -> None:
        if not keys or len(keys) > 5:
            raise ValueError("Provide one to five shortcut keys.")
        resolved = [self.modifier if key in {"mod", "primary", "ctrl_or_cmd"} else key for key in keys]
        self._gui().hotkey(*resolved)

    def write(self, text: str, *, interval: float = 0.03) -> None:
        if not isinstance(text, str) or not 0 <= interval <= 1:
            raise ValueError("Expected text and a typing interval between 0 and 1.")
        if text.isascii():
            self._gui().write(text, interval=interval)
        else:
            self.paste(text)

    def paste(self, text: str) -> None:
        """Paste Unicode through the clipboard; replaces its current contents."""
        self._check_cancelled()
        import pyperclip

        pyperclip.copy(text)
        self.hotkey("mod", "v")

    def press(self, key: str, *, presses: int = 1) -> None:
        if type(presses) is not int or not 1 <= presses <= 1_000:
            raise ValueError("presses must be between 1 and 1,000.")
        self._gui().press(key, presses=presses, interval=0.05)

    def scroll(self, amount: int, *, x: int | None = None, y: int | None = None) -> None:
        if type(amount) is not int or not -100 <= amount <= 100:
            raise ValueError("Scroll amount must be an integer between -100 and 100.")
        gui = self._gui()
        if x is not None or y is not None:
            if x is None or y is None:
                raise ValueError("Both scroll coordinates must be supplied.")
            x, y = self._point(x, y)
            width, height = gui.size()
            if not 0 <= x < width or not 0 <= y < height:
                raise ValueError("Scroll point lies outside the primary display.")
            gui.moveTo(x, y)
        gui.scroll(amount)

    def _on_screen(self, x: float, y: float) -> tuple[int, int]:
        x, y = self._point(x, y)
        width, height = self._gui().size()
        if not 0 <= x < width or not 0 <= y < height:
            raise ValueError("Point lies outside the primary display.")
        return x, y

    def position(self) -> tuple[int, int]:
        point = self._gui().position()
        return int(point.x), int(point.y)

    def move(self, x: float, y: float, *, duration: float = 0) -> None:
        if not 0 <= duration <= 10:
            raise ValueError("Move duration must be between 0 and 10 seconds.")
        x, y = self._on_screen(x, y)
        self._gui().moveTo(x, y, duration=duration)

    def drag(self, from_x: float, from_y: float, to_x: float, to_y: float, *,
             button: str = "left", duration: float = 0.5) -> None:
        if button not in {"left", "right", "middle"} or not 0 <= duration <= 10:
            raise ValueError("Invalid drag button or duration.")
        start, end = self._on_screen(from_x, from_y), self._on_screen(to_x, to_y)
        gui = self._gui()
        gui.moveTo(*start)
        gui.mouseDown(button=button)
        try:
            # Small steps let applications see a real drag rather than a jump.
            gui.moveTo(*end, duration=max(duration, 0.1))
        finally:
            gui.mouseUp(button=button)

    def hscroll(self, amount: int, *, x: int | None = None, y: int | None = None) -> None:
        if type(amount) is not int or not -100 <= amount <= 100:
            raise ValueError("Scroll amount must be an integer between -100 and 100.")
        gui = self._gui()
        if x is not None and y is not None:
            gui.moveTo(*self._on_screen(x, y))
        # Positive scrolls right on both systems (macOS wheel events count leftwards).
        gui.hscroll(-amount if sys.platform == "darwin" else amount)

    def key_down(self, key: str) -> None:
        self._gui().keyDown(self.modifier if key == "mod" else key)

    def key_up(self, key: str) -> None:
        self._gui().keyUp(self.modifier if key == "mod" else key)

    def pixel(self, x: float, y: float) -> tuple[int, int, int]:
        x, y = self._on_screen(x, y)
        color = self.screenshot((x, y, 1, 1)).convert("RGB").getpixel((0, 0))
        return int(color[0]), int(color[1]), int(color[2])

    def screenshot(self, region: Region | None = None) -> Any:
        gui = self._gui()
        gui.failSafeCheck()
        image = gui.screenshot()
        size = tuple(gui.size())
        if image.size != size:
            image = image.resize(size)
        if region is not None:
            if len(region) != 4 or any(type(v) is not int for v in region):
                raise ValueError("Region is (left, top, width, height) in logical pixels.")
            x, y, width, height = region
            if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > size[0] or y + height > size[1]:
                raise ValueError("Screenshot region lies outside the primary display.")
            image = image.crop((x, y, x + width, y + height))
        return image

    def find_template(
        self, path: str | Path, *, region: Region | None = None,
        confidence: float | None = None, template_scale: float = 1.0,
    ) -> Match | None:
        found = Vision.match_template(
            self.screenshot(region), path,
            threshold=self.confidence if confidence is None else confidence,
            template_scale=template_scale,
        )
        if found is not None and region is not None:
            return Match(found.x + region[0], found.y + region[1], found.width, found.height, found.confidence)
        return found

    def wait_for_template(
        self, path: str | Path, *, timeout: float | None = None,
        region: Region | None = None, confidence: float | None = None,
        template_scale: float = 1.0, visible: bool = True, poll_interval: float = 0.2,
    ) -> Match | None:
        duration = self.default_timeout if timeout is None else timeout
        if not math.isfinite(duration) or duration <= 0 or not 0.01 <= poll_interval <= 5:
            raise ValueError("Invalid timeout or polling interval.")
        deadline = time.monotonic() + duration
        while True:
            self._check_cancelled()
            match = self.find_template(path, region=region, confidence=confidence, template_scale=template_scale)
            if (match is not None) == visible:
                return match
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Expected screen template state was not reached before timeout.")
            time.sleep(min(poll_interval, remaining))

    def click_template(self, path: str | Path, **kwargs: Any) -> Match:
        match = self.wait_for_template(path, **kwargs)
        if match is None:
            raise ValueError("Cannot click a missing template.")
        self.click(*match.center)
        return match
