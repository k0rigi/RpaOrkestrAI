"""Headless check of the built app, using only a temporary workspace."""

from __future__ import annotations

import importlib
import json
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from random import Random
from urllib.error import HTTPError
from urllib.request import ProxyHandler, build_opener


def _check_accessibility() -> None:
    """Load the field-structure backend without touching any window (no permission prompt)."""
    import platform

    # The recorder's platform backend is imported dynamically by pynput.
    from pynput import keyboard, mouse

    from .desktop.tables import AxTables, UiaTables

    if not (keyboard.Listener and mouse.Listener):
        raise RuntimeError("Paket içindeki hareket kaydedici yüklenemedi.")
    if platform.system() == "Windows":
        UiaTables()._context()
    elif platform.system() == "Darwin":
        AxTables().ax.AXIsProcessTrusted()


def _check_ocr_and_tables(folder: Path) -> None:
    """System OCR on a generated image and an Excel round trip, inside the packaged app."""
    import platform

    from PIL import Image, ImageDraw, ImageFont

    from .actions.files import read_table, write_table
    from .desktop.ocr import read_text

    image = Image.new("RGB", (700, 120), "white")
    try:
        font = ImageFont.load_default(size=48)
    except TypeError:
        font = ImageFont.load_default()
    ImageDraw.Draw(image).text((20, 30), "INVOICE 2026", fill="black", font=font)
    if platform.system() in {"Darwin", "Windows"} and "INVOICE" not in read_text(image, engine="system").upper():
        raise RuntimeError("Paket içindeki sistem OCR'ı metni okuyamadı.")
    book = folder / "check.xlsx"
    write_table(None, {"rows": [{"No": 1, "Ad": "Çağrı"}], "path": str(book)})
    if read_table(None, {"path": str(book)})[0]["Ad"] != "Çağrı":
        raise RuntimeError("Paket içindeki Excel okuma/yazma doğrulanamadı.")


def _check_databases(folder: Path) -> None:
    """Veritabanı sorgusu inside the package: a real SQLite query and every bundled driver loads."""
    import platform
    import sqlite3

    import sqlalchemy as sa

    from .database.query import QueryDatabase

    database = folder / "check.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE stok (kod TEXT, adet INTEGER)")
        connection.execute("INSERT INTO stok VALUES ('Ç-1', 3)")
    connection.close()
    with QueryDatabase({"engine": "sqlite", "path": str(database)}) as reader:
        rows, _ = reader.query("SELECT kod, adet FROM stok WHERE adet > ${n}", lambda name: 1, 10)
    if rows != [{"kod": "Ç-1", "adet": 3}]:
        raise RuntimeError("Paket içindeki veritabanı sorgusu doğrulanamadı.")
    sql_server = "mssql+pyodbc" if platform.system() == "Windows" else "mssql+pymssql"
    for scheme in ("postgresql+psycopg", sql_server, "mysql+pymysql", "oracle+oracledb"):
        # Creating an engine loads the driver without connecting.
        sa.create_engine(f"{scheme}://kullanici:sifre@localhost/veritabani").dispose()


def _check_license_verification() -> None:
    """Sign with a throwaway key and verify with the packaged license code (no network)."""
    import base64

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from .licensing import LicenseError, verify_license

    key = Ed25519PrivateKey.generate()
    nonce = "ab" * 16
    payload = json.dumps({
        "surum": 1, "urun": "rpa-orkestrai", "modul": "MOD_RPA", "kullanici_id": 1, "kullanici": "paket",
        "firma_id": 1, "bitis": None, "cihaz": "0" * 32, "verildi": "2026-01-01T00:00:00+03:00",
        "gecerlilik": "2026-01-01T01:00:00+03:00", "tolerans": 3600, "aralik": 600, "nonce": nonce,
    }).encode()
    envelope = {"payload": base64.b64encode(payload).decode(), "signature": base64.b64encode(key.sign(payload)).decode()}
    if verify_license(envelope, key.public_key(), "0" * 32, nonce).user != "paket":
        raise RuntimeError("Paket içindeki lisans doğrulaması çalışmadı.")
    # The same signed answer must not pass for another request or another computer.
    for device, value in (("0" * 32, "cd" * 16), ("1" * 32, nonce)):
        try:
            verify_license(envelope, key.public_key(), device, value)
        except LicenseError:
            continue
        raise RuntimeError("Paket içindeki lisans doğrulaması başka bir isteğin yanıtını kabul etti.")


def _check_password_store() -> None:
    """Kayıtlı şifreler must reach the Keychain / Credential Manager; nothing is written here."""
    from .vault import system_store

    store = system_store()
    if not all(callable(getattr(store, name, None)) for name in ("store", "load", "remove")):
        raise RuntimeError("Şifre kasası paketlenen uygulamada yüklenemedi.")


def _check_login_item() -> None:
    """Bilgisayar açılınca başlat must find the installed program; nothing is registered here."""
    import platform

    from . import autostart

    if not getattr(sys, "frozen", False):
        return
    if not autostart.supported():
        raise RuntimeError("Bilgisayar açılınca başlat ayarı paketlenen uygulamada kullanılamıyor.")
    if platform.system() == "Darwin":
        arguments = autostart.agent(autostart.app_bundle())["ProgramArguments"]
        if not arguments[2].endswith(".app") or arguments[-1] != autostart.MINIMIZED:
            raise RuntimeError("macOS giriş öğesi uygulama paketini gösteremedi.")
    elif not autostart.windows_command().lower().endswith('.exe" --minimized'):
        raise RuntimeError("Windows başlangıç kaydı programı gösteremedi.")


