"""Window discovery and guarded input on macOS/Windows; native imports are lazy."""

from __future__ import annotations

import math
import platform
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath
from typing import Any

from .vision import AmbiguousMatchError, Match, Vision

SUPPORTED_KEYS = frozenset({
    "enter", "tab", "esc", "backspace", "delete", "space", "up", "down", "left", "right",
    "home", "end", "pageup", "pagedown",
} | {f"f{index}" for index in range(1, 13)} | set("abcdefghijklmnopqrstuvwxyz0123456789"))
SUPPORTED_MODIFIERS = frozenset({"none", "mod", "shift", "alt", "ctrl"})


class WindowError(RuntimeError):
    """Public window/permission error, suitable for the Studio inspector."""


@dataclass(frozen=True)
class WindowInfo:
    window_id: int
    pid: int
    application: str
    title: str
    x: int
    y: int
    width: int
    height: int

    def result(self) -> dict:
        return {"found": True, "platform": platform.system(), **asdict(self)}


def validate_selector(application: str, title: str, match: str, timeout: float = 0) -> None:
    if not isinstance(application, str) or not isinstance(title, str):
        raise WindowError("Uygulama adı ve pencere başlığı metin olmalıdır.")
    if not title.strip() or len(title) > 500 or len(application) > 200:
        raise WindowError("Pencere başlığı gereklidir (en fazla 500 karakter).")
    if match not in {"exact", "contains"}:
        raise WindowError("Başlık eşleşmesi 'Tam eşleşme' veya 'İçerir' olmalıdır.")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 <= timeout <= 120:
        raise WindowError("Pencere bekleme süresi 0–120 saniye arasında olmalıdır.")


