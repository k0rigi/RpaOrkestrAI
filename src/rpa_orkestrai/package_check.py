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
from urllib.request import ProxyHandler, build_opener


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
            from .config import Settings
            from .desktop.targets import CaptureStore
            from .desktop.vision import Vision
            from .desktop.windows import WindowInfo
            from .updates import current_platform_key

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
            for route, expected in (("/", b"RpaOrkestrAI"), ("/app.js", b"renderLibrary"),
                                    ("/styles.css", b"step-library"), ("/api/bootstrap", b"desktop.window_fill")):
                with opener.open(url + route, timeout=5) as response:
                    if response.status != 200 or expected not in response.read():
                        raise RuntimeError(f"Paket kaynağı doğrulanamadı: {route}")
            result = {"ok": True, "frozen": bool(getattr(sys, "frozen", False)),
                      "version": __version__, "platform": current_platform_key(),
                      "checks": ["native-import", "automation-imports", "target-crop-and-match", "http-api", "bundled-static-files"]}
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
