"""Dosya / script çalıştır: a script or program in a folder runs the way its kind needs, on both platforms."""

import platform
import sys
import threading
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from rpa_orkestrai.actions import system
from rpa_orkestrai.config import Settings
from rpa_orkestrai.engine import Executor, WorkflowError
from rpa_orkestrai.errors import Cancelled
from rpa_orkestrai.models import Run, Step, Workflow
from rpa_orkestrai.storage import Store

WINDOWS = platform.system() == "Windows"


@pytest.fixture
def runner(tmp_path):
    settings = Settings(tmp_path / "data", dotenv=False)
    store = Store(settings.data_dir)
    run = Run(workflow_id="0" * 32, workflow_name="Test", department="Genel")
    return Executor(settings, store, run, threading.Event(), lambda: store.save_run(run))


def go(runner, **params):
    runner.execute(Workflow(steps=[Step(action="system.run_file", params={"output": "script", **params})]))
    return runner.variables["script"]


@pytest.fixture
def python_found(monkeypatch):
    # The Python that runs the tests stands in for the one installed on the computer.
    monkeypatch.setattr(system, "find_program", lambda *names: sys.executable if names[0] != "py" else None)


def test_a_python_script_runs_in_its_folder_with_values_and_its_output_is_kept(runner, tmp_path, python_found):
    folder = tmp_path / "Masaüstü scriptleri"
    folder.mkdir()
    script = folder / "aktar.py"
    script.write_text("import os, sys\nprint('Merhaba', sys.argv[1], sys.argv[2])\nprint(os.path.basename(os.getcwd()))\n",
                      encoding="utf-8")
    result = go(runner, path=str(script), arguments='"Ayşe Çelik" 42')
    assert result["code"] == 0 and result["output"].splitlines() == ["Merhaba Ayşe Çelik 42", "Masaüstü scriptleri"]
    assert result["opened"] is False and result["file"] == str(script)


def test_a_failing_script_stops_the_flow_unless_told_otherwise(runner, tmp_path, python_found):
    script = tmp_path / "hata.py"
    script.write_text("import sys\nprint('kayıt yok', file=sys.stderr)\nsys.exit(4)\n", encoding="utf-8")
    with pytest.raises(WorkflowError, match=r"hata.py hata koduyla bitti \(4\). kayıt yok"):
        go(runner, path=str(script))
    result = go(runner, path=str(script), fail_on_error=False)
    assert (result["code"], result["error"]) == (4, "kayıt yok")


def test_a_script_that_runs_too_long_or_is_stopped_is_closed(runner, tmp_path, python_found):
    script = tmp_path / "uzun.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    started = time.monotonic()
    with pytest.raises(WorkflowError, match="1 saniyede bitmedi"):
        go(runner, path=str(script), timeout=1)
    assert time.monotonic() - started < 10
    threading.Timer(0.6, runner.cancel.set).start()
    started = time.monotonic()
    with pytest.raises(Cancelled):
        system.run_file(runner, {"path": str(script)})
    assert time.monotonic() - started < 10


def test_without_waiting_the_flow_moves_on(runner, tmp_path, python_found):
    script = tmp_path / "arka.py"
    marker = tmp_path / "bitti.txt"
    script.write_text(f"import time\ntime.sleep(0.5)\nopen({str(marker)!r}, 'w').write('tamam')\n", encoding="utf-8")
    started = time.monotonic()
    result = go(runner, path=str(script), wait_finish="no")
    assert time.monotonic() - started < 0.5 and result["code"] is None and not marker.exists()
    deadline = time.monotonic() + 15
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert marker.read_text() == "tamam"


def test_documents_open_with_their_program_and_missing_files_are_reported(runner, tmp_path, monkeypatch):
    opened = Mock()
    monkeypatch.setattr(system, "open_target", opened)
    book = tmp_path / "rapor.xlsm"
    book.write_bytes(b"x")
    result = go(runner, path=str(book))
    assert result["opened"] is True and opened.call_args.args[1]["target"] == str(book)
    with pytest.raises(WorkflowError, match="Dosya bulunamadı"):
        go(runner, path=str(tmp_path / "yok.py"))
    with pytest.raises(WorkflowError, match="Çalışma klasörü bulunamadı"):
        go(runner, path=str(book), folder=str(tmp_path / "yok"))


@pytest.mark.parametrize("name, system_name, expected", [
    ("a.ps1", "Windows", ["POWERSHELL", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]),
    ("a.vbs", "Windows", ["cscript.exe", "//nologo"]),
    ("a.bat", "Windows", []),
    ("a.exe", "Windows", []),
    ("a.sh", "Darwin", ["/bin/bash"]),
    ("a.scpt", "Darwin", ["/usr/bin/osascript"]),
    ("a.jar", "Darwin", ["JAVA", "-jar"]),
])
def test_each_kind_runs_with_its_program(monkeypatch, tmp_path, name, system_name, expected):
    monkeypatch.setattr(system.platform, "system", lambda: system_name)
    monkeypatch.setattr(system, "find_program", lambda *names: {"powershell": "POWERSHELL", "java": "JAVA"}.get(names[0]))
    file = tmp_path / name
    command = system.script_command(file, ["x"])
    assert [Path(part).name if part.endswith("cscript.exe") else part for part in command[:len(expected)]] == expected
    assert command[-2:] == [str(file), "x"]


