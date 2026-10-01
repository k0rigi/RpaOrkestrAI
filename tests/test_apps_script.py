"""Google Sheets via Apps Script: client, the pasted script itself (run under Node) and wiring."""

import io
import json
import shutil
import subprocess
import threading

import pytest

from rpa_orkestrai.config import Settings
from rpa_orkestrai.engine import Executor, WorkflowError
from rpa_orkestrai.integrations.apps_script import (
    SCRIPT_TEMPLATE,
    AppsScriptSheets,
    _GoogleOnly,
    new_token,
    script_code,
    validate_url,
)
from rpa_orkestrai.models import Run, Step, Workflow
from rpa_orkestrai.storage import Store

URL = "https://script.google.com/macros/s/AKfycbx" + "a" * 40 + "/exec"
TOKEN = "t" * 32


class FakeSheet:
    """In-memory spreadsheet served like the deployed script would."""

    def __init__(self, rows):
        self.rows = [list(row) for row in rows]
        self.requests = []

    def open(self, request, timeout):
        body = json.loads(request.data)
        self.requests.append(body)
        if body["token"] != TOKEN:
            return Reply({"ok": False, "error": "Güvenlik anahtarı eşleşmiyor."})
        if body["action"] == "ping":
            return Reply({"ok": True, "spreadsheet": "Faturalar"})
        if body["action"] == "read":
            start, end = body["range"].split(":") if ":" in body["range"] else (body["range"], body["range"])
            first, last = int(start[1:]), int(end[1:])
            columns = range(ord(start[0]) - 65, ord(end[0]) - 64)
            return Reply({"ok": True, "values": [[self.cell(r, c) for c in columns] for r in range(first, last + 1)]})
        if body["action"] == "write":
            row, column = int(body["range"][1:]), ord(body["range"][0]) - 65
            self.set(row, column, body["values"][0][0])
            return Reply({"ok": True})
        return Reply({"ok": False, "error": "Bilinmeyen işlem"})

    def cell(self, row, column):
        try:
            return self.rows[row - 1][column]
        except IndexError:
            return ""

    def set(self, row, column, value):
        while len(self.rows) < row:
            self.rows.append([])
        while len(self.rows[row - 1]) <= column:
            self.rows[row - 1].append("")
        self.rows[row - 1][column] = value


class Reply(io.BytesIO):
    def __init__(self, payload, content_type="application/json"):
        super().__init__(payload.encode() if isinstance(payload, str) else json.dumps(payload).encode())
        self.headers = {"Content-Type": content_type}


SHEET = [["No", "Durum"], ["INV-1", "Bekliyor"], ["INV-2", "Tamamlandı"], ["INV-3", ""], ["", ""]]


def client(fake, token=TOKEN):
    return AppsScriptSheets(URL, token, "1" + "x" * 30, "Sayfa1", opener=fake, attempts=1)


def test_rows_are_read_and_status_written_through_the_script():
    fake = FakeSheet(SHEET)
    sheets = client(fake)
    rows = sheets.get_rows(start_row=2, max_rows=10, columns={"form_id": "A", "durum": "B"}, key="form_id")
    assert rows == [{"row_number": 2, "form_id": "INV-1", "durum": "Bekliyor"},
                    {"row_number": 3, "form_id": "INV-2", "durum": "Tamamlandı"},
                    {"row_number": 4, "form_id": "INV-3", "durum": ""}]
    sheets.update_cell("B2", "Tamamlandı")
    assert fake.rows[1][1] == "Tamamlandı"
    assert fake.requests[-1]["raw"] is True and fake.requests[-1]["sheet"] == "Sayfa1"
    assert sheets.get_cell("B4") is None


def test_wrong_token_html_login_and_invalid_addresses_are_explained():
    with pytest.raises(WorkflowError, match="anahtarı eşleşmiyor"):
        client(FakeSheet(SHEET), token="w" * 32).get_range("A1")

    class LoginPage:
        def open(self, request, timeout):
            return Reply("<html>Google hesabı</html>", "text/html")

    with pytest.raises(WorkflowError, match="Herkes"):
        client(LoginPage()).ping()
    for url in ("https://example.com/exec", "http://script.google.com/macros/s/" + "a" * 40 + "/exec",
                "https://script.google.com/macros/s/" + "a" * 40 + "/dev"):
        with pytest.raises(ValueError):
            validate_url(url)
    assert validate_url("https://script.google.com/a/macros/sirket.com.tr/s/" + "b" * 40 + "/exec")
    with pytest.raises(WorkflowError, match="anahtarı eksik"):
        AppsScriptSheets(URL, "", "abc", "Sayfa1", opener=FakeSheet(SHEET))


def test_redirects_only_follow_google_script_hosts():
    handler = _GoogleOnly()
    request = type("R", (), {"get_method": lambda self: "POST", "full_url": URL, "headers": {},
                             "data": b"x", "unredirected_hdrs": {}, "origin_req_host": "script.google.com",
                             "get_full_url": lambda self: URL})()
    assert handler.redirect_request(request, None, 302, "Found", {}, "https://evil.example/steal") is None


def test_token_and_code_generation():
    token = new_token()
    assert len(token) >= 24 and token != new_token()
    code = script_code(token)
    assert f'const RPA_TOKEN = "{token}";' in code and "__TOKEN__" not in code
    with pytest.raises(ValueError):
        script_code('"; alert(1); "')


