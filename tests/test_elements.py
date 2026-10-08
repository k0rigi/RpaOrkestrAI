"""Structural field targeting with fake accessibility trees; no real desktop input."""

import platform
import threading
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rpa_orkestrai.desktop.elements import (
    AxElements,
    ElementInfo,
    ElementService,
    UiaElements,
    validate_locator,
)
from rpa_orkestrai.desktop.windows import WindowError, WindowInfo, WindowService

SYSTEM = platform.system()
WINDOW = WindowInfo(7, 42, "ERP", "İade Faturası", 100, 80, 800, 600)


@pytest.mark.parametrize("changed", [{"CurrentProcessId": 99}, {"CurrentHasKeyboardFocus": False},
                                     {"CurrentIsEnabled": False}])
def test_windows_focused_editor_rejects_wrong_process_or_focus(changed):
    backend = object.__new__(UiaElements)
    element = SimpleNamespace(**{"CurrentControlType": 50004, "CurrentProcessId": 42,
                                 "CurrentHasKeyboardFocus": True, "CurrentIsEnabled": True, **changed})
    backend._context = lambda: (SimpleNamespace(GetFocusedElement=lambda: element), None, None)
    with pytest.raises(WindowError, match="odağı"):
        backend.focused_editor(WINDOW)


@pytest.mark.parametrize("role,focused,enabled,writable", [("AXTextField", True, True, True),
    ("AXTextArea", True, True, True), ("AXTable", True, True, True),
    ("AXTextField", False, True, True), ("AXTextField", True, False, True),
    ("AXTextField", True, True, False)])
def test_mac_focused_editor_requires_writable_focused_text(role, focused, enabled, writable):
    backend = object.__new__(AxElements)
    backend.ax = SimpleNamespace(AXUIElementIsAttributeSettable=Mock(return_value=(0, writable)))
    editor = field(role=role, value="OLD")
    backend._application = Mock(return_value="app")
    backend._attribute = lambda element, name: {"AXFocusedUIElement": "editor", "AXRole": role,
                                                "AXFocused": focused, "AXEnabled": enabled}[name]
    backend._info = Mock(return_value=editor)
    if role == "AXTable":
        assert backend.focused_editor(WINDOW) is None
    elif not (focused and enabled and writable):
        with pytest.raises(WindowError):
            backend.focused_editor(WINDOW)
    else:
        assert backend.focused_editor(WINDOW) == editor
    backend._application.assert_called_once_with(WINDOW)


def field(**values):
    base = dict(role="Edit", automation_id="txtFormId", name="FormID", class_name="WindowsForms10.EDIT",
                x=300, y=200, width=160, height=24)
    return ElementInfo(**{**base, **values})


class FakeTree:
    def __init__(self, items, at=None):
        self.items = list(items)
        self.at = at
        self.calls = 0

    def elements(self, window, role=None):
        self.calls += 1
        return [item for item in self.items if role is None or item.role == role]

    def element_at(self, window, x, y):
        if self.at is not None:
            return self.at
        inside = [item for item in self.items if item.contains(x, y)]
        return min(inside, key=lambda item: item.width * item.height) if inside else None


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


def service(tree, clock=None, cancel=None):
    clock = clock or Clock()
    cancel = cancel or threading.Event()
    elements = ElementService(tree, cancel=cancel, clock=clock, system=SYSTEM)
    # Waiting advances the fake clock instead of sleeping.
    elements.cancel = SimpleNamespace(is_set=cancel.is_set,
                                      wait=lambda seconds: setattr(clock, "value", clock.value + seconds))
    return elements


def test_describe_uses_automation_id_and_role():
    described = service(FakeTree([field()])).describe_at(WINDOW, 310, 210)
    assert described["available"] is True and described["unique"] is True
    assert described["locator"] == {"platform": SYSTEM, "role": "Edit", "automation_id": "txtFormId",
                                    "name": "FormID", "class_name": "WindowsForms10.EDIT", "index": 0}
    assert "kimlik txtFormId" in described["summary"]


def test_name_equal_to_current_value_is_not_an_identity():
    item = field(automation_id="", name="INV-1001", value="INV-1001")
    described = service(FakeTree([item])).describe_at(WINDOW, 310, 210)
    assert described["available"] is False
    assert "kimlik veya ad" in described["reason"]


def test_duplicate_names_keep_their_order():
    first, second = field(automation_id="", y=150), field(automation_id="", y=260)
    described = service(FakeTree([first, second])).describe_at(WINDOW, 310, 265)
    assert described["locator"]["index"] == 1 and described["unique"] is False
    assert "2 alanın 2. sırası" in described["summary"]


