import json
import sys
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from urllib.error import HTTPError, URLError

import pytest

from rpa_orkestrai.config import Settings
from rpa_orkestrai.instance import StartupError, existing_instance, identity
from rpa_orkestrai.native import open_window, serve_native


def test_connection_env_is_loaded_from_launch_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RPA_DATABASE_URL", raising=False)
    # Track the variable so monkeypatch also restores load_dotenv's mutation.
    monkeypatch.setenv("RPA_DATABASE_URL", "")
    monkeypatch.delenv("RPA_DATABASE_URL")
    (tmp_path / ".env").write_text("RPA_DATABASE_URL=postgresql://example.invalid/demo\n")
    settings = Settings(tmp_path / "data")
    assert settings.get("database_url") == "postgresql://example.invalid/demo"


def mock_opener(monkeypatch, *, metadata=None, failure=None):
    response = Mock()
    response.read.return_value = json.dumps(metadata).encode()
    opener = MagicMock()
    opener.open.return_value.__enter__.return_value = response
    opener.open.side_effect = failure
    monkeypatch.setattr("rpa_orkestrai.instance.build_opener", Mock(return_value=opener))
    return opener


def test_probe_reuses_only_matching_workspace(monkeypatch, tmp_path):
    opener = mock_opener(monkeypatch, metadata=identity(tmp_path))
    assert existing_instance("http://127.0.0.1:8765", tmp_path)
    opener.open.assert_called_once_with("http://127.0.0.1:8765/api/instance", timeout=2)
    mock_opener(monkeypatch, metadata=identity(tmp_path / "different"))
    with pytest.raises(StartupError, match="farklı"):
        existing_instance("http://127.0.0.1:8765", tmp_path)


@pytest.mark.parametrize("failure", [
    HTTPError("http://127.0.0.1:8765/api/instance", 404, "missing", {}, None),
    URLError(TimeoutError()),
])
def test_probe_does_not_treat_another_server_or_timeout_as_a_free_port(monkeypatch, tmp_path, failure):
    mock_opener(monkeypatch, failure=failure)
    with pytest.raises(StartupError):
        existing_instance("http://127.0.0.1:8765", tmp_path)


def test_probe_distinguishes_connection_refused(monkeypatch, tmp_path):
    mock_opener(monkeypatch, failure=URLError(ConnectionRefusedError()))
    assert not existing_instance("http://127.0.0.1:8765", tmp_path)


def test_attach_opens_gui_on_main_thread_without_constructing_a_server(monkeypatch, tmp_path):
    monkeypatch.setattr("rpa_orkestrai.native.existing_instance", Mock(return_value=True))
    gui = SimpleNamespace()
    monkeypatch.setitem(sys.modules, "webview", gui)
    server_factory = Mock(side_effect=AssertionError("Must not create a second backend"))
    monkeypatch.setattr("uvicorn.Server", server_factory)
    calls = []
    monkeypatch.setattr("rpa_orkestrai.native.open_window",
                        lambda *args, **kwargs: calls.append((args, kwargs, threading.current_thread())))
    settings = Settings(tmp_path, dotenv=False)
    serve_native(settings)
    # The window only attaches: it neither guards closing nor takes the countdown of another process.
    assert calls == [((gui, f"http://127.0.0.1:{settings.port}"), {"minimized": False}, threading.main_thread())]
    server_factory.assert_not_called()


def test_new_native_window_stops_only_its_own_server(monkeypatch, tmp_path):
    monkeypatch.setattr("rpa_orkestrai.native.existing_instance", Mock(return_value=False))
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace())
    monkeypatch.setattr("rpa_orkestrai.app.create_app", Mock())
    finished = threading.Event()

    class FakeServer:
        started = False
        should_exit = False

        def run(self):
            self.started = True
            # simulate cooperative server shutdown, without binding a socket
            while not self.should_exit:
                finished.wait(0.01)
            finished.set()

    server = FakeServer()
    monkeypatch.setattr("uvicorn.Server", Mock(return_value=server))
    monkeypatch.setattr("rpa_orkestrai.native.open_window", Mock(side_effect=ValueError("window failed")))
    with pytest.raises(ValueError, match="window failed"):
        serve_native(Settings(tmp_path, dotenv=False))
    assert server.should_exit
    assert finished.is_set()


