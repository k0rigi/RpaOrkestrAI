"""Native window lifecycle; an existing Studio remains owned by its first process."""

from __future__ import annotations

import errno
import json
import platform
import socket
import threading
import time
from contextlib import ExitStack

from .config import Settings, atomic_json
from .errors import Cancelled, WorkflowError
from .instance import StartupError, existing_instance, identity

# Shown when the window is closed while a schedule is on (pywebview reads confirm_close at that moment).
CLOSE_TEXTS = {
    "global.quitConfirmation": "Zamanlanmış akışlar yalnız Studio açıkken çalışır. Studio kapatılsın mı?",
    "global.quit": "Kapat",
    "global.cancel": "Açık kalsın",
}


GUARD_INTERVAL = 3.0
MINIMIZE_TIMEOUT = 5.0
# The Studio sidebar (--nav-bg / --nav-ink) continues into the native title bar.
TITLE_BAR = (0x15, 0x1A, 0x26)
TITLE_TEXT = (0xF2, 0xEF, 0xE7)


def style_title_bar(window) -> None:
    """Paint the title bar like the sidebar; any failure keeps the system title bar."""
    try:
        if platform.system() == "Windows":
            windows_title_bar(int(window.native.Handle.ToInt64()))
        elif platform.system() == "Darwin":
            macos_title_bar(window.native)
    except Exception:
        pass


def windows_title_bar(hwnd: int) -> int:
    """Return the caption color HRESULT (0 on Windows 11)."""
    import ctypes
    from ctypes import wintypes

    def set_attribute(attribute: int, value: int) -> int:
        data = wintypes.DWORD(value)
        return ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), wintypes.DWORD(attribute), ctypes.byref(data), ctypes.sizeof(data))

    def colorref(red: int, green: int, blue: int) -> int:
        return red | green << 8 | blue << 16

    # Windows 10 1809+: dark caption (attribute 19 before 20H1, 20 afterwards).
    if set_attribute(20, 1) != 0:
        set_attribute(19, 1)
    # Windows 11 22000+: exact border, caption and text colors; Windows 10 ignores them.
    set_attribute(34, colorref(*TITLE_BAR))
    result = set_attribute(35, colorref(*TITLE_BAR))
    set_attribute(36, colorref(*TITLE_TEXT))
    # Redraw the non-client area: SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED.
    ctypes.windll.user32.SetWindowPos(wintypes.HWND(hwnd), None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0020)
    return result


def macos_title_bar(ns_window) -> None:
    from AppKit import NSAppearance, NSColor
    from PyObjCTools import AppHelper

    def apply() -> None:
        # AppKit objects belong to the main thread.
        ns_window.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameDarkAqua"))
        ns_window.setTitlebarAppearsTransparent_(True)
        ns_window.setBackgroundColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(
            *(channel / 255 for channel in TITLE_BAR), 1.0))

    AppHelper.callAfter(apply)


def minimize_for_run(window, minimized: threading.Event, cancel: threading.Event) -> None:
    """Wait for the native minimize event before the worker can touch the screen."""
    if cancel.is_set():
        raise Cancelled()
    try:
        window.on_top = False
        window.minimize()
    except Exception as exc:
        raise WorkflowError("Studio küçültülemedi; ekran adımlarına başlanmadı. "
                            "Masaüstü uygulamasını yeniden açıp deneyin.") from exc
    deadline = time.monotonic() + MINIMIZE_TIMEOUT
    while not minimized.is_set():
        if cancel.wait(0.05):
            raise Cancelled()
        if time.monotonic() >= deadline:
            raise WorkflowError("Studio'nun küçülmesi beklenirken süre doldu; ekran adımlarına başlanmadı. "
                                "Açık Studio pencerelerini kontrol edip yeniden deneyin.")
    # Let the compositor finish exposing the window below, including macOS's Dock animation.
    if cancel.wait(0.25):
        raise Cancelled()


def watch_schedules(window, settings: Settings) -> None:
    """Ask before closing only while a schedule is on; follow changes made in the Studio."""
    from .scheduler import ScheduleBook

    book = ScheduleBook(settings.data_dir)
    closed = threading.Event()
    window.events.closed += closed.set

    def follow():
        while not closed.is_set():
            try:
                window.confirm_close = book.active()
            except Exception:
                window.confirm_close = False
            closed.wait(GUARD_INTERVAL)

    threading.Thread(target=follow, daemon=True, name="rpa-close-guard").start()


def bring_to_front(window, minimized: bool) -> None:
    """A scheduled run is about to take the screen: show its countdown above other windows."""
    # Restoring a maximized window would shrink it (Windows); only a minimized one is restored.
    if minimized:
        window.restore()
    window.show()
    window.on_top = True
    timer = threading.Timer(2.0, lambda: setattr(window, "on_top", False))
    timer.daemon = True
    timer.start()


