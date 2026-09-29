"""Applications, commands and the clipboard on macOS and Windows (AutoHotkey Run/WinClose/Clipboard)."""

from __future__ import annotations

import locale
import os
import platform
import shlex
import subprocess
from pathlib import Path

from ..errors import WorkflowError
from . import handler
from .common import number, text

OUTPUT_LIMIT = 200_000


def _no_window() -> dict:
    # Never flash a console window from the windowed Studio on Windows.
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}


def _arguments(value) -> list[str]:
    raw = text(value, "Parametreler", required=False, limit=4000).strip()
    if not raw:
        return []
    try:
        return shlex.split(raw, posix=os.name != "nt")
    except ValueError as exc:
        raise WorkflowError("Parametrelerdeki tırnak işaretlerini kontrol edin.") from exc


@handler("system.open")
def open_target(ctx, p):
    """Open an application, a document/folder or a web address with the default program."""
    target = text(p.get("target"), "Açılacak uygulama, dosya veya adres", limit=4096).strip().strip('"')
    arguments = _arguments(p.get("arguments"))
    expanded = os.path.expandvars(os.path.expanduser(target))
    is_url = "://" in target or target.startswith(("mailto:", "www."))
    if target.startswith("www."):
        expanded = "https://" + target
    try:
        if platform.system() == "Windows":
            if arguments:
                subprocess.Popen([expanded, *arguments], **_no_window())
            else:
                os.startfile(expanded)  # noqa: S606 - opens documents, folders, apps and URLs like Explorer
        elif platform.system() == "Darwin":
            if is_url or Path(expanded).exists() and not expanded.endswith(".app"):
                command = ["/usr/bin/open", expanded]
            else:
                # "Microsoft Excel", "TextEdit" or /Applications/Name.app
                command = ["/usr/bin/open", "-a", expanded]
            if arguments:
                command += ["--args", *arguments]
            subprocess.run(command, check=True, capture_output=True, timeout=30)
        else:
            raise WorkflowError("Uygulama açma macOS ve Windows'ta desteklenir.")
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkflowError(f"“{target}” açılamadı. Uygulama adını, dosya yolunu veya adresi kontrol edin.") from exc
    wait = number(p.get("wait", 2), "Açıldıktan sonra bekleme", 0, 120)
    if wait:
        ctx.wait(wait)


@handler("system.close_app")
def close_app(ctx, p):
    name = text(p.get("application"), "Uygulama adı", limit=200).strip()
    force = p.get("force") is True
    if any(character in name for character in "/\\\"'") or name.startswith("-"):
        raise WorkflowError("Uygulama adı yol veya tırnak içermemelidir (ör. excel.exe, Microsoft Excel).")
    if platform.system() == "Windows":
        image = name if name.lower().endswith(".exe") else name + ".exe"
        command = ["taskkill", "/IM", image] + (["/F"] if force else [])
    elif platform.system() == "Darwin":
        command = ["/usr/bin/pkill", "-x", name] if force else \
            ["/usr/bin/osascript", "-e", "on run argv\ntell application (item 1 of argv) to quit\nend run", name]
    else:
        raise WorkflowError("Uygulama kapatma macOS ve Windows'ta desteklenir.")
    try:
        result = subprocess.run(command, capture_output=True, timeout=30, **_no_window())
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkflowError("Uygulama kapatılamadı.") from exc
    if result.returncode != 0 and p.get("ignore_missing", True) is not True:
        raise WorkflowError(f"“{name}” kapatılamadı; uygulama açık olmayabilir.")
    return result.returncode == 0


def _console_encodings() -> list[str]:
    """Windows console programs write in the OEM code page (cp857 in Turkish), others in ANSI."""
    if os.name != "nt":
        return [locale.getpreferredencoding(False)]
    import ctypes

    return [f"cp{ctypes.windll.kernel32.GetOEMCP()}", f"cp{ctypes.windll.kernel32.GetACP()}"]


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", *_console_encodings(), "cp857", "cp1254"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


@handler("system.command")
def command(ctx, p):
    """Run a shell command (cmd.exe on Windows, /bin/sh on macOS) and capture its output."""
    line = text(p.get("command"), "Komut", limit=8000)
    timeout = number(p.get("timeout", 60), "Zaman aşımı", 1, 3600)
    folder = p.get("folder")
    cwd = None
    if folder:
        cwd = Path(os.path.expandvars(os.path.expanduser(str(folder))))
        if not cwd.is_dir():
            raise WorkflowError("Çalışma klasörü bulunamadı.")
    try:
        result = subprocess.run(line, shell=True, capture_output=True, timeout=timeout, cwd=cwd,  # noqa: S602
                                **_no_window())
    except subprocess.TimeoutExpired as exc:
        raise WorkflowError(f"Komut {timeout:g} saniyede bitmedi ve durduruldu.") from exc
    except OSError as exc:
        raise WorkflowError("Komut başlatılamadı.") from exc
    output = {"code": result.returncode, "output": _decode(result.stdout)[-OUTPUT_LIMIT:].strip(),
              "error": _decode(result.stderr)[-OUTPUT_LIMIT:].strip()}
    if result.returncode != 0 and p.get("fail_on_error", True) is True:
        detail = output["error"].splitlines()[-1] if output["error"] else ""
        raise WorkflowError(f"Komut hata koduyla bitti ({result.returncode}). {detail}"[:500])
    return output


@handler("clipboard.set")
def clipboard_set(ctx, p):
    import pyperclip

    pyperclip.copy(text(p.get("value"), "Panoya kopyalanacak değer", required=False, limit=1_000_000))


@handler("clipboard.get")
def clipboard_get(ctx, p):
    import pyperclip

    return pyperclip.paste()
