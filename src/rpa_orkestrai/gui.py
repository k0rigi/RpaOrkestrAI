"""Console-free entry point for installed apps and source-checkout shortcuts."""

from __future__ import annotations

import io
import logging
import os
import platform
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


class LogStream(io.TextIOBase):
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def write(self, text: str) -> int:
        if text.strip():
            self.logger.info(text.rstrip())
        return len(text)

    def flush(self) -> None:
        for handler in self.logger.handlers:
            handler.flush()


def default_workspace() -> Path:
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        return base / "RpaOrkestrAI" / "workspace"
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "RpaOrkestrAI" / "workspace"
    return Path.home() / ".local" / "share" / "RpaOrkestrAI" / "workspace"


def configure_logging(workspace: Path) -> tuple[logging.Logger, Path]:
    folder = workspace / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "studio.log"
    logger = logging.getLogger("rpa.gui")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    # pythonw/PyInstaller have None streams. Uvicorn and libraries expect file-like streams.
    sys.stdout = LogStream(logger)
    sys.stderr = LogStream(logger)
    return logger, path


def show_error(message: str) -> None:
    if platform.system() == "Windows":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "RpaOrkestrAI açılamadı", 0x10)
    elif platform.system() == "Darwin":
        from AppKit import NSAlert

        alert = NSAlert.alloc().init()
        alert.setMessageText_("RpaOrkestrAI açılamadı")
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_("Tamam")
        alert.runModal()
    else:
        from tkinter import Tk, messagebox

        root = Tk()
        root.withdraw()
        messagebox.showerror("RpaOrkestrAI açılamadı", message)
        root.destroy()


def main(*, workspace: Path | None = None, argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) == 2 and args[0] == "--self-test":
        from .package_check import run_check

        return run_check(Path(args[1]).resolve())
    previous_stdout, previous_stderr, previous_cwd = sys.stdout, sys.stderr, Path.cwd()
    logger, log_path = None, None
    try:
        root = (workspace or default_workspace()).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        os.chdir(root)
        logger, log_path = configure_logging(root)
        (root / "assets" / "templates").mkdir(parents=True, exist_ok=True)
        from .config import Settings
        from .native import serve_native

        logger.info("Masaüstü uygulaması başlatılıyor.")
        serve_native(Settings(), auto_port=True)
        return 0
    except Exception as exc:
        if logger:
            logger.exception("Uygulama başlatılamadı.")
        from .instance import StartupError

        detail = str(exc) if isinstance(exc, StartupError) else (
            "Uygulama başlatılamadı. Kurulumun tamamlandığını ve gerekli sistem bileşenlerini kontrol edin."
        )
        if platform.system() == "Windows":
            detail += "\nMicrosoft Edge WebView2 Runtime kurulu olmalıdır."
        if log_path:
            detail += f"\n\nHata günlüğü: {log_path}"
        try:
            show_error(detail)
        except Exception:
            if logger:
                logger.exception("Hata penceresi de açılamadı.")
        return 1
    finally:
        sys.stdout, sys.stderr = previous_stdout, previous_stderr
        os.chdir(previous_cwd)
        if logger:
            for handler in list(logger.handlers):
                handler.close()
                logger.removeHandler(handler)