def run_script(requests_, rows):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    harness = """
const rows = %(rows)s;
function range(a1) {
  const [start] = a1.split(":"); const end = a1.split(":")[1] || start;
  const r1 = +start.slice(1), r2 = +end.slice(1), c1 = start.charCodeAt(0) - 65, c2 = end.charCodeAt(0) - 65;
  return { getRow: () => r1, getColumn: () => c1 + 1,
    getDisplayValues: () => Array.from({length: r2 - r1 + 1}, (_, i) =>
      Array.from({length: c2 - c1 + 1}, (_, j) => String(((rows[r1 + i - 1] || [])[c1 + j]) ?? ""))) };
}
const sheet = { getRange: (a, b, h, w) => typeof a === "string" ? range(a) : { setValues: (values) => {
  values.forEach((row, i) => row.forEach((v, j) => { rows[a + i - 1] = rows[a + i - 1] || []; rows[a + i - 1][b + j - 1] = v; })); } },
  appendRow: (values) => rows.push(values) };
const book = { getName: () => "Faturalar", getSheetByName: (name) => name === "Sayfa1" ? sheet : null };
const SpreadsheetApp = { getActiveSpreadsheet: () => book, openById: () => book, flush: () => {} };
const LockService = { getScriptLock: () => ({ waitLock: () => {}, releaseLock: () => {} }) };
const ContentService = { MimeType: { JSON: "json" }, createTextOutput: (text) => ({ setMimeType: () => text }) };
%(script)s
const results = %(requests)s.map((body) => JSON.parse(doPost({ postData: { contents: JSON.stringify(body) } })));
console.log(JSON.stringify({ results, rows }));
""" % {"rows": json.dumps(rows), "script": script_code(TOKEN), "requests": json.dumps(requests_)}
    output = subprocess.run([node, "-e", harness], capture_output=True, text=True, encoding="utf-8", timeout=30,
                            check=True)
    return json.loads(output.stdout)


def test_the_apps_script_code_itself_reads_writes_and_guards_input():
    base = {"token": TOKEN, "spreadsheet": "abc", "sheet": "Sayfa1"}
    result = run_script([
        {**base, "action": "ping"},
        {**base, "action": "read", "range": "A2:B3"},
        {**base, "action": "write", "range": "B2", "values": [["Tamamlandı"]], "raw": True},
        {**base, "action": "write", "range": "C2", "values": [["=HACK()"]], "raw": True},
        {**base, "action": "write", "range": "D2", "values": [["0042"]], "raw": True},
        {**base, "token": "yanlis", "action": "read", "range": "A1"},
        {**base, "sheet": "Yok", "action": "read", "range": "A1"},
        {**base, "action": "sil"},
    ], [["No", "Durum"], ["INV-1", "Bekliyor"], ["INV-2", ""]])
    ping, read, write, formula, number, wrong, missing, unknown = result["results"]
    assert ping == {"ok": True, "version": 1, "spreadsheet": "Faturalar"}
    assert read["values"] == [["INV-1", "Bekliyor"], ["INV-2", ""]]
    assert write["ok"] and result["rows"][1][1] == "Tamamlandı"
    assert result["rows"][1][2] == "'=HACK()" and result["rows"][1][3] == "'0042"
    assert wrong == {"ok": False, "error": "Güvenlik anahtarı eşleşmiyor."}
    assert missing["ok"] is False and "Sayfa bulunamadı" in missing["error"]
    assert unknown["ok"] is False
    assert "SpreadsheetApp.openById" in SCRIPT_TEMPLATE


def test_workflow_steps_use_apps_script_when_selected(tmp_path, monkeypatch):
    settings = Settings(tmp_path, dotenv=False)
    settings.update({"sheets_connection": "apps_script", "sheets_script_url": URL, "sheets_script_token": TOKEN})
    fake = FakeSheet(SHEET)
    original = AppsScriptSheets.__init__

    def with_fake(self, url, token, spreadsheet, sheet, **kwargs):
        original(self, url, token, spreadsheet, sheet, opener=fake, attempts=1)

    monkeypatch.setattr(AppsScriptSheets, "__init__", with_fake)
    store = Store(tmp_path)
    run = Run(workflow_id="0" * 32, workflow_name="T", department="Genel")
    executor = Executor(settings, store, run, threading.Event(), lambda: store.save_run(run))
    sheet_url = "https://docs.google.com/spreadsheets/d/1" + "x" * 30 + "/edit"
    executor.execute(Workflow(steps=[
        Step(action="sheets.read_rows", params={"spreadsheet_id": sheet_url, "worksheet": "Sayfa1", "start_row": 2,
                                                "max_rows": 10, "columns": {"form_id": "A", "durum": "B"},
                                                "key": "form_id", "output": "sheet_rows"}),
        Step(action="control.for_each", params={"items": "${sheet_rows}", "item_name": "row"}, children=[
            Step(action="control.if", params={"left": "${row.durum}", "operator": "eq", "right": "Bekliyor"},
                 children=[Step(action="sheets.write_cell", params={
                     "spreadsheet_id": sheet_url, "worksheet": "Sayfa1", "cell": "B${row.row_number}",
                     "value": "Tamamlandı"})]),
        ]),
    ]))
    assert [row[1] for row in fake.rows[1:4]] == ["Tamamlandı", "Tamamlandı", ""]
    assert sum(1 for request in fake.requests if request["action"] == "write") == 1
