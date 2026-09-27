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
                        lambda *args: calls.append((args, threading.current_thread())))
    settings = Settings(tmp_path, dotenv=False)
    serve_native(settings)
    assert calls == [((gui, f"http://127.0.0.1:{settings.port}"), threading.main_thread())]
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
