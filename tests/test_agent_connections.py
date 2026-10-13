"""API anahtarları yalnız ayrı kasa alanında; firma sınırları tüm işlemlerde korunur."""

import json

import pytest

from rpa_orkestrai.agents.connections import ProviderConnectionStore
from rpa_orkestrai.agents.models import ProviderConnection
from rpa_orkestrai.vault import Vault


class MemorySecrets:
    def __init__(self):
        self.values = {}

    def store(self, account, value):
        self.values[account] = value

    def load(self, account):
        return self.values.get(account)

    def remove(self, account):
        self.values.pop(account, None)


def make_store(tmp_path):
    secret_store = MemorySecrets()
    vault = Vault(tmp_path, store=secret_store, purpose="agent_provider")
    return ProviderConnectionStore(tmp_path, vault=vault), vault, secret_store


def test_provider_keys_are_not_workflow_secrets_or_json_fields(tmp_path):
    store, vault, memory = make_store(tmp_path)
    connection = store.save(ProviderConnection(name="Model", provider="openai", company_id=1), 1)
    key_name = "c" + connection.id
    store.set_key(connection.id, "hidden-api-key", 1)
    assert store.has_key(connection.id, 1)
    assert store.public(connection.id, 1)["has_key"] is True
    assert vault.get(key_name) == "hidden-api-key"
    legacy = Vault(tmp_path, store=memory)
    assert legacy.get(key_name) is None and not legacy.names()
    legacy.set(key_name, "flow-secret")
    assert legacy.get(key_name) == "flow-secret" and vault.get(key_name) == "hidden-api-key"
    for path in tmp_path.glob("*.json"):
        text = path.read_text()
        assert "hidden-api-key" not in text and "flow-secret" not in text
    assert "hidden-api-key" not in json.dumps(store.public(connection.id, 1))


def test_existing_vault_identity_and_index_stay_unchanged(tmp_path):
    memory = MemorySecrets()
    default = Vault(tmp_path, store=memory)
    default.set("erp", "secret")
    assert default.account("erp") == f"{default.scope}:erp"
    assert default.index.name == "secrets.json"
    namespaced = Vault(tmp_path, store=memory, purpose="agent_provider")
    assert namespaced.account("erp") != default.account("erp")
    assert namespaced.index.name != default.index.name and namespaced.get("erp") is None


def test_tenant_isolation_in_every_read_write_key_operation(tmp_path):
    store, _, _ = make_store(tmp_path)
    record = store.save(ProviderConnection(name="A", provider="openai", company_id=1), 1)
    assert store.list(2) == []
    for operation in (lambda: store.get(record.id, 2), lambda: store.public(record.id, 2),
                      lambda: store.has_key(record.id, 2), lambda: store.set_key(record.id, "key", 2),
                      lambda: store.delete_key(record.id, 2), lambda: store.delete(record.id, 2),
                      lambda: store.provider(record.id, 2)):
        with pytest.raises(KeyError):
            operation()
    with pytest.raises(KeyError):
        store.save(record.model_copy(update={"company_id": 2}), 2)
    with pytest.raises(ValueError):
        store.save(record, 2)


def test_key_deletion_and_connection_deletion_clear_system_vault(tmp_path):
    store, _, memory = make_store(tmp_path)
    record = store.save(ProviderConnection(name="A", provider="openai", company_id=1), 1)
    store.set_key(record.id, "key1", 1)
    assert store.delete_key(record.id, 1)
    assert not store.has_key(record.id, 1) and not memory.values
    store.set_key(record.id, "key2", 1)
    store.delete(record.id, 1)
    assert not memory.values and store.list(1) == []


def test_connection_cannot_inject_keys_or_activate_fake_provider(tmp_path):
    store, _, _ = make_store(tmp_path)
    with pytest.raises(ValueError):
        ProviderConnection(name="A", provider="openai", company_id=1, api_key="secret")
    with pytest.raises(ValueError):
        store.save(ProviderConnection(name="A", provider="fake", company_id=1), 1)
    with pytest.raises(ValueError):
        store.save(ProviderConnection(name="A", provider="ollama", company_id=1, base_url="http://192.168.1.1"), 1)


def test_save_uses_loopback_default_and_preserves_company_scope(tmp_path):
    store, _, _ = make_store(tmp_path)
    record = store.save(ProviderConnection(name="Yerel", provider="ollama", company_id=1, model="secilen-model"), 1)
    assert record.base_url == "http://127.0.0.1:11434"
    assert store.public(record.id, 1)["sends_to_cloud"] is False
    assert store.provider(record.id, 1).kind == "ollama"


def test_connection_changes_cannot_reuse_a_key_for_another_provider(tmp_path):
    store, _, _ = make_store(tmp_path)
    record = store.save(ProviderConnection(name="A", provider="openai", company_id=1), 1)
    store.set_key(record.id, "only-for-openai", 1)
    with pytest.raises(ValueError):
        store.save(record.model_copy(update={"provider": "gemini"}), 1)


def test_profile_and_vault_symlink_are_not_followed(tmp_path):
    store, vault, _ = make_store(tmp_path)
    outside = tmp_path / "dis.json"
    outside.write_text("{}")
    try:
        store.path.symlink_to(outside)
    except OSError:
        pytest.skip("Sembolik bağlantı oluşturma izni yok.")
    with pytest.raises(ValueError):
        store.list(1)
    store.path.unlink()
    vault.index.symlink_to(outside)
    with pytest.raises(ValueError):
        store.list(1)
