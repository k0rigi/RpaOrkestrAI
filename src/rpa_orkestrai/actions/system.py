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
from .common import number, path, text

OUTPUT_LIMIT = 200_000


def _no_window() -> dict:
    # Never flash a console window from the windowed Studio on Windows.
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}


def _waited() -> dict:
    # A process the step waits for leads its own group on macOS, so stop() can end its children too.
    return _no_window() if os.name == "nt" else {"start_new_session": True}


def _arguments(value) -> list[str]:
    raw = text(value, "Parametreler", required=False, limit=4000).strip()
    if not raw:
        return []
    try:
        parts = shlex.split(raw, posix=os.name != "nt")
    except ValueError as exc:
        raise WorkflowError("Parametrelerdeki tırnak işaretlerini kontrol edin.") from exc
    # Windows splitting keeps the quotes ("Ayşe Çelik"); the program must receive the value without them.
    return [part[1:-1] if len(part) >= 2 and part[0] == part[-1] == '"' else part for part in parts]


@handler("system.open")
def open_target(ctx, p):
    """Open an application, a document/folder or a web address with the default program."""
    target = text(p.get("target"), "Açılacak uygulama, dosya veya adres", limit=4096).strip().strip('"')
    raw_arguments = text(p.get("arguments"), "Parametreler", required=False, limit=4000).strip()
    expanded = os.path.expandvars(os.path.expanduser(target))
    is_url = "://" in target or target.startswith(("mailto:", "www."))
    if target.startswith("www."):
        expanded = "https://" + target
    if not is_url and expanded.replace("\\", "/").rsplit("/", 1)[-1].lower() in {"javaws", "javaws.exe"} \
            and not raw_arguments:
        raise WorkflowError("Java Web Start tek başına Canias'ı açamaz. «Ne açılsın?» alanında Canias kısayolunu "
                            "(.lnk) veya .jnlp dosyasını seçin. javaws.exe kullanacaksanız «Parametreler» alanına "
                            "Canias kısayolunun parametrelerini (JNLP dosyası veya adresi dahil) girin.")
    try:
        if platform.system() == "Windows":
            if raw_arguments:
                # ShellExecute keeps Windows quoting and supports shortcuts/file associations as well as EXEs.
                os.startfile(expanded, "open", raw_arguments)
            else:
                os.startfile(expanded)  # noqa: S606 - opens documents, folders, apps and URLs like Explorer
        elif platform.system() == "Darwin":
            arguments = _arguments(raw_arguments)
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
    if os.name == "nt" and len(raw) >= 4 and raw[1::2].count(0) >= len(raw) // 4:
        try:
            return raw.decode("utf-16-le")
        except UnicodeDecodeError:
            pass
    for encoding in ("utf-8", *_console_encodings(), "cp857", "cp1254"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


@handler("system.command")
def command(ctx, p):
    """Like typing into a terminal or PowerShell: a command line or a script file; waits and keeps the output."""
    if p.get("run", "command") == "file":
        return run_script(ctx, p)
    line = text(p.get("command"), "Komut", limit=8000)
    timeout = number(p.get("timeout", 300), "Zaman aşımı", 1, 86400)
    folder = p.get("folder")
    cwd = None
    if folder:
        cwd = Path(os.path.expandvars(os.path.expanduser(str(folder))))
        if not cwd.is_dir():
            raise WorkflowError("Çalışma klasörü bulunamadı.")
    if p.get("shell", "system") == "powershell":
        return powershell(ctx, line, cwd, timeout, p.get("fail_on_error", True) is True)
    if os.name == "nt":
        # /u: cmd's own commands (echo, dir, type) write Unicode, so Turkish text survives any code page.
        comspec = os.environ.get("COMSPEC", "cmd.exe")
        invocation, shell = f'"{comspec}" /d /u /s /c "{line}"', False
    else:
        invocation, shell = line, True
    try:
        process = subprocess.Popen(invocation, shell=shell, cwd=cwd, stdin=subprocess.DEVNULL,  # noqa: S602
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, **_waited())
    except OSError as exc:
        raise WorkflowError("Komut başlatılamadı.") from exc
    stdout, stderr = finish(ctx, process, timeout, "Komut")
    return _result(process.returncode, stdout, stderr, p.get("fail_on_error", True) is True, "Komut")


def powershell(ctx, line: str, cwd: Path | None, timeout: float, fail: bool) -> dict:
    """A PowerShell command, written to a temporary .ps1 so quotes, pipes and Turkish text arrive unchanged."""
    import tempfile

    if platform.system() != "Windows" and not find_program("pwsh"):
        raise WorkflowError("PowerShell (pwsh) bu Mac'te kurulu değil. Komut İstemi / Terminal seçeneğini kullanın "
                            "veya PowerShell'i kurun.")
    with tempfile.TemporaryDirectory(prefix="rpa-ps-") as folder:
        script = Path(folder) / "komut.ps1"
        # Windows PowerShell 5.1 reads a script without a BOM in the ANSI code page.
        script.write_text("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n$OutputEncoding = "
                          "[System.Text.Encoding]::UTF8\n$ProgressPreference = 'SilentlyContinue'\n" + line + "\n",
                          encoding="utf-8-sig")
        invocation, env = launch(script_command(script, []), script)
        try:
            process = subprocess.Popen(invocation, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, **_waited())
        except OSError as exc:
            raise WorkflowError("PowerShell başlatılamadı.") from exc
        stdout, stderr = finish(ctx, process, timeout, "Komut")
    return _result(process.returncode, stdout, stderr, fail, "Komut")


def finish(ctx, process: subprocess.Popen, timeout: float, name: str) -> tuple[bytes, bytes]:
    """Wait for the process; Durdur and the time limit end it."""
    import time

    deadline = time.monotonic() + timeout
    while True:
        try:
            return process.communicate(timeout=0.5)
        except subprocess.TimeoutExpired:
            pass
        try:
            ctx.check_cancelled()
        except BaseException:
            stop(process)
            raise
        if time.monotonic() >= deadline:
            stop(process)
            raise WorkflowError(f"{name} {timeout:g} saniyede bitmedi ve durduruldu.")


def stop(process: subprocess.Popen) -> None:
    """End the process with everything it started (cmd's ping, a script's child program)."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], capture_output=True, timeout=10,
                           **_no_window())
        else:
            import signal

            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    process.kill()
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _result(code: int, stdout: bytes, stderr: bytes, fail: bool, name: str, **extra) -> dict:
    output = {"code": code, "output": _decode(stdout)[-OUTPUT_LIMIT:].strip(),
              "error": _decode(stderr)[-OUTPUT_LIMIT:].strip(), **extra}
    if code != 0 and fail:
        detail = output["error"].splitlines()[-1] if output["error"] else ""
        raise WorkflowError(f"{name} hata koduyla bitti ({code}). {detail}"[:500])
    return output


@handler("clipboard.set")
def clipboard_set(ctx, p):
    import pyperclip

    pyperclip.copy(text(p.get("value"), "Panoya kopyalanacak değer", required=False, limit=1_000_000))


@handler("clipboard.get")
def clipboard_get(ctx, p):
    import pyperclip

    return pyperclip.paste()


# ----- Dosya / script çalıştır: any file in a folder, run the way its kind needs ----------------
# A Studio opened from the Dock or Explorer has a short PATH; programs are also looked for here.
EXTRA_PATHS = {
    "Darwin": ["/opt/homebrew/bin", "/usr/local/bin", "/Library/Frameworks/Python.framework/Versions/Current/bin",
               "/usr/bin", "/bin"],
    "Windows": [],
}
SCRIPT_KINDS = {
    ".py": "python", ".pyw": "python", ".ps1": "powershell", ".bat": "direct", ".cmd": "direct", ".exe": "direct",
    ".com": "direct", ".vbs": "wsh", ".vbe": "wsh", ".wsf": "wsh", ".sh": "bash", ".command": "bash", ".bash": "bash",
    ".zsh": "zsh", ".scpt": "osascript", ".applescript": "osascript", ".jar": "java",
}
ONLY_ON = {"wsh": "Windows", "bash": "Darwin", "zsh": "Darwin", "osascript": "Darwin"}


def find_program(*names: str) -> str | None:
    import shutil

    search = os.pathsep.join([os.environ.get("PATH", ""), *EXTRA_PATHS.get(platform.system(), [])])
    for name in names:
        found = shutil.which(name, path=search)
        # The Microsoft Store stub only offers to install Python; it never runs a script.
        if found and "WindowsApps" not in found:
            return found
    return None


def script_command(file: Path, arguments: list[str]) -> list[str] | None:
    """How to run this file on this computer; None when it is a document to open with its program."""
    system = platform.system()
    kind = SCRIPT_KINDS.get(file.suffix.lower())
    if kind == "direct" and system != "Windows":
        kind = None
    if kind in ONLY_ON and ONLY_ON[kind] != system:
        names = {"wsh": "VBScript (.vbs)", "bash": "Kabuk betiği", "zsh": "Kabuk betiği", "osascript": "AppleScript"}
        other = "Windows" if ONLY_ON[kind] == "Windows" else "macOS"
        raise WorkflowError(f"{names[kind]} yalnız {other}'ta çalışır.")
    if kind is None and system != "Windows" and not file.is_dir() and os.access(file, os.X_OK) and not file.suffix:
        kind = "direct"  # an executable file without an extension (#! script or program)
    if kind is None:
        return None
    if kind == "direct":
        return [str(file), *arguments]
    if kind == "python":
        python = find_program("py") if system == "Windows" else None
        if python:
            return [python, "-3", str(file), *arguments]
        python = find_program("python", "python3") if system == "Windows" else find_program("python3", "python")
        if not python:
            raise WorkflowError("Python bulunamadı. Bu bilgisayara Python kurun (python.org); Windows'ta kurulumda "
                                "'Add python.exe to PATH' seçeneğini işaretleyin.")
        return [python, str(file), *arguments]
    if kind == "powershell":
        shell = (find_program("powershell", "pwsh") or str(Path(os.environ.get("SystemRoot", r"C:\Windows"))
                 / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")) if system == "Windows" \
            else find_program("pwsh")
        if not shell:
            raise WorkflowError("PowerShell (pwsh) bu Mac'te kurulu değil.")
        return [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(file), *arguments]
    if kind == "wsh":
        cscript = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cscript.exe"
        return [str(cscript), "//nologo", str(file), *arguments]
    if kind in {"bash", "zsh"}:
        return [f"/bin/{kind}", str(file), *arguments]
    if kind == "osascript":
        return ["/usr/bin/osascript", str(file), *arguments]
    java = find_program("java")
    if not java:
        raise WorkflowError("Java bulunamadı; .jar dosyasını çalıştırmak için Java kurun.")
    return [java, "-jar", str(file), *arguments]


def launch(command: list[str], file: Path) -> tuple[list[str] | str, dict | None]:
    """The process to start and its environment: Turkish text must survive the console code page.

    Python writes UTF-8 when told to. On Windows, .bat/.cmd and PowerShell run in a console switched to UTF-8
    (chcp 65001), and cmd's own commands write Unicode (/u); English Windows otherwise turns ş into s.
    """
    env = None
    if command[0] != str(file) and Path(command[0]).stem.lower() in {"py", "python", "python3", "pythonw"}:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    if platform.system() == "Windows" and (file.suffix.lower() in {".bat", ".cmd"}
                                           or Path(command[0]).stem.lower() in {"powershell", "pwsh"}):
        comspec = os.environ.get("COMSPEC", "cmd.exe")
        return f'"{comspec}" /d /u /s /c "chcp 65001 >nul & {subprocess.list2cmdline(command)}"', env
    return command, env


@handler("system.run_file")
def run_file(ctx, p):
    """Run a script or program from a folder (.py, .ps1, .bat, .vbs, .exe, .sh …); open any other file."""
    file = path(p.get("path"), "Çalıştırılacak dosya")
    if not file.exists():
        raise WorkflowError(f"Dosya bulunamadı: {file}")
    arguments = _arguments(p.get("arguments"))
    folder = p.get("folder")
    cwd = path(folder, "Çalışma klasörü") if folder else (file if file.is_dir() else file.parent)
    if not cwd.is_dir():
        raise WorkflowError("Çalışma klasörü bulunamadı.")
    command = script_command(file, arguments)
    if command is None:
        # A document (Excel, PDF, …): its own program opens it, like a double click.
        open_target(ctx, {"target": str(file), "arguments": p.get("arguments", ""), "wait": 0})
        ctx.log(f"{file.name} varsayılan programıyla açıldı; bitmesi beklenmez.")
        return {"code": None, "output": "", "error": "", "file": str(file), "opened": True}
    mode = p.get("wait_finish", "auto")
    if isinstance(mode, bool):
        mode = "wait" if mode else "no"
    # A program such as the ERP stays open; only a script is something to wait for.
    program = command[0] == str(file) and file.suffix.lower() not in {".bat", ".cmd"}
    waits = mode == "wait" or (mode == "auto" and not program)
    command, env = launch(command, file)
    try:
        if not waits:
            subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=os.name != "nt", **_no_window())
            ctx.log(f"{file.name} başlatıldı; akış bitmesini beklemeden devam ediyor.")
            return {"code": None, "output": "", "error": "", "file": str(file), "opened": False}
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, **_waited())
    except OSError as exc:
        raise WorkflowError(f"{file.name} başlatılamadı: {exc.strerror or exc}") from exc
    timeout = number(p.get("timeout", 600), "Zaman aşımı", 1, 86400)
    stdout, stderr = finish(ctx, process, timeout, file.name)
    return _result(process.returncode, stdout, stderr, p.get("fail_on_error", True) is True, file.name,
                   file=str(file), opened=False)


def run_script(ctx, p):
    """Komut / script çalıştır with a file: the script runs with its interpreter and is waited for."""
    file = path(p.get("path"), "Script dosyası")
    if not file.is_file():
        raise WorkflowError(f"Dosya bulunamadı: {file}")
    folder = p.get("folder")
    cwd = path(folder, "Çalışma klasörü") if folder else file.parent
    if not cwd.is_dir():
        raise WorkflowError("Çalışma klasörü bulunamadı.")
    command = script_command(file, _arguments(p.get("arguments")))
    if command is None:
        raise WorkflowError(f"“{file.name}” bir script değil. Programları ve belgeleri «Uygulama, dosya veya adres "
                            "aç» adımıyla açın.")
    command, env = launch(command, file)
    try:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, **_waited())
    except OSError as exc:
        raise WorkflowError(f"{file.name} başlatılamadı: {exc.strerror or exc}") from exc
    timeout = number(p.get("timeout", 300), "Zaman aşımı", 1, 86400)
    stdout, stderr = finish(ctx, process, timeout, file.name)
    return _result(process.returncode, stdout, stderr, p.get("fail_on_error", True) is True, file.name,
                   file=str(file))
