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
from .instance import StartupError, existing_instance, identity

# Shown when the window is closed while a schedule is on (pywebview reads confirm_close at that moment).
CLOSE_TEXTS = {
    "global.quitConfirmation": "Zamanlanmış akışlar yalnız Studio açıkken çalışır. Studio kapatılsın mı?",
    "global.quit": "Kapat",
    "global.cancel": "Açık kalsın",
}


GUARD_INTERVAL = 3.0


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
        background_color="#F5F7F3", minimized=minimized, localization=CLOSE_TEXTS,
    )
    if settings is not None:
        watch_schedules(window, settings)
        shown = {"minimized": minimized}
        window.events.minimized += lambda: shown.update(minimized=True)
        window.events.restored += lambda: shown.update(minimized=False)
        window.events.maximized += lambda: shown.update(minimized=False)
        # The scheduler in this process calls it when a countdown starts.
        settings.bring_to_front = lambda: bring_to_front(window, shown["minimized"])

    def on_loaded():
        print("Masaüstü penceresi hazır.", flush=True)

    window.events.loaded += on_loaded
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
