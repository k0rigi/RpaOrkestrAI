"""Kayıtlı şifreler: passwords a flow uses as ${sifre.ad}, kept in the system password store.

macOS: the login Keychain (Security framework through pyobjc). Windows: Credential Manager
(advapi32 CredWriteW / CredReadW). The Studio keeps only the names (data/secrets.json); a value
never goes into a flow file, an export, a run log or a step-test result.
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import atomic_json

SERVICE = "RpaOrkestrAI Studio"
NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
NAME_RULE = "Ad küçük harfle başlamalı; yalnız İngilizce küçük harf, rakam ve alt çizgi içerebilir (ör. erp)."
MAX_LENGTH = 1000  # Credential Manager keeps at most 2560 bytes (UTF-16)


class VaultError(Exception):
    pass


# ----- the system password stores ----------------------------------------------------------------
class MacKeychain:
    NOT_FOUND = -25300

    def __init__(self):
        import Security

        self.security = Security

    def _query(self, account: str) -> dict:
        s = self.security
        return {s.kSecClass: s.kSecClassGenericPassword, s.kSecAttrService: SERVICE, s.kSecAttrAccount: account}

    def store(self, account: str, value: str) -> None:
        s = self.security
        data = value.encode("utf-8")
        status = s.SecItemUpdate(self._query(account), {s.kSecValueData: data})
        if status == self.NOT_FOUND:
            status = s.SecItemAdd({**self._query(account), s.kSecValueData: data}, None)[0]
        if status != 0:
            raise VaultError(f"Şifre Anahtar Zinciri'ne kaydedilemedi (kod {status}).")

    def load(self, account: str) -> str | None:
        s = self.security
        query = {**self._query(account), s.kSecReturnData: True, s.kSecMatchLimit: s.kSecMatchLimitOne}
        status, data = s.SecItemCopyMatching(query, None)
        if status == self.NOT_FOUND:
            return None
        if status != 0:
            raise VaultError(f"Şifre Anahtar Zinciri'nden okunamadı (kod {status}). Anahtar Zinciri erişim "
                             "isteğini onaylayın.")
        return bytes(data).decode("utf-8")

    def remove(self, account: str) -> None:
        status = self.security.SecItemDelete(self._query(account))
        if status not in (0, self.NOT_FOUND):
            raise VaultError(f"Şifre Anahtar Zinciri'nden silinemedi (kod {status}).")


class WindowsCredentials:
    GENERIC, LOCAL_MACHINE, NOT_FOUND = 1, 2, 1168

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class Credential(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                        ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                        ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                        ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                        ("UserName", wintypes.LPWSTR)]

        self.ctypes, self.Credential = ctypes, Credential
        api = ctypes.WinDLL("advapi32", use_last_error=True)
        self.write, self.read, self.delete, self.free = api.CredWriteW, api.CredReadW, api.CredDeleteW, api.CredFree
        self.write.argtypes = [ctypes.POINTER(Credential), wintypes.DWORD]
        self.read.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              ctypes.POINTER(ctypes.POINTER(Credential))]
        self.delete.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self.free.argtypes = [ctypes.c_void_p]
        for function in (self.write, self.read, self.delete):
            function.restype = wintypes.BOOL

    @staticmethod
    def target(account: str) -> str:
        return f"{SERVICE}/{account}"

    def store(self, account: str, value: str) -> None:
        ctypes = self.ctypes
        blob = value.encode("utf-16-le")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob) if blob else None
        credential = self.Credential(Type=self.GENERIC, TargetName=self.target(account), UserName=account,
                                     Persist=self.LOCAL_MACHINE, CredentialBlobSize=len(blob),
                                     CredentialBlob=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
        if not self.write(ctypes.byref(credential), 0):
            raise VaultError(f"Şifre Kimlik Bilgisi Yöneticisi'ne kaydedilemedi (kod {ctypes.get_last_error()}).")

    def load(self, account: str) -> str | None:
        ctypes = self.ctypes
        found = ctypes.POINTER(self.Credential)()
        if not self.read(self.target(account), self.GENERIC, 0, ctypes.byref(found)):
            error = ctypes.get_last_error()
            if error == self.NOT_FOUND:
                return None
            raise VaultError(f"Şifre Kimlik Bilgisi Yöneticisi'nden okunamadı (kod {error}).")
        try:
            credential = found.contents
            return ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize).decode("utf-16-le")
        finally:
            self.free(found)

    def remove(self, account: str) -> None:
        if not self.delete(self.target(account), self.GENERIC, 0):
            error = self.ctypes.get_last_error()
            if error != self.NOT_FOUND:
                raise VaultError(f"Şifre Kimlik Bilgisi Yöneticisi'nden silinemedi (kod {error}).")


def system_store():
    if platform.system() == "Darwin":
        return MacKeychain()
    if platform.system() == "Windows":
        return WindowsCredentials()
    raise VaultError("Kayıtlı şifreler macOS ve Windows'ta kullanılabilir.")


# ----- the names, per workspace -------------------------------------------------------------------
class Vault:
    def __init__(self, data_dir: Path, store=None):
        self.index = Path(data_dir) / "secrets.json"
        # Two workspaces on one computer keep separate passwords under the same name.
        self.scope = hashlib.sha256(str(Path(data_dir).resolve()).encode()).hexdigest()[:10]
        self._store = store
        self._lock = threading.RLock()

    @property
    def store(self):
        if self._store is None:
            self._store = system_store()
        return self._store

    def account(self, name: str) -> str:
        return f"{self.scope}:{name}"

    def _read(self) -> dict[str, dict]:
        try:
            return json.loads(self.index.read_text(encoding="utf-8")).get("names", {})
        except (OSError, ValueError, AttributeError):
            return {}

    def names(self) -> list[dict]:
        with self._lock:
            return [{"name": name, **info} for name, info in sorted(self._read().items())]

    def has(self, name: str) -> bool:
        return name in self._read()

    @staticmethod
    def check_name(name: str) -> str:
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise VaultError(NAME_RULE)
        return name

    def set(self, name: str, value: str) -> None:
        self.check_name(name)
        if not isinstance(value, str) or not value or len(value) > MAX_LENGTH or "\x00" in value:
            raise VaultError(f"Şifre 1 ile {MAX_LENGTH} karakter arasında olmalıdır.")
        with self._lock:
            names = self._read()
            if name not in names and len(names) >= 200:
                raise VaultError("En fazla 200 şifre kaydedilebilir.")
            self.store.store(self.account(name), value)
            names[name] = {"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            atomic_json(self.index, {"names": names})

    def get(self, name: str) -> str | None:
        if not self.has(name):
            return None
        return self.store.load(self.account(name))

    def delete(self, name: str) -> bool:
        with self._lock:
            names = self._read()
            if name not in names:
                return False
            self.store.remove(self.account(name))
            del names[name]
            atomic_json(self.index, {"names": names})
            return True
