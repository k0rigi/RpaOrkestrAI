"""Native message and input boxes; the run waits for the person at the computer."""

from __future__ import annotations

import base64
import os
import platform
import subprocess

from ..errors import WorkflowError
from ..file_types import extension_of, parse_extensions
from . import handler
from .common import choice, number, path, text

BUTTONS = {"ok": ("Tamam",), "ok_cancel": ("İptal", "Tamam"), "yes_no": ("Hayır", "Evet")}
ANSWERS = {"Tamam": "ok", "İptal": "cancel", "Evet": "yes", "Hayır": "no"}
MB_TIMEDOUT = 32000

MAC_MESSAGE = '''on run argv
    set labels to {}
    repeat with index from 4 to count of argv
        set end of labels to item index of argv
    end repeat
    set answer to display dialog (item 2 of argv) with title (item 1 of argv) buttons labels default button (last item of labels) giving up after ((item 3 of argv) as integer)
    if gave up of answer then return "timeout"
    return button returned of answer
end run'''
MAC_INPUT = '''on run argv
    set answer to display dialog (item 2 of argv) with title (item 1 of argv) default answer (item 3 of argv) buttons {"İptal", "Tamam"} default button "Tamam" cancel button "İptal" giving up after ((item 4 of argv) as integer)
    if gave up of answer then return "timeout"
    return "ok:" & text returned of answer
end run'''
WINDOWS_INPUT = r'''
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()
$form = New-Object System.Windows.Forms.Form
$form.Text = $env:RPA_TITLE
$form.TopMost = $true
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.ClientSize = New-Object System.Drawing.Size(440, 150)
$label = New-Object System.Windows.Forms.Label
$label.Text = $env:RPA_PROMPT
$label.SetBounds(12, 12, 416, 48)
$box = New-Object System.Windows.Forms.TextBox
$box.Text = $env:RPA_DEFAULT
$box.SetBounds(12, 66, 416, 24)
$ok = New-Object System.Windows.Forms.Button
$ok.Text = 'Tamam'
$ok.DialogResult = [System.Windows.Forms.DialogResult]::OK
$ok.SetBounds(256, 108, 82, 30)
$cancel = New-Object System.Windows.Forms.Button
$cancel.Text = 'İptal'
$cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$cancel.SetBounds(346, 108, 82, 30)
$form.AcceptButton = $ok
$form.CancelButton = $cancel
$form.Controls.AddRange(@($label, $box, $ok, $cancel))
$form.Add_Shown({ $form.Activate(); $box.SelectAll(); $box.Focus() })
$result = $form.ShowDialog()
[Console]::OutputEncoding = [Text.Encoding]::UTF8
if ($result -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Out.Write('ok:' + $box.Text) }
else { [Console]::Out.Write('cancel') }
'''


# argv: prompt, start folder ("" = the system's last folder), then the allowed extensions.
MAC_CHOOSE_FILE = '''on run argv
    set question to item 1 of argv
    set startFolder to item 2 of argv
    set kinds to {}
    repeat with index from 3 to count of argv
        set end of kinds to item index of argv
    end repeat
    activate
    if startFolder is "" then
        if (count of kinds) is 0 then
            set chosen to choose file with prompt question
        else
            set chosen to choose file with prompt question of type kinds
        end if
    else
        set place to (POSIX file startFolder) as alias
        if (count of kinds) is 0 then
            set chosen to choose file with prompt question default location place
        else
            set chosen to choose file with prompt question of type kinds default location place
        end if
    end if
    return "ok:" & POSIX path of chosen
end run'''
# RPA_CHECK_ONLY: build the dialog and its filter without showing it (the Windows test checks the filter is valid).
WINDOWS_CHOOSE_FILE = r'''
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = $env:RPA_TITLE
$dialog.Filter = $env:RPA_FILTER
$dialog.CheckFileExists = $true
$dialog.Multiselect = $false
if ($env:RPA_FOLDER) { $dialog.InitialDirectory = $env:RPA_FOLDER }
if ($env:RPA_CHECK_ONLY) { [Console]::Out.Write('check:' + $dialog.Filter); exit 0 }
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$result = $dialog.ShowDialog($owner)
if ($result -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Out.Write('ok:' + $dialog.FileName) }
else { [Console]::Out.Write('cancel') }
'''


def windows_filter(extensions: list[str]) -> str:
    if not extensions:
        return "Tüm dosyalar (*.*)|*.*"
    patterns = ";".join(f"*.{item}" for item in extensions)
    return f"İzin verilen dosyalar ({patterns})|{patterns}"


def run_windows_dialog(script: str, environment: dict, timeout: float) -> str:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                                capture_output=True, env={**os.environ, **environment}, timeout=timeout,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkflowError("Dosya seçme penceresi açılamadı.") from exc
    return result.stdout.decode("utf-8", errors="replace").lstrip("\ufeff")


