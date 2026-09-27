import sys
import threading
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from rpa_orkestrai.integrations import BrowserService, SheetsService


def test_sheets_uses_raw_named_range_update_and_does_not_open_connection():
    service = SheetsService("unused.json", "spreadsheet-id")
    worksheet = Mock()
    service._worksheet = worksheet
    service.update_cell("B2", "=SUM(A1:A4)")
    worksheet.update.assert_called_once_with(values=[["=SUM(A1:A4)"]], range_name="B2", raw=True)
    worksheet.acell.return_value.value = "sample"
    assert service.get_cell("B2") == "sample"
    with pytest.raises(ValueError):
        service.update_cell("Other!A1", "data")
    with pytest.raises(ValueError):
        service.update_range("A1", [[1], [2, 3]])


def test_sheets_retries_idempotent_updates_but_never_appends(monkeypatch):
    # No optional network dependency needs to be installed to run this test.
    requests = ModuleType("requests")
    requests.exceptions = SimpleNamespace(Timeout=TimeoutError, ConnectionError=ConnectionError)
    monkeypatch.setitem(sys.modules, "requests", requests)
    monkeypatch.setattr("rpa_orkestrai.integrations.sheets.time.sleep", Mock())
    error = RuntimeError("server temporarily unavailable")
    error.response = SimpleNamespace(status_code=503)
    service = SheetsService("unused.json", "spreadsheet-id", max_attempts=3, backoff=0)
    worksheet = Mock()
    worksheet.update.side_effect = [error, {"updatedCells": 1}]
    worksheet.append_row.side_effect = error
    service._worksheet = worksheet
    assert service.update_cell("A1", 10) == {"updatedCells": 1}
    assert worksheet.update.call_count == 2
    with pytest.raises(RuntimeError):
        service.append_row([10])
    worksheet.append_row.assert_called_once()


def test_sheets_authentication_failure_is_not_retried(monkeypatch):
    requests = ModuleType("requests")
    requests.exceptions = SimpleNamespace(Timeout=TimeoutError, ConnectionError=ConnectionError)
    monkeypatch.setitem(sys.modules, "requests", requests)
    error = RuntimeError("permission denied")
    error.response = SimpleNamespace(status_code=403)
    service = SheetsService("unused.json", "spreadsheet-id")
    operation = Mock(side_effect=error)
    with pytest.raises(RuntimeError):
        service._retry(operation)
    assert operation.call_count == 1


@pytest.fixture
def fake_playwright(monkeypatch):
    runtime = Mock()
    runtime.chromium.launch.return_value.new_context.return_value.new_page.return_value.url = "https://example.com/"
    factory = Mock()
    factory.return_value.start.return_value = runtime
    module = ModuleType("playwright.sync_api")
    module.sync_playwright = factory
    monkeypatch.setitem(sys.modules, "playwright", ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)
    return runtime


def test_browser_context_closes_on_workflow_error(fake_playwright):
    browser = fake_playwright.chromium.launch.return_value
    context = browser.new_context.return_value
    with pytest.raises(ValueError), BrowserService() as service:
        assert service.goto("https://example.com") == "https://example.com/"
        service.fill("#username", "user")
        service.click("#submit")
        raise ValueError("workflow failed")
    context.close.assert_called_once()
    browser.close.assert_called_once()
    fake_playwright.stop.assert_called_once()
    context.new_page.return_value.locator.assert_any_call("#submit")


def test_browser_partial_start_cleans_resources(fake_playwright):
    browser = fake_playwright.chromium.launch.return_value
    browser.new_context.side_effect = RuntimeError("could not create context")
    with pytest.raises(RuntimeError):
        BrowserService().start()
    browser.close.assert_called_once()
    fake_playwright.stop.assert_called_once()


def test_browser_cleanup_continues_after_context_close_failure(fake_playwright):
    service = BrowserService().start()
    fake_playwright.chromium.launch.return_value.new_context.return_value.close.side_effect = RuntimeError("closed")
    with pytest.raises(RuntimeError):
        service.close()
    fake_playwright.chromium.launch.return_value.close.assert_called_once()
    fake_playwright.stop.assert_called_once()


def test_browser_rejects_cross_thread_access_and_non_web_urls(fake_playwright):
    service = BrowserService()
    with pytest.raises(ValueError):
        service.goto("file:///etc/passwd")
    fake_playwright.chromium.launch.assert_not_called()
    service.start()
    service._owner = threading.get_ident() + 1
    with pytest.raises(RuntimeError, match="owning workflow thread"):
        service.text("body")
    service._owner = threading.get_ident()
    service.close()
