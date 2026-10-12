"""Onay kutusu: read a checkbox's state and set it, never acting on an uncertain state.

By field identity (UI Automation / Accessibility) the application reports the state itself.
Java and custom-drawn applications do not: then two small saved pictures — the box checked and
unchecked — are compared only around the target point, so other checkboxes on the screen are
never mistaken for it. A state is accepted only with a clear winner; after a change the new
state must be seen before the step succeeds.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .windows import WindowError

THRESHOLD = 0.9
MARGIN = 0.05
VERIFY_SECONDS = 3.0


@dataclass(frozen=True)
class Seen:
    checked: bool
    point: tuple[int, int]  # screen point of the box itself


def best_match(image: Any, template: Any) -> tuple[float, tuple[int, int]]:
    """Highest normalized correlation and the top-left corner where it occurs."""
    import cv2
    import numpy as np

    from .vision import Vision

    screen, target = Vision._gray(image), Vision._gray(template)
    if target.shape[0] > screen.shape[0] or target.shape[1] > screen.shape[1]:
        return -1.0, (0, 0)
    if float(np.std(target)) < 1:
        raise WindowError("Onay kutusu görüntüsü düz bir renk; kutuyu çerçevesiyle birlikte yeniden seçin.")
    _, score, _, location = cv2.minMaxLoc(cv2.matchTemplate(screen, target, cv2.TM_CCOEFF_NORMED))
    return (float(score) if np.isfinite(score) else -1.0), (int(location[0]), int(location[1]))


def decide(image: Any, checked: Any, unchecked: Any) -> tuple[bool, tuple[int, int]]:
    """State and box center inside image; a weak or close result raises instead of guessing."""
    on, on_at = best_match(image, checked)
    off, off_at = best_match(image, unchecked)
    if max(on, off) < THRESHOLD:
        raise WindowError("Onay kutusu hedefin yanında tanınmadı (işaretli/işaretsiz görüntülerle eşleşmedi). Hedefi "
                          "ve görüntüleri kontrol edin; işlem yapılmadı.")
    if abs(on - off) < MARGIN:
        raise WindowError("Onay kutusunun işaretli mi işaretsiz mi olduğu ayırt edilemedi; işlem yapılmadı. "
                          "Görüntüleri kutuyu ve işaretini içerecek şekilde yeniden seçin.")
    template, (x, y) = (checked, on_at) if on > off else (unchecked, off_at)
    return on > off, (x + template.width // 2, y + template.height // 2)


def look(service: Any, target: dict, desktop: Any, point: tuple[int, int], checked: Any, unchecked: Any) -> Seen:
    window, image = service._capture_window(target, desktop)
    radius = max(checked.width, checked.height, unchecked.width, unchecked.height) + 40
    x, y = point[0] - window.x, point[1] - window.y
    left, top = max(0, x - radius), max(0, y - radius)
    crop = image.crop((left, top, min(image.width, x + radius), min(image.height, y + radius)))
    state, (cx, cy) = decide(crop, checked, unchecked)
    return Seen(state, (window.x + left + cx, window.y + top + cy))


def checkbox(service: Any, target: dict, desktop: Any, *, operation: str, targeting: dict,
             checked: Any = None, unchecked: Any = None, locate: bool = False) -> Any:
    """operation: read | check | uncheck. Returns the final state (None: indeterminate on read)."""
    from .elements import checkbox_info

    if operation not in {"read", "check", "uncheck"}:
        raise WindowError("Onay kutusu işlemi geçersiz.")
    by_identity = targeting.get("target_mode") == "element"
    if by_identity:
        window = service.focus(target)
        info = checkbox_info(service.elements, window, targeting.get("element"),
                             timeout=float(targeting.get("timeout", 10)))
        if locate:
            return service._point_in_window(window, info.center[0] - window.x, info.center[1] - window.y, desktop)

        def state() -> bool | None:
            service._guard(target, window)
            return service.elements.backend.checkbox_state(window, info)
    else:
        if checked is None or unchecked is None:
            raise WindowError("Onay kutusunun işaretli ve işaretsiz görüntülerini seçin.")
        window, point = service._resolve_target(target, desktop, **targeting)
        seen = look(service, target, desktop, point, checked, unchecked)
        if locate:
            return seen.point

        def state() -> bool | None:
            nonlocal seen
            seen = look(service, target, desktop, point, checked, unchecked)
            return seen.checked

    current = state()
    if operation == "read":
        return current
    wanted = operation == "check"
    if current is None:
        raise WindowError("Onay kutusu kısmen işaretli (belirsiz) görünüyor; işlem yapılmadı.")
    if current == wanted:
        return current
    service._guard(target, window)
    if by_identity:
        service.elements.backend.toggle_checkbox(window, info)
    else:
        # One click on the box itself; never repeated (a second click would undo it).
        desktop.click(*seen.point, clicks=1, button="left")
    deadline = time.monotonic() + VERIFY_SECONDS
    while True:
        if service.cancel.wait(0.2):
            service._check()
        try:
            if state() == wanted:
                return wanted
        except WindowError:
            if time.monotonic() >= deadline:
                raise
        if time.monotonic() >= deadline:
            raise WindowError("Onay kutusuna tıklandı ancak durumu değişmedi; yeniden tıklanmadı. Uygulamayı kontrol "
                              "edin.")
