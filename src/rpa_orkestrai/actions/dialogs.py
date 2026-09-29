"""Native message and input boxes; the run waits for the person at the computer."""

from __future__ import annotations

import base64
import os
import platform
import subprocess

from ..errors import WorkflowError
from . import handler
from .common import choice, number, text

BUTTONS = {"ok": ("Tamam",), "ok_cancel": ("İptal", "Tamam"), "yes_no": ("Hayır", "Evet")}
ANSWERS = {"Tamam": "ok", "İptal": "cancel", "Evet": "yes", "Hayır": "no"}

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
Add-Type -AssemblyName Microsoft.VisualBasic
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$value = [Microsoft.VisualBasic.Interaction]::InputBox($env:RPA_PROMPT, $env:RPA_TITLE, $env:RPA_DEFAULT)
[Console]::Out.Write($value)
'''


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

        style = {"ok": 0x0, "ok_cancel": 0x1, "yes_no": 0x4}[buttons] | 0x40 | 0x10000 | 0x40000
        result = ctypes.windll.user32.MessageBoxW(None, body, title, style)  # MB_ICONINFORMATION|SETFOREGROUND|TOPMOST
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
        value = result.stdout.decode("utf-8", errors="replace").lstrip("﻿")
        if value:
            return value
        cancelled = None
    else:
        raise WorkflowError("Değer isteme kutusu macOS ve Windows'ta desteklenir.")
    if p.get("on_cancel", "stop") == "stop":
        raise WorkflowError("Kullanıcı değer girmedi veya iptal etti.")
    return cancelled if cancelled is not None else ""
