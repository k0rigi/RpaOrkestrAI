"""Native window lifecycle; an existing Studio remains owned by its first process."""

from __future__ import annotations

import threading
import time

from .config import Settings
from .instance import StartupError, existing_instance


def open_window(webview, url: str) -> None:
    # CSV downloads are disabled by pywebview unless explicitly enabled.
    webview.settings["ALLOW_DOWNLOADS"] = True
    window = webview.create_window(
        "RpaOrkestrAI Studio", url, width=1440, height=940, min_size=(980, 680),
        background_color="#F5F7F3",
    )

    def on_loaded():
        print("Masaüstü penceresi hazır.", flush=True)

    window.events.loaded += on_loaded
    # pywebview requires the GUI loop on the main thread on both platforms.
    webview.start()


def serve_native(settings: Settings) -> None:
    url = f"http://127.0.0.1:{settings.port}"
    reuse = existing_instance(url, settings.data_dir)
    print("Masaüstü penceresi hazırlanıyor…", flush=True)
    try:
        import webview
    except ImportError as exc:
        raise StartupError('Masaüstü penceresi için önce: python -m pip install ".[native]"') from exc
    if reuse:
        print("Açık çalışma alanına bağlanılıyor.", flush=True)
        open_window(webview, url)
        return

    print("Yerel çalışma alanı başlatılıyor…", flush=True)
    import uvicorn

    from .app import create_app

    server = uvicorn.Server(uvicorn.Config(
        create_app(settings), host="127.0.0.1", port=settings.port, log_level="info",
    ))
    startup_failure: list[str] = []

    def run_server():
        try:
            server.run()
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
        open_window(webview, url)
    finally:
        # Only stop the server created by this window, never one it attached to.
        server.should_exit = True
        thread.join(timeout=35)
