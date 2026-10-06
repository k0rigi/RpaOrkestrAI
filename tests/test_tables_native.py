"""Real Windows WPF grid: exercise UIA Grid, Table and Value COM interfaces."""
import platform
import subprocess
import time
import uuid

import pytest

from rpa_orkestrai.desktop.tables import UiaTables, resolve_cell
from rpa_orkestrai.desktop.windows import Win32Windows

pytestmark = pytest.mark.skipif(platform.system() != "Windows", reason="Windows UI Automation")


def test_native_grid_addresses_and_writes_the_requested_cell(tmp_path):
    title = "RpaOrkestrAI grid test " + uuid.uuid4().hex
    script = tmp_path / "grid.ps1"
    script.write_text('''Add-Type -AssemblyName PresentationFramework
Add-Type -AssemblyName System.Data
$window = New-Object System.Windows.Window
$window.Title = "TITLE"
$window.Width = 600
$window.Height = 350
$grid = New-Object System.Windows.Controls.DataGrid
$grid.AutoGenerateColumns = $true
$grid.CanUserAddRows = $false
$grid.IsReadOnly = $false
[System.Windows.Automation.AutomationProperties]::SetAutomationId($grid, "invoiceGrid")
$table = New-Object System.Data.DataTable
[void]$table.Columns.Add("Invoice")
[void]$table.Columns.Add("Amount")
[void]$table.Rows.Add("INV-2", "10")
[void]$table.Rows.Add("INV-1", "20")
$grid.ItemsSource = $table.DefaultView
$window.Content = $grid
[void]$window.ShowDialog()
'''.replace("TITLE", title), encoding="utf-8-sig")
    process = subprocess.Popen(["powershell.exe", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass",
                                "-File", str(script)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        windows = Win32Windows()
        deadline, found = time.monotonic() + 30, []
        while time.monotonic() < deadline:
            found = [w for w in windows.list_windows() if w.title == title]
            if found:
                break
            assert process.poll() is None, process.communicate()[1].decode(errors="replace")
            time.sleep(0.2)
        assert len(found) == 1
        window, backend = found[0], UiaTables()
        deadline, grids = time.monotonic() + 15, []
        while time.monotonic() < deadline:
            grids = backend.tables(window, lambda: None)
            if grids and grids[0].shape() == (2, 2):
                break
            time.sleep(0.2)
        assert len(grids) == 1 and grids[0].shape() == (2, 2)
        assert grids[0].headers(2) == ["Invoice", "Amount"]
        cell, row, column = resolve_cell(backend, window, table="invoiceGrid", row_mode="match", row=1,
                                         column="Amount", match_column="Invoice", match_value="INV-1", check=lambda: None, point=grids[0].info().center)
        assert (row, column) == (1, 1) and cell.read() == "20"
        assert cell.info().usable_in(window)
        cell.write("42.50", lambda: None)
        assert grids[0].cell(1, 1).read() == "42.50"
        assert grids[0].cell(0, 1).read() == "10"
    finally:
        process.terminate()
        process.communicate(timeout=15)
