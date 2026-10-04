"""Kayıtlı şifreler: values live in the system password store; flows, logs and test results never hold them."""

import json
import os
import platform
import time
from uuid import uuid4

import pytest

from rpa_orkestrai import vault as vault_module
from rpa_orkestrai.vault import Vault, VaultError


class MemoryStore:
    def __init__(self):
        self.items = {}

    def store(self, account, value):
        self.items[account] = value

    def load(self, account):
        return self.items.get(account)

    def remove(self, account):
        self.items.pop(account, None)


@pytest.fixture
def memory(monkeypatch):
    store = MemoryStore()
    monkeypatch.setattr(vault_module, "system_store", lambda: store)
    return store


def test_names_are_kept_here_and_values_in_the_store(tmp_path, memory):
    vault = Vault(tmp_path)
    vault.set("erp", "Gizli-Şifre 1")
    assert vault.get("erp") == "Gizli-Şifre 1"
    assert [entry["name"] for entry in vault.names()] == ["erp"]
    index = (tmp_path / "secrets.json").read_text(encoding="utf-8")
    assert "Gizli" not in index
    assert list(memory.items.values()) == ["Gizli-Şifre 1"]
    # Another workspace on the same computer has its own value under the same name.
    other = Vault(tmp_path / "baska")
    assert other.get("erp") is None
    vault.set("erp", "yeni")
    assert vault.get("erp") == "yeni" and len(memory.items) == 1
    assert vault.delete("erp") and not vault.delete("erp") and memory.items == {}


@pytest.mark.parametrize("name", ["ERP", "1erp", "erp şifre", "", "a" * 41, "erp-giris"])
def test_names_follow_the_variable_rule(tmp_path, memory, name):
    with pytest.raises(VaultError, match="küçük harfle"):
        Vault(tmp_path).set(name, "x")


def test_empty_or_too_long_values_are_refused(tmp_path, memory):
    with pytest.raises(VaultError, match="1 ile 1000"):
        Vault(tmp_path).set("erp", "")
    with pytest.raises(VaultError, match="1 ile 1000"):
        Vault(tmp_path).set("erp", "x" * 1001)


def studio(tmp_path):
    from fastapi.testclient import TestClient

    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    return TestClient(create_app(Settings(tmp_path / "data", dotenv=False)))


def finished(client, run):
    deadline = time.monotonic() + 10
    while run["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.05)
        run = client.get(f"/api/runs/{run['id']}").json()
    return run


def test_api_never_returns_a_value_and_runs_never_keep_it(tmp_path, memory):
    secret = "Pa$$w0rd-Çok-Gizli"
    with studio(tmp_path) as client:
        saved = client.put("/api/secrets/erp", json={"value": secret})
        assert saved.status_code == 200 and secret not in saved.text
        assert [entry["name"] for entry in client.get("/api/secrets").json()["names"]] == ["erp"]
        assert client.put("/api/secrets/ERP", json={"value": "x"}).status_code == 422
        flow = client.post("/api/workflows", json={"name": "Giriş", "steps": [
            {"id": "log", "action": "core.log", "params": {"message": "Şifre: ${sifre.erp}"}},
            {"id": "upper", "action": "text.transform", "params": {"text": "${sifre.erp}", "operation": "upper",
                                                                    "output": "buyuk"}},
            {"id": "copy", "action": "core.set", "params": {"name": "kopya", "value": "${sifre.erp}"}},
            {"id": "open", "action": "system.run_file", "params": {"path": "/yok/${sifre.erp}.py"}},
        ]}).json()
        # The flow file holds only the name.
        assert secret not in json.dumps(client.get(f"/api/workflows/{flow['id']}/export").json())
        run = finished(client, client.post(f"/api/workflows/{flow['id']}/run", json={}).json())
        assert run["status"] == "failed"
        text = json.dumps(run, ensure_ascii=False)
        assert secret not in text and json.dumps(secret)[1:-1] not in text
        assert "Şifre: [gizlendi]" in text and "[gizlendi]" in run["error"]
        # A single-step test shows the values it used, masked.
        test = finished(client, client.post(f"/api/workflows/{flow['id']}/steps/copy/test", json={}).json())
        assert test["variables"]["kopya"] == "[gizlendi]" and "sifre" not in test["variables"]
        assert secret not in json.dumps(test, ensure_ascii=False)
        assert client.delete("/api/secrets/erp").status_code == 200
        assert client.delete("/api/secrets/erp").status_code == 404
        gone = finished(client, client.post(f"/api/workflows/{flow['id']}/run", json={}).json())
        assert "Kayıtlı şifre bulunamadı: erp" in gone["error"]


def round_trip(store):
    account = f"test:{uuid4().hex[:8]}"
    try:
        store.store(account, "İlk şifre ğüşıöç")
        assert store.load(account) == "İlk şifre ğüşıöç"
        store.store(account, "ikinci")
        assert store.load(account) == "ikinci"
    finally:
        store.remove(account)
    assert store.load(account) is None
    store.remove(account)  # already gone: nothing to do


@pytest.mark.skipif(platform.system() != "Windows", reason="Kimlik Bilgisi Yöneticisi yalnız Windows'ta var")
def test_windows_credential_manager_for_real():
    round_trip(vault_module.WindowsCredentials())


@pytest.mark.skipif(platform.system() != "Darwin" or not os.environ.get("CI"),
                    reason="Anahtar Zinciri testi CI'daki macOS makinesinde çalışır, kişisel zincire dokunmaz")
def test_macos_keychain_for_real():
    round_trip(vault_module.MacKeychain())