def test_startup_failure_is_reported_without_waiting_full_deadline(monkeypatch, tmp_path):
    monkeypatch.setattr("rpa_orkestrai.native.existing_instance", Mock(return_value=False))
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace())
    monkeypatch.setattr("rpa_orkestrai.app.create_app", Mock())
    server = SimpleNamespace(started=False, should_exit=False, run=Mock(side_effect=SystemExit(1)))
    monkeypatch.setattr("uvicorn.Server", Mock(return_value=server))
    window = Mock()
    monkeypatch.setattr("rpa_orkestrai.native.open_window", window)
    with pytest.raises(StartupError, match="Sunucu başlatılamadı"):
        serve_native(Settings(tmp_path, dotenv=False))
    window.assert_not_called()
    assert server.should_exit


def test_native_window_enables_report_downloads():
    gui = SimpleNamespace(settings={}, create_window=MagicMock(), start=Mock())
    open_window(gui, "http://127.0.0.1:8765")
    assert gui.settings["ALLOW_DOWNLOADS"] is True
    gui.start.assert_called_once()


class Hook:
    """window.events.<name> of pywebview: handlers are added with +=."""

    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self):
        for handler in self.handlers:
            handler()


def test_window_asks_before_closing_only_while_a_schedule_is_on(monkeypatch, tmp_path):
    import time

    from rpa_orkestrai import native
    from rpa_orkestrai.models import Schedule
    from rpa_orkestrai.scheduler import ScheduleBook

    monkeypatch.setattr(native, "GUARD_INTERVAL", 0.02)
    window = MagicMock()
    for name in ("closed", "loaded", "minimized", "restored", "maximized"):
        setattr(window.events, name, Hook())
    gui = SimpleNamespace(settings={}, create_window=MagicMock(return_value=window), start=Mock())
    settings = Settings(tmp_path, dotenv=False)
    open_window(gui, "http://127.0.0.1:8765", minimized=True, settings=settings)
    options = gui.create_window.call_args.kwargs
    assert options["minimized"] is True
    assert options["localization"]["global.quitConfirmation"].startswith("Zamanlanmış akışlar yalnız Studio açıkken")

    def settles(expected):
        deadline = time.monotonic() + 3
        while window.confirm_close is not expected and time.monotonic() < deadline:
            time.sleep(0.01)
        return window.confirm_close is expected

    assert settles(False)
    ScheduleBook(settings.data_dir).add(Schedule(workflow_id="a" * 32))
    assert settles(True)
    window.events.closed.fire()

    # Started minimized at login: the countdown restores the window; a maximized one only comes forward.
    settings.bring_to_front()
    assert window.restore.call_count == 1 and window.show.call_count == 1 and window.on_top is True
    window.events.maximized.fire()
    settings.bring_to_front()
    assert window.restore.call_count == 1 and window.show.call_count == 2

    window.minimize.side_effect = window.events.minimized.fire
    settings.prepare_run(threading.Event())
    window.minimize.assert_called_once()
    assert window.on_top is False
    assert window.restore.call_count == 1 and window.show.call_count == 2


def test_run_minimizing_waits_for_native_event(monkeypatch):
    from rpa_orkestrai import native

    minimized, cancel = threading.Event(), threading.Event()
    calls = []
    window = Mock()
    window.minimize.side_effect = lambda: calls.append("minimize")

    def wait(seconds):
        if seconds == 0.05:
            calls.append("native event")
            minimized.set()
        else:
            calls.append("settled")
        return False

    monkeypatch.setattr(cancel, "wait", wait)
    native.minimize_for_run(window, minimized, cancel)
    assert calls == ["minimize", "native event", "settled"]
    assert window.on_top is False
    window.restore.assert_not_called()
    window.show.assert_not_called()


