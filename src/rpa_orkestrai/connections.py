"""Named connections (Google Sheets, databases) that steps select, like n8n credentials.

Profiles live in the workspace (data/connections.json, owner-only permissions) and
are never part of an exported workflow: a step stores only the profile id. The
first start converts the old global settings into default profiles, so existing
workflows keep working. A step without a chosen profile uses the default of its type.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from pathlib import Path
from typing import Any

from .config import atomic_json
from .errors import WorkflowError

TYPES = {"google_sheets": "Google Sheets", "database": "Veritabanı"}
SHEETS_METHODS = {"apps_script": "Apps Script", "service_account": "Servis hesabı"}
SECRET_FIELDS = {"script_token", "credentials_path", "url", "password"}
DATABASE_FIELDS = ("host", "port", "database", "user", "path")
NAME_LIMIT = 80


def _text(value: Any, label: str, limit: int = 4096) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"{label} en fazla {limit} karakterlik metin olmalıdır.")
    return value.strip()


class Connections:
    def __init__(self, data_dir: Path | str, settings: Any = None):
        self._path = Path(data_dir) / "connections.json"
        self._lock = threading.RLock()
        if not self._path.exists():
            self._save(self._migrate(settings))

    # ----- storage ------------------------------------------------------------------
    def _load(self) -> list[dict]:
        try:
            items = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [item for item in items if isinstance(item, dict) and item.get("type") in TYPES] \
            if isinstance(items, list) else []

    def _save(self, items: list[dict]) -> None:
        atomic_json(self._path, items)

    @staticmethod
    def _migrate(settings: Any) -> list[dict]:
        """Turn 0.6 global settings (or .env values) into default profiles."""
        if settings is None:
            return []
        values = settings.snapshot()
        items = []
        script = values.get("sheets_script_url") and values.get("sheets_script_token")
        if script or values.get("google_credentials_path"):
            method = "apps_script" if script and values.get("sheets_connection") == "apps_script" or \
                not values.get("google_credentials_path") else "service_account"
            items.append({"id": uuid.uuid4().hex, "name": "Google Sheets", "type": "google_sheets", "default": True,
                          "config": {"method": method, "script_url": values.get("sheets_script_url") or "",
                                     "script_token": values.get("sheets_script_token") or "",
                                     "credentials_path": values.get("google_credentials_path") or ""}})
        if values.get("database_url"):
            items.append({"id": uuid.uuid4().hex, "name": "Veritabanı", "type": "database", "default": True,
                          "config": {"url": values["database_url"],
                                     "allowed_tables": list(values.get("allowed_tables") or [])}})
        return items

    # ----- validation ---------------------------------------------------------------
    def _clean(self, kind: str, config: dict, previous: dict | None = None) -> dict:
        previous = previous or {}
        if not isinstance(config, dict):
            raise ValueError("Bağlantı ayarları bir nesne olmalıdır.")

        def secret(key: str, label: str) -> str:
            # A blank secret keeps the stored one; the API never sends secrets to the page.
            value = _text(config.get(key), label)
            return value or previous.get(key, "")

        if kind == "google_sheets":
            method = config.get("method") or previous.get("method") or "apps_script"
            if method not in SHEETS_METHODS:
                raise ValueError("Google Sheets bağlantı yöntemi Apps Script veya servis hesabı olmalıdır.")
            url = _text(config.get("script_url"), "Apps Script adresi") if "script_url" in config \
                else previous.get("script_url", "")
            if url:
                from .integrations.apps_script import validate_url

                validate_url(url)
            token = secret("script_token", "Apps Script anahtarı")
            if token:
                from .integrations.apps_script import TOKEN_PATTERN

                if not TOKEN_PATTERN.fullmatch(token):
                    raise ValueError("Apps Script anahtarı geçersiz.")
            return {"method": method, "script_url": url, "script_token": token,
                    "credentials_path": secret("credentials_path", "Servis hesabı dosyası")}
        from .database.query import ENGINES

        tables = config.get("allowed_tables", previous.get("allowed_tables", []))
        if isinstance(tables, str):
            tables = [part.strip() for part in tables.split(",")]
        if not isinstance(tables, list) or not all(isinstance(t, str) for t in tables):
            raise ValueError("İzin verilen tablolar virgülle ayrılmış tablo adları olmalıdır.")
        # Profiles from before 0.9.4 hold only an address: they are "Bağlantı adresi (gelişmiş)".
        engine = config.get("engine") or previous.get("engine") or "url"
        if engine not in ENGINES:
            raise ValueError("Veritabanı türü geçersiz.")
        cleaned = {"engine": engine, "allowed_tables": [t.strip() for t in tables if t.strip()]}
        for key in DATABASE_FIELDS:
            value = config.get(key, previous.get(key, ""))
            value = "" if value is None else str(value) if isinstance(value, int) and not isinstance(value, bool) \
                else value
            cleaned[key] = _text(value, {"host": "Sunucu", "port": "Port", "database": "Veritabanı adı",
                                         "user": "Kullanıcı", "path": "Dosya"}[key], 1024)
        if cleaned["port"] and not (cleaned["port"].isdigit() and 0 < int(cleaned["port"]) < 65536):
            raise ValueError("Port 1 ile 65535 arasında bir sayı olmalıdır.")
        if engine == "url":
            cleaned["url"] = secret("url", "Bağlantı adresi")
        else:
            cleaned["password"] = secret("password", "Şifre") if previous.get("engine") == engine or \
                config.get("password") else ""
        return cleaned

    @staticmethod
    def ready(item: dict) -> bool:
        config = item["config"]
        if item["type"] == "database":
            engine = config.get("engine") or "url"
            if engine == "url":
                return bool(config.get("url"))
            if engine == "sqlite":
                return bool(config.get("path"))
            return bool(config.get("host") and config.get("user"))
        if config.get("method") == "apps_script":
            return bool(config.get("script_url") and config.get("script_token"))
        return bool(config.get("credentials_path"))

    def public(self, item: dict) -> dict:
        """Everything the page may show: never the token, password URL or key path."""
        config = item["config"]
        data = {"id": item["id"], "name": item["name"], "type": item["type"], "type_label": TYPES[item["type"]],
                "default": bool(item.get("default")), "ready": self.ready(item)}
        if item["type"] == "google_sheets":
            data.update(method=config["method"], method_label=SHEETS_METHODS[config["method"]],
                        script_url=config.get("script_url", ""), has_token=bool(config.get("script_token")),
                        has_credentials=bool(config.get("credentials_path")))
        else:
            from .database.query import engine_label

            url = config.get("url", "")
            data.update(allowed_tables=config.get("allowed_tables", []), has_url=bool(url),
                        engine=config.get("engine") or "url", engine_label=engine_label(config),
                        has_password=bool(config.get("password")),
                        url_kind=re.split(r"[:+]", url, 1)[0] if url else "",
                        **{key: config.get(key, "") for key in DATABASE_FIELDS})
        return data

    # ----- API ----------------------------------------------------------------------
    def list(self) -> list[dict]:
        with self._lock:
            return [self.public(item) for item in self._load()]

    def get(self, connection_id: str) -> dict:
        with self._lock:
            for item in self._load():
                if item["id"] == connection_id:
                    return json.loads(json.dumps(item))
        raise KeyError(connection_id)

    def create(self, data: dict) -> dict:
        kind = data.get("type")
        if kind not in TYPES:
            raise ValueError("Bağlantı türü Google Sheets veya veritabanı olmalıdır.")
        with self._lock:
            items = self._load()
            item = {"id": uuid.uuid4().hex, "name": self._name(data.get("name"), kind, items), "type": kind,
                    "default": not any(existing["type"] == kind for existing in items),
                    "config": self._clean(kind, data.get("config") or {})}
            items.append(item)
            self._save(items)
            return self.public(item)

    def update(self, connection_id: str, data: dict) -> dict:
        with self._lock:
            items = self._load()
            for item in items:
                if item["id"] == connection_id:
                    if "name" in data:
                        item["name"] = self._name(data["name"], item["type"], items, exclude=connection_id)
                    if "config" in data:
                        item["config"] = self._clean(item["type"], data["config"], item["config"])
                    if data.get("default") is True:
                        for other in items:
                            if other["type"] == item["type"]:
                                other["default"] = other is item
                    self._save(items)
                    return self.public(item)
        raise KeyError(connection_id)

    def delete(self, connection_id: str) -> None:
        with self._lock:
            items = self._load()
            removed = next((item for item in items if item["id"] == connection_id), None)
            if removed is None:
                raise KeyError(connection_id)
            items.remove(removed)
            if removed.get("default"):
                same = [item for item in items if item["type"] == removed["type"]]
                if same:
                    same[0]["default"] = True
            self._save(items)

    @staticmethod
    def _name(value: Any, kind: str, items: list[dict], exclude: str | None = None) -> str:
        name = _text(value, "Bağlantı adı", NAME_LIMIT)
        if not name:
            raise ValueError("Bağlantıya bir ad verin (ör. Satış tablosu).")
        if any(item["type"] == kind and item["name"].casefold() == name.casefold() and item["id"] != exclude
               for item in items):
            raise ValueError(f"“{name}” adında bir {TYPES[kind]} bağlantısı zaten var.")
        return name

    def resolve(self, connection_id: Any, kind: str) -> dict:
        """The profile a step uses: the chosen one, otherwise the default of its type."""
        label = TYPES[kind]
        with self._lock:
            items = [item for item in self._load() if item["type"] == kind]
        if connection_id:
            item = next((item for item in items if item["id"] == connection_id), None)
            if item is None:
                raise WorkflowError(f"Adımda seçilen {label} bağlantısı bu bilgisayarda yok. Adımı açıp bağlantıyı "
                                    "seçin veya yeni bağlantı oluşturun.")
        else:
            item = next((item for item in items if item.get("default")), items[0] if items else None)
            if item is None:
                raise WorkflowError(f"Bu adım için {label} bağlantısı tanımlı değil. Adımı açıp Bağlantı alanından "
                                    "yeni bağlantı oluşturun.")
        if not self.ready(item):
            raise WorkflowError(f"“{item['name']}” bağlantısının ayarları eksik. Adımdaki Bağlantı alanından "
                                "düzenleyin.")
        return item

    def secrets(self) -> list[str]:
        """Values to mask in run logs."""
        with self._lock:
            return [value for item in self._load() for key, value in item["config"].items()
                    if key in SECRET_FIELDS and isinstance(value, str) and len(value) >= 6]
