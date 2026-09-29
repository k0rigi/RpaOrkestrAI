"""Screen-level mouse and keyboard, like AutoHotkey's Click/Send; primary display only."""

from __future__ import annotations

from typing import Any

from ..errors import WorkflowError
from . import handler
from .common import choice, integer, number, optional_integer, text

BUTTONS = {"left", "right", "middle"}
KEY_ALIASES = {
    "control": "ctrl", "cmd": "command", "windows": "win", "option": "alt", "escape": "esc",
    "return": "enter", "del": "delete", "ins": "insert", "pgup": "pageup", "pgdn": "pagedown",
    "space": "space", "spacebar": "space", "arrowup": "up", "arrowdown": "down", "arrowleft": "left",
    "arrowright": "right", "prtsc": "printscreen", "caps": "capslock",
}


def key_name(value: Any) -> str:
    """Normalize one key; 'mod' becomes Command on macOS and Ctrl on Windows."""
    key = text(value, "Tuş", limit=40).strip().lower()
    key = KEY_ALIASES.get(key, key)
    if key == "mod":
        return key
    try:
        from pyautogui import KEYBOARD_KEYS
    except (ImportError, KeyError) as exc:
        raise WorkflowError("Klavye otomasyonu için masaüstü otomasyon paketleri gerekir.") from exc
    if key not in KEYBOARD_KEYS:
        raise WorkflowError(f"Tanınmayan tuş: {value}. Örnek: enter, tab, esc, f5, a, ctrl, shift, alt, mod.")
    return key


def key_combination(value: Any) -> list[str]:
    raw = text(value, "Kısayol", limit=120)
    keys = [part for part in (item.strip() for item in raw.replace(" ", "").split("+")) if part]
    if raw.strip().endswith("++"):
        keys.append("+")
    if not 1 <= len(keys) <= 5:
        raise WorkflowError("Kısayol 1–5 tuştan oluşmalıdır; tuşları + ile ayırın (ör. mod+s, ctrl+shift+esc).")
    return [key_name(key) for key in keys]


def point(p: dict, x: str = "x", y: str = "y") -> tuple[float, float]:
    return number(p.get(x), "X konumu", 0, 100_000), number(p.get(y), "Y konumu", 0, 100_000)


def screen_call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except ValueError as exc:
        raise WorkflowError("Konum ana ekranın dışında. X/Y değerlerini ana ekrana göre alın.") from exc


@handler("input.mouse_click")
def mouse_click(ctx, p):
    clicks = integer(p.get("clicks", 1), "Tıklama sayısı", 1, 3)
    button = choice(p.get("button", "left"), "Fare düğmesi", BUTTONS)
    screen_call(ctx.desktop().click, *point(p), clicks=clicks, button=button)


@handler("input.mouse_move")
def mouse_move(ctx, p):
    screen_call(ctx.desktop().move, *point(p), duration=number(p.get("duration", 0.2), "Hareket süresi", 0, 10))


@handler("input.drag")
def drag(ctx, p):
    start, end = point(p, "from_x", "from_y"), point(p, "to_x", "to_y")
    screen_call(ctx.desktop().drag, *start, *end, button=choice(p.get("button", "left"), "Fare düğmesi", BUTTONS),
                duration=number(p.get("duration", 0.5), "Sürükleme süresi", 0, 10))


@handler("input.scroll")
def scroll(ctx, p):
    amount = integer(p.get("amount", -5), "Kaydırma miktarı", -100, 100)
    x, y = optional_integer(p.get("x"), "X konumu", 0, 100_000), optional_integer(p.get("y"), "Y konumu", 0, 100_000)
    if (x is None) != (y is None):
        raise WorkflowError("Kaydırma konumu için X ve Y birlikte girilmeli ya da ikisi de boş bırakılmalıdır.")
    desktop = ctx.desktop()
    if choice(p.get("direction", "vertical"), "Kaydırma yönü", {"vertical", "horizontal"}) == "horizontal":
        screen_call(desktop.hscroll, amount, x=x, y=y)
    else:
        screen_call(desktop.scroll, amount, x=x, y=y)


@handler("input.type")
def type_text(ctx, p):
    value = text(p.get("text"), "Yazılacak metin", limit=20_000)
    interval = number(p.get("interval", 0.02), "Harfler arası bekleme", 0, 1)
    method = choice(p.get("method", "auto"), "Yazma yöntemi", {"auto", "type", "paste"})
    desktop = ctx.desktop()
    if method == "paste" or (method == "auto" and not value.isascii()):
        # Unicode (ç, ğ, ş…) is pasted: keyboard layouts differ between computers.
        desktop.paste(value)
    elif value.isascii():
        desktop.write(value, interval=interval)
    else:
        raise WorkflowError("Tuş tuş yazma yalnız İngilizce karakterlerde çalışır; Türkçe karakter için "
                            "yöntemi Otomatik veya Yapıştır seçin.")


@handler("input.hotkey")
def hotkey(ctx, p):
    ctx.desktop().hotkey(*key_combination(p.get("keys")))


@handler("input.press")
def press(ctx, p):
    key = key_name(p.get("key"))
    presses = integer(p.get("presses", 1), "Basma sayısı", 1, 500)
    interval = number(p.get("interval", 0.05), "Basışlar arası bekleme", 0, 5)
    desktop = ctx.desktop()
    if key == "mod":
        key = desktop.modifier
    for index in range(presses):
        ctx.check_cancelled()
        desktop.press(key)
        if interval and index + 1 < presses:
            ctx.wait(interval)


@handler("input.key_state")
def key_state(ctx, p):
    key = key_name(p.get("key"))
    if choice(p.get("state", "down"), "Tuş durumu", {"down", "up"}) == "down":
        ctx.desktop().key_down(key)
        ctx.held_keys.add(key)
    else:
        ctx.desktop().key_up(key)
        ctx.held_keys.discard(key)


@handler("input.mouse_position")
def mouse_position(ctx, p):
    x, y = ctx.desktop().position()
    return {"x": x, "y": y}
