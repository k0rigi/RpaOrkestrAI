"""Create a console-free source-checkout shortcut after Windows setup."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    interpreter = root / ".venv" / "Scripts" / "pythonw.exe"
    entry = root / "launch_gui.pyw"
    if os.name != "nt" or not interpreter.is_file() or not entry.is_file():
        raise SystemExit("Windows kurulumu tamamlanmadan kisayol olusturulamaz.")
    env = {**os.environ, "RPA_SHORTCUT_PYTHON": str(interpreter), "RPA_SHORTCUT_ENTRY": str(entry),
           "RPA_SHORTCUT_ROOT": str(root)}
    script = '''$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$link = $shell.CreateShortcut((Join-Path $desktop 'RpaOrkestrAI Studio.lnk'))
$link.TargetPath = $env:RPA_SHORTCUT_PYTHON
$link.Arguments = '"' + $env:RPA_SHORTCUT_ENTRY + '"'
$link.WorkingDirectory = $env:RPA_SHORTCUT_ROOT
$link.Description = 'RpaOrkestrAI Studio'
$link.Save()
'''
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], env=env, check=True)


if __name__ == "__main__":
    main()