class WindowService:
    def __init__(self, *, cancel: threading.Event | None = None, backend: Any = None):
        self.cancel = cancel or threading.Event()
        self._backend = backend

    @property
    def backend(self):
        if self._backend is None:
            system = platform.system()
            if system == "Darwin":
                self._backend = MacWindows()
            elif system == "Windows":
                self._backend = Win32Windows()
            else:
                raise WindowError("Pencere tanıma macOS ve Windows üzerinde desteklenir.")
        return self._backend

    def _check(self):
        if self.cancel.is_set():
            raise InterruptedError("Pencere işlemi iptal edildi.")

    def list_windows(self) -> list[WindowInfo]:
        self._check()
        return self.backend.list_windows()

    def find(self, application: str, title: str, match: str = "exact", timeout: float = 0,
             on_missing: str = "stop") -> dict:
        validate_selector(application, title, match, timeout)
        if on_missing not in {"stop", "continue"}:
            raise WindowError("Pencere bulunamadığında yapılacak işlem geçersiz.")
        deadline = time.monotonic() + timeout
        while True:
            matches = [window for window in self.list_windows()
                       if (not application.strip() or window.application.casefold() == application.strip().casefold())
                       and (window.title.casefold() == title.strip().casefold() if match == "exact"
                            else title.strip().casefold() in window.title.casefold())]
            if len(matches) > 1:
                raise WindowError("Birden fazla pencere eşleşti. Uygulama adını veya başlığı daraltın.")
            if matches:
                return matches[0].result()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if on_missing == "continue":
                    return {"found": False}
                raise WindowError("Tanıtılan pencere bulunamadı. ERP ekranını açıp yeniden deneyin.")
            if self.cancel.wait(min(0.2, remaining)):
                self._check()

    def current(self, target: dict) -> WindowInfo:
        if not isinstance(target, dict) or target.get("found") is not True:
            raise WindowError("Önce Pencereyi tanı adımının bulunan pencere sonucunu seçin.")
        if target.get("platform") != platform.system():
            raise WindowError("Pencere başka bir işletim sisteminde tanınmış. Bu bilgisayarda yeniden tanıtın.")
        for window in self.list_windows():
            if all(getattr(window, key) == target.get(key) for key in ("window_id", "pid", "application", "title")):
                return window
        raise WindowError("Tanıtılan pencere kapanmış veya başlığı değişmiş. Yeniden Pencereyi tanı adımı ekleyin.")

    def focus(self, target: dict) -> WindowInfo:
        window = self.current(target)
        self._check()
        self.backend.activate(window)
        deadline = time.monotonic() + 2
        while not self.backend.is_active(window):
            self._check()
            if time.monotonic() >= deadline:
                raise WindowError("Hedef pencere öne getirilemedi. Pencereyi elle öne alıp tekrar deneyin.")
            self.cancel.wait(0.1)
        return self.current(target)

    def click(self, target: dict, x: float, y: float, desktop: Any) -> None:
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (x, y)):
            raise WindowError("Tıklama konumu iki geçerli sayı olmalıdır.")
        window = self.current(target)
        if not 0 <= round(x) < window.width or not 0 <= round(y) < window.height:
            raise WindowError("Tıklama konumu pencere sınırlarının dışında.")
        window = self.focus(target)
        if not 0 <= round(x) < window.width or not 0 <= round(y) < window.height:
            raise WindowError("Pencere boyutu değişti; tıklama konumunu yeniden belirleyin.")
        self._check()
        if not self.backend.is_active(window):
            raise WindowError("Pencere odağı değişti; tıklama yapılmadı.")
        desktop.click(window.x + x, window.y + y)

    def write(self, target: dict, text: str, desktop: Any) -> None:
        if not isinstance(text, str) or not text:
            raise WindowError("Yazılacak metin boş olmamalıdır.")
        window = self.focus(target)
        self._check()
        if not self.backend.is_active(window):
            raise WindowError("Pencere odağı değişti; metin yazılmadı.")
        desktop.write(text)

    @staticmethod
    def _numbers(*values: float) -> None:
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
               for value in values):
            raise WindowError("Hedef konumu geçerli sayılardan oluşmalıdır.")

    def _guard(self, target: dict, expected: WindowInfo | None = None) -> WindowInfo:
        self._check()
        window = self.current(target)
        if expected is not None and window != expected:
            raise WindowError("Pencere konumu veya boyutu değişti; hedefi yeniden belirleyin.")
        if not self.backend.is_active(window):
            raise WindowError("Pencere odağı değişti; işlem durduruldu.")
        self._check()
        return window

    @staticmethod
    def _screen_size(desktop: Any) -> tuple[int, int]:
        width, height = desktop.size()
        if any(type(value) is not int or value <= 0 for value in (width, height)):
            raise WindowError("Ana ekranın boyutu okunamadı.")
        return width, height

    def _point_in_window(self, window: WindowInfo, x: float, y: float, desktop: Any) -> tuple[int, int]:
        self._numbers(x, y)
        x, y = round(x), round(y)
        if not 0 <= x < window.width or not 0 <= y < window.height:
            raise WindowError("Hedef konumu pencere sınırlarının dışında.")
        screen_x, screen_y = window.x + x, window.y + y
        width, height = self._screen_size(desktop)
        if not 0 <= screen_x < width or not 0 <= screen_y < height:
            raise WindowError("Hedef ana ekranın dışında. ERP penceresini ana ekrana taşıyın.")
        return screen_x, screen_y

    def _capture_window(self, target: dict, desktop: Any) -> tuple[WindowInfo, Any]:
        window = self._guard(target)
        width, height = self._screen_size(desktop)
        if window.width <= 0 or window.height <= 0:
            raise WindowError("ERP penceresinin tamamını ana ekranın içine taşıyın.")
        clipped = (window.x < 0 or window.y < 0 or window.x + window.width > width
                   or window.y + window.height > height)
        if clipped:
            allows_clipping = getattr(self.backend, "allows_frame_clipping", None)
            if allows_clipping is None or allows_clipping(window, width, height) is not True:
                raise WindowError("ERP penceresinin tamamını ana ekranın içine taşıyın.")
        left, top = max(0, window.x), max(0, window.y)
        right, bottom = min(width, window.x + window.width), min(height, window.y + window.height)
        if right <= left or bottom <= top:
            raise WindowError("ERP penceresinin tamamını ana ekranın içine taşıyın.")
        image = desktop.screenshot((left, top, right - left, bottom - top))
        self._guard(target, window)
        if image.size != (right - left, bottom - top):
            raise WindowError("Pencere görüntüsünün ölçeği değişti. Ekranı yeniden tanıtın.")
        if clipped:
            from PIL import Image

            # GetWindowRect includes the invisible resize frame even when maximized.
            # Keep its origin and dimensions so existing relative targets do not move;
            # never ask the screen capture API to read outside the primary display.
            canvas = Image.new(image.mode, (window.width, window.height))
            canvas.paste(image, (left - window.x, top - window.y))
            image = canvas
        return window, image

    def screenshot_window(self, target: dict, desktop: Any) -> tuple[WindowInfo, Any]:
        """Capture the identified window in logical pixels, including its title bar."""
        self.focus(target)
        return self._capture_window(target, desktop)

    @staticmethod
    def _image_arguments(template: Path | None, confidence: float, timeout: float) -> Path:
        WindowService._numbers(confidence, timeout)
        if not 0 < confidence <= 1 or not 0 <= timeout <= 120:
            raise WindowError("Görsel güveni 0–1, bekleme süresi 0–120 saniye arasında olmalıdır.")
        if not isinstance(template, (str, Path)) or not str(template).strip():
            raise WindowError("Önce bir hedef görsel kaydedin veya seçin.")
        path = Path(template).expanduser()
        if not path.is_file():
            raise WindowError("Hedef görsel dosyası bulunamadı. Görseli yeniden kaydedin.")
        return path

    def _wait_image(
        self, target: dict, template: Path, desktop: Any, *, confidence: float, timeout: float, visible: bool,
    ) -> tuple[WindowInfo, Match | None]:
        deadline = time.monotonic() + timeout
        self.focus(target)
        while True:
            window, image = self._capture_window(target, desktop)
            try:
                match = Vision.match_template(image, template, threshold=confidence, require_unique=True)
            except AmbiguousMatchError as exc:
                raise WindowError("Hedef görsel birden fazla yerde bulundu. Daha ayırt edici bir görsel seçin.") from exc
            except (ValueError, OSError) as exc:
                raise WindowError("Hedef görsel okunamadı veya ayırt edici ayrıntı içermiyor.") from exc
            self._guard(target, window)
            if (match is not None) == visible:
                return window, match
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                state = "görünmesi" if visible else "kaybolması"
                raise TimeoutError(f"Hedef görselin {state} için bekleme süresi doldu.")
            if self.cancel.wait(min(0.2, remaining)):
                self._check()

    def wait_image(
        self, target: dict, template: Path, desktop: Any, *, confidence: float = 0.9,
        timeout: float = 10, visible: bool = True,
    ) -> Match | None:
        if type(visible) is not bool:
            raise WindowError("Görsel bekleme durumu geçersiz.")
        template = self._image_arguments(template, confidence, timeout)
        window, match = self._wait_image(target, template, desktop, confidence=confidence,
                                         timeout=timeout, visible=visible)
        if match is None:
            return None
        return Match(match.x + window.x, match.y + window.y, match.width, match.height, match.confidence)

    def _resolve_target(
        self, target: dict, desktop: Any, *, target_mode: str = "coordinates",
        x: float | None = None, y: float | None = None, template: Path | None = None,
        offset_x: float = 0, offset_y: float = 0, confidence: float = 0.9, timeout: float = 10,
    ) -> tuple[WindowInfo, tuple[int, int]]:
        self._numbers(offset_x, offset_y)
        if target_mode == "coordinates":
            self._numbers(x, y)
            # Reject a malformed target before bringing another application forward.
            self._point_in_window(self.current(target), x, y, desktop)
            window = self.focus(target)
            point = self._point_in_window(window, x, y, desktop)
        elif target_mode == "image":
            template = self._image_arguments(template, confidence, timeout)
            window, match = self._wait_image(target, template, desktop, confidence=confidence,
                                             timeout=timeout, visible=True)
            point = self._point_in_window(window, match.center[0] + offset_x, match.center[1] + offset_y, desktop)
        else:
            raise WindowError("Hedef yöntemi koordinat veya görsel olmalıdır.")
        self._guard(target, window)
        return window, point

    def click_target(
        self, target: dict, desktop: Any, *, target_mode: str = "coordinates", x: float | None = None,
        y: float | None = None, template: Path | None = None, offset_x: float = 0, offset_y: float = 0,
        confidence: float = 0.9, timeout: float = 10, clicks: int = 1, button: str = "left",
    ) -> None:
        if (type(clicks) is not int or not 1 <= clicks <= 3 or not isinstance(button, str)
                or button not in {"left", "right", "middle"}):
            raise WindowError("Tıklama sayısı veya fare düğmesi geçersiz.")
        window, point = self._resolve_target(target, desktop, target_mode=target_mode, x=x, y=y,
                                             template=template, offset_x=offset_x, offset_y=offset_y,
                                             confidence=confidence, timeout=timeout)
        self._guard(target, window)
        desktop.click(*point, clicks=clicks, button=button)

    def fill_target(self, target: dict, text: str, desktop: Any, *, clear: bool = True, **targeting: Any) -> None:
        if not isinstance(text, str) or not text:
            raise WindowError("Yazılacak metin boş olmamalıdır.")
        if len(text) > 10_000:
            raise WindowError("Alanı doldur değeri en fazla 10.000 karakter olabilir.")
        if any(ord(character) < 32 or ord(character) == 127 for character in text):
            raise WindowError("Alanı doldur değeri Enter, Tab veya kontrol karakteri içeremez. "
                              "Hücreyi düzeltin; tuş göndermek için Pencerede tuşa bas adımını kullanın.")
        if type(clear) is not bool:
            raise WindowError("Alanı temizleme seçimi geçersiz.")
        clicks = targeting.pop("clicks", 1)
        if type(clicks) is not int or clicks != 1 or targeting.pop("button", "left") != "left":
            raise WindowError("Alan doldurma tek sol tıklama kullanır.")
        window, point = self._resolve_target(target, desktop, **targeting)
        self._guard(target, window)
        desktop.click(*point, clicks=1, button="left")
        self._guard(target, window)
        if clear:
            desktop.hotkey("mod", "a")
            self._guard(target, window)
            desktop.press("backspace")
            self._guard(target, window)
        desktop.write(text)

    def press_key(self, target: dict, key: str, modifier: str, desktop: Any) -> None:
        if (not isinstance(key, str) or not isinstance(modifier, str)
                or key not in SUPPORTED_KEYS or modifier not in SUPPORTED_MODIFIERS):
            raise WindowError("Tuş veya değiştirici desteklenmiyor.")
        window = self.focus(target)
        self._guard(target, window)
        if modifier == "none":
            desktop.press(key)
        else:
            desktop.hotkey(modifier, key)