def run_check(report: Path) -> int:
    previous_stdout, previous_stderr = sys.stdout, sys.stderr
    server, worker, logger, sock = None, None, None, None
    result = {"ok": False}
    with tempfile.TemporaryDirectory(prefix="rpa-package-check-") as folder:
        try:
            from .gui import configure_logging

            root = Path(folder)
            logger, _ = configure_logging(root)
            # Import GUI without opening a window. Actual desktop permissions/input
            # remain a separate test on the destination computer.
            for name in ("webview", "gspread", "PIL.Image", "cv2", "pyperclip"):
                importlib.import_module(name)
            import uvicorn
            from PIL import Image

            from . import __version__
            from .app import create_app
            from .catalog import library_catalog
            from .config import Settings
            from .desktop.picker import LivePicker, overlay_html
            from .desktop.targets import CaptureStore
            from .desktop.vision import Vision
            from .desktop.windows import WindowInfo
            from .updates import current_platform_key

            _check_license_verification()
            _check_accessibility()
            _check_ocr_and_tables(root)
            _check_databases(root)
            _check_login_item()
            _check_password_store()

            # Exercise the packaged crop/matching dependencies using generated
            # pixels only; never read or control the real desktop during checks.
            pixels = Random(42)
            reference = Image.frombytes("RGB", (24, 18), bytes(pixels.randrange(220) for _ in range(24 * 18 * 3)))
            screen = Image.new("RGB", (200, 120), "white")
            screen.paste(reference, (70, 40))
            captures = CaptureStore()
            captured = captures.add(WindowInfo(1, 1, "Test", "ERP fixture", 0, 0, 200, 120), screen)
            cropped = captures.crop(captured["id"], 70, 40, 24, 18, root / "templates")
            matched = Vision.match_template(screen, root / "templates" / cropped["template"], require_unique=True)
            if matched is None or (matched.x, matched.y) != (70, 40):
                raise RuntimeError("Paket içindeki görsel hedef seçimi doğrulanamadı.")

            # Validate the frozen native overlay code without opening a desktop
            # window or requesting screen/input permissions in the build runner.
            fixture = WindowInfo(1, 1, "Test", "ERP fixture", 0, 0, 200, 120)
            overlay = overlay_html(fixture, captured["image"], "image", (200, 120))
            if "pywebview" not in overlay or "canvas" not in overlay:
                raise RuntimeError("Paket içindeki fareyle hedef seçimi doğrulanamadı.")
            if not callable(LivePicker.pick):
                raise RuntimeError("Canlı hedef seçimi yüklenemedi.")

            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            url = f"http://127.0.0.1:{sock.getsockname()[1]}"
            server = uvicorn.Server(uvicorn.Config(create_app(Settings(root / "data", dotenv=False)),
                                                 host="127.0.0.1", port=0, loop="asyncio", http="h11", ws="none"))
            worker = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
            worker.start()
            deadline = time.monotonic() + 30
            while not server.started:
                if not worker.is_alive() or time.monotonic() > deadline:
                    raise RuntimeError("Paket içindeki servis başlatılamadı.")
                time.sleep(0.05)
            opener = build_opener(ProxyHandler({}))
            for route, expected in (("/", b"RpaOrkestrAI"), ("/app.js", b"showLicenseGate"),
                                    ("/styles.css", b"step-library"), ("/theme.js", b"rpa.theme"),
                                    ("/fonts/barlow-400-latin.woff2", b"wOF2"),
                                    ("/api/license", b"login_required")):
                with opener.open(url + route, timeout=5) as response:
                    if response.status != 200 or expected not in response.read():
                        raise RuntimeError(f"Paket kaynağı doğrulanamadı: {route}")
            # A fresh workspace has no license: the Studio API must refuse work.
            try:
                opener.open(url + "/api/bootstrap", timeout=5).close()
                raise RuntimeError("Lisanssız çalışma alanı Studio API'sine erişebildi.")
            except HTTPError as exc:
                if exc.code != 403 or b"login_required" not in exc.read():
                    raise RuntimeError("Lisans kapısı doğrulanamadı.") from exc
            if not any(spec["type"] == "desktop.window_fill" for spec in library_catalog()):
                raise RuntimeError("Paket içindeki adım kütüphanesi eksik.")
            result = {"ok": True, "frozen": bool(getattr(sys, "frozen", False)),
                      "version": __version__, "platform": current_platform_key(),
                      "checks": ["native-import", "automation-imports", "target-crop-and-match", "native-picker-overlay",
                                 "license-verification", "license-gate", "accessibility-backend", "system-ocr",
                                 "excel-tables", "http-api", "login-item", "password-store",
                                 "bundled-static-files"]}
        except Exception as exc:
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        finally:
            if server:
                server.should_exit = True
            if worker:
                worker.join(timeout=35)
                if worker.is_alive():
                    result = {"ok": False, "error": "Paket kontrol servisi kapanmadı."}
            if sock:
                sock.close()
            if logger:
                for handler in list(logger.handlers):
                    handler.close()
                    logger.removeHandler(handler)
            sys.stdout, sys.stderr = previous_stdout, previous_stderr
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1
