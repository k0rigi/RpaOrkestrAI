"""Headless check of the built app, using only a temporary workspace."""

from __future__ import annotations

import hashlib
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


def _check_office_assets(static_root: Path | None = None) -> None:
    """Check actual frozen resources; never fetch a missing vendor file from a CDN."""
    root = static_root or Path(__file__).parent / "static"
    vendor = root / "vendor" / "three"
    required = {"three.module.js", "addons/controls/OrbitControls.js", "LICENSE"}
    try:
        manifest = json.loads((vendor / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("version") != "0.160.0" or set(manifest.get("files", {})) != required:
            raise ValueError
        for name in required:
            content = (vendor / name).read_bytes()
            if hashlib.sha256(content).hexdigest() != manifest["files"][name]["sha256"]:
                raise ValueError
        if "MIT License" not in (vendor / "LICENSE").read_text(encoding="utf-8"):
            raise ValueError
        if "const REVISION = '160'" not in (vendor / "three.module.js").read_text(encoding="utf-8"):
            raise ValueError
        for name in ("office.js", "office.css", "agents.js", "agents.css", "native-office-check.js"):
            if not (root / name).is_file():
                raise ValueError
    except (OSError, KeyError, TypeError, ValueError):
        raise RuntimeError("Paket içindeki yerel ofis kaynakları, Three.js sürümü veya lisansı doğrulanamadı.") from None


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
    from .desktop.screen_tables import TableText, locate_image

    image = Image.new("RGB", (700, 120), "white")
    try:
        font = ImageFont.load_default(size=48)
    except TypeError:
        font = ImageFont.load_default()
    ImageDraw.Draw(image).text((20, 30), "INVOICE 2026", fill="black", font=font)
    if platform.system() in {"Darwin", "Windows"} and "INVOICE" not in read_text(image, engine="system").upper():
        raise RuntimeError("Paket içindeki sistem OCR'ı metni okuyamadı.")
    if platform.system() in {"Darwin", "Windows"}:
        table_image = Image.new("RGB", (750, 180), "white")
        draw = ImageDraw.Draw(table_image)
        table_font = ImageFont.load_default(size=30)
        for x, header, value in [(20, "Code", "A125"), (260, "Status", "READY"), (520, "Count", "1")]:
            draw.text((x, 20), header, fill="black", font=table_font)
            draw.text((x, 85), value, fill="black", font=table_font)
        table = TableText.parse("A125\tREADY\t1", header=False)
        cell = locate_image(table_image, table, 0, 1, reference_point=(40, 100),
                            ocr_options={"engine": "system"})
        if not (260 <= cell.point[0] < 400 and 85 <= cell.point[1] < 130):
            raise RuntimeError("Paket içindeki tablo hücresi konumu doğrulanamadı.")
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


def _check_integrations(folder: Path) -> None:
    """Kurumsal entegrasyon inside the package: a real SQLite write with rollback, IMAP/FTP/API/message
    helpers and the agent web guard. Nothing connects to a network."""
    import ftplib
    import imaplib
    import sqlite3

    from .actions.transfer import message_payload
    from .agents.automations import safe_names
    from .agents.web import check_url
    from .database.query import QueryDatabase
    from .errors import WorkflowError
    from .integrations import api, ftp, imap

    database = folder / "yazma.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE siparis (no INTEGER, durum TEXT)")
        connection.executemany("INSERT INTO siparis VALUES (?, ?)", [(1, "Yeni"), (2, "Yeni")])
    connection.close()
    config = {"engine": "sqlite", "path": str(database), "allow_write": True, "write_targets": ["siparis"]}
    with QueryDatabase(config, read_only=False) as writer:
        changed = writer.execute("UPDATE siparis SET durum = ${d} WHERE no = ${n}", {"d": "İşlendi", "n": 1}.get, 1)
        try:
            writer.execute("UPDATE siparis SET durum = 'x' WHERE no > 0", lambda name: None, 1)
            raise RuntimeError("Paket içindeki veritabanı yazma sınırı değişikliği geri almadı.")
        except WorkflowError:
            pass
    with sqlite3.connect(database) as connection:
        states = [row[0] for row in connection.execute("SELECT durum FROM siparis ORDER BY no")]
    connection.close()
    if changed["affected"] != 1 or states != ["İşlendi", "Yeni"]:
        raise RuntimeError("Paket içindeki veritabanında değişiklik yap adımı doğrulanamadı.")
    if not (imaplib.IMAP4_SSL and ftplib.FTP_TLS) or imap.folder_name("Gelen/Ödemeler") != '"Gelen/&ANY-demeler"':
        raise RuntimeError("Paket içindeki e-posta (IMAP) ve FTP desteği yüklenemedi.")
    if api.resolve_url({"base_url": "https://erp.example.com/api"}, "/v1/siparis") != "https://erp.example.com/api/v1/siparis":
        raise RuntimeError("Paket içindeki API bağlantısı adresi çözemedi.")
    if message_payload("teams", "Başlık", "Metin")["attachments"][0]["content"]["type"] != "AdaptiveCard":
        raise RuntimeError("Paket içindeki mesaj gönderme biçimi doğrulanamadı.")
    if safe_names({"Müşteri Adı": "x"}) != {"Musteri_Adi": "x"}:
        raise RuntimeError("Paket içindeki otomasyon kayıt adları doğrulanamadı.")
    for refused in (lambda: ftp.remote("../disari"), lambda: check_url("http://127.0.0.1/", None),
                    lambda: api.resolve_url({"base_url": "https://erp.example.com"}, "https://baska.example.com/x")):
        try:
            refused()
        except WorkflowError:
            continue
        raise RuntimeError("Paket içindeki bağlantı güvenlik kontrolleri çalışmıyor.")


def _check_documents(folder: Path) -> None:
    """Zip with Turkish names, PDF text and page rendering (pdfminer + pdfium) inside the package."""
    from types import SimpleNamespace

    from .actions.documents import page_image, read_pdf, zip_files

    source = folder / "zip-kaynak"
    source.mkdir()
    (source / "çağrı özeti.txt").write_text("ğüşıöç", encoding="utf-8")
    ctx = SimpleNamespace(log=lambda message, **kw: None, check_cancelled=lambda: None)
    zip_files(ctx, {"operation": "create", "items": str(source), "destination": str(folder / "paket.zip")})
    zip_files(ctx, {"operation": "extract", "source": str(folder / "paket.zip"), "folder": str(folder / "zip-acilan")})
    if (folder / "zip-acilan" / "zip-kaynak" / "çağrı özeti.txt").read_text(encoding="utf-8") != "ğüşıöç":
        raise RuntimeError("Paket içindeki zip açma/oluşturma doğrulanamadı.")
    stream = "BT /F1 18 Tf 72 700 Td (Fatura INV-1069) Tj ET"
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [5 0 R] /Count 1 >>",
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
               "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> "
               "/Contents 4 0 R >>"]
    data, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(data)
    data += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    data += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    data += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    pdf = folder / "fatura.pdf"
    pdf.write_bytes(bytes(data))
    if "INV-1069" not in read_pdf(ctx, {"path": str(pdf), "ocr": False}):
        raise RuntimeError("Paket içindeki PDF metin okuma doğrulanamadı.")
    if page_image(pdf, 0).size[0] < 1000:
        raise RuntimeError("Paket içindeki PDF sayfa görüntüsü (taranmış sayfa okuma) oluşturulamadı.")