class MacWindows:
    def __init__(self):
        try:
            import AppKit
            import Quartz
        except ImportError as exc:
            raise WindowError("Pencere tanıma için macOS otomasyon paketlerini kurun: .[automation]") from exc
        self.quartz, self.appkit = Quartz, AppKit

    def list_windows(self) -> list[WindowInfo]:
        q = self.quartz
        if not q.CGPreflightScreenCaptureAccess():
            raise WindowError("Pencere başlıklarını okumak için Sistem Ayarları → Gizlilik ve Güvenlik → "
                              "Ekran Kaydı bölümünden RpaOrkestrAI'ye izin verip uygulamayı yeniden açın. "
                              "Kaynak koddan çalıştırıyorsanız Python/Terminal'e izin verin.")
        records = q.CGWindowListCopyWindowInfo(q.kCGWindowListOptionOnScreenOnly | q.kCGWindowListExcludeDesktopElements,
                                             q.kCGNullWindowID)
        if records is None:
            raise WindowError("Pencereler okunamadı. Açık bir masaüstü oturumu gerekir.")
        windows = []
        for record in records:
            title = str(record.get(q.kCGWindowName, ""))
            bounds = record.get(q.kCGWindowBounds, {})
            if record.get(q.kCGWindowLayer) != 0 or not title.strip() or bounds.get("Width", 0) <= 0:
                continue
            windows.append(WindowInfo(int(record[q.kCGWindowNumber]), int(record[q.kCGWindowOwnerPID]),
                                      str(record.get(q.kCGWindowOwnerName, "")), title,
                                      *(round(bounds.get(key, 0)) for key in ("X", "Y", "Width", "Height"))))
        return windows

    def activate(self, window: WindowInfo):
        # Arguments are data, never interpolated into AppleScript source.
        script = '''on run argv
    set targetPID to (item 1 of argv) as integer
    set targetTitle to item 2 of argv
    tell application "System Events"
        set targetProcess to first application process whose unix id is targetPID
        tell targetProcess
            set candidates to every window whose name is targetTitle
            if (count of candidates) is not 1 then error "Ambiguous or missing window"
            set frontmost to true
            perform action "AXRaise" of item 1 of candidates
        end tell
    end tell
end run'''
        try:
            subprocess.run(["/usr/bin/osascript", "-e", script, str(window.pid), window.title],
                           check=True, capture_output=True, timeout=5)
        except (subprocess.SubprocessError, OSError) as exc:
            raise WindowError("Pencere öne getirilemedi. macOS Erişilebilirlik ve Otomasyon izinlerini kontrol edin; "
                              "aynı uygulamada aynı başlıklı iki pencere varsa birini kapatın.") from exc

    def is_active(self, window: WindowInfo) -> bool:
        front = self.appkit.NSWorkspace.sharedWorkspace().frontmostApplication()
        if front is None or front.processIdentifier() != window.pid:
            return False
        # Quartz returns front-to-back order. A dialog from this app must not be
        # mistaken for the previously identified ERP window.
        q = self.quartz
        records = q.CGWindowListCopyWindowInfo(q.kCGWindowListOptionOnScreenOnly | q.kCGWindowListExcludeDesktopElements,
                                             q.kCGNullWindowID) or []
        windows = [entry for entry in records if entry.get(q.kCGWindowOwnerPID) == window.pid
                   and entry.get(q.kCGWindowLayer) == 0]
        return bool(windows and int(windows[0][q.kCGWindowNumber]) == window.window_id)


