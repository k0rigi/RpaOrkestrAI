"""Macro recording: event-to-step conversion and the recording job, without real input hooks."""

import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rpa_orkestrai.desktop.recorder import Event, RecordJobs, _key, events_to_steps
from rpa_orkestrai.desktop.windows import WindowInfo
from rpa_orkestrai.engine import validate_workflow
from rpa_orkestrai.models import Workflow

ERP = WindowInfo(9, 4242, "ERP", "İade Faturası", 100, 50, 900, 700)


def key(t, name, text="", mods=()):
    return Event("key", t, key=name, text=text, modifiers=tuple(mods))


def click(t, x, y, window=ERP, button="left"):
    return [Event("mouse_down", t, x, y, button, window=window), Event("mouse_up", t + 0.05, x, y, button)]


def summary(steps):
    return [(step["action"], {k: v for k, v in step["params"].items() if k not in {"interval", "method", "timeout",
                                                                                     "on_missing", "match"}})
            for step in steps]


def test_clicks_typing_and_keys_become_window_steps():
    events = [*click(0.0, 300, 200), *[key(0.3 + i * 0.05, c.lower(), c) for i, c in enumerate("İade 42")],
              key(0.8, "backspace"), key(0.9, "enter"), key(1.0, "tab"), key(1.05, "tab"),
              key(1.2, "s", "s", ["ctrl"]), key(1.3, "tab", "", ["shift"])]
    steps = events_to_steps(events, system="Windows")
    assert summary(steps) == [
        ("desktop.find_window", {"application": "ERP", "title": "İade Faturası", "output": "pencere1"}),
        ("desktop.window_click", {"window": "${pencere1}", "target_mode": "coordinates", "x": 200, "y": 150,
                                  "clicks": 1, "button": "left"}),
        ("input.type", {"text": "İade 4"}),
        ("input.press", {"key": "enter", "presses": 1}),
        ("input.press", {"key": "tab", "presses": 2}),
        ("input.hotkey", {"keys": "mod+s"}),
        ("input.hotkey", {"keys": "shift+tab"}),
    ]
    workflow = Workflow(steps=steps)
    validate_workflow(workflow)


def test_macos_command_is_the_portable_modifier_and_ctrl_stays_ctrl():
    steps = events_to_steps([key(0, "c", "c", ["cmd"]), key(0.1, "a", "", ["ctrl"])], system="Darwin")
    assert [step["params"]["keys"] for step in steps] == ["mod+c", "ctrl+a"]


def test_double_clicks_drags_scrolls_and_waits():
    down, up = Event("mouse_down", 5.0, 10, 10), Event("mouse_up", 5.4, 400, 300)
    events = [*click(0.0, 300, 200), *click(0.2, 302, 201), *click(3.0, 500, 400, window=None, button="right"),
              down, up, Event("scroll", 6.0, 50, 60, dy=-2), Event("scroll", 6.2, 50, 60, dy=-3)]
    steps = events_to_steps(events, system="Windows")
    actions = [(step["action"], step["params"].get("clicks"), step["params"].get("seconds"),
                step["params"].get("amount")) for step in steps]
    assert actions == [
        ("desktop.find_window", None, None, None), ("desktop.window_click", 2, None, None),
        ("core.wait", None, 2.8, None), ("input.mouse_click", 1, None, None),
        ("core.wait", None, 2.0, None), ("input.drag", None, None, None), ("input.scroll", None, None, -5),
    ]
    assert steps[3]["params"]["button"] == "right"
    assert [step["action"] for step in events_to_steps(events, system="Windows", record_waits=False)].count(
        "core.wait") == 0
    validate_workflow(Workflow(steps=steps))


def test_screen_coordinates_when_windows_are_not_used():
    steps = events_to_steps(click(0, 300, 200), system="Windows", relative_windows=False)
    assert summary(steps) == [("input.mouse_click", {"x": 300, "y": 200, "button": "left", "clicks": 1})]


def test_same_window_is_recognized_once_and_unknown_keys_are_skipped():
    events = [*click(0, 300, 200), *click(1, 310, 220), key(1.1, "menu"), key(1.2, "media_play_pause")]
    steps = events_to_steps(events, system="Windows")
    assert [step["action"] for step in steps].count("desktop.find_window") == 1
    assert all(step["action"] != "input.press" for step in steps)


def test_pynput_keys_are_normalized(monkeypatch):
    monkeypatch.setattr("rpa_orkestrai.desktop.recorder.platform.system", lambda: "Windows")
    assert _key(SimpleNamespace(name="shift_r")) == ("shift", "")
    assert _key(SimpleNamespace(name="page_down")) == ("pagedown", "")
    assert _key(SimpleNamespace(name="space")) == ("space", " ")
    assert _key(SimpleNamespace(char="Ş", vk=None)) == ("ş", "Ş")
    assert _key(SimpleNamespace(char="\x03", vk=67)) == ("c", "")


class FakeSource:
    def __init__(self, events):
        self.events = events
        self.stopped = False

    def start(self, events, stop, clock):
        for event in self.events:
            events.put(event)

        def finish():
            time.sleep(0.3)
            stop.set()

        threading.Thread(target=finish, daemon=True).start()

    def stop(self):
        self.stopped = True


def wait_done(jobs, key):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = jobs.status(key)
        if status["status"] in {"completed", "cancelled", "error"}:
            return status
        time.sleep(0.02)
    pytest.fail("recording did not finish")


def test_recording_job_ignores_studio_windows_and_releases_the_desktop():
    own = WindowInfo(1, os.getpid(), "RpaOrkestrAI", "Studio", 0, 0, 200, 200)
    raw = [Event("mouse_down", 1.0, 50, 50), Event("mouse_up", 1.05, 50, 50),
           Event("mouse_down", 1.2, 300, 200), Event("mouse_up", 1.25, 300, 200), key(1.4, "a", "a")]
    source = FakeSource(raw)
    windows = Mock()
    windows.list_windows.return_value = [own, ERP]
    manager = Mock()
    manager.reserve_desktop.return_value = "token"
    jobs = RecordJobs(manager, source_factory=lambda: source, windows_factory=lambda: windows,
                      permissions=lambda: None)
    started = jobs.start(delay=1)
    assert started["status"] == "starting"
    with pytest.raises(RuntimeError, match="sürüyor"):
        jobs.start(delay=1)
    result = wait_done(jobs, started["id"])
    assert result["status"] == "completed", result
    assert [step["action"] for step in result["result"]["steps"]] == [
        "desktop.find_window", "desktop.window_click", "input.type"]
    assert source.stopped
    manager.release_desktop.assert_called_once_with("token")


def test_recording_can_be_cancelled_during_countdown():
    manager = Mock()
    jobs = RecordJobs(manager, source_factory=lambda: FakeSource([]), permissions=lambda: None)
    started = jobs.start(delay=5)
    jobs.cancel(started["id"])
    assert wait_done(jobs, started["id"])["status"] == "cancelled"
    manager.release_desktop.assert_called_once()


def test_recording_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    with TestClient(create_app(Settings(tmp_path, dotenv=False))) as client:
        records = client.app.state.records
        records.permissions = lambda: None
        records.source_factory = lambda: FakeSource(click(1.0, 300, 200, None))
        records.windows_factory = None
        started = client.post("/api/desktop/record", json={"delay": 1}).json()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status = client.get(f"/api/desktop/record/{started['id']}").json()
            if status["status"] == "completed":
                break
            time.sleep(0.05)
        assert [step["action"] for step in status["result"]["steps"]] == ["input.mouse_click"]
        assert client.post("/api/desktop/record", json={"delay": 11}).status_code == 422