@pytest.mark.parametrize("name, system_name, message", [
    ("a.vbs", "Darwin", "yalnız Windows'ta"),
    ("a.sh", "Windows", "yalnız macOS'ta"),
    ("a.scpt", "Windows", "yalnız macOS'ta"),
])
def test_a_kind_of_the_other_platform_is_refused(monkeypatch, tmp_path, name, system_name, message):
    monkeypatch.setattr(system.platform, "system", lambda: system_name)
    with pytest.raises(WorkflowError, match=message):
        system.script_command(tmp_path / name, [])


def test_turkish_text_survives_the_console_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(system.platform, "system", lambda: "Windows")
    monkeypatch.setenv("COMSPEC", r"C:\Windows\system32\cmd.exe")
    batch = tmp_path / "Script klasörü" / "aktar.bat"
    command, env = system.launch([str(batch), "iş"], batch)
    assert command == rf'"C:\Windows\system32\cmd.exe" /d /u /s /c "chcp 65001 >nul & "{batch}" iş"'
    assert env is None
    shell, _ = system.launch(["powershell", "-File", str(tmp_path / "a.ps1")], tmp_path / "a.ps1")
    assert "chcp 65001" in shell and "powershell -File" in shell
    _, env = system.launch(["C:/Python/python.exe", str(tmp_path / "a.py")], tmp_path / "a.py")
    assert env["PYTHONIOENCODING"] == "utf-8" and env["PYTHONUTF8"] == "1"


def test_quoted_values_reach_the_script_without_their_quotes(monkeypatch):
    monkeypatch.setattr(system.os, "name", "nt")
    assert system._arguments('"Ayşe Çelik" 42 C:\\Rapor') == ["Ayşe Çelik", "42", "C:\\Rapor"]


def test_a_program_is_not_waited_for_by_default_but_a_script_is(runner, tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr(system.subprocess, "Popen", lambda command, **options: started.append(options) or Mock(
        communicate=Mock(return_value=(b"", b"")), returncode=0))
    program = tmp_path / "ERP"
    program.write_text("#!/bin/sh\n")
    program.chmod(0o755)
    monkeypatch.setattr(system.platform, "system", lambda: "Darwin")
    assert go(runner, path=str(program))["code"] is None  # left running, the flow goes on
    assert started[-1]["stdout"] == system.subprocess.DEVNULL
    script = tmp_path / "rapor.sh"
    script.write_text("echo x\n")
    assert go(runner, path=str(script))["code"] == 0  # waited for
    assert started[-1]["stdout"] == system.subprocess.PIPE
    assert go(runner, path=str(program), wait_finish="wait")["code"] == 0


def test_a_flow_saved_with_the_old_yes_no_box_still_runs():
    from rpa_orkestrai.models import Step

    assert Step(action="system.run_file", params={"wait_finish": True}).params["wait_finish"] == "wait"
    assert Step(action="system.run_file", params={"wait_finish": False}).params["wait_finish"] == "no"


def test_python_must_be_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(system, "find_program", lambda *names: None)
    with pytest.raises(WorkflowError, match="Python bulunamadı"):
        system.script_command(tmp_path / "a.py", [])


def test_the_store_stub_is_not_taken_for_python(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name, path=None: r"C:\Users\x\AppData\Local\Microsoft\WindowsApps\python.exe")
    assert system.find_program("python") is None


@pytest.mark.skipif(WINDOWS, reason="macOS kabuk betiği")
def test_shell_script_runs_on_mac(runner, tmp_path):
    script = tmp_path / "yedek.sh"
    script.write_text('echo "yedek $1"\n', encoding="utf-8")
    assert go(runner, path=str(script), arguments="hazır")["output"] == "yedek hazır"


@pytest.mark.skipif(not WINDOWS, reason="Windows script türleri yalnız Windows'ta var")
def test_windows_batch_powershell_and_vbscript_run_for_real(runner, tmp_path):
    folder = tmp_path / "Script klasörü"
    folder.mkdir()
    batch = folder / "aktar.bat"
    batch.write_text("@echo off\r\necho toplu %1\r\n", encoding="utf-8")
    assert go(runner, path=str(batch), arguments="iş")["output"] == "toplu iş"
    shell = folder / "rapor.ps1"
    shell.write_text('Write-Output ("ps " + $args[0])\r\nexit 0\r\n', encoding="utf-8")
    assert go(runner, path=str(shell), arguments="hazır")["output"] == "ps hazır"
    vbs = folder / "makro.vbs"
    vbs.write_text('WScript.Echo "vbs " & WScript.Arguments(0)\r\n', encoding="utf-8")
    assert go(runner, path=str(vbs), arguments="tamam")["output"] == "vbs tamam"
    failing = folder / "hata.ps1"
    failing.write_text("exit 5\r\n", encoding="utf-8")
    with pytest.raises(WorkflowError, match=r"hata koduyla bitti \(5\)"):
        go(runner, path=str(failing))
