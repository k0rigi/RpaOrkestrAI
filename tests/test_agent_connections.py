"""API anahtarları yalnız ayrı kasa alanında; firma sınırları tüm işlemlerde korunur."""

import json

import pytest

from rpa_orkestrai.agents.connections import ProviderConnectionStore
from rpa_orkestrai.agents.models import ProviderConnection
from rpa_orkestrai.agents.providers import ProviderError
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


@pytest.mark.parametrize("field,secret,metadata", [
    ("name", "private-provider-key", "Bağlantı private-provider-key"),
    ("model", "private-provider-key", "model-private-provider-key"),
    ("base_url", "34567", "http://127.0.0.1:34567"),
    ("name", "özel-anahtar", "Bağlantı %C3%B6zel-anahtar"),
    ("name", "[gizlendi]", "Bağlantı [gizlendi]"),
])
def test_registered_keys_cannot_enter_new_or_updated_metadata(tmp_path, field, secret, metadata):
    store, _, _ = make_store(tmp_path)
    record = store.save(ProviderConnection(name="Yerel", provider="ollama", model="deneme", company_id=1), 1)
    store.set_key(record.id, secret, 1)
    original = store.path.read_bytes()
    for candidate in (record.model_copy(update={field: metadata}),
                      ProviderConnection(name="Yeni", provider="ollama", company_id=1).model_copy(
                          update={field: metadata})):
        with pytest.raises(ValueError) as error:
            store.save(candidate, 1)
        assert secret not in str(error.value)
        assert store.path.read_bytes() == original
    assert secret not in json.dumps(store.public(record.id, 1), ensure_ascii=False)


@pytest.mark.parametrize("field,secret,metadata", [
    ("name", "later-provider-key", "later-provider-key"),
    ("model", "later-provider-key", "prefix-later-provider-key"),
    ("base_url", "34567", "http://127.0.0.1:34567"),
])
def test_key_registration_rejects_value_already_present_in_any_metadata(tmp_path, field, secret, metadata):
    store, vault, _ = make_store(tmp_path)
    target = store.save(ProviderConnection(name="Anahtar", provider="openai", company_id=1), 1)
    other = ProviderConnection(name="Başka", provider="ollama", company_id=2).model_copy(update={field: metadata})
    store.save(other, 2)
    with pytest.raises(ValueError) as error:
        store.set_key(target.id, secret, 1)
    assert secret not in str(error.value)
    assert not store.has_key(target.id, 1)
    assert vault.get("c" + target.id) is None


def test_rotation_keeps_previous_key_when_new_key_collides_with_metadata(tmp_path):
    store, vault, _ = make_store(tmp_path)
    record = store.save(ProviderConnection(name="candidate-key", provider="openai", company_id=1), 1)
    store.set_key(record.id, "original-secret", 1)
    with pytest.raises(ValueError):
        store.set_key(record.id, "candidate-key", 1)
    assert vault.get("c" + record.id) == "original-secret"


def test_other_company_secret_is_protected_without_exposing_its_record(tmp_path):
    store, _, _ = make_store(tmp_path)
    original = store.save(ProviderConnection(name="Kayıt", provider="openai", company_id=1), 1)
    store.set_key(original.id, "cross-company-private-key", 1)
    assert store.list(2) == []
    with pytest.raises(ValueError):
        store.save(ProviderConnection(name="cross-company-private-key", provider="ollama", company_id=2), 2)
    assert store.list(2) == []


@pytest.mark.parametrize("failure", ["missing", "unreadable"])
def test_registered_but_unreadable_keys_fail_closed_before_save_public_or_provider(tmp_path, monkeypatch, failure):
    store, _, memory = make_store(tmp_path)
    record = store.save(ProviderConnection(name="Yerel", provider="ollama", company_id=1), 1)
    store.set_key(record.id, "registered-private-key", 1)
    original = store.path.read_bytes()
    if failure == "missing":
        memory.values.clear()
    else:
        def fail(_):
            raise RuntimeError("registered-private-key")
        monkeypatch.setattr(memory, "load", fail)
    for operation in (lambda: store.secrets(1), lambda: store.public(record.id, 1),
                      lambda: store.save(record.model_copy(update={"name": "Yeni"}), 1),
                      lambda: store.save(ProviderConnection(name="Yeni", provider="openai", company_id=1), 1),
                      lambda: store.provider(record.id, 1)):
        with pytest.raises((ValueError, ProviderError)) as error:
            operation()
        assert "registered-private-key" not in str(error.value)
        assert store.path.read_bytes() == original


@pytest.mark.parametrize("metadata", ["{}", "[]", "bozuk", '{"names":{"bad-name":{}}}',
                                    '{"names":[]}', '{"names":{"valid":null}}'])
def test_corrupt_vault_index_never_becomes_an_empty_secret_list(tmp_path, metadata):
    store, vault, _ = make_store(tmp_path)
    record = store.save(ProviderConnection(name="Yerel", provider="ollama", company_id=1), 1)
    vault.index.write_text(metadata, encoding="utf-8")
    for operation in (lambda: store.secrets(1), lambda: store.public(record.id, 1),
                      lambda: store.save(record, 1)):
        with pytest.raises(ValueError):
            operation()


