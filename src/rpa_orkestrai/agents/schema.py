"""Boyutu sınırlı, ağ erişimi kapalı JSON Schema 2020-12 doğrulaması."""

from __future__ import annotations

import json

from ..errors import WorkflowError
from .models import validate_json_value

SCHEMA_LIMIT = 16_000
RESULT_LIMIT = 32_000
SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"


def parse_json(text):
    def pairs(items):
        result = {}
        for name, value in items:
            if name in result:
                raise ValueError
            result[name] = value
        return result

    def invalid_constant(value):
        raise ValueError

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)
        return validate_json_value(value, max_bytes=RESULT_LIMIT)
    except (ValueError, TypeError, RecursionError):
        raise WorkflowError("Yapay zekâ yanıtı geçerli JSON değil; sonuç değişkeni yazılmadı.") from None


def compile_schema(schema, *, check=lambda: None):
    if schema is None or schema == "":
        return None
    try:
        from jsonschema import Draft202012Validator, FormatChecker, validators
        from referencing import Registry, Resource
        from referencing.exceptions import NoSuchResource
        from referencing.jsonschema import DRAFT202012
    except ImportError:
        raise WorkflowError("JSON şeması doğrulayıcısı bulunamadı; uygulamayı güncelleyin.") from None

    try:
        validate_json_value(schema, max_bytes=SCHEMA_LIMIT, max_depth=16)
    except ValueError:
        raise WorkflowError("JSON şeması en fazla 16.000 bayt ve 16 iç içe düzey olabilir.") from None
    if type(schema) not in (dict, bool):
        raise WorkflowError("JSON şeması bir nesne veya doğru/yanlış değeri olmalıdır.")
    known = set(Draft202012Validator.VALIDATORS) | {
        "$schema", "$defs", "$anchor", "$dynamicAnchor", "$comment", "title", "description", "default",
        "examples", "deprecated", "readOnly", "writeOnly", "definitions", "contentEncoding", "contentMediaType",
    }
    checker = FormatChecker()
    nodes = 0
    references = []

    def inspect(value, depth=0):
        nonlocal nodes
        check()
        nodes += 1
        if nodes > 256 or depth > 12:
            raise WorkflowError("JSON şeması doğrulama karmaşıklığı sınırını aşıyor.")
        if type(value) is bool:
            return
        if not isinstance(value, dict):
            raise WorkflowError("JSON şemasındaki alt tanım geçersiz.")
        if "pattern" in value or "patternProperties" in value:
            raise WorkflowError("Bu adımda düzenli ifadeli şemalar desteklenmiyor; enum veya uzunluk sınırı kullanın.")
        if "$id" in value:
            raise WorkflowError("JSON şemasında dış kimlik kullanılamaz; yerel $defs tanımlarını kullanın.")
        if set(value) - known:
            raise WorkflowError("JSON şeması desteklenmeyen veya yanlış yazılmış bir kural içeriyor.")
        if "$schema" in value and (depth or value["$schema"] not in {SCHEMA_URI, SCHEMA_URI + "#"}):
            raise WorkflowError("Yalnız JSON Schema Draft 2020-12 desteklenir; alt şemada sürüm seçilemez.")
        for key in ("$ref", "$dynamicRef"):
            if key in value and (not isinstance(value[key], str) or not value[key].startswith("#")):
                raise WorkflowError("JSON şeması yalnız kendi içindeki başvuruları kullanabilir; uzak erişim kapalıdır.")
            if key in value:
                references.append(value[key])
        if "format" in value and (not isinstance(value["format"], str) or value["format"] not in checker.checkers):
            raise WorkflowError("JSON şemasının biçim denetimi bu kurulumda desteklenmiyor.")
        for key in ("properties", "$defs", "definitions", "dependentSchemas"):
            entries = value.get(key, {})
            if not isinstance(entries, dict):
                raise WorkflowError("JSON şemasındaki alan tanımları bir nesne olmalıdır.")
            for entry in entries.values():
                inspect(entry, depth + 1)
        for key in ("allOf", "anyOf", "oneOf", "prefixItems"):
            entries = value.get(key, [])
            if not isinstance(entries, list):
                raise WorkflowError("JSON şemasındaki seçenek tanımları liste olmalıdır.")
            for entry in entries:
                inspect(entry, depth + 1)
        for key in ("items", "contains", "additionalProperties", "unevaluatedProperties", "propertyNames",
                    "not", "if", "then", "else", "unevaluatedItems"):
            if key in value:
                inspect(value[key], depth + 1)

    inspect(schema)
    def refuse_remote(uri):
        raise NoSuchResource(ref=uri)

    registry = Registry(retrieve=refuse_remote)
    try:
        Draft202012Validator.check_schema(schema)
        resolver = registry.resolver_with_root(Resource(schema, DRAFT202012))
        for reference in references:
            if type(resolver.lookup(reference).contents) not in (dict, bool):
                raise ValueError
    except Exception:
        raise WorkflowError("JSON şeması veya yerel başvurusu geçersiz; sağlayıcıya istek gönderilmedi.") from None

    class BoundedValidation:
        def validate(self, value):
            operations = 0

            def bounded(function):
                def validate(validator, rule, instance, subschema):
                    nonlocal operations
                    check()
                    operations += 1
                    if operations > 10_000:
                        raise WorkflowError("JSON sonucu doğrulama karmaşıklığı sınırını aşıyor.")
                    yield from function(validator, rule, instance, subschema)
                return validate

            guarded = validators.extend(Draft202012Validator, {
                key: bounded(function) for key, function in Draft202012Validator.VALIDATORS.items()
            })
            # Strip only the dialect annotation: it is fixed and checked above. This keeps
            # recursive evolves on the guarded validator instead of the unbounded base class.
            local = {key: value for key, value in schema.items() if key != "$schema"} if type(schema) is dict else schema
            validator = guarded(local, registry=registry, format_checker=checker)
            try:
                validator.validate(value)
            except WorkflowError:
                raise
            except Exception:
                # Validation errors can contain the entire input or schema; never expose them.
                raise WorkflowError("Yapay zekâ sonucu JSON şemasına uymuyor; sonuç değişkeni yazılmadı.") from None

    return BoundedValidation()