def test_field_outside_window_or_missing_is_reported_not_raised():
    assert service(FakeTree([])).describe_at(WINDOW, 310, 210)["available"] is False
    outside = field(x=950, y=900)
    assert service(FakeTree([outside], at=outside)).describe_at(WINDOW, 960, 905)["available"] is False
    broken = Mock()
    broken.element_at.side_effect = WindowError("Erişilebilirlik izni gerekli.")
    assert service(broken).describe_at(WINDOW, 1, 1) == {"available": False, "reason": "Erişilebilirlik izni gerekli."}


def test_find_waits_for_the_field_and_skips_offscreen_copies():
    tree = FakeTree([field(offscreen=True)])
    clock = Clock()
    elements = service(tree, clock)
    locator = elements.describe_at(WINDOW, 310, 210)
    assert locator["available"] is False  # the only match is on a hidden tab

    locator = {"platform": SYSTEM, "role": "Edit", "automation_id": "txtFormId", "name": "", "index": 0}
    original = tree.elements

    def appears_later(window, role=None):
        if clock.value >= 0.5:
            tree.items = [field(offscreen=True), field(y=400)]
        return original(window, role)

    tree.elements = appears_later
    assert elements.find(WINDOW, locator, timeout=2).y == 400
    with pytest.raises(WindowError, match="Alan bulunamadı"):
        elements.find(WINDOW, {**locator, "automation_id": "missing"}, timeout=1)


@pytest.mark.parametrize("locator", [
    None, [], {"platform": SYSTEM, "automation_id": 5}, {"platform": SYSTEM, "name": "x" * 301},
    {"platform": SYSTEM, "name": "FormID", "index": -1}, {"platform": SYSTEM, "name": "FormID", "index": True},
    {"platform": SYSTEM, "name": "FormID", "extra": 1}, {"platform": SYSTEM, "role": "Edit"},
])
def test_invalid_locators_are_rejected(locator):
    with pytest.raises(WindowError):
        validate_locator(locator, SYSTEM)


def test_locator_from_another_operating_system_is_rejected():
    other = "Windows" if SYSTEM != "Windows" else "Darwin"
    with pytest.raises(WindowError, match="başka bir işletim sisteminde"):
        validate_locator({"platform": other, "automation_id": "txtFormId"}, SYSTEM)


@pytest.fixture
def windows_service():
    tree = FakeTree([field()])
    backend = SimpleNamespace(list_windows=Mock(return_value=[WINDOW]), activate=Mock(),
                              is_active=Mock(return_value=True))
    return WindowService(backend=backend, elements=service(tree)), backend, tree


def element_locator():
    return {"platform": SYSTEM, "role": "Edit", "automation_id": "txtFormId", "name": "FormID", "index": 0}


def test_element_target_clicks_field_center_and_follows_resized_window(windows_service):
    service_, backend, tree = windows_service
    desktop = Mock()
    desktop.size.return_value = (1920, 1080)
    service_.fill_target(WINDOW.result(), "INV-7", desktop, target_mode="element", element=element_locator(),
                         timeout=1)
    desktop.click.assert_called_once_with(380, 212, clicks=1, button="left")
    desktop.write.assert_called_once_with("INV-7")

    # Larger window, different layout: the same locator follows the field.
    resized = replace(WINDOW, width=1400, height=900)
    backend.list_windows.return_value = [resized]
    tree.items = [field(x=900, y=500, width=300, height=30)]
    desktop.reset_mock()
    service_.click_target(resized.result(), desktop, target_mode="element", element=element_locator(), timeout=1)
    desktop.click.assert_called_once_with(1050, 515, clicks=1, button="left")


def test_invalid_element_locator_never_focuses_or_clicks(windows_service):
    service_, backend, _ = windows_service
    desktop = Mock()
    with pytest.raises(WindowError):
        service_.click_target(WINDOW.result(), desktop, target_mode="element", element={"platform": SYSTEM})
    backend.activate.assert_not_called()
    desktop.click.assert_not_called()


def test_missing_element_stops_without_input(windows_service):
    service_, _, tree = windows_service
    tree.items = []
    desktop = Mock()
    desktop.size.return_value = (1920, 1080)
    with pytest.raises(WindowError, match="Alan bulunamadı"):
        service_.fill_target(WINDOW.result(), "INV-7", desktop, target_mode="element",
                             element=element_locator(), timeout=0.5)
    desktop.click.assert_not_called()
    desktop.write.assert_not_called()


def test_engine_passes_element_target_and_requires_it():
    from rpa_orkestrai.engine import WorkflowError, validate_workflow
    from rpa_orkestrai.models import Step, Workflow

    step = Step(action="desktop.window_fill", params={"window": "${erp_window}", "target_mode": "element",
                                                        "text": "x", "clear": True})
    with pytest.raises(WorkflowError, match="Alan kimliği gereklidir"):
        validate_workflow(Workflow(name="Akış", steps=[step]))
    step.params["element"] = element_locator()
    validate_workflow(Workflow(name="Akış", steps=[step]))
