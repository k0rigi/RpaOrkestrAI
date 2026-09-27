"""Window discovery and guarded input on macOS/Windows; native imports are lazy."""

from __future__ import annotations

import math
import platform
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import PureWindowsPath
from typing import Any


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
                              "Ekran Kaydı bölümünden uygulamayı başlatan Python/Terminal'e izin verip yeniden açın.")
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
