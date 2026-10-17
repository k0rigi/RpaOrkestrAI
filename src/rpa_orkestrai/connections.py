"""Named connections (Google Sheets, databases, mail, APIs, FTP, messaging) that steps select, like n8n credentials.

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
from urllib.parse import urlsplit

from .config import atomic_json
from .errors import WorkflowError

TYPES = {"google_sheets": "Google Sheets", "database": "Veritabanı", "smtp": "E-posta (SMTP)",
         "imap": "Gelen e-posta (IMAP)", "api": "Web servisi (API)", "ftp": "FTP / FTPS",
         "webhook": "Mesajlaşma (Teams, Slack, WhatsApp, Telegram…)"}
SHEETS_METHODS = {"apps_script": "Apps Script", "service_account": "Servis hesabı"}
SECRET_FIELDS = {"script_token", "credentials_path", "url", "password", "token", "api_key", "client_secret"}
API_AUTH = {"none": "Kimlik doğrulama yok", "bearer": "Bearer token", "basic": "Kullanıcı adı ve şifre (Basic)",
            "api_key": "API anahtarı", "oauth2": "OAuth 2.0 istemci bilgileri"}
IMAP_SECURITY = {"ssl": "SSL/TLS (genellikle 993)", "starttls": "STARTTLS (genellikle 143)",
                 "none": "Şifrelemesiz (yalnız iç ağ)"}
IMAP_PORTS = {"ssl": "993", "starttls": "143", "none": "143"}
FTP_SECURITY = {"ftps": "FTPS · açık TLS (önerilen)", "none": "Şifrelemesiz FTP (yalnız iç ağ)"}
WEBHOOK_SERVICES = {"teams": "Microsoft Teams (İş Akışları)", "slack": "Slack", "google_chat": "Google Chat",
                    "discord": "Discord", "telegram": "Telegram (bot)", "whatsapp": "WhatsApp (Business Cloud API)",
                    "generic": "Diğer (JSON gövde)"}
# Telegram and WhatsApp are reached with a token and an address; the others with a secret webhook address.
TOKEN_SERVICES = {"telegram", "whatsapp"}
TELEGRAM_CHAT = re.compile(r"^(-?\d{1,20}|@[A-Za-z0-9_]{5,32})$")
WHATSAPP_NUMBER = re.compile(r"^\d{8,15}$")
GRAPH_VERSION = re.compile(r"^v\d{2,3}\.\d$")
WHATSAPP_TEMPLATE = re.compile(r"^[a-z0-9_]{1,512}$")
LANGUAGE_CODE = re.compile(r"^[a-z]{2,3}(_[A-Z]{2})?$")
WHATSAPP_API_VERSION = "v26.0"


def phone_number(value: Any) -> str:
    """A WhatsApp recipient: country code and number, digits only (+90 532 … → 90532…)."""
    digits = re.sub(r"[\s()+.-]", "", str(value or ""))
    if digits and not WHATSAPP_NUMBER.fullmatch(digits):
        raise ValueError("WhatsApp numarası ülke koduyla yazılmalıdır (ör. 905321234567).")
    return digits
HEADER_NAME = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,100}$")
# Credentials belong in the protected fields, never in plain default headers.
CREDENTIAL_HEADERS = {"authorization", "proxy-authorization", "cookie", "x-api-key", "api-key"}
WRITE_TARGET = re.compile(r"^[A-Za-z0-9_$#@.\[\]\"` -]{1,200}$")
DATABASE_FIELDS = ("host", "port", "database", "user", "path")
SMTP_SECURITY = {"starttls": "STARTTLS (genellikle 587)", "ssl": "SSL/TLS (genellikle 465)",
                 "none": "Şifrelemesiz (yalnız iç ağ)"}
SMTP_PORTS = {"starttls": "587", "ssl": "465", "none": "25"}
EMAIL = re.compile(r"^[^@\s,;<>\"]+@[^@\s,;<>\"]+\.[^@\s,;<>\"]+$")
NAME_LIMIT = 80


def _text(value: Any, label: str, limit: int = 4096) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"{label} en fazla {limit} karakterlik metin olmalıdır.")
    return value.strip()


class Connections:
    _locks: dict[Path, threading.RLock] = {}
    _locks_guard = threading.Lock()

    def __init__(self, data_dir: Path | str, settings: Any = None):
        self._path = Path(data_dir).expanduser().resolve() / "connections.json"
        # API, engine and agents create separate Connections objects for the same
        # workspace. Migration and read/modify/write must share one path lock.
        with self._locks_guard:
            self._lock = self._locks.setdefault(self._path, threading.RLock())
        with self._lock:
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
        if kind == "smtp":
            return self._clean_smtp(config, previous, secret)
        if kind == "imap":
            return self._clean_imap(config, previous, secret)
        if kind == "api":
            return self._clean_api(config, previous, secret)
        if kind == "ftp":
            return self._clean_ftp(config, previous, secret)
        if kind == "webhook":
            return self._clean_webhook(config, previous, secret)
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
        # Changing records is a separate, explicit permission with its own list of tables and procedures.
        allow_write = config.get("allow_write", previous.get("allow_write", False))
        if not isinstance(allow_write, bool):
            raise ValueError("Yazma izni açık veya kapalı olmalıdır.")
        targets = config.get("write_targets", previous.get("write_targets", []))
        if isinstance(targets, str):
            targets = [part.strip() for part in re.split(r"[,\n]", targets)]
        if not isinstance(targets, list) or not all(isinstance(item, str) for item in targets):
            raise ValueError("Değiştirilebilecek tablolar virgülle ayrılmış adlar olmalıdır.")
        targets = [item.strip() for item in targets if item.strip()]
        if len(targets) > 200 or any(not WRITE_TARGET.fullmatch(item) for item in targets):
            raise ValueError("Değiştirilebilecek tablo ve yordam adlarını şema.ad biçiminde yazın (en fazla 200).")
        if allow_write and not targets:
            raise ValueError("Yazma izni için değiştirilebilecek en az bir tablo veya saklı yordam yazın.")
        cleaned.update(allow_write=allow_write, write_targets=targets)
        return cleaned

    @staticmethod
    def _value(config: dict, previous: dict, key: str, label: str, limit: int = 320) -> str:
        raw = config.get(key, previous.get(key, ""))
        raw = str(raw) if isinstance(raw, int) and not isinstance(raw, bool) else raw
        return _text(raw, label, limit)

    @staticmethod
    def _port(value: str) -> str:
        if not (value.isdigit() and 0 < int(value) < 65536):
            raise ValueError("Port 1 ile 65535 arasında bir sayı olmalıdır.")
        return value

    def _clean_imap(self, config: dict, previous: dict, secret: Any) -> dict:
        security = config.get("security") or previous.get("security") or "ssl"
        if security not in IMAP_SECURITY:
            raise ValueError("Şifreleme SSL/TLS, STARTTLS veya şifrelemesiz olmalıdır.")
        cleaned = {"host": self._value(config, previous, "host", "IMAP sunucusu", 255), "security": security,
                   "user": self._value(config, previous, "user", "Kullanıcı"),
                   "folder": self._value(config, previous, "folder", "Klasör", 200) or "INBOX"}
        cleaned["port"] = self._port(self._value(config, previous, "port", "Port", 5) or IMAP_PORTS[security])
        if any(char in cleaned["folder"] for char in "\r\n\"\\"):
            raise ValueError("Klasör adında tırnak, ters bölü veya satır sonu olamaz.")
        same = previous.get("host") == cleaned["host"] and previous.get("user") == cleaned["user"]
        cleaned["password"] = secret("password", "Şifre") if same or config.get("password") else ""
        return cleaned

    def _clean_api(self, config: dict, previous: dict, secret: Any) -> dict:
        base = self._value(config, previous, "base_url", "Ana adres", 2000).rstrip("/")
        if base:
            parts = urlsplit(base)
            if parts.scheme not in {"https", "http"} or not parts.hostname:
                raise ValueError("Ana adres https:// (veya iç ağda http://) ile başlayan tam bir adres olmalıdır.")
            if parts.username or parts.password or parts.fragment:
                raise ValueError("Ana adrese kullanıcı adı, şifre veya # bölümü yazmayın; kimlik doğrulama alanlarını "
                                 "kullanın.")
        auth = config.get("auth") or previous.get("auth") or "none"
        if auth not in API_AUTH:
            raise ValueError("Kimlik doğrulama türü geçersiz.")
        headers = config.get("headers", previous.get("headers", {})) or {}
        if not isinstance(headers, dict) or len(headers) > 30:
            raise ValueError("Varsayılan başlıklar en fazla 30 alanlı bir nesne olmalıdır.")
        clean_headers = {}
        for name, value in headers.items():
            if not isinstance(name, str) or not HEADER_NAME.fullmatch(name):
                raise ValueError(f"Başlık adı geçersiz: {name}")
            if name.casefold() in CREDENTIAL_HEADERS:
                raise ValueError(f"{name} başlığını kimlik doğrulama alanlarına yazın; düz başlıklar korunmaz.")
            value = str(value)
            if len(value) > 1000 or any(char in value for char in "\r\n"):
                raise ValueError(f"{name} başlığının değeri en fazla 1000 karakter olmalı ve satır sonu içermemelidir.")
            clean_headers[name] = value
        key_in = config.get("key_in") or previous.get("key_in") or "header"
        if key_in not in {"header", "query"}:
            raise ValueError("API anahtarı başlıkta veya adres parametresinde gönderilmelidir.")
        key_name = self._value(config, previous, "key_name", "Anahtar adı", 100) or "X-API-Key"
        if not HEADER_NAME.fullmatch(key_name):
            raise ValueError("Anahtar adı yalnız harf, rakam ve - _ . karakterlerinden oluşmalıdır.")
        token_url = self._value(config, previous, "token_url", "Token adresi", 2000)
        if token_url and urlsplit(token_url).scheme != "https":
            raise ValueError("OAuth token adresi https:// ile başlamalıdır.")
        test_path = self._value(config, previous, "test_path", "Test adresi", 500)
        if "://" in test_path:
            raise ValueError("Test adresi ana adrese göre bir yol olmalıdır (ör. /v1/durum).")
        cleaned = {"base_url": base, "auth": auth, "headers": clean_headers, "key_in": key_in, "key_name": key_name,
                   "user": self._value(config, previous, "user", "Kullanıcı"), "token_url": token_url,
                   "client_id": self._value(config, previous, "client_id", "İstemci kimliği", 500),
                   "scope": self._value(config, previous, "scope", "Kapsam (scope)", 1000), "test_path": test_path}
        # Secrets typed for one server are never sent to another one the user switched to.
        same = urlsplit(previous.get("base_url", "")).netloc == urlsplit(base).netloc
        for key, label in (("token", "Token"), ("password", "Şifre"), ("api_key", "API anahtarı"),
                           ("client_secret", "İstemci sırrı")):
            cleaned[key] = secret(key, label) if same or config.get(key) else ""
        return cleaned

    def _clean_ftp(self, config: dict, previous: dict, secret: Any) -> dict:
        security = config.get("security") or previous.get("security") or "ftps"
        if security not in FTP_SECURITY:
            raise ValueError("FTP güvenliği FTPS veya şifrelemesiz olmalıdır.")
        passive = config.get("passive", previous.get("passive", True))
        if not isinstance(passive, bool):
            raise ValueError("Pasif mod açık veya kapalı olmalıdır.")
        cleaned = {"host": self._value(config, previous, "host", "FTP sunucusu", 255), "security": security,
                   "user": self._value(config, previous, "user", "Kullanıcı"), "passive": passive,
                   "base_dir": self._value(config, previous, "base_dir", "Başlangıç klasörü", 500) or "/"}
        cleaned["port"] = self._port(self._value(config, previous, "port", "Port", 5) or "21")
        same = previous.get("host") == cleaned["host"] and previous.get("user") == cleaned["user"]
        cleaned["password"] = secret("password", "Şifre") if same or config.get("password") else ""
        return cleaned

    @staticmethod
    def _clean_webhook(config: dict, previous: dict, secret: Any) -> dict:
        service = config.get("service") or previous.get("service") or "teams"
        if service not in WEBHOOK_SERVICES:
            raise ValueError("Mesajlaşma servisi geçersiz.")
        if service not in TOKEN_SERVICES:
            url = secret("url", "Webhook adresi")
            if url and urlsplit(url).scheme != "https":
                raise ValueError("Webhook adresi https:// ile başlamalıdır.")
            return {"service": service, "url": url}
        # A token saved for another service is never carried over to this one.
        token = secret("token", "Erişim anahtarı") if previous.get("service") == service \
            else _text(config.get("token"), "Erişim anahtarı")
        if token and any(ord(char) < 33 for char in token):
            raise ValueError("Erişim anahtarı boşluk veya satır sonu içeremez.")

        def value(key: str, label: str, limit: int = 200) -> str:
            return _text(str(config.get(key, previous.get(key, "")) or ""), label, limit)

        if service == "telegram":
            chat = value("chat_id", "Sohbet kimliği", 40)
            if chat and not TELEGRAM_CHAT.fullmatch(chat):
                raise ValueError("Telegram sohbet kimliği bir sayı (ör. -1001234567890) veya @kanaladi olmalıdır.")
            return {"service": service, "token": token, "chat_id": chat}
        number_id = value("phone_number_id", "Telefon numarası kimliği", 30)
        if number_id and not number_id.isdigit():
            raise ValueError("Telefon numarası kimliği (Phone number ID) yalnız rakamlardan oluşur.")
        version = value("api_version", "API sürümü", 10) or WHATSAPP_API_VERSION
        if not GRAPH_VERSION.fullmatch(version):
            raise ValueError("API sürümü v26.0 biçiminde olmalıdır.")
        mode = config.get("mode") or previous.get("mode") or "text"
        if mode not in {"text", "template"}:
            raise ValueError("WhatsApp gönderim türü serbest metin veya şablon olmalıdır.")
        template = value("template_name", "Şablon adı", 512)
        if mode == "template" and not WHATSAPP_TEMPLATE.fullmatch(template):
            raise ValueError("Şablon adını Meta'da onaylandığı gibi küçük harf, rakam ve alt çizgiyle yazın.")
        language = value("template_language", "Şablon dili", 10) or "tr"
        if not LANGUAGE_CODE.fullmatch(language):
            raise ValueError("Şablon dili tr veya en_US biçiminde olmalıdır.")
        return {"service": service, "token": token, "phone_number_id": number_id, "to": phone_number(value("to", "Alıcı", 30)),
                "api_version": version, "mode": mode, "template_name": template if mode == "template" else "",
                "template_language": language}

    @staticmethod
    def _clean_smtp(config: dict, previous: dict, secret: Any) -> dict:
        def value(key: str, label: str, limit: int = 320) -> str:
            raw = config.get(key, previous.get(key, ""))
            raw = str(raw) if isinstance(raw, int) and not isinstance(raw, bool) else raw
            return _text(raw, label, limit)

        security = config.get("security") or previous.get("security") or "starttls"
        if security not in SMTP_SECURITY:
            raise ValueError("Şifreleme STARTTLS, SSL/TLS veya şifrelemesiz olmalıdır.")
        cleaned = {"host": value("host", "SMTP sunucusu", 255), "port": value("port", "Port", 5) or SMTP_PORTS[security],
                   "security": security, "user": value("user", "Kullanıcı"), "sender": value("sender", "Gönderen adresi"),
                   "sender_name": value("sender_name", "Gönderen adı", 120)}
        if not (cleaned["port"].isdigit() and 0 < int(cleaned["port"]) < 65536):
            raise ValueError("Port 1 ile 65535 arasında bir sayı olmalıdır.")
        if cleaned["sender"] and not EMAIL.fullmatch(cleaned["sender"]):
            raise ValueError("Gönderen adresi geçerli bir e-posta adresi olmalıdır (ör. rpa@firma.com).")
        if any(char in cleaned["sender_name"] for char in "\r\n"):
            raise ValueError("Gönderen adı satır sonu içeremez.")
        # A changed server or user must not reuse a password typed for another account.
        same = previous.get("host") == cleaned["host"] and previous.get("user") == cleaned["user"]
        cleaned["password"] = secret("password", "Şifre") if same or config.get("password") else ""
        return cleaned

    @staticmethod
    def ready(item: dict) -> bool:
        config = item["config"]
        if item["type"] == "smtp":
            return bool(config.get("host") and config.get("sender"))
        if item["type"] == "imap":
            return bool(config.get("host") and config.get("user") and config.get("password"))
        if item["type"] == "ftp":
            return bool(config.get("host"))
        if item["type"] == "webhook":
            if config.get("service") == "telegram":
                return bool(config.get("token") and config.get("chat_id"))
            if config.get("service") == "whatsapp":
                return bool(config.get("token") and config.get("phone_number_id"))
            return bool(config.get("url"))
        if item["type"] == "api":
            needed = {"none": (), "bearer": ("token",), "basic": ("user", "password"), "api_key": ("api_key",),
                      "oauth2": ("token_url", "client_id", "client_secret")}[config.get("auth", "none")]
            return bool(config.get("base_url")) and all(config.get(key) for key in needed)
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
        elif item["type"] == "smtp":
            data.update(has_password=bool(config.get("password")), security_label=SMTP_SECURITY[config["security"]],
                        **{key: config.get(key, "") for key in ("host", "port", "security", "user", "sender",
                                                                "sender_name")})
        elif item["type"] == "imap":
            data.update(has_password=bool(config.get("password")), security_label=IMAP_SECURITY[config["security"]],
                        **{key: config.get(key, "") for key in ("host", "port", "security", "user", "folder")})
        elif item["type"] == "ftp":
            data.update(has_password=bool(config.get("password")), security_label=FTP_SECURITY[config["security"]],
                        passive=bool(config.get("passive", True)),
                        **{key: config.get(key, "") for key in ("host", "port", "security", "user", "base_dir")})
        elif item["type"] == "webhook":
            data.update(service=config["service"], service_label=WEBHOOK_SERVICES[config["service"]],
                        has_url=bool(config.get("url")), has_token=bool(config.get("token")),
                        **{key: config.get(key, "") for key in ("chat_id", "phone_number_id", "to", "api_version", "mode",
                                                                "template_name", "template_language")})
        elif item["type"] == "api":
            data.update(auth_label=API_AUTH[config["auth"]], headers=dict(config.get("headers") or {}),
                        has_token=bool(config.get("token")), has_password=bool(config.get("password")),
                        has_api_key=bool(config.get("api_key")), has_client_secret=bool(config.get("client_secret")),
                        **{key: config.get(key, "") for key in ("base_url", "auth", "key_in", "key_name", "user",
                                                                "token_url", "client_id", "scope", "test_path")})
        else:
            from .database.query import engine_label

            url = config.get("url", "")
            data.update(allowed_tables=config.get("allowed_tables", []), has_url=bool(url),
                        engine=config.get("engine") or "url", engine_label=engine_label(config),
                        has_password=bool(config.get("password")),
                        url_kind=re.split(r"[:+]", url, 1)[0] if url else "",
                        allow_write=bool(config.get("allow_write")), write_targets=config.get("write_targets", []),
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
            raise ValueError("Bağlantı türü geçersiz.")
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

    def secrets(self, *, include_short: bool = False) -> list[str]:
        """Values to mask in run logs."""
        with self._lock:
            return [value for item in self._load() for key, value in item["config"].items()
                    if key in SECRET_FIELDS and isinstance(value, str)
                    and len(value) >= (1 if include_short else 6)]
