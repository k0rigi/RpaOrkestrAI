"""Firma kapsamlı sağlayıcı profilleri; anahtarlar yalnız ayrı sistem kasasındadır."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from ..config import atomic_json
from ..models import now
from ..vault import MAX_LENGTH, Vault
from .models import ProviderConnection
from .provider_adapters import create_provider, local_endpoint
from .providers import ProviderError
from .redaction import Redactor

MAX_CONNECTION_BYTES = 1024 * 1024


class ProviderConnectionStore:
    _locks = {}
    _guard = threading.Lock()

    def __init__(self, data_dir: Path, *, vault=None):
        self.root = Path(data_dir).expanduser().absolute()
        if self.root.is_symlink():
            raise ValueError("Sağlayıcı veri dizini sembolik bağlantı olamaz.")
        self.root.mkdir(parents=True, exist_ok=True)
        self.root = self.root.resolve()
        self.path = self.root / "agent_connections.json"
        self.vault = vault if vault is not None else Vault(self.root, purpose="agent_provider")
        if getattr(self.vault, "purpose", None) != "agent_provider":
            raise ValueError("Sağlayıcı anahtarları ayrı şifre kasasında saklanmalıdır.")
        with self._guard:
            self._lock = self._locks.setdefault(str(self.path), threading.RLock())

    def _safe_path(self):
        if self.path.is_symlink() or self.path.with_suffix(".tmp").is_symlink():
            raise ValueError("Sağlayıcı kaydı sembolik bağlantı olamaz.")
        if self.vault.index.is_symlink() or self.vault.index.with_suffix(".tmp").is_symlink():
            raise ValueError("Sağlayıcı kasa dizini sembolik bağlantı olamaz.")

    @staticmethod
    def _company(company_id):
        if type(company_id) is not int or company_id <= 0:
            raise ValueError("Doğrulanmış firma kimliği gereklidir.")

    def _read(self):
        self._safe_path()
        if not self.path.exists():
            return {}
        if self.path.stat().st_size > MAX_CONNECTION_BYTES:
            raise ValueError("Sağlayıcı kayıtları boyut sınırını aşıyor.")
        try:
            with self.path.open("rb") as handle:
                data = handle.read(MAX_CONNECTION_BYTES + 1)
            if len(data) > MAX_CONNECTION_BYTES:
                raise ValueError
            raw = json.loads(data)
            if type(raw) is not dict or set(raw) != {"connections"} or type(raw["connections"]) is not list:
                raise ValueError
            values = [ProviderConnection.model_validate(item) for item in raw["connections"]]
            if len(values) > 200 or len({item.id for item in values}) != len(values):
                raise ValueError
            return {item.id: item for item in values}
        except (ValueError, TypeError, OSError):
            raise ValueError("Sağlayıcı kayıtları okunamadı; kayıt biçimi geçersiz.") from None

    def _write(self, records):
        self._safe_path()
        data = {"connections": [item.model_dump(mode="json") for item in records.values()]}
        if len(json.dumps(data, ensure_ascii=False).encode()) > MAX_CONNECTION_BYTES:
            raise ValueError("Sağlayıcı kayıtları boyut sınırını aşıyor.")
        atomic_json(self.path, data)

    def _registered_secrets(self, *, repair_name=None) -> dict[str, str]:
        """Read registered values strictly; an intentionally keyless profile has no index entry."""
        try:
            self._safe_path()
            try:
                with self.vault.index.open("rb") as source:
                    raw = source.read(256 * 1024 + 1)
            except FileNotFoundError:
                return {}
            metadata = json.loads(raw)
            if (len(raw) > 256 * 1024 or type(metadata) is not dict or set(metadata) != {"names"}
                    or type(metadata["names"]) is not dict or len(metadata["names"]) > 200):
                raise ValueError
            values = {}
            for name, entry in metadata["names"].items():
                self.vault.check_name(name)
                if type(entry) is not dict:
                    raise ValueError
                value = self.vault.store.load(self.vault.account(name))
                if value is None and name == repair_name:
                    continue  # Replacing this missing key is an explicit recovery action.
                if type(value) is not str or not value or len(value) > MAX_LENGTH or "\x00" in value:
                    raise ValueError
                values[name] = value
            return values
        except Exception:
            raise ValueError("Kayıtlı sağlayıcı sırları güvenli biçimde doğrulanamadı.") from None

    @staticmethod
    def _check_metadata(connection, values):
        redactor = Redactor(values)
        if any(redactor.contains_secret(value) for value in (connection.name, connection.model, connection.base_url or "")):
            raise ValueError("Bağlantı adı, model veya adres kayıtlı bir gizli değer içeremez.")

    def list(self, company_id: int) -> list[ProviderConnection]:
        self._company(company_id)
        with self._lock:
            return [item for item in self._read().values() if item.company_id == company_id]

    def get(self, identity: str, company_id: int) -> ProviderConnection:
        self._company(company_id)
        with self._lock:
            value = self._read().get(identity)
            if value is None or value.company_id != company_id:
                raise KeyError("Sağlayıcı bağlantısı bulunamadı.")
            return value

    def save(self, connection: ProviderConnection, company_id: int) -> ProviderConnection:
        self._company(company_id)
        try:
            value = ProviderConnection.model_validate(connection.model_dump())
        except ValueError:
            raise ValueError("Sağlayıcı bağlantısı geçersiz.") from None
        if value.company_id != company_id or value.provider == "fake":
            raise ValueError("Bu sağlayıcı bağlantısına izin verilmiyor.")
        if value.provider in {"ollama", "local_openai"}:
            value.base_url = local_endpoint(value.base_url, provider=value.provider)
        with self._lock:
            records = self._read()
            self._check_metadata(value, self._registered_secrets().values())
            old = records.get(value.id)
            if old is not None and old.company_id != company_id:
                raise KeyError("Sağlayıcı bağlantısı bulunamadı.")
            if old is None and len(records) >= 200:
                raise ValueError("En fazla 200 sağlayıcı bağlantısı kaydedilebilir.")
            if old is not None and old.provider != value.provider:
                raise ValueError("Sağlayıcı türünü değiştirmek için yeni bağlantı oluşturun.")
            value.created_at = old.created_at if old else value.created_at
            value.updated_at = now()
            records[value.id] = value
            known = self._registered_secrets().values()
            for record in records.values():
                self._check_metadata(record, known)
            self._write(records)
            return value.model_copy(deep=True)

    @staticmethod
    def _key_name(identity):
        return "c" + identity

    def has_key(self, identity: str, company_id: int) -> bool:
        with self._lock:
            self.get(identity, company_id)
            return self.vault.has(self._key_name(identity))

    def set_key(self, identity: str, value: str, company_id: int) -> None:
        with self._lock:
            if self.get(identity, company_id).provider == "shared":
                raise ValueError("Kurum bağlantısı Studio oturumunu kullanır; API anahtarı kaydedilmez.")
            if not isinstance(value, str) or any(ord(char) < 32 for char in value):
                raise ValueError("API anahtarı geçerli tek satırlı metin olmalıdır.")
            known = list(self._registered_secrets(repair_name=self._key_name(identity)).values())
            # Validate the new value before it becomes a secret, too: metadata may
            # have been saved first and must not become a plaintext credential.
            for connection in self._read().values():
                self._check_metadata(connection, [*known, value])
            try:
                self.vault.set(self._key_name(identity), value)
            except Exception:
                raise ValueError("API anahtarı sistem şifre kasasına kaydedilemedi.") from None

    def delete_key(self, identity: str, company_id: int) -> bool:
        with self._lock:
            self.get(identity, company_id)
            try:
                return self.vault.delete(self._key_name(identity))
            except Exception:
                raise ValueError("API anahtarı sistem şifre kasasından silinemedi.") from None

    def delete(self, identity: str, company_id: int) -> None:
        with self._lock:
            self.get(identity, company_id)
            self.delete_key(identity, company_id)
            records = self._read()
            del records[identity]
            self._write(records)

    def public(self, identity: str, company_id: int) -> dict:
        with self._lock:
            connection = self.get(identity, company_id)
            self._check_metadata(connection, self._registered_secrets().values())
            return {**connection.model_dump(mode="json"), "has_key": self.has_key(identity, company_id),
                    "sends_to_cloud": connection.provider in {"openai", "gemini", "anthropic"},
                    "sends_to_company_server": connection.provider == "shared"}

    def secrets(self, company_id: int) -> list[str]:
        """Internal redaction input only; never expose through a response or export."""
        self._company(company_id)
        with self._lock:
            # Metadata shares one local file. Protect registered values from every
            # company in that file; this internal list is never serialized.
            return list(self._registered_secrets().values())

    def provider(self, identity: str, company_id: int, *, transport=None):
        with self._lock:
            connection = self.get(identity, company_id)
            try:
                values = self._registered_secrets()
                self._check_metadata(connection, values.values())
                key = values.get(self._key_name(identity))
            except ValueError:
                raise ProviderError() from None
            return create_provider(connection, key, transport=transport)

    def test_connection(self, identity: str, company_id: int, *, model: str | None = None,
                        cancel=None, transport=None) -> dict:
        """Explicit UI action only; no workflow/business data, cloud usage can still be billable."""
        connection = self.get(identity, company_id)
        selected_model = model or connection.model
        redactor = Redactor(self.secrets(company_id))
        if redactor.contains_secret(selected_model):
            raise ValueError("Model adı kayıtlı bir gizli değer içeremez.")
        provider = self.provider(identity, company_id, transport=transport)
        response = provider.complete([{"role": "user", "content": "Bağlantı testi. Kısaca tamam yaz."}], [],
                                     model=selected_model, max_tokens=256,
                                     cancel=cancel or threading.Event(), deadline=time.monotonic() + 30)
        return {"ok": True, "input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens,
                "message": "Sağlayıcı bağlantısı doğrulandı."}