@pytest.mark.parametrize("failure", ["timeout", "error", "cancel", "already_cancelled"])
def test_minimize_failure_or_cancellation_never_continues(monkeypatch, failure):
    from rpa_orkestrai import native
    from rpa_orkestrai.errors import Cancelled, WorkflowError

    minimized, cancel = threading.Event(), threading.Event()
    window = Mock()
    monkeypatch.setattr(native, "MINIMIZE_TIMEOUT", 0)
    if failure == "error":
        window.minimize.side_effect = RuntimeError("native failure")
    elif failure == "cancel":
        window.minimize.side_effect = cancel.set
    elif failure == "already_cancelled":
        cancel.set()
    with pytest.raises(Cancelled if "cancel" in failure else WorkflowError):
        native.minimize_for_run(window, minimized, cancel)
    if failure == "already_cancelled":
        window.minimize.assert_not_called()
    window.restore.assert_not_called()


def test_already_minimized_studio_can_start_without_another_native_event(monkeypatch):
    from rpa_orkestrai import native

    minimized, cancel = threading.Event(), threading.Event()
    minimized.set()
    monkeypatch.setattr(cancel, "wait", lambda seconds: False)
    window = Mock()
    native.minimize_for_run(window, minimized, cancel)
    window.minimize.assert_called_once()


def test_gui_uses_free_port_and_rediscovers_it_without_touching_other_server(monkeypatch, tmp_path):
    import socket
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.request import ProxyHandler, build_opener

    other_identity = identity(tmp_path / "other-workspace")

    class OtherStudio(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(other_identity).encode())

        def log_message(self, *_):
            pass

    other = ThreadingHTTPServer(("127.0.0.1", 0), OtherStudio)
    worker = threading.Thread(target=other.serve_forever, daemon=True)
    worker.start()
    original_port = other.server_address[1]
    monkeypatch.setitem(sys.modules, "webview", SimpleNamespace())
    settings = Settings(tmp_path / "installed", dotenv=False)
    settings.port = original_port
    opener = build_opener(ProxyHandler({}))
    windows = []

    def window(_gui, url, **_options):
        windows.append(url)
        with opener.open(url + "/api/instance", timeout=5) as response:
            assert json.load(response) == identity(settings.data_dir)
        assert url != f"http://127.0.0.1:{original_port}"
        if len(windows) == 1:
            # A second launch must find the first process's alternate port.
            second = Settings(settings.data_dir, dotenv=False)
            second.port = original_port
            serve_native(second, auto_port=True)

    monkeypatch.setattr("rpa_orkestrai.native.open_window", window)
    # A stale hint that points to another workspace must also be rejected.
    (settings.data_dir / ".native-instance.json").write_text(json.dumps({
        "identity": identity(settings.data_dir), "port": original_port,
    }))
    try:
        serve_native(settings, auto_port=True)
        assert len(windows) == 2 and windows[0] == windows[1]
        # Windows may time out rather than refuse a connection to a closed port.
        with socket.socket() as closed_probe:
            closed_probe.settimeout(0.5)
            assert closed_probe.connect_ex(("127.0.0.1", settings.port)) != 0
        with opener.open(f"http://127.0.0.1:{original_port}/api/instance", timeout=5) as response:
            assert json.load(response) == other_identity
    finally:
        other.shutdown()
        other.server_close()
        worker.join(timeout=5)


def test_command_line_keeps_explicit_port_conflict_error(monkeypatch, tmp_path):
    monkeypatch.setattr("rpa_orkestrai.native.existing_instance",
                        Mock(side_effect=StartupError("Port kullanımda")))
    with pytest.raises(StartupError, match="Port kullanımda"):
        serve_native(Settings(tmp_path, dotenv=False))