class Win32Windows:
    def __init__(self):
        import ctypes
        from ctypes import wintypes as w

        self.c, self.w = ctypes, w
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.callback = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
        signatures = {
            "EnumWindows": ([self.callback, w.LPARAM], w.BOOL),
            "IsWindowVisible": ([w.HWND], w.BOOL), "IsIconic": ([w.HWND], w.BOOL),
            "IsZoomed": ([w.HWND], w.BOOL),
            "GetSystemMetrics": ([ctypes.c_int], ctypes.c_int),
            "GetWindowTextLengthW": ([w.HWND], ctypes.c_int),
            "GetWindowTextW": ([w.HWND, w.LPWSTR, ctypes.c_int], ctypes.c_int),
            "GetWindowThreadProcessId": ([w.HWND, ctypes.POINTER(w.DWORD)], w.DWORD),
            "GetWindowRect": ([w.HWND, ctypes.POINTER(w.RECT)], w.BOOL),
            "SetForegroundWindow": ([w.HWND], w.BOOL),
            "GetForegroundWindow": ([], w.HWND),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.user, name)
            function.argtypes, function.restype = args, result
        self.kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        self.kernel.OpenProcess.restype = w.HANDLE
        self.kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
        self.kernel.QueryFullProcessImageNameW.restype = w.BOOL
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.kernel.CloseHandle.restype = w.BOOL
        # Match the primary-display coordinate space used by PyAutoGUI.
        # The native shell may have already chosen a process DPI mode.
        self.user.SetProcessDPIAware()

    def allows_frame_clipping(self, window: WindowInfo, width: int, height: int) -> bool:
        """Permit only the native invisible frame of a maximized primary window."""
        if not self.user.IsZoomed(window.window_id):
            return False
        # Use the primary display's resize frame and captioned-window padding
        # (SM_CXSIZEFRAME, SM_CYSIZEFRAME, SM_CXPADDEDBORDER). Other displays
        # remain outside the supported capture area.
        border = self.user.GetSystemMetrics(92)
        horizontal = self.user.GetSystemMetrics(32) + border
        vertical = self.user.GetSystemMetrics(33) + border
        if not 0 <= horizontal <= 64 or not 0 <= vertical <= 64:
            return False
        return (-horizontal <= window.x < width and -vertical <= window.y < height
                and 0 < window.x + window.width <= width + horizontal
                and 0 < window.y + window.height <= height + vertical)

    def list_windows(self) -> list[WindowInfo]:
        c, w, user = self.c, self.w, self.user
        windows = []

        def visit(handle, _):
            if not user.IsWindowVisible(handle) or user.IsIconic(handle):
                return True
            length = user.GetWindowTextLengthW(handle)
            if not length:
                return True
            title = c.create_unicode_buffer(length + 1)
            user.GetWindowTextW(handle, title, length + 1)
            pid, rect = w.DWORD(), w.RECT()
            user.GetWindowThreadProcessId(handle, c.byref(pid))
            if not user.GetWindowRect(handle, c.byref(rect)):
                return True
            application = ""
            process = self.kernel.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
            if process:
                try:
                    size = w.DWORD(32768)
                    path = c.create_unicode_buffer(size.value)
                    if self.kernel.QueryFullProcessImageNameW(process, 0, path, c.byref(size)):
                        application = PureWindowsPath(path.value).name
                finally:
                    self.kernel.CloseHandle(process)
            if title.value.strip() and rect.right > rect.left and rect.bottom > rect.top:
                windows.append(WindowInfo(int(handle), pid.value, application, title.value,
                                          rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top))
            return True

        if not user.EnumWindows(self.callback(visit), 0):
            raise WindowError("Windows pencere listesi okunamadı. Açık masaüstü oturumunu kontrol edin.")
        return windows

    def activate(self, window: WindowInfo):
        self.user.SetForegroundWindow(window.window_id)

    def is_active(self, window: WindowInfo) -> bool:
        return self.user.GetForegroundWindow() == window.window_id
