"""Open the bundled office in the real native renderer, using synthetic data only.

This diagnostic has its own loopback server. It never creates the Studio app,
reads a workspace, accesses the vault, or exposes automation through a JS bridge.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import platform
import re
import secrets
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

CHECKS = frozenset({"module_import", "three_rendered", "theme", "svg_fallback", "accessible_list",
                    "safe_text", "cleanup", "readonly", "local_resources"})
BODY_LIMIT = 16_384
STATIC = Path(__file__).parent / "static"


def validate_browser_report(value: object) -> dict:
    if (type(value) is not dict or set(value) != {"checks", "webgl_available", "draw_calls", "errors"}
            or type(value["checks"]) is not dict or set(value["checks"]) != CHECKS
            or any(type(item) is not bool for item in value["checks"].values())
            or type(value["webgl_available"]) is not bool
            or type(value["draw_calls"]) is not int or not 0 <= value["draw_calls"] <= 1_000_000
            or type(value["errors"]) is not list or len(value["errors"]) > 20
            or any(type(item) is not str or len(item) > 200 for item in value["errors"])):
        raise ValueError("Ofis kontrol raporunun biçimi geçersiz.")
    return value


class OfficeFixture:
    def __init__(self, static_root: Path = STATIC):
        self.static_root = static_root.resolve(strict=True)
        self.token = secrets.token_urlsafe(32)
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.browser_report: dict | None = None
        self.origin = ""
        self.native: dict = {}
        self.error = ""
        index = (self.static_root / "index.html").read_text(encoding="utf-8")
        head = index.split("<head>", 1)[1].split("</head>", 1)[0]
        head = re.sub(r'<script\b[^>]*\bsrc="/app\.js"[^>]*>\s*</script>', "", head)
        match = re.search(r'<script type="importmap">(.*?)</script>', head)
        if not match or '"three":"/vendor/three/three.module.js"' not in match[1]:
            raise ValueError("Paketin yerel ofis modül eşlemesi bulunamadı.")
        digest = base64.b64encode(hashlib.sha256(match[1].encode()).digest()).decode()
        self.csp = (f"default-src 'self'; script-src 'self' 'sha256-{digest}'; style-src 'self'; "
                    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
                    "base-uri 'none'; form-action 'none'")
        self.page = ('<!doctype html><html lang="tr"><head>'
                     f'<meta name="rpa-office-check" content="{html.escape(self.token, quote=True)}">'
                     '<script src="/native-office-check.js"></script>' + head
                     + '</head><body><main id="native-office-root"></main></body></html>').encode()

    def asset(self, raw_path: str) -> tuple[bytes, str] | None:
        path = unquote(urlsplit(raw_path).path)
        if path == "/":
            return self.page, "text/html; charset=utf-8"
        parts = path.removeprefix("/").split("/")
        if any(part in {"", ".", ".."} or "\\" in part or "\x00" in part for part in parts):
            return None
        item = self.static_root
        for part in parts:
            item /= part
            if item.is_symlink():
                return None
        types = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
                 ".woff2": "font/woff2"}
        if item.suffix not in types or not item.is_file() or not item.resolve().is_relative_to(self.static_root):
            return None
        return item.read_bytes(), types[item.suffix]

    def accept(self, value: object) -> bool:
        report = validate_browser_report(value)
        with self.lock:
            if self.browser_report is not None:
                return False
            self.browser_report = report
            self.done.set()
            return True


def fixture_server(fixture: OfficeFixture) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def log_message(self, *_args):
            pass

        def respond(self, status: int, body: bytes = b"", content_type: str = "text/plain; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", fixture.csp)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def host_allowed(self) -> bool:
            return self.headers.get("Host") == urlsplit(fixture.origin).netloc

        def do_GET(self):
            if not self.host_allowed():
                self.respond(403)
                return
            asset = fixture.asset(self.path)
            if asset is None:
                self.respond(404)
            else:
                self.respond(200, *asset)

        def do_POST(self):
            if (self.path != "/__office_report" or not self.host_allowed()
                    or self.headers.get("Origin") != fixture.origin
                    or not hmac.compare_digest(self.headers.get("X-Office-Check", "").encode(), fixture.token.encode())):
                self.respond(403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if (not 0 < length <= BODY_LIMIT or self.headers.get("Transfer-Encoding") is not None
                        or self.headers.get("Content-Type") != "application/json"):
                    self.respond(413)
                    return
                accepted = fixture.accept(json.loads(self.rfile.read(length)))
            except (ValueError, OSError):
                self.respond(400)
                return
            self.respond(204 if accepted else 409)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    fixture.origin = f"http://127.0.0.1:{server.server_port}"
    return server


def native_identity(window, renderer: str | None, system: str) -> dict:
    """Verify the actual native object; a browser user-agent is not evidence."""
    if system == "Darwin":
        from WebKit import WKWebView

        if renderer != "wkwebview" or not isinstance(window.native.contentView(), WKWebView):
            raise RuntimeError("Ofis gerçek WKWebView içinde açılmadı.")
        return {"renderer": "wkwebview", "native_type": "WebKit.WKWebView"}
    if system == "Windows":
        control = window.native.webview
        # Reading CoreWebView2 from this observer thread is not allowed by every
        # runtime. The native control type plus the GL report proves initialization.
        if renderer != "edgechromium" or control.GetType().FullName != "Microsoft.Web.WebView2.WinForms.WebView2":
            raise RuntimeError("Ofis gerçek Microsoft Edge WebView2 içinde açılmadı.")
        return {"renderer": "edgechromium", "native_type": "Microsoft.Web.WebView2.WinForms.WebView2"}
    raise RuntimeError("Yerel ofis kontrolü yalnız macOS ve Windows üzerinde çalışır.")


def open_native_fixture(fixture: OfficeFixture, folder: Path, timeout: float) -> None:
    import webview

    system = platform.system()
    if system not in {"Darwin", "Windows"}:
        raise RuntimeError("Yerel ofis kontrolü yalnız macOS ve Windows üzerinde çalışır.")
    # Avoid pywebview's injected inline no-selection stylesheet: the diagnostic
    # keeps Studio's strict CSP, without unsafe-inline or unsafe-eval exceptions.
    window = webview.create_window("RpaOrkestrAI · Ofis paket kontrolü", fixture.origin, width=1280, height=960,
                                   hidden=False, minimized=False, confirm_close=False, text_select=True)

    def observe():
        try:
            if not fixture.done.wait(timeout):
                fixture.error = "Ofis kontrolü süre sınırında tamamlanmadı. Grafik oturumunu kontrol edin."
            else:
                fixture.native = native_identity(window, webview.renderer, system)
        except Exception:
            fixture.error = "Gerçek yerel WebView motoru doğrulanamadı."
        finally:
            window.destroy()

    webview.start(observe, gui="edgechromium" if system == "Windows" else "cocoa", private_mode=True,
                  storage_path=str(folder / "browser"), debug=False)


def run_native_check(report: Path, *, timeout: float = 90) -> int:
    from . import __version__
    from .package_check import _check_office_assets
    from .updates import current_platform_key

    result = {"ok": False, "frozen": bool(getattr(sys, "frozen", False)), "version": __version__,
              "platform": current_platform_key(), "renderer": None, "native_type": None}
    server, worker = None, None
    try:
        _check_office_assets()
        with tempfile.TemporaryDirectory(prefix="rpa-native-office-") as temporary:
            fixture = OfficeFixture()
            server = fixture_server(fixture)
            worker = threading.Thread(target=server.serve_forever, daemon=True, name="rpa-office-fixture")
            worker.start()
            open_native_fixture(fixture, Path(temporary), timeout)
            result.update(fixture.native)
            if fixture.browser_report:
                result.update(fixture.browser_report)
            result["ok"] = bool(fixture.native and fixture.browser_report and not fixture.error
                                and all(fixture.browser_report["checks"].values())
                                and fixture.browser_report["webgl_available"]
                                and fixture.browser_report["draw_calls"] > 0
                                and not fixture.browser_report["errors"])
            if fixture.error:
                result["error"] = fixture.error
            elif not result["ok"]:
                result["error"] = "Yerel ofis, 3D çizim veya yedek görünüm kontrollerinden geçemedi."
    except Exception:
        result["error"] = "Yerel ofis kontrolü başlatılamadı. Paket kaynaklarını ve grafik oturumunu kontrol edin."
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if worker:
            worker.join(timeout=5)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1
