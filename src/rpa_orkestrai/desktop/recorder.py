"""Record mouse and keyboard actions and turn them into workflow steps (a macro recorder).

Listener callbacks only enqueue raw events: Windows removes low-level hooks that
answer slowly. A worker thread adds the window under each click, and the final
list becomes steps: window-relative clicks with a Pencereyi tanı step, typed
text, shortcuts, special keys, drags, scrolling and (optionally) waits. Clicks on
RpaOrkestrAI's own windows and the stop key (F9) are never recorded.
"""

from __future__ import annotations

import copy
import math
import os
import platform
import queue
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from .windows import WindowError, WindowInfo

STOP_KEY = "f9"
CLICK_RADIUS = 6
DOUBLE_CLICK_SECONDS = 0.45
DRAG_DISTANCE = 10
WAIT_THRESHOLD = 1.5
MAX_WAIT = 30
MAX_EVENTS = 5000
MAX_SECONDS = 1800
MODIFIERS = {"shift", "ctrl", "alt", "cmd"}
KEY_NAMES = {
    "shift_l": "shift", "shift_r": "shift", "ctrl_l": "ctrl", "ctrl_r": "ctrl", "alt_l": "alt", "alt_r": "alt",
    "alt_gr": "alt", "cmd_l": "cmd", "cmd_r": "cmd", "page_up": "pageup", "page_down": "pagedown",
    "caps_lock": "capslock", "print_screen": "printscreen", "num_lock": "numlock", "scroll_lock": "scrolllock",
}
SPECIAL_KEYS = {"enter", "tab", "esc", "backspace", "delete", "insert", "up", "down", "left", "right", "home",
                "end", "pageup", "pagedown", "capslock", "printscreen", *(f"f{i}" for i in range(1, 25))}


@dataclass
class Event:
    kind: str  # mouse_down, mouse_up, scroll, key
    time: float
    x: int = 0
    y: int = 0
    button: str = "left"
    dx: int = 0
    dy: int = 0
    key: str = ""
    text: str = ""
    modifiers: tuple[str, ...] = ()
    window: WindowInfo | None = None


def _step(action: str, label: str, /, **params: Any) -> dict:
    return {"id": uuid.uuid4().hex[:12], "title": label[:200], "action": action, "params": params,
            "children": [], "otherwise": []}


