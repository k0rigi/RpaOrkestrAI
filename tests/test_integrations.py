import sys
import threading
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from rpa_orkestrai.integrations import BrowserService, SheetsService
from rpa_orkestrai.integrations.sheets import normalize_spreadsheet_id


@pytest.mark.parametrize("value", [
    "sheet-ID_123",
    "  sheet-ID_123\n",
    "https://docs.google.com/spreadsheets/d/sheet-ID_123",
    "https://docs.google.com/spreadsheets/d/sheet-ID_123/",
    "https://docs.google.com/spreadsheets/d/sheet-ID_123/edit?gid=42#gid=42",
    "https://docs.google.com/spreadsheets/u/0/d/sheet-ID_123/edit?usp=sharing",
    "https://DOCS.GOOGLE.COM:443/spreadsheets/d/sheet-ID_123/view",
    "https://docs.google.com/spreadsheets/d/sheet-ID_123/copy",
])
def test_sheets_normalizes_id_and_google_sharing_urls_without_connecting(value):
    assert normalize_spreadsheet_id(value) == "sheet-ID_123"
    service = SheetsService("nonexistent-credentials.json", value)
    assert service.spreadsheet_id == "sheet-ID_123"
    assert service._worksheet is None


@pytest.mark.parametrize("value", [
    None, 42, "", "  ", "sheet id", "sheet/id",
    "http://docs.google.com/spreadsheets/d/sheet-ID_123/edit",
    "https://example.com/spreadsheets/d/sheet-ID_123/edit",
    "https://docs.google.com.evil.example/spreadsheets/d/sheet-ID_123/edit",
    "https://user@docs.google.com/spreadsheets/d/sheet-ID_123/edit",
    "https://user:password@docs.google.com/spreadsheets/d/sheet-ID_123/edit",
    "https://docs.google.com:8443/spreadsheets/d/sheet-ID_123/edit",
    "https://docs.google.com:not-a-port/spreadsheets/d/sheet-ID_123/edit",
    "https://docs.google.com/spreadsheets/d//edit",
    "https://docs.google.com/document/d/sheet-ID_123/edit",
    "https://docs.google.com/spreadsheets/d/sheet-ID_123/edit/extra",
    "https://docs.google.com/spreadsheets/d/sheet%2FID_123/edit",
    "https://docs.google.com/spreadsheets/d/sheet-ID_123/../other",
    "https://docs.google.com/spreadsheets/d/sheet-ID_123/ed\nit",
    "https://docs.google.com/spreadsheets/d/sheet-ID_123/edit\x00",
    "https://[docs.google.com/spreadsheets/d/sheet-ID_123/edit",
])
def test_sheets_rejects_malformed_or_untrusted_urls(value):
    with pytest.raises(ValueError, match="Google spreadsheet"):
        SheetsService("nonexistent-credentials.json", value)


def test_sheets_column_keeps_formatted_ids_and_reads_a_bounded_range_once():
    service = SheetsService("unused.json", "sheet-id")
    worksheet = Mock()
    worksheet.get.return_value = [["00125"], ["123,45"], [" 00026 "]]
    service._worksheet = worksheet
    assert service.get_column() == [
        {"row_number": 2, "cell": "B2", "value": "00125"},
        {"row_number": 3, "cell": "B3", "value": "123,45"},
        {"row_number": 4, "cell": "B4", "value": " 00026 "},
    ]
    worksheet.get.assert_called_once_with("B2:B101", value_render_option="FORMATTED_VALUE")


@pytest.mark.parametrize("blank", [[], [""], [" \t "], [None]])
def test_sheets_column_stops_at_first_blank(blank):
    service = SheetsService("unused.json", "sheet-id")
    worksheet = Mock()
    worksheet.get.return_value = [["00125"], blank, ["later"]]
    service._worksheet = worksheet
    assert service.get_column("$b$2", max_rows=3, empty_policy="stop") == [
        {"row_number": 2, "cell": "B2", "value": "00125"},
    ]
    worksheet.get.assert_called_once_with("B2:B4", value_render_option="FORMATTED_VALUE")


def test_sheets_column_skips_blanks_without_renumbering_and_preserves_zero():
    service = SheetsService("unused.json", "sheet-id")
    worksheet = Mock()
    worksheet.get.return_value = [[], ["00125"], [""], [" \t "], [None], [0], ["0"]]
    service._worksheet = worksheet
    assert service.get_column("AA9", max_rows=10, empty_policy="skip") == [
        {"row_number": 10, "cell": "AA10", "value": "00125"},
        {"row_number": 14, "cell": "AA14", "value": "0"},
        {"row_number": 15, "cell": "AA15", "value": "0"},
    ]
    worksheet.get.assert_called_once_with("AA9:AA18", value_render_option="FORMATTED_VALUE")


@pytest.mark.parametrize("rows, policy", [([], "stop"), ([], "skip"), ([[], ["  "]], "skip")])
def test_sheets_empty_column_returns_no_records(rows, policy):
    service = SheetsService("unused.json", "sheet-id")
    service._worksheet = Mock()
    service._worksheet.get.return_value = rows
    assert service.get_column(empty_policy=policy) == []


@pytest.mark.parametrize("kwargs", [
    {"start_cell": "B0"}, {"start_cell": "B2:B99"}, {"start_cell": "Faturalar!B2"},
    {"start_cell": "B"}, {"start_cell": None},
    {"max_rows": 0}, {"max_rows": -1}, {"max_rows": 1001}, {"max_rows": True},
    {"max_rows": "100"}, {"max_rows": 1.0},
    {"empty_policy": "keep"}, {"empty_policy": None},
])
def test_sheets_column_validates_all_inputs_before_connecting(kwargs):
    service = SheetsService("unused.json", "sheet-id")
    service._connect = Mock(side_effect=AssertionError("must validate before connecting"))
    with pytest.raises(ValueError):
        service.get_column(**kwargs)
    service._connect.assert_not_called()


@pytest.mark.parametrize("max_rows, expected_range", [(1, "B2:B2"), (1000, "B2:B1001")])
def test_sheets_column_limits_apply_to_physical_rows(max_rows, expected_range):
    service = SheetsService("unused.json", "sheet-id")
    service._worksheet = Mock()
    # Even an unexpectedly oversized adapter response cannot expand the loop.
    service._worksheet.get.return_value = [[str(index)] for index in range(max_rows + 1)]
    result = service.get_column(max_rows=max_rows, empty_policy="skip")
    assert len(result) == max_rows
    assert result[-1]["row_number"] == max_rows + 1
    service._worksheet.get.assert_called_once_with(expected_range, value_render_option="FORMATTED_VALUE")


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
