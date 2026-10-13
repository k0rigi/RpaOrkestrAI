"""Hiçbir gizli nesne okunmaz; temizleme kırpma ve dışa aktarımdan önce yapılır."""

import json

import pytest

from rpa_orkestrai.agents.redaction import MASK, Redactor, sanitize
from rpa_orkestrai.vault import Vault, VaultError


def test_secret_values_keys_short_passwords_and_escaped_forms():
    secret = 'Türkçe-"anahtar"'
    redactor = Redactor([secret, "xy"])
    value = {"ordinary": f"Başlangıç {secret} son", "password": "bilinmeyen",
             "list": ["xy", {secret: json.dumps(secret, ensure_ascii=True)[1:-1]}]}
    encoded = json.dumps(redactor.sanitize(value), ensure_ascii=False)
    assert secret not in encoded and "bilinmeyen" not in encoded and "xy" not in encoded
    assert MASK in encoded


def test_secret_dict_subclasses_and_unknown_objects_are_never_accessed():
    class Trap(dict):
        def items(self):
            raise AssertionError("Gizli nesne okunmamalı")

        def __repr__(self):
            raise AssertionError("Gizli nesne gösterilmemeli")

        def __str__(self):
            raise AssertionError("Gizli nesne gösterilmemeli")

    class Opaque:
        def __str__(self):
            raise AssertionError("Nesne gösterilmemeli")

    assert sanitize({"alias": Trap(), "object": Opaque()}) == {"alias": MASK, "object": MASK}


def test_redaction_precedes_prefix_truncation_and_total_budget():
    secret = "1234567890-SECRET"
    result = sanitize("prefix-" + secret, [secret], max_string=12)
    assert "12345" not in result
    result = sanitize({f"item{i}": "a" * 5000 for i in range(200)}, max_bytes=2000)
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= 2000


def test_recursive_and_nonfinite_values_are_safe_json():
    value = [float("inf")]
    value.append(value)
    json.dumps(sanitize(value), allow_nan=False)


def test_runtime_can_merge_newly_discovered_secrets_without_exporting_them():
    source = Redactor(["gizli-123"])
    destination = Redactor()
    destination.merge(source)
    assert destination.sanitize({"value": "gizli-123"}) == {"value": MASK}


def test_short_secret_masking_is_idempotent_even_inside_mask_word():
    redactor = Redactor(["i", "g", "secret"])
    masked = redactor.text("gizli secret")
    assert redactor.text(masked) == masked
    assert redactor.text(redactor.text(masked)) == masked


def test_raw_metadata_validation_checks_markers_and_encoded_secrets_without_mutating_them():
    redactor = Redactor(["[gizlendi]", "özel anahtar"])
    for value in ("[gizlendi]", "ön-özel anahtar-son", "%C3%B6zel%20anahtar", r"\u00f6zel anahtar"):
        assert redactor.contains_secret(value)
    assert not redactor.contains_secret("güvenli model")
    assert redactor.text("[gizlendi]") == "[gizlendi]"


@pytest.fixture
def memory_vault(tmp_path, monkeypatch):
    class MemoryStore:
        def __init__(self):
            self.values = {}

        def store(self, account, value):
            self.values[account] = value

        def load(self, account):
            return self.values.get(account)

    memory = MemoryStore()
    monkeypatch.setattr("rpa_orkestrai.vault.system_store", lambda: memory)
    return Vault(tmp_path)


def test_registered_vault_values_include_short_passwords_and_keep_workspace_scope(memory_vault):
    assert memory_vault.secrets_for_redaction() == []
    memory_vault.set("long", "registered-secret")
    memory_vault.set("short", "i")
    provider = Vault(memory_vault.index.parent, purpose="agent_provider")
    provider.set("long", "separate-provider-secret")
    assert memory_vault.secrets_for_redaction() == ["registered-secret", "i"]
    assert provider.secrets_for_redaction() == ["separate-provider-secret"]
    redactor = Redactor(memory_vault.secrets_for_redaction())
    assert redactor.text("registered-secret") == MASK
    assert redactor.text("i") == MASK


@pytest.mark.parametrize("mode", ["malformed", "shape", "name", "missing", "failed", "large", "symlink", "unreadable"])
def test_vault_masking_fails_closed_without_leaking_store_error(memory_vault, monkeypatch, mode):
    memory_vault.set("registered", "registered-secret")
    if mode == "malformed":
        memory_vault.index.write_text("not-json")
    elif mode == "shape":
        memory_vault.index.write_text('{"names": []}')
    elif mode == "name":
        memory_vault.index.write_text('{"names": {"../private": {}}}')
    elif mode == "missing":
        memory_vault.store.values.clear()
    elif mode == "failed":
        def failure(account):
            raise RuntimeError("registered-secret")
        monkeypatch.setattr(memory_vault.store, "load", failure)
    elif mode == "large":
        memory_vault.index.write_bytes(b" " * (256 * 1024 + 1))
    elif mode == "symlink":
        target = memory_vault.index.with_suffix(".other")
        memory_vault.index.rename(target)
        try:
            memory_vault.index.symlink_to(target)
        except OSError:
            pytest.skip("Bu ortamda sembolik bağlantı oluşturma izni yok.")
    elif mode == "unreadable":
        def failed_open(*args, **kwargs):
            raise PermissionError("registered-secret")
        monkeypatch.setattr(type(memory_vault.index), "open", failed_open)
    with pytest.raises(VaultError) as caught:
        memory_vault.secrets_for_redaction()
    assert "registered-secret" not in str(caught.value)
