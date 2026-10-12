"""Onay kutusu: the state is proven before and after a change; doubt never clicks."""
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image, ImageDraw

from rpa_orkestrai.desktop import checkbox as module
from rpa_orkestrai.desktop.checkbox import checkbox, decide
from rpa_orkestrai.desktop.elements import ElementInfo
from rpa_orkestrai.desktop.windows import WindowError, WindowInfo


def box(checked, size=18):
    image = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((1, 1, size - 2, size - 2), outline="#333333", width=2)
    if checked:
        draw.line((4, 9, 8, 13), fill="#1a5fb4", width=3)
        draw.line((8, 13, 14, 4), fill="#1a5fb4", width=3)
    return image


CHECKED, UNCHECKED = box(True), box(False)


def screen(states):
    """A form with a checkbox row per state; each box at x=40, rows 60 px apart, with a label."""
    image = Image.new("RGB", (400, 60 * len(states) + 40), "#f2f2f2")
    draw = ImageDraw.Draw(image)
    for index, state in enumerate(states):
        image.paste(box(state), (40, 30 + index * 60))
        draw.text((70, 33 + index * 60), f"Secenek {index + 1}", fill="black")
    return image


def test_decide_reads_each_state_and_refuses_doubt():
    assert decide(screen([True]), CHECKED, UNCHECKED)[0] is True
    state, center = decide(screen([False]), CHECKED, UNCHECKED)
    assert state is False and abs(center[0] - 49) <= 1 and abs(center[1] - 39) <= 1
    with pytest.raises(WindowError, match="tanınmadı"):
        decide(_noise(), CHECKED, UNCHECKED)
    with pytest.raises(WindowError, match="ayırt edilemedi"):
        decide(screen([True]), CHECKED, CHECKED.copy())


def _noise():
    image = Image.new("RGB", (120, 120), "white")
    ImageDraw.Draw(image).ellipse((10, 10, 100, 100), outline="black", width=4)
    return image


@pytest.fixture
def form(monkeypatch):
    """Two checkboxes; the target point is on the second. A click near a box toggles that box."""
    window = WindowInfo(1, 2, "App", "Form", 100, 50, 400, 200)
    states = [True, False]
    clicks = []

    def capture(target, desktop):
        return window, screen(states)

    def click(x, y, clicks=1, button="left"):
        clicks_list.append((x, y))
        row = round((y - window.y - 39) / 60)
        if form.effective and 0 <= row < len(states) and abs(x - window.x - 49) <= 9:
            states[row] = not states[row]

    clicks_list = clicks
    service = SimpleNamespace(
        _resolve_target=lambda target, desktop, **kw: (window, (window.x + 49, window.y + 99)),
        _capture_window=capture, _guard=Mock(), cancel=threading.Event(), _check=Mock(),
        focus=lambda target: window, _point_in_window=lambda w, x, y, d: (w.x + x, w.y + y))
    form = SimpleNamespace(service=service, desktop=SimpleNamespace(click=click), states=states, clicks=clicks,
                           window=window, effective=True)
    monkeypatch.setattr(module, "VERIFY_SECONDS", 0.5)
    service.cancel.wait = lambda seconds: False
    return form


def run(form, operation):
    return checkbox(form.service, {"found": True}, form.desktop, operation=operation,
                    targeting={"target_mode": "coordinates", "x": 49, "y": 99}, checked=CHECKED, unchecked=UNCHECKED)


def test_reads_and_checks_only_the_box_at_the_target(form):
    assert run(form, "read") is False and form.clicks == []
    assert run(form, "check") is True
    assert form.states == [True, True] and len(form.clicks) == 1  # the first box was not touched
    assert run(form, "check") is True and len(form.clicks) == 1  # already checked: no click
    assert run(form, "uncheck") is False and form.states == [True, False]


def test_click_without_effect_is_reported_and_not_repeated(form):
    form.effective = False
    with pytest.raises(WindowError, match="durumu değişmedi"):
        run(form, "check")
    assert len(form.clicks) == 1


def test_missing_pictures_stop_before_any_click(form):
    with pytest.raises(WindowError, match="görüntülerini"):
        checkbox(form.service, {"found": True}, form.desktop, operation="check",
                 targeting={"target_mode": "image"}, checked=None, unchecked=UNCHECKED)
    assert form.clicks == []


def test_locate_points_at_the_box_without_changing_it(form):
    point = checkbox(form.service, {"found": True}, form.desktop, operation="check",
                     targeting={"target_mode": "coordinates"}, checked=CHECKED, unchecked=UNCHECKED, locate=True)
    assert abs(point[0] - (100 + 49)) <= 1 and abs(point[1] - (50 + 99)) <= 1 and form.clicks == []


def test_identity_mode_uses_the_application_state(monkeypatch):
    window = WindowInfo(1, 2, "App", "Form", 0, 0, 400, 200)
    info = ElementInfo("CheckBox", "chkOnay", "Onaylandı", "", 10, 10, 16, 16)
    state = {"value": False}
    backend = SimpleNamespace(checkbox_state=lambda w, i: state["value"],
                              toggle_checkbox=lambda w, i: state.update(value=not state["value"]))
    service = SimpleNamespace(focus=lambda target: window, elements=SimpleNamespace(backend=backend),
                              _guard=Mock(), cancel=threading.Event(), _check=Mock())
    service.cancel.wait = lambda seconds: False
    monkeypatch.setattr("rpa_orkestrai.desktop.elements.checkbox_info", lambda *a, **kw: info)
    targeting = {"target_mode": "element", "element": {}}
    assert checkbox(service, {}, None, operation="check", targeting=targeting) is True and state["value"] is True
    state["value"] = None
    with pytest.raises(WindowError, match="kısmen"):
        checkbox(service, {}, None, operation="uncheck", targeting=targeting)
    assert checkbox(service, {}, None, operation="read", targeting=targeting) is None


def test_a_non_checkbox_field_is_refused():
    from rpa_orkestrai.desktop.elements import checkbox_info

    service = SimpleNamespace(find=lambda *a, **kw: ElementInfo("Edit", "x", "Ad", "", 0, 0, 10, 10))
    with pytest.raises(WindowError, match="onay kutusu değil"):
        checkbox_info(service, None, {}, timeout=1)
