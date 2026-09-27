from __future__ import annotations

import argparse
import importlib.util
import json
import platform
import shutil
import threading
import time
import webbrowser

from . import __version__
from .config import Settings


def doctor(settings: Settings) -> dict:
    modules = ["fastapi", "pandas", "sqlalchemy", "pyautogui", "cv2", "pytesseract",
               "gspread", "playwright", "psycopg", "pyodbc", "webview"]
    checks = {name: importlib.util.find_spec(name) is not None for name in modules}
    checks["tesseract_executable"] = bool(shutil.which(settings.get("tesseract_cmd") or "tesseract"))
    browser_ready = False
    if checks["playwright"]:
        from pathlib import Path

        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser_ready = Path(playwright.chromium.executable_path).is_file()
    checks["chromium_installed"] = browser_ready
    drivers = []
    if checks["pyodbc"]:
        try:
            import pyodbc

            drivers = pyodbc.drivers()
        except (ImportError, OSError):
            pass
    checks["sql_server_odbc_driver"] = any("SQL Server" in driver for driver in drivers)
    return {"version": __version__, "platform": platform.system(), "checks": checks,
            "odbc_drivers": drivers, "settings": settings.public(), "data_dir": str(settings.data_dir)}


def run_demo(settings: Settings) -> None:
    from .demo import demo_workflow
    from .engine import RunManager
    from .locking import WorkspaceLock
    from .storage import Store

    with WorkspaceLock(settings.data_dir):
        store = Store(settings.data_dir)
        manager = RunManager(settings, store)
        workflow = demo_workflow()
        store.save_workflow(workflow)
        run = manager.start(workflow)
        try:
            while store.run(run.id).status in {"queued", "running"}:
                time.sleep(0.05)
        finally:
            manager.close()
        result = store.run(run.id)
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
    if result.status != "succeeded":
        raise SystemExit(1)


def serve(settings: Settings, *, native: bool, open_browser: bool) -> None:
    print(f"RpaOrkestrAI Studio {__version__} — http://127.0.0.1:{settings.port}", flush=True)
    if native:
        from .native import serve_native

        serve_native(settings)
        return

    import uvicorn

    from .app import create_app

    app = create_app(settings)
    url = f"http://127.0.0.1:{settings.port}"
    config = uvicorn.Config(app, host="127.0.0.1", port=settings.port, log_level="info")
    server = uvicorn.Server(config)
    if open_browser:
        def launch_when_ready():
            deadline = time.monotonic() + 10
            while not server.started and time.monotonic() < deadline:
                time.sleep(0.1)
            if server.started:
                webbrowser.open(url)

        threading.Thread(target=launch_when_ready, daemon=True).start()
    server.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="RpaOrkestrAI görsel otomasyon uygulaması")
    parser.add_argument("command", nargs="?", choices=["serve", "doctor", "demo"], default="serve")
    parser.add_argument("--no-browser", action="store_true", help="Tarayıcıyı otomatik açma")
    parser.add_argument("--native", action="store_true", help="Bağımsız masaüstü penceresinde aç")
    parser.add_argument("--port", type=int, help="Yerel HTTP portu (varsayılan 8765)")
    parser.add_argument("--data-dir", help="Özel yerel veri klasörü")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args()
    settings = Settings(data_dir=args.data_dir)
    if args.port is not None:
        if not 1024 <= args.port <= 65535:
            parser.error("Port 1024–65535 aralığında olmalıdır.")
        settings.port = args.port
    if args.command == "doctor":
        print(json.dumps(doctor(settings), ensure_ascii=False, indent=2))
    elif args.command == "demo":
        run_demo(settings)
    else:
        from .instance import StartupError

        try:
            serve(settings, native=args.native, open_browser=not args.no_browser)
        except StartupError as exc:
            parser.exit(1, f"Uygulama açılamadı: {exc}\n")


if __name__ == "__main__":
    main()
