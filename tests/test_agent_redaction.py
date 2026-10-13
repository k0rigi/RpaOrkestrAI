"""Hiçbir gizli nesne okunmaz; temizleme kırpma ve dışa aktarımdan önce yapılır."""

import json

from rpa_orkestrai.agents.redaction import MASK, Redactor, sanitize


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