def _check_web_driver() -> None:
    """Web adımları: Playwright's bundled driver starts (no browser is launched or downloaded)."""
    from playwright.sync_api import sync_playwright

    runtime = sync_playwright().start()
    try:
        if runtime.chromium is None:
            raise RuntimeError("Paket içindeki web sürücüsü başlatılamadı.")
    finally:
        runtime.stop()


def app_identity() -> str:
    """The process's AppUserModelID as Windows reports it."""
    import ctypes
    from ctypes import wintypes

    value = ctypes.c_wchar_p()
    shell32 = ctypes.windll.shell32
    if shell32.GetCurrentProcessExplicitAppUserModelID(ctypes.byref(value)) != 0 or not value.value:
        return ""
    try:
        return value.value
    finally:
        ctypes.windll.ole32.CoTaskMemFree(ctypes.cast(value, wintypes.LPVOID))


def file_description(path: str) -> str:
    import ctypes

    version = ctypes.windll.version
    size = version.GetFileVersionInfoSizeW(path, None)
    if not size:
        return ""
    data = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(path, 0, size, data):
        return ""
    pointer, length = ctypes.c_void_p(), ctypes.c_uint()
    if not version.VerQueryValueW(data, "\\StringFileInfo\\041F04B0\\FileDescription",
                                  ctypes.byref(pointer), ctypes.byref(length)) or not length.value:
        return ""
    return ctypes.wstring_at(pointer, length.value).rstrip("\x00")


def _check_windows_identity() -> None:
    """Pinning and search show "RpaOrkestrAI Studio": the exe's version resource and the app id."""
    import platform

    from .gui import APP_USER_MODEL_ID, set_app_identity

    if platform.system() != "Windows" or not getattr(sys, "frozen", False):
        return
    set_app_identity()
    if app_identity() != APP_USER_MODEL_ID:
        raise RuntimeError("Uygulama kimliği (AppUserModelID) atanamadı; görev çubuğu sabitlemesi bozulur.")
    if file_description(sys.executable) != "RpaOrkestrAI Studio":
        raise RuntimeError("EXE dosyasında sürüm bilgisi (FileDescription) yok; arama ve sabitleme adı göstermez.")


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


def _check_ai_schema() -> None:
    """The packaged validator and bundled metaschemas must work without a network request."""
    from .agents.schema import compile_schema
    from .errors import WorkflowError

    validator = compile_schema({"type": "object", "properties": {"karar": {"enum": ["evet", "hayır"]}},
                                "required": ["karar"], "additionalProperties": False})
    validator.validate({"karar": "evet"})
    try:
        validator.validate({"karar": "tahmin"})
    except WorkflowError:
        return
    raise RuntimeError("Paket içindeki yapay zekâ JSON şeması doğrulaması çalışmıyor.")


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
            _check_integrations(root)
            _check_documents(root)
            _check_web_driver()
            _check_windows_identity()
            _check_login_item()
            _check_password_store()
            _check_office_assets()
            _check_ai_schema()

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
                                    ("/office.js", b"mountOffice"), ("/office.css", b"office-frame"),
                                    ("/vendor/three/three.module.js", b"const REVISION = '160'"),
                                    ("/vendor/three/addons/controls/OrbitControls.js", b"class OrbitControls"),
                                    ("/vendor/three/LICENSE", b"MIT License"),
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
                                 "screen-table-target", "excel-tables", "http-api", "login-item", "password-store",
                                 "bundled-static-files", "local-three-office-assets", "offline-ai-json-schema",
                                 "enterprise-integrations"]}
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
