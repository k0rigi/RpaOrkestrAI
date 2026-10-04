"""Bilgisayar açılınca Studio'yu başlat: a login item for the installed desktop app.

Windows: a value under HKCU ...\\CurrentVersion\\Run. macOS: a LaunchAgent that opens the app at
login. Both start the Studio minimized (--minimized), so scheduled flows can run without anyone
opening it. Only the installed (frozen) app registers itself: from source there is no stable
program to point at.
"""

from __future__ import annotations

import os
import platform
import plistlib
import sys
from pathlib import Path

VALUE_NAME = "RpaOrkestrAI Studio"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AGENT_LABEL = "net.orkestrai.rpa.studio"
MINIMIZED = "--minimized"


def supported() -> bool:
    return bool(getattr(sys, "frozen", False)) and platform.system() in {"Windows", "Darwin"}


def status() -> dict:
    if not supported():
        return {"supported": False, "enabled": False,
                "reason": "Yalnız kurulu masaüstü uygulamasında (Windows veya macOS) kullanılabilir."}
    return {"supported": True, "enabled": enabled(), "reason": None}


def enabled() -> bool:
    if platform.system() == "Windows":
        return read_run_value() is not None
    if platform.system() == "Darwin":
        return agent_path().exists()
    return False


def set_enabled(on: bool) -> dict:
    if not supported():
        raise RuntimeError(status()["reason"])
    if platform.system() == "Windows":
        if on:
            write_run_value(windows_command())
        else:
            delete_run_value()
    elif on:
        write_agent(app_bundle())
    else:
        agent_path().unlink(missing_ok=True)
    return status()


# ----- Windows -------------------------------------------------------------------------------
def windows_command(executable: str | None = None) -> str:
    return f'"{executable or sys.executable}" {MINIMIZED}'


def read_run_value(name: str = VALUE_NAME) -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, name)[0]
    except FileNotFoundError:
        return None


def write_run_value(command: str, name: str = VALUE_NAME) -> None:
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)


def delete_run_value(name: str = VALUE_NAME) -> None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, name)
    except FileNotFoundError:
        pass


# ----- macOS ---------------------------------------------------------------------------------
def app_bundle(executable: str | None = None) -> Path:
    """…/RpaOrkestrAI.app/Contents/MacOS/RpaOrkestrAI → …/RpaOrkestrAI.app"""
    for parent in Path(executable or sys.executable).resolve().parents:
        if parent.suffix == ".app":
            # Opened from the disk image or from a quarantined copy (App Translocation): that path is
            # gone at the next login.
            if parent.parts[1:2] == ("Volumes",) or "AppTranslocation" in parent.parts:
                raise RuntimeError("Studio disk görüntüsünden veya geçici bir konumdan çalışıyor. Önce "
                                   "RpaOrkestrAI'yi Uygulamalar klasörüne taşıyın, oradan açıp yeniden deneyin.")
            return parent
    raise RuntimeError("Uygulama paketi (.app) bulunamadı; Studio'yu Uygulamalar klasöründen açın.")


def agent_path(home: Path | None = None) -> Path:
    return (home or Path.home()) / "Library" / "LaunchAgents" / f"{AGENT_LABEL}.plist"


def agent(app: Path) -> dict:
    # open -a starts the app the way Finder does, so it keeps its permissions (Erişilebilirlik, Ekran Kaydı).
    return {"Label": AGENT_LABEL, "ProgramArguments": ["/usr/bin/open", "-a", str(app), "--args", MINIMIZED],
            "RunAtLoad": True, "ProcessType": "Interactive", "LimitLoadToSessionType": "Aqua"}


def write_agent(app: Path, home: Path | None = None) -> Path:
    path = agent_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(plistlib.dumps(agent(app)))
    os.chmod(temporary, 0o644)
    temporary.replace(path)
    return path
