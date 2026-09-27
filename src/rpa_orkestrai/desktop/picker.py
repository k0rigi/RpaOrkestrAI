"""Explicit, cancellable on-screen target selection without sending ERP input.

The HTTP process owns the session/run reservation. This module only owns the
native windows and RAM-only screenshot while ``pick`` runs in its worker thread.
"""

from __future__ import annotations

import base64
import ctypes
import io
import json
import math
import platform
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .controller import DesktopController
from .windows import WindowError, WindowInfo, WindowService, validate_selector

_host: tuple[Any, Any] | None = None
_host_lock = threading.Lock()


def register_native_host(webview: Any, window: Any) -> None:
    global _host
    with _host_lock:
        _host = (webview, window)


def unregister_native_host(window: Any) -> None:
    global _host
    with _host_lock:
        if _host is not None and _host[1] is window:
            _host = None


def native_available() -> bool:
    with _host_lock:
        return _host is not None


def _native_host() -> tuple[Any, Any]:
    with _host_lock:
        if _host is None:
            raise WindowError("Canlı hedef seçimi için RpaOrkestrAI masaüstü uygulamasını açın.")
        return _host


def _escape_pressed() -> bool:
    if platform.system() == "Windows":
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000)
    if platform.system() == "Darwin":
        import Quartz

        return bool(Quartz.CGEventSourceKeyState(Quartz.kCGEventSourceStateCombinedSessionState, 53))
    raise WindowError("Canlı hedef seçimi macOS ve Windows üzerinde desteklenir.")


def _mouse_position() -> tuple[int, int]:
    # position() only reads the mouse; it never clicks or moves it.
    import pyautogui

    point = pyautogui.position()
    return int(point.x), int(point.y)


def _png_data(image: Any) -> str:
    output = io.BytesIO()
    image.save(output, format="PNG")
    if output.tell() > 12 * 1024 * 1024:
        raise WindowError("ERP görüntüsü çok büyük. Pencereyi küçültüp yeniden deneyin.")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def _windows_geometry(window: Any, x: int, y: int, width: int, height: int) -> None:
    """Fit a pywebview window to physical pixels despite Windows display scaling.

    pywebview's width/move API takes DIP pixels; desktop automation uses Win32
    pixels. SetWindowPos is safe across threads and does not inject user input.
    """
    from ctypes import wintypes

    user = ctypes.WinDLL("user32", use_last_error=True)
    position = user.SetWindowPos
    position.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                         ctypes.c_int, ctypes.c_int, wintypes.UINT]
    position.restype = wintypes.BOOL
    handle = int(window.native.Handle.ToInt64())
    # Preserve on-top order and ERP keyboard focus while moving the HUD.
    if not position(handle, None, x, y, width, height, 0x0004 | 0x0010 | 0x0040):
        raise WindowError("Hedef seçim penceresi ekran boyutuna ayarlanamadı.")


def _window_scale(window: Any) -> float:
    if platform.system() != "Windows":
        return 1.0
    from ctypes import wintypes

    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetDpiForWindow.argtypes = [wintypes.HWND]
    user.GetDpiForWindow.restype = wintypes.UINT
    dpi = user.GetDpiForWindow(int(window.native.Handle.ToInt64()))
    if not 96 <= dpi <= 768:
        raise WindowError("Ekran ölçeği okunamadı. Ekran ayarlarını kontrol edin.")
    return dpi / 96


@dataclass
class PickerResult:
    window: WindowInfo
    image: Any
    x: int | None = None
    y: int | None = None
    crop: dict[str, int] | None = None
    point: dict[str, int] | None = None

    def as_dict(self) -> dict:
        result = {"window": self.window, "image": self.image}
        if self.x is not None:
            result.update(x=self.x, y=self.y)
        if self.crop is not None:
            result["crop"] = self.crop
        if self.point is not None:
            result["point"] = self.point
        return result


class _SelectionBridge:
    """Only three operations are exposed to the private, local overlay document."""

    def __init__(self, cancel: threading.Event, move: Callable | None = None):
        self._cancel = cancel
        self._move = move
        self._done = threading.Event()
        self._lock = threading.Lock()
        self._payload: dict | None = None

    def finish(self, selection: dict) -> None:
        with self._lock:
            if not self._done.is_set() and not self._cancel.is_set():
                self._payload = selection
                self._done.set()

    def cancel(self) -> None:
        self._cancel.set()
        self._done.set()

    def move(self) -> None:
        if self._move is not None:
            self._move()


