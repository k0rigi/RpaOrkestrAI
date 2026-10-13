"""Sırları nesneye dönüştürmeden temizleyen, toplam boyutu sınırlı veri görünümü."""

from __future__ import annotations

import json
import math
import re
from urllib.parse import quote

MASK = "[gizlendi]"
OMITTED = "[desteklenmeyen veya fazla büyük veri]"
SECRET_KEYS = frozenset({"sifre", "password", "passwd", "api_key", "apikey", "access_token",
                         "refresh_token", "authorization", "client_secret", "secret"})


class Redactor:
    def __init__(self, secrets=(), *, max_bytes: int = 65_536, max_string: int = 20_000):
        self.max_bytes, self.max_string = max_bytes, max_string
        self._secrets: set[str] = set()
        for secret in secrets:
            self.remember(secret)

    def remember(self, secret) -> None:
        if type(secret) is str and secret:
            self._secrets.update({secret, json.dumps(secret, ensure_ascii=False)[1:-1],
                                  json.dumps(secret, ensure_ascii=True)[1:-1], quote(secret, safe="")})

    def merge(self, other: Redactor) -> None:
        """Copy in-memory secrets only; never expose the dictionary through run records."""
        if not isinstance(other, Redactor):
            raise TypeError("Gizli veri temizleyicisi bekleniyor.")
        self._secrets.update(other._secrets)

    def text(self, value: str) -> str:
        if not self._secrets:
            return value
        # Existing markers remain stable and newly inserted markers are not matched again.
        expression = "|".join(re.escape(secret) for secret in sorted(self._secrets, key=len, reverse=True))
        return MASK.join(re.sub(expression, lambda match: MASK, part) for part in value.split(MASK))

    def sanitize(self, value):
        remaining = self.max_bytes
        seen: set[int] = set()

        def visit(item, depth=0):
            nonlocal remaining
            if depth > 20 or remaining < 32:
                return OMITTED
            remaining -= 8
            if item is None or type(item) is bool:
                return item
            if type(item) in (int, float):
                if type(item) is float and not math.isfinite(item):
                    return OMITTED
                return MASK if str(item) in self._secrets else item
            if type(item) is str:
                # Redact the entire value before taking a prefix; otherwise a partial secret leaks.
                clean = self.text(item)
                limit = min(self.max_string, max(0, remaining // 4))
                clean = clean[:limit] + ("…" if len(clean) > limit else "")
                remaining -= len(clean.encode("utf-8"))
                return clean
            # In particular, never iterate/str/repr a SecretVariables dict subclass.
            if type(item) not in (dict, list, tuple):
                return MASK
            if id(item) in seen:
                return OMITTED
            seen.add(id(item))
            try:
                if type(item) in (list, tuple):
                    result = []
                    for part in item:
                        if remaining < 32:
                            result.append(OMITTED)
                            break
                        result.append(visit(part, depth + 1))
                    return result
                result = {}
                for key, part in item.items():
                    if remaining < 32:
                        result["_sinir"] = OMITTED
                        break
                    if type(key) is not str:
                        continue
                    clean_key = self.text(key)[:200]
                    remaining -= len(clean_key.encode("utf-8")) + 4
                    result[clean_key] = MASK if key.casefold() in SECRET_KEYS else visit(part, depth + 1)
                return result
            finally:
                seen.remove(id(item))

        result = visit(value)
        if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")) > self.max_bytes:
            return OMITTED
        return result


def sanitize(value, secrets=(), *, max_bytes: int = 65_536, max_string: int = 20_000):
    return Redactor(secrets, max_bytes=max_bytes, max_string=max_string).sanitize(value)
