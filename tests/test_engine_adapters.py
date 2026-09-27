"""Verify the engine calls the actual adapter interfaces, without external effects."""

import threading
from types import SimpleNamespace
from unittest.mock import Mock, create_autospec

import pytest
import sqlalchemy as sa

from rpa_orkestrai.catalog import defaults
from rpa_orkestrai.config import Settings
from rpa_orkestrai.database.reader import ReadOnlyDatabase
from rpa_orkestrai.desktop.dropdown import DropdownIterator
from rpa_orkestrai.engine import Executor
from rpa_orkestrai.integrations.sheets import SheetsService
from rpa_orkestrai.models import Run
from rpa_orkestrai.storage import Store


def executor(tmp_path):
    settings = Settings(tmp_path, dotenv=False)
    settings.update({"database_url": "postgresql+psycopg://reader:placeholder@localhost/erp",
                     "google_credentials_path": "credentials/test.json"})
    store = Store(tmp_path)
    run = Run(workflow_id="test", workflow_name="Test", department="Test")
    return Executor(settings, store, run, threading.Event(), lambda: None)


def test_database_engine_matches_real_constructor_and_methods(tmp_path, monkeypatch):
    adapter = create_autospec(ReadOnlyDatabase)
    instance = adapter.return_value
    instance.__enter__.return_value = instance
    instance.read_table.return_value = SimpleNamespace(to_json=lambda **kw: '[{"ID": 1}]')
    monkeypatch.setattr("rpa_orkestrai.database.reader.ReadOnlyDatabase", adapter)
    runner = executor(tmp_path)
    with runner.resources:
        result = runner.perform("database.read", defaults("database.read"))
    assert result == [{"ID": 1}]
    assert adapter.call_args.kwargs["timeout_seconds"] == runner.settings.action_timeout
    instance.__exit__.assert_called_once()


def test_dropdown_engine_matches_real_scan_interface(tmp_path, monkeypatch):
    adapter = create_autospec(DropdownIterator)
    adapter.return_value.scan.return_value = ["A", "B"]
    monkeypatch.setattr("rpa_orkestrai.desktop.dropdown.DropdownIterator", adapter)
    runner = executor(tmp_path)
    runner._desktop = SimpleNamespace(scroll=lambda *args, **kw: None)
    assert runner.perform("desktop.scan_dropdown", defaults("desktop.scan_dropdown")) == ["A", "B"]
    assert adapter.return_value.scan.call_args.kwargs["ocr_timeout"] == runner.settings.action_timeout


def test_sheets_engine_matches_constructor_and_raw_range_interface(tmp_path, monkeypatch):
    adapter = create_autospec(SheetsService)
    instance = adapter.return_value
    instance.__enter__.return_value = instance
    monkeypatch.setattr("rpa_orkestrai.integrations.sheets.SheetsService", adapter)
    runner = executor(tmp_path)
    parameters = {**defaults("sheets.write"), "spreadsheet_id": "sheet-id"}
    with runner.resources:
        runner.perform("sheets.write", parameters)
    instance.update_range.assert_called_once_with("A1", [["Örnek", 1]])
    instance.__exit__.assert_called_once()


@pytest.mark.parametrize("backend", ["postgresql", "mssql"])
def test_database_timeouts_are_applied_to_driver_and_queries(monkeypatch, backend):
    factory = Mock(return_value=object())
    listener = Mock()
    monkeypatch.setattr(sa, "create_engine", factory)
    monkeypatch.setattr(sa.event, "listen", listener)
    url = "postgresql://reader:placeholder@localhost/erp" if backend == "postgresql" else (
        "mssql+pyodbc://reader:placeholder@localhost/erp?driver=ODBC+Driver+18+for+SQL+Server"
    )
    database = ReadOnlyDatabase(url, {"erp.orders": None}, timeout_seconds=2.5)
    database._get_engine()
    options = factory.call_args.kwargs["connect_args"]
    assert factory.call_args.kwargs["pool_timeout"] == 2.5
    if backend == "postgresql":
        assert options["connect_timeout"] == 3
        assert "statement_timeout=2500" in options["options"]
        assert factory.call_args.args[0].drivername == "postgresql+psycopg"
    else:
        assert options["timeout"] == 3
        callback = listener.call_args.args[2]
        connection = SimpleNamespace(timeout=0)
        callback(connection, None)
        assert connection.timeout == 3
        assert listener.call_args.kwargs["insert"] is True