class NativePickerView:
    """pywebview windows, created from the worker while its main GUI loop runs."""

    def __init__(self, host: tuple[Any, Any] | None = None):
        self.webview, self.studio = host or _native_host()
        self.hud = None
        self.overlay = None
        self.hud_bounds: tuple[int, int, int, int] | None = None
        self.screen_height = 0

    def hide_studio(self) -> None:
        self.studio.hide()

    def restore_studio(self) -> None:
        self.studio.show()

    def _ready(self, window: Any, check: Callable[[], None]) -> None:
        deadline = time.monotonic() + 15
        while not window.events.loaded.wait(0.03):
            check()
            if time.monotonic() >= deadline:
                raise WindowError("Hedef seçim penceresi açılamadı. Tekrar deneyin.")
        check()

    def _primary_screen(self):
        for screen in self.webview.screens:
            if screen.x == 0 and screen.y == 0:
                return screen
        raise WindowError("Ana ekran bulunamadı. Ekran ayarlarını kontrol edip yeniden deneyin.")

    def open_countdown(self, width: int, height: int, cancel: threading.Event,
                       check: Callable[[], None]) -> None:
        bridge = _SelectionBridge(cancel, self.move_countdown)
        self.screen_height = height
        hud_width, hud_height = min(460, width), min(110, height)
        x, y = max(0, (width - hud_width) // 2), max(0, height - hud_height - 50)
        self.hud_bounds = (x, y, hud_width, hud_height)
        self.hud = self.webview.create_window(
            "RpaOrkestrAI hedef seçimi", html=_HUD_HTML, js_api=bridge,
            width=hud_width, height=hud_height, x=x, y=y,
            screen=self._primary_screen(),
            min_size=(200, 70), resizable=False,
            frameless=True, easy_drag=False, shadow=False, focus=False, on_top=True,
            background_color="#173638",
        )
        if self.hud is None:
            raise WindowError("Geri sayım penceresi oluşturulamadı.")
        self._ready(self.hud, check)
        if platform.system() == "Windows":
            scale = _window_scale(self.hud)
            hud_width, hud_height = min(round(460 * scale), width), min(round(110 * scale), height)
            x, y = max(0, (width - hud_width) // 2), max(0, height - hud_height - 50)
            self.hud_bounds = (x, y, hud_width, hud_height)
            _windows_geometry(self.hud, *self.hud_bounds)

    def move_countdown(self) -> None:
        if self.hud is not None and self.hud_bounds is not None:
            x, y, width, height = self.hud_bounds
            y = 30 if y > self.screen_height // 2 else max(0, self.screen_height - height - 50)
            self.hud_bounds = (x, y, width, height)
            if platform.system() == "Windows":
                _windows_geometry(self.hud, *self.hud_bounds)
            else:
                self.hud.move(x, y)

    def countdown(self, remaining: int, mode: str) -> None:
        instruction = ("Fareyi hedef alanın üzerine götürün; tıklamayın."
                       if mode == "coordinates" else "ERP ekranını hazırlayın; ardından alanı sürükleyerek seçin.")
        self.hud.evaluate_js(f"updateCountdown({remaining}, {json.dumps(instruction)})")

    def close_countdown(self) -> None:
        if self.hud is not None:
            self.hud.destroy()
            self.hud.events.closed.wait(2)
            self.hud = None
            self.hud_bounds = None

    def select(self, window: WindowInfo, image: Any, mode: str, size: tuple[int, int],
               cancel: threading.Event, check: Callable[[], None]) -> dict:
        bridge = _SelectionBridge(cancel)
        html = overlay_html(window, _png_data(image), mode, size)
        self.overlay = self.webview.create_window(
            "RpaOrkestrAI — hedef alanını seçin", html=html, js_api=bridge,
            width=size[0], height=size[1], x=0, y=0,
            screen=self._primary_screen(),
            min_size=(200, 100), resizable=False, frameless=True,
            easy_drag=False, shadow=False, focus=True, on_top=True,
            background_color="#16292a",
        )
        if self.overlay is None:
            raise WindowError("Görsel seçim penceresi oluşturulamadı.")
        def on_closed():
            if not bridge._done.is_set():
                bridge.cancel()

        self.overlay.events.closed += on_closed
        self._ready(self.overlay, check)
        if platform.system() == "Windows":
            _windows_geometry(self.overlay, 0, 0, *size)
        while not bridge._done.wait(0.03):
            check()
        check()
        return bridge._payload or {}

    def close(self) -> None:
        self.close_countdown()
        if self.overlay is not None:
            # Closing a completed overlay must not cancel the successful session.
            self.overlay.destroy()
            self.overlay.events.closed.wait(2)
            self.overlay = None


class LivePicker:
    """Blocking picker; run in a reserved desktop worker, never the GUI thread."""

    def __init__(self, *, view_factory: Callable = NativePickerView,
                 windows_factory: Callable = WindowService,
                 desktop_factory: Callable = DesktopController,
                 pointer: Callable = _mouse_position, escape: Callable = _escape_pressed,
                 clock: Callable = time.monotonic):
        self.view_factory = view_factory
        self.windows_factory = windows_factory
        self.desktop_factory = desktop_factory
        self.pointer = pointer
        self.escape = escape
        self.clock = clock

    @staticmethod
    def _point(window: WindowInfo, point: Any, size: tuple[int, int]) -> dict[str, int]:
        if (not isinstance(point, dict) or set(point) != {"x", "y"}
                or any(type(point[key]) is not int for key in ("x", "y"))):
            raise WindowError("Seçilen hedef noktası geçersiz.")
        x, y = point["x"], point["y"]
        if not (0 <= x < window.width and 0 <= y < window.height
                and 0 <= x + window.x < size[0] and 0 <= y + window.y < size[1]):
            raise WindowError("Fare hedef ERP penceresinin dışında. Hedefi yeniden seçin.")
        return {"x": x, "y": y}

    @classmethod
    def _selection(cls, window: WindowInfo, image: Any, selection: dict,
                   mode: str, size: tuple[int, int]) -> PickerResult:
        if not isinstance(selection, dict):
            raise WindowError("Görsel seçim sonucu geçersiz.")
        crop = selection.get("crop")
        if (not isinstance(crop, dict) or set(crop) != {"x", "y", "width", "height"}
                or any(type(value) is not int for value in crop.values())):
            raise WindowError("Görsel alanı geçerli bir dikdörtgen olmalıdır.")
        x, y, width, height = (crop[key] for key in ("x", "y", "width", "height"))
        if min(width, height) < 8 or max(width, height) > 4000 or width * height > 2_000_000:
            raise WindowError("8 × 8 ile 2 milyon piksel arasında, ayırt edici küçük bir görsel seçin.")
        cls._point(window, {"x": x, "y": y}, size)
        cls._point(window, {"x": x + width - 1, "y": y + height - 1}, size)
        from PIL import ImageStat

        if ImageStat.Stat(image.crop((x, y, x + width, y + height)).convert("L")).stddev[0] < 1:
            raise WindowError("Seçilen alan düz renk. FormID etiketi gibi ayırt edici bir alan seçin.")
        point = cls._point(window, selection.get("point"), size) if mode == "image" else None
        return PickerResult(window, image, crop=crop, point=point)

    def pick(self, selector: dict, mode: str, delay: int, *, cancel: threading.Event,
             on_state: Callable[[dict], None] | None = None) -> dict:
        if not isinstance(selector, dict):
            raise WindowError("Önce hedef ERP penceresini tanıtın.")
        application, title, match = (selector.get(key, default) for key, default in
                                     (("application", ""), ("title", ""), ("match", "exact")))
        validate_selector(application, title, match)
        if mode not in {"coordinates", "image", "image_only"}:
            raise WindowError("Hedef seçim yöntemi geçersiz.")
        if type(delay) is not int or delay not in {3, 5, 10}:
            raise WindowError("Geri sayım 3, 5 veya 10 saniye olmalıdır.")
        if cancel.is_set():
            raise InterruptedError("Hedef seçimi iptal edildi.")
        started = self.clock()

        def check():
            if cancel.is_set() or self.escape():
                cancel.set()
                raise InterruptedError("Hedef seçimi iptal edildi.")
            if self.clock() - started >= 120:
                raise WindowError("Hedef seçiminin süresi doldu. Yeniden başlatın.")

        def state(status: str, **values):
            if on_state:
                on_state({"status": status, **values})

        view = self.view_factory()
        windows = self.windows_factory(cancel=cancel)
        desktop = self.desktop_factory(cancel_check=cancel.is_set)
        target = windows.find(application, title, match)
        width, height = windows._screen_size(desktop)
        window = windows.current(target)
        # Reject entirely offscreen windows before hiding Studio. Clipped native
        # maximize frames are validated by screenshot_window at capture time.
        if not (window.x < width and window.y < height
                and window.x + window.width > 0 and window.y + window.height > 0):
            raise WindowError("ERP penceresini ana ekrana taşıyıp yeniden deneyin.")
        try:
            state("preparing", message="ERP penceresi hazırlanıyor.")
            view.hide_studio()
            view.open_countdown(width, height, cancel, check)
            window = windows.focus(target)
            deadline = self.clock() + delay
            last_remaining = None
            sampled = None
            while True:
                check()
                remaining_seconds = deadline - self.clock()
                if remaining_seconds <= 0:
                    # Read the physical mouse position at the deadline, before
                    # native UI rendering or OS window enumeration can delay it.
                    if mode == "coordinates":
                        sampled = self.pointer()
                    state("countdown", remaining=0)
                    break
                remaining = math.ceil(remaining_seconds)
                if remaining != last_remaining:
                    state("countdown", remaining=remaining)
                    view.countdown(remaining, mode)
                    last_remaining = remaining
                cancel.wait(min(0.03, max(0, deadline - self.clock())))
            check()
            windows._guard(target, window)
            point = None
            if mode == "coordinates":
                screen_x, screen_y = sampled
                point = self._point(window, {"x": screen_x - window.x, "y": screen_y - window.y},
                                    (width, height))
                bounds = view.hud_bounds
                if bounds is not None:
                    left, top, hud_width, hud_height = bounds
                    if left <= screen_x < left + hud_width and top <= screen_y < top + hud_height:
                        raise WindowError("Fare geri sayım kutusunun üzerinde. ERP alanını yeniden seçin.")
            view.close_countdown()
            check()
            # No inputs are sent to ERP. The screenshot is only a review preview
            # for a coordinate result or the frozen canvas used for image selection.
            captured_window, image = windows._capture_window(target, desktop)
            if captured_window != window:
                raise WindowError("ERP penceresinin konumu değişti. Hedefi yeniden seçin.")
            if width * height > 16_000_000 or image.width * image.height > 16_000_000:
                raise WindowError("Ekran görüntüsü çok büyük. ERP penceresini küçültün.")
            if mode == "coordinates":
                return PickerResult(window, image, **point).as_dict()
            state("selecting", message="Görsel alanını sürükleyerek seçin; Esc ile iptal edin.")
            selection = view.select(window, image, mode, (width, height), cancel, check)
            check()
            # Overlay owns focus now; identity and geometry must still match,
            # but ERP is intentionally not the foreground application.
            if windows.current(target) != window:
                raise WindowError("ERP penceresi değişti. Hedefi yeniden seçin.")
            return self._selection(window, image, selection, mode, (width, height)).as_dict()
        finally:
            try:
                view.close()
            finally:
                view.restore_studio()


_HUD_HTML = """<!doctype html><html lang="tr"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'">
<style>*{box-sizing:border-box}body{margin:0;padding:14px 18px;background:#173638;color:white;
font:14px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;display:flex;align-items:center;gap:16px}
#count{font-size:40px;font-weight:700;min-width:42px}p{margin:4px 0}small{color:#bfd9d1}
button{margin-left:auto;background:#355354;border:1px solid #729d92;border-radius:7px;color:white;padding:9px;cursor:pointer}</style>
<div id="count">…</div><div><p id="instruction">Ekran hazırlanıyor…</p><small>Esc: iptal</small></div>
<button title="Kutuyu ekranın diğer ucuna taşı" onclick="window.pywebview?.api.move()">↕</button>
<button onclick="window.pywebview?.api.cancel()">İptal</button>
<script>function updateCountdown(seconds, message){document.getElementById('count').textContent=seconds;
document.getElementById('instruction').textContent=message;}</script></html>"""


def overlay_html(window: WindowInfo, image_url: str, mode: str, size: tuple[int, int]) -> str:
    data = {"window": {key: getattr(window, key) for key in ("x", "y", "width", "height")},
            "image": image_url, "mode": mode, "screen": {"width": size[0], "height": size[1]}}
    # All embedded values are numeric or a locally generated PNG data URI.
    return _OVERLAY_HTML.replace("__PICKER_DATA__", json.dumps(data))


_OVERLAY_HTML = r"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; script-src 'unsafe-inline' 'unsafe-eval'; style-src 'unsafe-inline'">
<style>*{box-sizing:border-box}html,body{width:100%;height:100%;margin:0;overflow:hidden;user-select:none;
font:14px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#16292a;color:white}
canvas{position:absolute;inset:0;width:100%;height:100%;cursor:crosshair;touch-action:none}
#toolbar{position:fixed;top:22px;left:50%;transform:translateX(-50%);max-width:calc(100% - 32px);
background:#173638f5;border:1px solid #7fa493;border-radius:12px;padding:14px 18px;box-shadow:0 8px 32px #0006;
display:flex;align-items:center;gap:12px;z-index:2;cursor:default}
#toolbar.bottom{top:auto;bottom:22px}#help{min-width:240px;max-width:560px}strong{display:block;margin-bottom:5px}
small{display:block;color:#d1e2dc;line-height:1.4}button{flex:none;padding:10px;border:1px solid #789a91;
border-radius:7px;background:#2d5050;color:white;font:inherit;cursor:pointer}button.primary{background:#177e69}
button:disabled{opacity:.45;cursor:default}#error{color:#ffe0a8;margin-top:4px}#position{font:12px ui-monospace,monospace;color:#9cd1bb}</style></head>
<body><canvas id="surface"></canvas><div id="toolbar"><div id="help"><strong id="title"></strong>
<small id="instruction"></small><small id="position"></small><small>H: araç çubuğunu taşı · R: yeniden seç</small>
<small id="error" role="alert"></small></div>
<button id="reset">Yeniden seç</button><button id="confirm" class="primary" disabled>Seçimi kullan</button>
<button id="cancel">İptal · Esc</button></div>
<script>
const cfg=__PICKER_DATA__, canvas=document.getElementById('surface'), ctx=canvas.getContext('2d');
const title=document.getElementById('title'),instruction=document.getElementById('instruction'),
error=document.getElementById('error'),confirmButton=document.getElementById('confirm'),toolbar=document.getElementById('toolbar');
let crop=null,point=null,start=null,drag=null,phase='crop',ready=false,submitting=false;
const picture=new Image();canvas.width=cfg.screen.width;canvas.height=cfg.screen.height;
const bounds={left:Math.max(0,cfg.window.x),top:Math.max(0,cfg.window.y),
right:Math.min(cfg.screen.width,cfg.window.x+cfg.window.width),bottom:Math.min(cfg.screen.height,cfg.window.y+cfg.window.height)};
function bridgeReady(){ready=true;update();}window.addEventListener('pywebviewready',bridgeReady);
if(window.pywebview?.api)bridgeReady();
function localPoint(e){const r=canvas.getBoundingClientRect();return {x:Math.floor((e.clientX-r.left)*canvas.width/r.width),
y:Math.floor((e.clientY-r.top)*canvas.height/r.height)};}
function inside(p){return p.x>=bounds.left&&p.y>=bounds.top&&p.x<bounds.right&&p.y<bounds.bottom;}
function clamp(p){return{x:Math.max(bounds.left,Math.min(bounds.right-1,p.x)),y:Math.max(bounds.top,Math.min(bounds.bottom-1,p.y))};}
function rect(a,b){return{x:Math.min(a.x,b.x)-cfg.window.x,y:Math.min(a.y,b.y)-cfg.window.y,
width:Math.abs(a.x-b.x)+1,height:Math.abs(a.y-b.y)+1};}
function update(){title.textContent=phase==='crop'?'1. Referans görselini seçin':phase==='point'?'2. İşlem yapılacak alanı seçin':'Seçimi kontrol edin';
instruction.textContent=phase==='crop'?'Sabit etiket veya simgenin çevresini fareyle sürükleyin. Değişen hücre içeriğini seçmeyin.':
phase==='point'?'Metnin yazılacağı veya tıklanacak alanın üzerine tıklayın.':cfg.mode==='image'?
'Hedefi değiştirmek için tekrar tıklayın. Seçimi kullan ile onaylayın.':'Seçimi kullan ile onaylayın. Yeniden seç ile başlayın.';
confirmButton.disabled=!ready||!crop||(cfg.mode==='image'&&!point)||submitting;
document.getElementById('position').textContent=crop?`Görsel ${crop.width} × ${crop.height}`+(point?` · Hedef X:${point.x} Y:${point.y}`:''):'';
draw();}
function draw(){ctx.clearRect(0,0,canvas.width,canvas.height);if(picture.complete&&picture.naturalWidth){ctx.drawImage(picture,cfg.window.x,cfg.window.y,cfg.window.width,cfg.window.height);}
ctx.fillStyle='#10282a88';ctx.fillRect(0,0,canvas.width,canvas.height);const selected=drag||crop;
if(selected){const x=selected.x+cfg.window.x,y=selected.y+cfg.window.y;ctx.save();ctx.beginPath();ctx.rect(x,y,selected.width,selected.height);ctx.clip();
ctx.drawImage(picture,cfg.window.x,cfg.window.y,cfg.window.width,cfg.window.height);ctx.restore();ctx.strokeStyle='#94edb6';ctx.lineWidth=2;
ctx.strokeRect(x+.5,y+.5,selected.width-1,selected.height-1);}
if(point){const x=point.x+cfg.window.x,y=point.y+cfg.window.y;ctx.strokeStyle='#ffdd74';ctx.lineWidth=2;ctx.beginPath();ctx.arc(x,y,10,0,Math.PI*2);
ctx.moveTo(x-17,y);ctx.lineTo(x+17,y);ctx.moveTo(x,y-17);ctx.lineTo(x,y+17);ctx.stroke();}}
picture.onload=update;picture.onerror=()=>{error.textContent='ERP görüntüsü yüklenemedi. İptal edip yeniden deneyin.'};picture.src=cfg.image;
canvas.addEventListener('pointerdown',e=>{if(e.button!==0||submitting||!picture.complete||!picture.naturalWidth)return;const p=localPoint(e);error.textContent='';
if(!inside(p)){error.textContent='Seçimi tanıtılan ERP penceresinin içinde yapın.';return;}
if(phase==='crop'){start=p;drag=null;canvas.setPointerCapture(e.pointerId);}
else if(phase==='point'||(phase==='review'&&cfg.mode==='image')){point={x:p.x-cfg.window.x,y:p.y-cfg.window.y};phase='review';update();}});
canvas.addEventListener('pointermove',e=>{if(!start)return;drag=rect(start,clamp(localPoint(e)));draw();});
canvas.addEventListener('pointerup',e=>{if(!start)return;const r=rect(start,clamp(localPoint(e)));start=null;drag=null;
if(canvas.hasPointerCapture(e.pointerId))canvas.releasePointerCapture(e.pointerId);
if(r.width<8||r.height<8){error.textContent='En az 8 × 8 piksel bir alan sürükleyin.';draw();return;}
if(r.width*r.height>2000000||r.width>4000||r.height>4000){error.textContent='Daha küçük ve ayırt edici bir referans seçin.';draw();return;}
const sample=document.createElement('canvas');sample.width=r.width;sample.height=r.height;const pixels=sample.getContext('2d');
pixels.drawImage(picture,r.x,r.y,r.width,r.height,0,0,r.width,r.height);const rgba=pixels.getImageData(0,0,r.width,r.height).data;
let sum=0,squares=0;for(let i=0;i<rgba.length;i+=4){const gray=.299*rgba[i]+.587*rgba[i+1]+.114*rgba[i+2];sum+=gray;squares+=gray*gray;}
const count=rgba.length/4;if(squares/count-(sum/count)**2<1){error.textContent='Bu alan düz renk. FormID etiketi gibi ayırt edici bir alan seçin.';draw();return;}
crop=r;phase=cfg.mode==='image'?'point':'review';update();});
canvas.addEventListener('pointercancel',()=>{start=null;drag=null;draw();});
function reset(){crop=null;point=null;start=null;drag=null;phase='crop';error.textContent='';update();}
document.getElementById('reset').onclick=reset;
function cancel(){if(window.pywebview?.api)window.pywebview.api.cancel();}
document.getElementById('cancel').onclick=cancel;
async function finish(){if(confirmButton.disabled)return;submitting=true;update();try{await window.pywebview.api.finish({crop,...(point?{point}:{})});}
catch(e){submitting=false;error.textContent='Seçim iletilemedi. Yeniden deneyin.';update();}}
confirmButton.onclick=finish;
window.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();cancel();}else if(e.key==='Enter'){e.preventDefault();finish();}
else if(e.key.toLowerCase()==='r'){reset();}else if(e.key.toLowerCase()==='h'){toolbar.classList.toggle('bottom');}});
// Move the toolbar away from a target under it without changing the canvas.
toolbar.title='Araç çubuğunu alta / üste taşımak için H tuşuna basın.';
update();
</script></body></html>"""
