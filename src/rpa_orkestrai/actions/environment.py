"""Built-in ${sistem} variable: the same workflow finds user folders on macOS and Windows."""

from __future__ import annotations

import getpass
import os
import platform
from datetime import datetime
from pathlib import Path

# Windows Known Folder IDs; Desktop/Documents may be redirected to OneDrive.
KNOWN_FOLDERS = {"masaustu": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
                 "belgeler": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
                 "indirilenler": "{374DE290-123F-4565-9164-39C4925E467B}"}
DEFAULT_FOLDERS = {"masaustu": "Desktop", "belgeler": "Documents", "indirilenler": "Downloads"}


def _windows_folder(guid: str) -> str | None:
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                        ("Data4", ctypes.c_ubyte * 8)]

        folder_id = GUID()
        ctypes.oledll.ole32.CLSIDFromString(guid, ctypes.byref(folder_id))
        path = ctypes.c_wchar_p()
        ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(path))
        try:
            return path.value
        finally:
            ctypes.windll.ole32.CoTaskMemFree(path)
    except (OSError, AttributeError, ValueError):
        return None


def system_variables() -> dict:
    home = Path.home()
    system = platform.system()
    folders = {}
    for key, name in DEFAULT_FOLDERS.items():
        found = _windows_folder(KNOWN_FOLDERS[key]) if system == "Windows" else None
        folders[key] = found or str(home / name)
    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        user = ""
    now = datetime.now()
    return {"isletim_sistemi": {"Darwin": "macOS"}.get(system, system), "kullanici": user, "ev": str(home),
            **folders, "bugun": now.strftime("%d.%m.%Y"), "baslangic": now.strftime("%d.%m.%Y %H:%M:%S"),
            "ayrac": os.sep}