def open_window(webview, url: str, *, minimized: bool = False, settings: Settings | None = None) -> None:
    # CSV downloads are disabled by pywebview unless explicitly enabled.
    webview.settings["ALLOW_DOWNLOADS"] = True
    window = webview.create_window(
        "RpaOrkestrAI Studio", url, width=1440, height=940, min_size=(980, 680),
        background_color="#EDEAE1", minimized=minimized, localization=CLOSE_TEXTS,
    )
    if settings is not None:
        watch_schedules(window, settings)
        minimized_state = threading.Event()
        if minimized:
            minimized_state.set()
        window.events.minimized += minimized_state.set
        window.events.restored += minimized_state.clear
        window.events.maximized += minimized_state.clear
        # The scheduler in this process calls it when a countdown starts.
        settings.bring_to_front = lambda: bring_to_front(window, minimized_state.is_set())
        settings.prepare_run = lambda cancel: minimize_for_run(window, minimized_state, cancel)

    def on_loaded():
        print("Masaüstü penceresi hazır.", flush=True)

    window.events.loaded += on_loaded
    window.events.shown += lambda: style_title_bar(window)
    from .desktop.picker import register_native_host, unregister_native_host

    register_native_host(webview, window)
    try:
        # pywebview requires the GUI loop on the main thread on both platforms.
        if platform.system() == "Windows":
            webview.start(gui="edgechromium")
        else:
            webview.start()
    finally:
        unregister_native_host(window)


def serve_native(settings: Settings, *, auto_port: bool = False, minimized: bool = False) -> None:
    # This is only a discovery hint. Never attach without verifying the live server.
    hint = settings.data_dir / ".native-instance.json"
    if auto_port:
        try:
            saved = json.loads(hint.read_text(encoding="utf-8"))
            port = saved.get("port")
            if (saved.get("identity") == identity(settings.data_dir)
                    and type(port) is int and 1 <= port <= 65535
                    and existing_instance(f"http://127.0.0.1:{port}", settings.data_dir)):
                settings.port = port
        except (OSError, ValueError, AttributeError, StartupError):
            pass
    url = f"http://127.0.0.1:{settings.port}"
    try:
        reuse = existing_instance(url, settings.data_dir)
    except StartupError:
        if not auto_port:
            raise
        reuse = False
    print("Masaüstü penceresi hazırlanıyor…", flush=True)
    try:
        import webview
    except ImportError as exc:
        raise StartupError('Masaüstü penceresi için önce: python -m pip install ".[native]"') from exc
    if reuse:
        print("Açık çalışma alanına bağlanılıyor.", flush=True)
        # The schedules run in the process that owns the server; closing this window stops nothing.
        open_window(webview, url, minimized=minimized)
        return

    with ExitStack() as resources:
        sock = None
        if auto_port:
            sock = resources.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
            if platform.system() == "Windows":
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                sock.bind(("127.0.0.1", settings.port))
            except OSError as exc:
                # Windows can report EACCES when another exclusive listener owns it.
                if exc.errno not in {errno.EADDRINUSE, errno.EACCES}:
                    raise
                sock.bind(("127.0.0.1", 0))
            settings.port = sock.getsockname()[1]
        _serve_new_window(settings, webview, sock, hint if auto_port else None, minimized)


def _serve_new_window(settings, webview, sock, hint, minimized: bool = False) -> None:
    url = f"http://127.0.0.1:{settings.port}"

    print("Yerel çalışma alanı başlatılıyor…", flush=True)
    import uvicorn

    from .app import create_app

    server = uvicorn.Server(uvicorn.Config(
        create_app(settings), host="127.0.0.1", port=settings.port, log_level="info",
    ))
    startup_failure: list[str] = []

    def run_server():
        try:
            if sock is None:
                server.run()
            else:
                # Keep the port reserved until uvicorn takes over; no bind race.
                server.run(sockets=[sock])
        except SystemExit:
            startup_failure.append("Sunucu başlatılamadı; port veya çalışma alanı kullanımda olabilir.")
        except Exception:
            startup_failure.append("Sunucu başlatılamadı; yukarıdaki açılış günlüğünü kontrol edin.")

    thread = threading.Thread(target=run_server, daemon=True, name="rpa-http")
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while not server.started:
            if not thread.is_alive() or time.monotonic() >= deadline:
                raise StartupError(startup_failure[0] if startup_failure else (
                    "Sunucu açılamadı. Çalışma alanı başka bir uygulamada açık olabilir; açılış günlüğünü kontrol edin."
                ))
            time.sleep(0.05)
        if hint is not None:
            atomic_json(hint, {"identity": identity(settings.data_dir), "port": settings.port})
        open_window(webview, url, minimized=minimized, settings=settings)
    finally:
        # Only stop the server created by this window, never one it attached to.
        server.should_exit = True
        thread.join(timeout=35)