def _osascript(script: str, *arguments: str, timeout: float) -> str:
    try:
        result = subprocess.run(["/usr/bin/osascript", "-e", script, *arguments], capture_output=True,
                                text=True, timeout=timeout + 30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkflowError("İletişim kutusu açılamadı.") from exc
    if result.returncode != 0:
        return "cancel" if "-128" in result.stderr else ""
    return result.stdout.rstrip("\n")


@handler("ui.message")
def message(ctx, p):
    title = text(p.get("title") or "RpaOrkestrAI", "Başlık", limit=200)
    body = text(p.get("text"), "Mesaj", limit=4000)
    buttons = choice(p.get("buttons", "ok"), "Düğmeler", BUTTONS)
    timeout = int(number(p.get("timeout", 0), "Otomatik kapanma", 0, 86400))
    if platform.system() == "Darwin":
        answer = _osascript(MAC_MESSAGE, title, body, str(timeout), *BUTTONS[buttons], timeout=timeout or 86400)
        return "timeout" if answer == "timeout" else ANSWERS.get(answer, "cancel")
    if platform.system() == "Windows":
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        style = {"ok": 0x0, "ok_cancel": 0x1, "yes_no": 0x4}[buttons] | 0x40 | 0x10000 | 0x40000
        if timeout:
            # user32's self-closing message box; it answers MB_TIMEDOUT when nobody clicked in time.
            show = user32.MessageBoxTimeoutW
            show.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT, wintypes.WORD,
                             wintypes.DWORD]
            show.restype = ctypes.c_int
            result = show(None, body, title, style, 0, timeout * 1000)
        else:
            result = user32.MessageBoxW(None, body, title, style)  # MB_ICONINFORMATION|SETFOREGROUND|TOPMOST
        if result == MB_TIMEDOUT:
            return "timeout"
        return {1: "ok", 2: "cancel", 6: "yes", 7: "no"}.get(result, "cancel")
    raise WorkflowError("Mesaj kutusu macOS ve Windows'ta desteklenir.")


@handler("ui.input")
def ask(ctx, p):
    title = text(p.get("title") or "RpaOrkestrAI", "Başlık", limit=200)
    prompt = text(p.get("prompt"), "Soru", limit=2000)
    default = text(p.get("default"), "Varsayılan değer", required=False, limit=2000)
    timeout = int(number(p.get("timeout", 0), "Otomatik kapanma", 0, 86400))
    if platform.system() == "Darwin":
        answer = _osascript(MAC_INPUT, title, prompt, default, str(timeout), timeout=timeout or 86400)
        if answer.startswith("ok:"):
            return answer[3:]
        cancelled = None
    elif platform.system() == "Windows":
        encoded = base64.b64encode(WINDOWS_INPUT.encode("utf-16-le")).decode("ascii")
        environment = {**os.environ, "RPA_PROMPT": prompt, "RPA_TITLE": title, "RPA_DEFAULT": default}
        try:
            result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                                    capture_output=True, env=environment, timeout=timeout or 86400,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError) as exc:
            raise WorkflowError("Değer isteme kutusu açılamadı.") from exc
        value = result.stdout.decode("utf-8", errors="replace").lstrip("\ufeff")
        if value.startswith("ok:"):
            return value[3:]
        cancelled = None
    else:
        raise WorkflowError("Değer isteme kutusu macOS ve Windows'ta desteklenir.")
    if p.get("on_cancel", "stop") == "stop":
        raise WorkflowError("Kullanıcı değer girmedi veya iptal etti.")
    return cancelled if cancelled is not None else ""


@handler("ui.choose_file")
def choose_file(ctx, p):
    """The system's own Open dialog; only the allowed extensions are offered, and the choice is checked again."""
    title = text(p.get("title") or "Dosya seçin", "Başlık", limit=200)
    allowed = parse_extensions(p.get("extensions"))
    raw_folder = str(p.get("folder") or "").strip()
    folder = path(raw_folder, "Başlangıç klasörü") if raw_folder else None
    if folder is not None and not folder.is_dir():
        raise WorkflowError(f"Başlangıç klasörü bulunamadı: {folder}")
    if platform.system() == "Darwin":
        answer = _osascript(MAC_CHOOSE_FILE, title, str(folder or ""), *allowed, timeout=86400)
    elif platform.system() == "Windows":
        answer = run_windows_dialog(WINDOWS_CHOOSE_FILE, {"RPA_TITLE": title, "RPA_FILTER": windows_filter(allowed),
                                                          "RPA_FOLDER": str(folder or "")}, 86400)
    else:
        raise WorkflowError("Dosya seçme penceresi macOS ve Windows'ta desteklenir.")
    if not answer.startswith("ok:"):
        if p.get("on_cancel", "stop") == "stop":
            raise WorkflowError("Kullanıcı dosya seçmedi veya iptal etti.")
        return ""
    chosen = path(answer[3:].strip(), "Seçilen dosya")
    if not chosen.is_file():
        raise WorkflowError(f"Seçilen dosya bulunamadı: {chosen}")
    if allowed and extension_of(chosen) not in allowed:
        raise WorkflowError(f"“{chosen.name}” izin verilen türde değil; izin verilenler: "
                            f"{', '.join('.' + item for item in allowed)}.")
    ctx.log(f"Seçilen dosya: {chosen}")
    return str(chosen)