def _short(value: str, limit: int = 40) -> str:
    value = " ".join(value.split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def events_to_steps(events: list[Event], *, system: str | None = None, record_waits: bool = True,
                    relative_windows: bool = True) -> list[dict]:
    """Convert recorded events into Studio steps; pure, so it can be tested and previewed."""
    system = system or platform.system()
    primary = "cmd" if system == "Darwin" else "ctrl"
    steps: list[dict] = []
    windows: dict[tuple[str, str], str] = {}
    text_buffer = ""
    last_time: float | None = None

    def flush_text() -> None:
        nonlocal text_buffer
        if text_buffer:
            steps.append(_step("input.type", f"Yaz: {_short(text_buffer)}", text=text_buffer, method="auto",
                               interval=0.02))
            text_buffer = ""

    def wait_before(moment: float) -> None:
        if record_waits and last_time is not None and moment - last_time >= WAIT_THRESHOLD:
            flush_text()
            seconds = round(min(moment - last_time, MAX_WAIT), 1)
            steps.append(_step("core.wait", f"Bekle {seconds:g} sn", seconds=seconds))

    def window_variable(window: WindowInfo) -> str:
        key = (window.application, window.title)
        if key not in windows:
            windows[key] = f"pencere{len(windows) + 1}"
            steps.append(_step("desktop.find_window", f"Pencereyi tanı: {_short(window.title)}",
                               application=window.application, title=window.title, match="exact", timeout=10,
                               on_missing="stop", output=windows[key]))
        return windows[key]

    # Pair presses with releases into clicks and drags; merge double clicks and scroll runs.
    gestures: list[dict] = []
    pending: dict[str, Event] = {}
    for event in sorted(events, key=lambda item: item.time):
        if event.kind == "mouse_down":
            pending[event.button] = event
        elif event.kind == "mouse_up":
            down = pending.pop(event.button, None)
            if down is None:
                continue
            if math.dist((down.x, down.y), (event.x, event.y)) > DRAG_DISTANCE:
                gestures.append({"kind": "drag", "time": down.time, "end": event.time, "down": down, "up": event})
                continue
            previous = gestures[-1] if gestures else None
            if (previous and previous["kind"] == "click" and previous["down"].button == down.button
                    and down.time - previous["end"] <= DOUBLE_CLICK_SECONDS and previous["clicks"] < 3
                    and math.dist((previous["down"].x, previous["down"].y), (down.x, down.y)) <= CLICK_RADIUS):
                previous["clicks"] += 1
                previous["end"] = event.time
            else:
                gestures.append({"kind": "click", "time": down.time, "end": event.time, "down": down, "clicks": 1})
        elif event.kind == "scroll":
            previous = gestures[-1] if gestures else None
            if previous and previous["kind"] == "scroll" and event.time - previous["end"] <= 0.6:
                previous["dx"] += event.dx
                previous["dy"] += event.dy
                previous["end"] = event.time
            else:
                gestures.append({"kind": "scroll", "time": event.time, "end": event.time, "x": event.x,
                                 "y": event.y, "dx": event.dx, "dy": event.dy})
        elif event.kind == "key":
            gestures.append({"kind": "key", "time": event.time, "end": event.time, "event": event})

    for gesture in gestures:
        if gesture["kind"] == "key":
            event = gesture["event"]
            held = [name for name in ("ctrl", "alt", "cmd", "shift") if name in event.modifiers]
            commanding = any(name in held for name in ("ctrl", "alt", "cmd"))
            if event.text and not commanding:
                if not (text_buffer and gesture["time"] - (last_time or 0) < WAIT_THRESHOLD):
                    wait_before(gesture["time"])
                text_buffer += event.text
                last_time = gesture["end"]
                continue
            if event.key == "backspace" and text_buffer and not held:
                text_buffer = text_buffer[:-1]
                last_time = gesture["end"]
                continue
            wait_before(gesture["time"])
            flush_text()
            if held and (event.key in SPECIAL_KEYS or commanding):
                names = ["mod" if name == primary else "command" if name == "cmd" else name for name in held]
                combo = "+".join([*names, event.key])
                steps.append(_step("input.hotkey", f"Kısayol: {combo}", keys=combo))
            elif event.key in SPECIAL_KEYS:
                previous = steps[-1] if steps else None
                if previous and previous["action"] == "input.press" and previous["params"]["key"] == event.key:
                    previous["params"]["presses"] += 1
                    previous["title"] = f"Tuşa bas: {event.key} × {previous['params']['presses']}"
                else:
                    steps.append(_step("input.press", f"Tuşa bas: {event.key}", key=event.key, presses=1,
                                       interval=0.05))
            last_time = gesture["end"]
            continue
        wait_before(gesture["time"])
        flush_text()
        if gesture["kind"] == "click":
            down = gesture["down"]
            window = down.window if relative_windows else None
            label = {1: "Tıkla", 2: "Çift tıkla", 3: "Üç kez tıkla"}[gesture["clicks"]]
            if down.button == "right":
                label = "Sağ tıkla"
            if window is not None:
                variable = window_variable(window)
                x, y = down.x - window.x, down.y - window.y
                steps.append(_step("desktop.window_click", f"{label}: {_short(window.title, 30)} ({x}, {y})",
                                   window="${" + variable + "}", target_mode="coordinates", x=x, y=y,
                                   clicks=gesture["clicks"] if gesture["clicks"] <= 2 else 2,
                                   button="right" if down.button == "right" else "left"))
            else:
                steps.append(_step("input.mouse_click", f"{label}: ({down.x}, {down.y})", x=down.x, y=down.y,
                                   button=down.button, clicks=gesture["clicks"]))
        elif gesture["kind"] == "drag":
            down, up = gesture["down"], gesture["up"]
            steps.append(_step("input.drag", f"Sürükle: ({down.x}, {down.y}) → ({up.x}, {up.y})",
                               from_x=down.x, from_y=down.y, to_x=up.x, to_y=up.y, button=down.button,
                               duration=round(min(max(gesture["end"] - gesture["time"], 0.2), 3), 1)))
        elif gesture["kind"] == "scroll":
            horizontal = gesture["dy"] == 0 and gesture["dx"] != 0
            amount = max(-100, min(100, gesture["dx"] if horizontal else gesture["dy"]))
            if amount:
                steps.append(_step("input.scroll", f"Kaydır: {amount}", amount=amount,
                                   direction="horizontal" if horizontal else "vertical", x=gesture["x"],
                                   y=gesture["y"]))
        last_time = gesture["end"]
    flush_text()
    return steps


# ----- live recording -------------------------------------------------------------
def _key(key: Any) -> tuple[str, str]:
    """(normalized key name, typed text) for a pynput key."""
    name = getattr(key, "name", None)
    if name:
        if name == "space":
            return "space", " "
        return KEY_NAMES.get(name, name), ""
    char = getattr(key, "char", None)
    vk = getattr(key, "vk", None)
    if char and char.isprintable():
        return char.lower(), char
    if platform.system() == "Windows" and vk is not None:
        if 65 <= vk <= 90:
            return chr(vk).lower(), ""
        if 48 <= vk <= 57:
            return chr(vk), ""
    return (char or "").lower(), ""


class PynputSource:
    """Mouse and keyboard listeners; callbacks only enqueue."""

    def __init__(self):
        try:
            from pynput import keyboard, mouse
        except ImportError as exc:
            raise WindowError("Hareket kaydı için masaüstü otomasyon paketlerini kurun: .[automation]") from exc
        self.keyboard, self.mouse = keyboard, mouse
        self.listeners: list[Any] = []

    def start(self, events: queue.Queue, stop: threading.Event, clock: Callable[[], float]) -> None:
        held: set[str] = set()

        def click(x, y, button, pressed):
            events.put(Event("mouse_down" if pressed else "mouse_up", clock(), int(x), int(y),
                             getattr(button, "name", "left")))

        def scroll(x, y, dx, dy):
            events.put(Event("scroll", clock(), int(x), int(y), dx=int(dx), dy=int(dy)))

        def press(key):
            name, typed = _key(key)
            if name == STOP_KEY and not held:
                stop.set()
                return
            if name in MODIFIERS:
                held.add(name)
                return
            events.put(Event("key", clock(), key=name, text=typed, modifiers=tuple(sorted(held))))

        def release(key):
            held.discard(_key(key)[0])

        self.listeners = [self.mouse.Listener(on_click=click, on_scroll=scroll),
                          self.keyboard.Listener(on_press=press, on_release=release)]
        for listener in self.listeners:
            listener.start()
        for listener in self.listeners:
            listener.wait()
        if platform.system() == "Darwin" and not all(getattr(listener, "IS_TRUSTED", True)
                                                     for listener in self.listeners):
            self.stop()
            raise WindowError("Hareket kaydı için Sistem Ayarları → Gizlilik ve Güvenlik bölümünde RpaOrkestrAI'ye "
                              "Erişilebilirlik ve Girdi İzleme izni verin, ardından uygulamayı yeniden açın.")

    def stop(self) -> None:
        for listener in self.listeners:
            listener.stop()
        self.listeners = []


def check_permissions() -> None:
    if platform.system() != "Darwin":
        return
    try:
        import ApplicationServices
        import Quartz
    except ImportError:
        return
    listen = getattr(Quartz, "CGPreflightListenEventAccess", lambda: True)()
    if not ApplicationServices.AXIsProcessTrusted() or not listen:
        request = getattr(Quartz, "CGRequestListenEventAccess", None)
        if request is not None:
            request()
        raise WindowError("Hareket kaydı için Sistem Ayarları → Gizlilik ve Güvenlik bölümünde RpaOrkestrAI'ye "
                          "Erişilebilirlik ve Girdi İzleme izni verin, ardından uygulamayı yeniden açın.")


class RecordJobs:
    """One recording at a time; shares the desktop reservation with runs and pickers."""

    def __init__(self, manager, *, source_factory: Callable = PynputSource, windows_factory: Callable | None = None,
                 view_factory: Callable | None = None, permissions: Callable = check_permissions,
                 clock: Callable[[], float] = time.monotonic):
        self.manager = manager
        self.source_factory, self.view_factory, self.permissions = source_factory, view_factory, permissions
        self.windows_factory = windows_factory
        self.clock = clock
        self._jobs: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.RLock()

    def start(self, *, delay: int = 3, record_waits: bool = True, relative_windows: bool = True) -> dict:
        self.permissions()
        with self._lock:
            if any(not job["done"] for job in self._jobs.values()):
                raise RuntimeError("Zaten bir kayıt sürüyor.")
            while len(self._jobs) >= 5:
                self._jobs.popitem(last=False)
            cancel, stop = threading.Event(), threading.Event()
            token = self.manager.reserve_desktop(cancel)
            key = uuid.uuid4().hex
            job = {"public": {"id": key, "status": "starting", "countdown": delay, "events": 0,
                              "message": "Kayıt hazırlanıyor."},
                   "cancel": cancel, "stop": stop, "token": token, "done": False}
            self._jobs[key] = job
            options = {"record_waits": record_waits, "relative_windows": relative_windows}
            threading.Thread(target=self._work, args=(job, delay, options), name="rpa-recorder", daemon=True).start()
            return copy.deepcopy(job["public"])

    def _update(self, job, **values) -> None:
        with self._lock:
            job["public"].update(values)

    def _work(self, job, delay, options) -> None:
        view = None
        source = None
        try:
            if self.view_factory is not None:
                view = self.view_factory(job["stop"], job["cancel"])
            deadline = self.clock() + delay
            while self.clock() < deadline:
                if job["cancel"].is_set():
                    raise InterruptedError()
                remaining = math.ceil(deadline - self.clock())
                self._update(job, status="countdown", countdown=remaining,
                             message=f"Kayıt {remaining} saniye içinde başlıyor.")
                if view is not None:
                    view.show(f"Kayıt {remaining} sn içinde başlıyor…")
                job["cancel"].wait(min(0.2, max(0.0, deadline - self.clock())))
            events: queue.Queue = queue.Queue()
            source = self.source_factory()
            source.start(events, job["stop"], self.clock)
            self._update(job, status="recording", countdown=0,
                         message="Kaydediliyor. Bitirmek için F9'a veya Kaydı bitir düğmesine basın.")
            recorded = self._collect(job, events, view)
            source.stop()
            source = None
            if job["cancel"].is_set():
                raise InterruptedError()
            steps = events_to_steps(recorded, **options)
            self._update(job, status="completed", message=f"{len(steps)} adım oluşturuldu.",
                         result={"steps": steps})
        except InterruptedError:
            self._update(job, status="cancelled", message="Kayıt iptal edildi.")
        except WindowError as exc:
            self._update(job, status="error", message=str(exc))
        except Exception:
            self._update(job, status="error", message="Kayıt tamamlanamadı. Ekran ve erişilebilirlik izinlerini kontrol edin.")
        finally:
            if source is not None:
                source.stop()
            if view is not None:
                view.close()
            self.manager.release_desktop(job["token"])
            with self._lock:
                job["done"] = True

    def _collect(self, job, events: queue.Queue, view) -> list[Event]:
        own = os.getpid()
        box = getattr(view, "bounds", None)
        windows = self.windows_factory() if self.windows_factory else None
        recorded: list[Event] = []
        started = self.clock()
        while not job["stop"].is_set() and not job["cancel"].is_set():
            if self.clock() - started > MAX_SECONDS or len(recorded) >= MAX_EVENTS:
                break
            try:
                event = events.get(timeout=0.2)
            except queue.Empty:
                if view is not None:
                    view.show(f"Kaydediliyor · {len(recorded)} hareket · F9: bitir")
                continue
            if box is not None and event.kind in {"mouse_down", "scroll"}:
                x, y, width, height = box
                if x - 10 <= event.x < x + width + 10 and y - 10 <= event.y < y + height + 10:
                    job.setdefault("ignored", set()).add(event.button)
                    continue
            if event.kind in {"mouse_down", "scroll"} and windows is not None:
                try:
                    under = next((w for w in windows.list_windows()
                                  if w.x <= event.x < w.x + w.width and w.y <= event.y < w.y + w.height), None)
                except (WindowError, OSError):
                    under = None
                if under is not None and under.pid == own:
                    # Studio or the recording box: never part of the automation.
                    job.setdefault("ignored", set()).add(event.button)
                    continue
                event = replace(event, window=under)
            elif event.kind == "mouse_up" and event.button in job.get("ignored", set()):
                job["ignored"].discard(event.button)
                continue
            recorded.append(event)
            self._update(job, events=len(recorded))
        return recorded

    def status(self, key: str) -> dict:
        with self._lock:
            if key not in self._jobs:
                raise KeyError(key)
            return copy.deepcopy(self._jobs[key]["public"])

    def stop(self, key: str) -> dict:
        with self._lock:
            if key not in self._jobs:
                raise KeyError(key)
            self._jobs[key]["stop"].set()
            return copy.deepcopy(self._jobs[key]["public"])

    def cancel(self, key: str) -> None:
        with self._lock:
            job = self._jobs.get(key)
            if job is not None:
                job["cancel"].set()

    def close(self) -> None:
        with self._lock:
            for job in self._jobs.values():
                job["cancel"].set()


class RecorderView:
    """Small always-on-top box with the state and a stop button (native app only)."""

    def __init__(self, stop: threading.Event, cancel: threading.Event):
        from .picker import _native_host

        self.webview, self.studio = _native_host()
        bridge = _RecorderBridge(stop, cancel)
        screen = next((s for s in self.webview.screens if s.x == 0 and s.y == 0), self.webview.screens[0])
        width, height = 380, 96
        self.bounds = (max(0, screen.width - width - 24), max(0, screen.height - height - 80), width, height)
        self.box = self.webview.create_window(
            "RpaOrkestrAI kayıt", html=_RECORDER_HTML, js_api=bridge, width=width, height=height,
            x=max(0, screen.width - width - 24), y=max(0, screen.height - height - 80), screen=screen,
            resizable=False, frameless=True, easy_drag=True, shadow=True, focus=False, on_top=True,
            background_color="#173638")
        self.studio.hide()
        self._last = ""

    def show(self, message: str) -> None:
        if message != self._last and self.box is not None:
            self._last = message
            try:
                import json

                self.box.evaluate_js(f"setState({json.dumps(message)})")
            except Exception:
                pass

    def close(self) -> None:
        try:
            if self.box is not None:
                self.box.destroy()
        finally:
            self.box = None
            self.studio.show()


class _RecorderBridge:
    def __init__(self, stop: threading.Event, cancel: threading.Event):
        self._stop, self._cancel = stop, cancel

    def stop(self) -> None:
        self._stop.set()

    def cancel(self) -> None:
        self._cancel.set()


_RECORDER_HTML = """<!doctype html><html lang="tr"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'">
<style>*{box-sizing:border-box}body{margin:0;padding:12px 14px;background:#173638;color:white;
font:13px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;display:flex;align-items:center;gap:10px}
.dot{width:12px;height:12px;border-radius:50%;background:#e0584c;flex:none;animation:p 1s infinite}
@keyframes p{50%{opacity:.35}}#state{flex:1}button{background:#355354;border:1px solid #729d92;border-radius:7px;
color:white;padding:8px 10px;cursor:pointer}</style>
<span class="dot"></span><div id="state">Kayıt hazırlanıyor…</div>
<button onclick="window.pywebview?.api.stop()">Kaydı bitir</button>
<button title="Kaydı iptal et" onclick="window.pywebview?.api.cancel()">✕</button>
<script>function setState(text){document.getElementById('state').textContent=text;}</script></html>"""