@pytest.mark.parametrize("recovery", ["replace", "remove", "delete"])
def test_missing_key_can_be_explicitly_replaced_or_removed(tmp_path, recovery):
    store, vault, memory = make_store(tmp_path)
    record = store.save(ProviderConnection(name="Yerel", provider="ollama", company_id=1), 1)
    store.set_key(record.id, "lost-key", 1)
    memory.values.clear()
    if recovery == "replace":
        store.set_key(record.id, "replacement-key", 1)
        assert vault.get("c" + record.id) == "replacement-key"
        assert store.public(record.id, 1)["has_key"] is True
    elif recovery == "remove":
        assert store.delete_key(record.id, 1)
        assert store.public(record.id, 1)["has_key"] is False
    else:
        store.delete(record.id, 1)
        assert store.list(1) == []


@pytest.mark.parametrize("provider", ["ollama", "shared"])
def test_intentionally_keyless_profiles_do_not_require_system_vault(tmp_path, monkeypatch, provider):
    store, _, memory = make_store(tmp_path)
    monkeypatch.setattr(memory, "load", lambda _: pytest.fail("Anahtarsız bağlantı kasayı okumamalı."))
    record = store.save(ProviderConnection(name="Anahtarsız", provider=provider, company_id=1), 1)
    assert store.public(record.id, 1)["has_key"] is False
    assert store.secrets(1) == []


def test_existing_unsafe_metadata_is_not_returned_or_used_for_provider(tmp_path):
    store, _, _ = make_store(tmp_path)
    record = store.save(ProviderConnection(name="Yerel", provider="ollama", company_id=1), 1)
    store.set_key(record.id, "stored-private-key", 1)
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    raw["connections"][0]["name"] = "stored-private-key"
    store.path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        store.public(record.id, 1)
    with pytest.raises(ProviderError):
        store.provider(record.id, 1)
    store.save(record, 1)
    assert "stored-private-key" not in store.path.read_text(encoding="utf-8")
    assert store.public(record.id, 1)["name"] == "Yerel"


def test_test_connection_model_is_checked_before_any_provider_or_network_call(tmp_path, monkeypatch):
    store, _, _ = make_store(tmp_path)
    record = store.save(ProviderConnection(name="Yerel", provider="ollama", model="safe-model", company_id=1), 1)
    store.set_key(record.id, "test-private-key", 1)
    monkeypatch.setattr(store, "provider", lambda *a, **kw: pytest.fail("Sağlayıcıya erişilmemeli."))
    with pytest.raises(ValueError) as error:
        store.test_connection(record.id, 1, model="test-private-key")
    assert "test-private-key" not in str(error.value)


def test_repairing_one_missing_key_does_not_ignore_another_missing_key(tmp_path):
    store, _, memory = make_store(tmp_path)
    first = store.save(ProviderConnection(name="Bir", provider="ollama", company_id=1), 1)
    second = store.save(ProviderConnection(name="İki", provider="ollama", company_id=1), 1)
    for record in (first, second):
        store.set_key(record.id, "old-private-key", 1)
    memory.values.clear()
    with pytest.raises(ValueError):
        store.set_key(first.id, "replacement-key", 1)
    assert memory.values == {}
    assert store.delete_key(second.id, 1)
    store.set_key(first.id, "replacement-key", 1)
    assert store.secrets(1) == ["replacement-key"]


@pytest.mark.parametrize("operation", ["store", "remove"])
def test_system_vault_write_delete_errors_do_not_echo_key(tmp_path, monkeypatch, operation):
    store, _, memory = make_store(tmp_path)
    record = store.save(ProviderConnection(name="Yerel", provider="ollama", company_id=1), 1)
    store.set_key(record.id, "private-key-in-system-error", 1)

    def fail(*args):
        raise RuntimeError("private-key-in-system-error")

    monkeypatch.setattr(memory, operation, fail)
    with pytest.raises(ValueError) as error:
        if operation == "store":
            store.set_key(record.id, "replacement-key", 1)
        else:
            store.delete_key(record.id, 1)
    assert "private-key-in-system-error" not in str(error.value)


def test_unrelated_metadata_update_does_not_rewrite_known_unsafe_legacy_value(tmp_path):
    store, _, _ = make_store(tmp_path)
    first = store.save(ProviderConnection(name="Bir", provider="ollama", company_id=1), 1)
    second = store.save(ProviderConnection(name="İki", provider="ollama", company_id=1), 1)
    store.set_key(first.id, "private-key-in-legacy-record", 1)
    raw = json.loads(store.path.read_text(encoding="utf-8"))
    raw["connections"][0]["model"] = "private-key-in-legacy-record"
    store.path.write_text(json.dumps(raw), encoding="utf-8")
    original = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.save(second.model_copy(update={"name": "Yeni"}), 1)
    assert store.path.read_bytes() == original
    store.save(first, 1)
    assert "private-key-in-legacy-record" not in store.path.read_text(encoding="utf-8")
