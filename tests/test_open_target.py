"""Launch shortcuts without dropping their arguments or working directory."""

import json
import platform
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rpa_orkestrai.actions import system
from rpa_orkestrai.desktop import path_picker
from rpa_orkestrai.errors import WorkflowError


@pytest.mark.parametrize("target,arguments", [
    (r"C:\Users\Ayşe\Desktop\Canias ERP.lnk", ""),
    (r"C:\Canias ERP\başlat.jnlp", ""),
    (r"C:\Program Files (x86)\Java\bin\javaws.exe",
     r'-localfile -J-Djnlp.application.href="https://erp.example/app.jnlp" "C:\Canias ERP\app.jnlp"'),
    (r"C:\ERP\erp.exe", r'--folder="C:\Ortak Alan\" --name "Ayşe Çelik"'),
    ("www.example.com", ""),
])
def test_windows_launch_preserves_target_and_raw_arguments(monkeypatch, target, arguments):
    start = Mock()
    monkeypatch.setattr(system.platform, "system", lambda: "Windows")
    monkeypatch.setattr(system.os, "startfile", start, raising=False)
    ctx = Mock()
    system.open_target(ctx, {"target": target, "arguments": arguments, "wait": 3})
    expected = "https://www.example.com" if target.startswith("www.") else target
    start.assert_called_once_with(*([expected, "open", arguments] if arguments else [expected]))
    ctx.wait.assert_called_once_with(3)


@pytest.mark.parametrize("target", [r"C:\Program Files (x86)\Java\bin\javaws.exe", "JAVAWS.EXE", "javaws"])
def test_bare_javaws_explains_how_to_launch_canias(monkeypatch, target):
    start = Mock()
    monkeypatch.setattr(system.os, "startfile", start, raising=False)
    with pytest.raises(WorkflowError, match="Canias kısayolunu"):
        system.open_target(Mock(), {"target": target, "arguments": "  "})
    start.assert_not_called()


def test_windows_launch_failure_stops_before_waiting(monkeypatch):
    monkeypatch.setattr(system.platform, "system", lambda: "Windows")
    monkeypatch.setattr(system.os, "startfile", Mock(side_effect=OSError("missing")), raising=False)
    ctx = Mock()
    with pytest.raises(WorkflowError, match="açılamadı"):
        system.open_target(ctx, {"target": r"C:\missing.lnk"})
    ctx.wait.assert_not_called()


@pytest.mark.parametrize("result,expected", [(1, r"C:\Desktop\Canias.lnk"), (0, None)])
def test_shortcut_selection_runs_on_ui_thread_and_disposes(monkeypatch, result, expected):
    monkeypatch.setattr(path_picker.platform, "system", lambda: "Windows")
    monkeypatch.setitem(sys.modules, "System", SimpleNamespace(Action=lambda callback: callback))
    monkeypatch.setitem(sys.modules, "System.Windows.Forms", SimpleNamespace(DialogResult=SimpleNamespace(OK=1)))
    dialog = Mock(FileName=r"C:\Desktop\Canias.lnk")
    dialog.ShowDialog.return_value = result
    monkeypatch.setattr(path_picker, "_windows_launch_dialog", lambda: dialog)
    window = Mock()
    window.native.Invoke.side_effect = lambda callback: callback()
    assert path_picker.choose_path(Mock(), window, "open", preserve_shortcuts=True) == expected
    window.native.Invoke.assert_called_once()
    dialog.ShowDialog.assert_called_once_with(window.native)
    dialog.Dispose.assert_called_once()
    window.create_file_dialog.assert_not_called()


@pytest.mark.parametrize("os_name,kind,preserve", [
    ("Darwin", "open", True), ("Windows", "open", False),
    ("Windows", "folder", True), ("Windows", "save", True),
])
def test_other_file_pickers_keep_their_behavior(monkeypatch, os_name, kind, preserve):
    monkeypatch.setattr(path_picker.platform, "system", lambda: os_name)
    window = Mock()
    window.create_file_dialog.return_value = ("selected",)
    webview = SimpleNamespace(FileDialog=SimpleNamespace(OPEN=10, FOLDER=20, SAVE=30))
    assert path_picker.choose_path(webview, window, kind, preserve_shortcuts=preserve) == "selected"
    window.create_file_dialog.assert_called_once_with({"open": 10, "folder": 20, "save": 30}[kind])
    window.create_file_dialog.return_value = None
    assert path_picker.choose_path(webview, window, kind, preserve_shortcuts=preserve) is None


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows Forms configuration")
def test_real_windows_dialog_preserves_shortcuts():
    dialog = path_picker._windows_launch_dialog()
    try:
        assert not dialog.DereferenceLinks
        assert not dialog.Multiselect
        assert dialog.RestoreDirectory
        assert dialog.CheckFileExists
    finally:
        dialog.Dispose()


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows ShellExecute shortcut integration")
def test_real_windows_shortcut_preserves_arguments_and_working_directory(tmp_path):
    import comtypes.client
    from comtypes.persist import IPersistFile
    from comtypes.shelllink import IShellLinkW, ShellLink

    folder = tmp_path / "Canias test alanı"
    folder.mkdir()
    output = folder / "result.json"
    script = folder / "capture.py"
    script.write_text("import json, os, sys\nfrom pathlib import Path\n"
                      "Path('result.json').write_text(json.dumps([sys.argv[1:], os.getcwd()]), encoding='utf-8')\n")
    shortcut = folder / "Canias test.lnk"
    # WScript.Shell uses ANSI paths/arguments; the fixture must preserve Turkish
    # text independently of the runner's Windows locale, just like Explorer does.
    link = comtypes.client.CreateObject(ShellLink, interface=IShellLinkW)
    link.SetPath(sys.executable)
    link.SetArguments(subprocess.list2cmdline([str(script), "Ayşe Çelik", "https://erp.example/app.jnlp"]))
    link.SetWorkingDirectory(str(folder))
    link.QueryInterface(IPersistFile).Save(str(shortcut), True)
    system.open_target(Mock(), {"target": str(shortcut), "wait": 0})
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            result = json.loads(output.read_text(encoding="utf-8"))
            break
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(0.05)
    else:
        pytest.fail("Kısayol hedefi başlatılamadı veya parametreleri kayboldu.")
    assert result == [["Ayşe Çelik", "https://erp.example/app.jnlp"], str(folder)]
