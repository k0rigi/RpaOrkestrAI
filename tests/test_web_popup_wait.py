"""Popup intent waiting never repeats a click or continues on the wrong page."""

import threading
from types import SimpleNamespace

import pytest

from rpa_orkestrai.errors import WorkflowError
from rpa_orkestrai.integrations import web_session
from rpa_orkestrai.integrations.web_session import Target, WebSession


@pytest.fixture
def popup_runtime(tmp_path, monkeypatch):
    clock, cancel = SimpleNamespace(now=0.0), threading.Event()
    monkeypatch.setattr(web_session, "time", SimpleNamespace(monotonic=lambda: clock.now))
    state = SimpleNamespace(clicks=0, intents=0, arrivals=[], waits=[], cancel_at=None, detached=False,
                            enable_failure=False)
    listeners, popup_listeners = {}, []

    class Client:
        def on(self, name, callback):
            listeners[name] = callback

        def send(self, name):
            assert name == "Page.enable"
            if state.enable_failure:
                from playwright.sync_api import Error

                raise Error("session unavailable")

        def detach(self):
            state.detached = True

    class Page:
        def is_closed(self):
            return False

        def on(self, name, callback):
            assert name == "popup"
            popup_listeners.append(callback)

        def remove_listener(self, name, callback):
            assert name == "popup"
            popup_listeners.remove(callback)

        def wait_for_timeout(self, milliseconds):
            assert milliseconds >= 0
            state.waits.append(milliseconds)
            clock.now += milliseconds / 1000
            if state.cancel_at is not None and clock.now >= state.cancel_at:
                cancel.set()
            while state.arrivals and state.arrivals[0] <= clock.now + 1e-9:
                state.arrivals.pop(0)
                for callback in tuple(popup_listeners):
                    callback(object())

    class Item:
        def evaluate(self, source):
            return False

        def click(self, **kwargs):
            state.clicks += 1
            for _ in range(state.intents):
                listeners["Page.windowOpen"]({"url": "https://ignored.invalid", "windowName": ""})

    session = WebSession(tmp_path / "profile", timeout_ms=15_000, cancel=cancel)
    session._page = Page()
    session._context = SimpleNamespace(new_cdp_session=lambda page: Client())
    monkeypatch.setattr(session, "single", lambda target: Item())
    return SimpleNamespace(session=session, state=state, clock=clock, cancel=cancel, listeners=popup_listeners)


def test_normal_click_does_not_wait_for_the_full_popup_timeout(popup_runtime):
    value = popup_runtime
    value.session.click(Target("button", "Kaydet", timeout_ms=15_000))
    assert value.state.clicks == 1 and value.state.waits == [150]
    assert value.state.detached and not value.listeners


@pytest.mark.parametrize("arrivals", [[0.6], [0.1, 0.6]])
def test_observed_windows_wait_for_each_popup_once_and_release_listener(popup_runtime, arrivals):
    value = popup_runtime
    value.state.intents = len(arrivals)
    value.state.arrivals = list(arrivals)
    value.session.click(Target("button", "Aç", timeout_ms=1000))
    assert value.state.clicks == 1 and not value.state.arrivals
    assert value.clock.now == pytest.approx(0.6)
    assert max(value.state.waits) <= 50
    assert value.state.detached and not value.listeners


def test_pending_popup_timeout_fails_without_a_second_click(popup_runtime):
    value = popup_runtime
    value.state.intents = 1
    with pytest.raises(WorkflowError, match="Yeni sekme.*süre doldu"):
        value.session.click(Target("button", "Aç", timeout_ms=250))
    assert value.state.clicks == 1 and value.clock.now == pytest.approx(0.25)
    assert value.state.detached and not value.listeners


def test_pending_popup_wait_honors_cancellation_without_a_second_click(popup_runtime):
    value = popup_runtime
    value.state.intents, value.state.cancel_at = 1, 0.1
    with pytest.raises(InterruptedError, match="iptal"):
        value.session.click(Target("button", "Aç", timeout_ms=15_000))
    assert value.state.clicks == 1 and value.clock.now == pytest.approx(0.1)
    assert value.state.detached and not value.listeners


def test_observer_failure_stops_before_clicking(popup_runtime):
    value = popup_runtime
    value.state.enable_failure = True
    with pytest.raises(WorkflowError, match="Tıklanamadı"):
        value.session.click(Target("button", "Aç"))
    assert value.state.clicks == 0 and value.state.detached and not value.listeners


def test_already_cancelled_stops_before_clicking(popup_runtime):
    value = popup_runtime
    value.cancel.set()
    with pytest.raises(InterruptedError, match="iptal"):
        value.session.click(Target("button", "Aç"))
    assert value.state.clicks == 0 and value.state.detached and not value.listeners
