"""Platform paths and private application settings, independent of GUI imports."""

from __future__ import annotations

import json
import os
import platform
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


def modifier_key(system: str | None = None) -> str:
    return "command" if (system or platform.system()) == "Darwin" else "ctrl"


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        json.dump(data, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


class Settings:
    """Secrets stay in .env or private local state, never in exported flows."""

    editable = {
        "database_url", "google_credentials_path", "allowed_tables", "tesseract_cmd",
        "ocr_language", "template_dir", "sheets_connection", "sheets_script_url", "sheets_script_token",
    }
    secrets = {"database_url", "google_credentials_path", "sheets_script_token"}

    def __init__(self, data_dir: Path | str | None = None, *, dotenv: bool = True):
        if dotenv:
            # The native runtime can live outside the project (e.g. macOS Library).
            # Connection settings belong to the launch directory, not package code.
            load_dotenv(Path.cwd() / ".env")
        self.data_dir = Path(data_dir or os.getenv("RPA_DATA_DIR", "data")).expanduser().resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._path = self.data_dir / "settings.json"
        self.port = int(os.getenv("RPA_PORT", "8765"))
        self.max_rows = int(os.getenv("RPA_MAX_ROWS", "10000"))
        self.action_timeout = float(os.getenv("RPA_ACTION_TIMEOUT", "30"))
        if not 1 <= self.max_rows <= 100000 or not 0 < self.action_timeout <= 300:
            raise ValueError("RPA_MAX_ROWS 1–100000; RPA_ACTION_TIMEOUT 0–300 aralığında olmalıdır.")
        defaults: dict[str, Any] = {
            "database_url": os.getenv("RPA_DATABASE_URL", ""),
            "google_credentials_path": os.getenv("RPA_GOOGLE_CREDENTIALS_PATH", ""),
            "allowed_tables": [s.strip() for s in os.getenv(
                "RPA_ALLOWED_TABLES", "public.IASSALITEM,public.IASINVITEM"
            ).split(",") if s.strip()],
            "tesseract_cmd": os.getenv("RPA_TESSERACT_CMD", ""),
            "ocr_language": os.getenv("RPA_OCR_LANGUAGE", "tur+eng"),
            "template_dir": os.getenv("RPA_TEMPLATE_DIR", "assets/templates"),
            "sheets_connection": os.getenv("RPA_SHEETS_CONNECTION", "service_account"),
            "sheets_script_url": os.getenv("RPA_SHEETS_SCRIPT_URL", ""),
            "sheets_script_token": os.getenv("RPA_SHEETS_SCRIPT_TOKEN", ""),
        }
        if self._path.exists():
            saved = json.loads(self._path.read_text(encoding="utf-8"))
            defaults.update({k: v for k, v in saved.items() if k in self.editable})
        self._values = defaults

    def get(self, key: str) -> Any:
        with self._lock:
            value = self._values[key]
            return list(value) if isinstance(value, list) else value

    def update(self, values: dict[str, Any]) -> dict[str, Any]:
        if set(values) - self.editable:
            raise ValueError("Bilinmeyen ayar alanı.")
        for key, value in values.items():
            if key == "allowed_tables":
                if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
                    raise ValueError("allowed_tables bir tablo adı listesi olmalıdır.")
            elif not isinstance(value, str) or len(value) > 4096:
                raise ValueError("Ayarlar en fazla 4096 karakterlik metin olmalıdır.")
            elif key == "sheets_connection" and value not in {"service_account", "apps_script"}:
                raise ValueError("Google Sheets bağlantı yöntemi servis hesabı veya Apps Script olmalıdır.")
            elif key == "sheets_script_url" and value:
                from .integrations.apps_script import validate_url

                validate_url(value)
        with self._lock:
            updated = {**self._values, **values}
            atomic_json(self._path, updated)
            self._values = updated
        return self.public()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {k: self.get(k) for k in self._values}

    def public(self) -> dict[str, Any]:
        values = self.snapshot()
        script_ready = bool(values["sheets_script_url"] and values["sheets_script_token"])
        return {
            **{k: v for k, v in values.items() if k not in self.secrets},
            "database_configured": bool(values["database_url"]),
            "service_account_configured": bool(values["google_credentials_path"]),
            "sheets_script_configured": script_ready,
            "sheets_configured": script_ready if values["sheets_connection"] == "apps_script"
            else bool(values["google_credentials_path"]),
            "platform": platform.system(),
            "modifier_key": modifier_key(),
        }
