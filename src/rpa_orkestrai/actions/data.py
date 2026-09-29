"""Calculations, text, dates and lists evaluated locally (safe in preview runs too)."""

from __future__ import annotations

import ast
import math
import operator
import re
from datetime import datetime, timedelta
from typing import Any

from ..errors import WorkflowError
from . import handler
from .common import choice, fold, integer, text

EXPRESSION_LIMIT = 1000
FUNCTIONS = {
    "round": lambda value, digits=0: round(_num(value), int(digits)), "abs": lambda value: abs(_num(value)),
    "min": min, "max": max, "int": lambda value: int(_num(value)), "float": lambda value: float(_num(value)),
    "number": lambda value: _num(value), "str": str, "len": len, "sum": lambda values: sum(_num(v) for v in values),
    "floor": lambda value: math.floor(_num(value)), "ceil": lambda value: math.ceil(_num(value)),
}
ARITHMETIC = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
              ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
COMPARISONS = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le,
               ast.Gt: operator.gt, ast.GtE: operator.ge, ast.In: lambda a, b: a in b,
               ast.NotIn: lambda a, b: a not in b}


def parse_number(value: Any) -> float | int | None:
    """42, 12.5, '1.234,56' (Turkish) or '1,234.56' → number; None if not numeric."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    if not isinstance(value, str):
        return None
    raw = value.strip().replace(" ", "").replace(" ", "").replace("₺", "").replace("TL", "")
    if not raw:
        return None
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".") if raw.rfind(",") > raw.rfind(".") else raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".") if raw.count(",") == 1 else raw.replace(",", "")
    elif raw.count(".") > 1:
        raw = raw.replace(".", "")
    try:
        result = float(raw)
    except ValueError:
        return None
    return int(result) if result.is_integer() and "." not in raw and "e" not in raw.lower() else result


def _num(value: Any) -> float | int:
    parsed = parse_number(value)
    if parsed is None:
        raise WorkflowError(f"“{value}” bir sayı değil.")
    return parsed


class _Unknown(Exception):
    """A preview value is involved; the result is unknown, not an error."""


class Evaluator:
    def __init__(self, variables: dict):
        self.variables = variables

    def run(self, expression: str) -> Any:
        from ..engine import UNKNOWN

        try:
            return self._run(expression)
        except _Unknown:
            return UNKNOWN

    def _lookup(self, path: str) -> Any:
        current: Any = self.variables
        for part in path.strip().split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
            else:
                raise WorkflowError(f"İfadede değişken bulunamadı: {path}")
            self._known(current)
        return current

    def _run(self, expression: str) -> Any:
        # ${row.Not} or ${row.Ürün} become placeholders, so any field name works in the expression.
        self.references: dict[str, Any] = {}

        def reference(match: re.Match) -> str:
            name = f"__ref{len(self.references)}"
            self.references[name] = self._lookup(match.group(1))
            return name

        source = re.sub(r"\$\{([^}]+)\}", reference, expression).strip()
        if not source or len(source) > EXPRESSION_LIMIT:
            raise WorkflowError(f"İfade 1–{EXPRESSION_LIMIT} karakter olmalıdır.")
        try:
            tree = ast.parse(source, mode="eval")
        except SyntaxError as exc:
            raise WorkflowError("İfade anlaşılamadı. Örnek: sayac + 1, round(tutar * 1.2, 2), "
                                "adet > 0 and durum == 'Bekliyor'") from exc
        return self.node(tree.body)

    def node(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str, bool, type(None))):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in getattr(self, "references", {}):
                return self.references[node.id]
            if node.id in {"true", "doğru", "dogru"}:
                return True
            if node.id in {"false", "yanlış", "yanlis"}:
                return False
            if node.id not in self.variables:
                raise WorkflowError(f"İfadede değişken bulunamadı: {node.id}")
            return self._known(self.variables[node.id])
        if isinstance(node, ast.Attribute):
            base = self.node(node.value)
            if isinstance(base, dict) and node.attr in base:
                return self._known(base[node.attr])
            raise WorkflowError(f"Alan bulunamadı: {node.attr}")
        if isinstance(node, ast.Subscript):
            base, key = self.node(node.value), self.node(node.slice)
            try:
                return base[int(key) if isinstance(base, (list, str)) else key]
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise WorkflowError(f"Öğe bulunamadı: [{key}]") from exc
        if isinstance(node, (ast.List, ast.Tuple)):
            return [self.node(item) for item in node.elts]
        if isinstance(node, ast.UnaryOp):
            value = self.node(node.operand)
            if isinstance(node.op, ast.Not):
                return not value
            if isinstance(node.op, ast.USub):
                return -_num(value)
            if isinstance(node.op, ast.UAdd):
                return _num(value)
        if isinstance(node, ast.BinOp) and type(node.op) in ARITHMETIC:
            return self.arithmetic(node.op, self.node(node.left), self.node(node.right))
        if isinstance(node, ast.BoolOp):
            values = node.values
            if isinstance(node.op, ast.And):
                result = True
                for item in values:
                    result = self.node(item)
                    if not result:
                        return result
                return result
            result = False
            for item in values:
                result = self.node(item)
                if result:
                    return result
            return result
        if isinstance(node, ast.Compare):
            left = self.node(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = self.node(comparator)
                if type(op) not in COMPARISONS:
                    break
                a, b = left, right
                if not isinstance(op, (ast.In, ast.NotIn, ast.Eq, ast.NotEq)):
                    a, b = _num(a), _num(b)
                elif isinstance(op, (ast.Eq, ast.NotEq)) and parse_number(a) is not None and parse_number(b) is not None \
                        and (isinstance(a, (int, float)) or isinstance(b, (int, float))):
                    a, b = _num(a), _num(b)
                if not COMPARISONS[type(op)](a, b):
                    return False
                left = right
            else:
                return True
        if isinstance(node, ast.IfExp):
            return self.node(node.body) if self.node(node.test) else self.node(node.orelse)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS \
                and not node.keywords:
            try:
                return FUNCTIONS[node.func.id](*[self.node(argument) for argument in node.args])
            except (TypeError, ValueError, OverflowError) as exc:
                raise WorkflowError(f"{node.func.id}() hesaplanamadı.") from exc
        raise WorkflowError("İfadede yalnız sayılar, metinler, değişkenler, + - * / // % **, karşılaştırmalar, "
                            "and/or/not ve round, abs, min, max, int, float, str, len, sum kullanılabilir.")

    @staticmethod
    def _known(value: Any) -> Any:
        if type(value).__name__ == "PreviewValue":
            raise _Unknown()
        return value

    @staticmethod
    def arithmetic(op: ast.AST, left: Any, right: Any) -> Any:
        if isinstance(op, ast.Add) and isinstance(left, str) and isinstance(right, str) \
                and (parse_number(left) is None or parse_number(right) is None):
            return left + right
        if isinstance(op, ast.Add) and isinstance(left, list) and isinstance(right, list):
            return left + right
        a, b = _num(left), _num(right)
        if isinstance(op, ast.Pow) and (abs(b) > 100 or abs(a) > 1e6):
            raise WorkflowError("Üs alma sınırı aşıldı.")
        try:
            result = ARITHMETIC[type(op)](a, b)
        except ZeroDivisionError as exc:
            raise WorkflowError("Sıfıra bölme yapılamaz.") from exc
        if isinstance(result, float) and not math.isfinite(result):
            raise WorkflowError("Hesap sonucu geçerli bir sayı değil.")
        return result


@handler("data.calculate")
def calculate(ctx, p):
    return Evaluator(ctx.variables).run(text(p.get("expression"), "İfade", limit=EXPRESSION_LIMIT))


def upper(value: str, turkish: bool) -> str:
    return (value.replace("i", "İ").replace("ı", "I") if turkish else value).upper()


def lower(value: str, turkish: bool) -> str:
    return (value.replace("I", "ı").replace("İ", "i") if turkish else value).lower()


@handler("text.transform")
def transform(ctx, p):
    value = p.get("text")
    value = "" if value is None else value if isinstance(value, str) else str(value)
    operation = choice(p.get("operation", "trim"), "Metin işlemi", {
        "trim", "upper", "lower", "title", "replace", "split", "substring", "regex_extract", "regex_replace",
        "length", "number", "pad_left", "contains", "starts_with", "ends_with", "lines", "remove_spaces"})
    turkish = p.get("turkish", True) is not False
    find = "" if p.get("find") is None else str(p.get("find"))
    if operation == "trim":
        return value.strip()
    if operation == "remove_spaces":
        return "".join(value.split())
    if operation == "upper":
        return upper(value, turkish)
    if operation == "lower":
        return lower(value, turkish)
    if operation == "title":
        return " ".join(upper(word[:1], turkish) + lower(word[1:], turkish) for word in value.split(" "))
    if operation == "replace":
        return value.replace(find, "" if p.get("replace_with") is None else str(p.get("replace_with")))
    if operation == "split":
        separator = find or ","
        return [part.strip() for part in value.split(separator)]
    if operation == "lines":
        return [line for line in value.splitlines() if line.strip()]
    if operation == "substring":
        start = integer(p.get("start", 0), "Başlangıç", -100_000, 100_000)
        length = p.get("length")
        end = None if length in (None, "") else start + integer(length, "Uzunluk", 0, 100_000)
        return value[start:end]
    if operation in {"regex_extract", "regex_replace"}:
        pattern = text(p.get("pattern"), "Desen (regex)", limit=500)
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            raise WorkflowError(f"Düzenli ifade geçersiz: {exc}") from exc
        if operation == "regex_replace":
            return compiled.sub("" if p.get("replace_with") is None else str(p.get("replace_with")), value)
        matches = list(compiled.finditer(value))
        extracted = [(m.group(1) if compiled.groups else m.group(0)) for m in matches]
        if p.get("all_matches") is True:
            return extracted
        return extracted[0] if extracted else ""
    if operation == "length":
        return len(value)
    if operation == "number":
        parsed = parse_number(value)
        if parsed is None:
            raise WorkflowError(f"“{value}” sayıya çevrilemedi.")
        return parsed
    if operation == "pad_left":
        width = integer(p.get("length", 10), "Uzunluk", 0, 1000)
        return value.rjust(width, (find or "0")[0])
    folded, needle = fold(value), fold(find)
    if operation == "contains":
        return needle in folded
    if operation == "starts_with":
        return folded.startswith(needle)
    return folded.endswith(needle)


DATE_INPUTS = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M",
               "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")
UNITS = {"seconds": 1, "minutes": 60, "hours": 3600, "days": 86400, "weeks": 604800}


def parse_date(value: Any, pattern: str | None = None) -> datetime:
    if isinstance(value, datetime):
        return value
    raw = text(value, "Tarih", limit=64).strip()
    if raw.lower() in {"now", "şimdi", "simdi", "bugün", "bugun", "today"}:
        return datetime.now()
    if pattern:
        try:
            return datetime.strptime(raw, pattern)
        except ValueError as exc:
            raise WorkflowError(f"“{raw}” tarihi {pattern} biçimine uymuyor.") from exc
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass
    for candidate in DATE_INPUTS:
        try:
            return datetime.strptime(raw, candidate)
        except ValueError:
            continue
    raise WorkflowError(f"“{raw}” tarih olarak anlaşılamadı. Örnek: 28.09.2026 veya 2026-09-28 14:30.")


def add_months(moment: datetime, months: int) -> datetime:
    month = moment.month - 1 + months
    year, month = moment.year + month // 12, month % 12 + 1
    days = [31, 29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return moment.replace(year=year, month=month, day=min(moment.day, days[month - 1]))


@handler("data.date")
def date_operation(ctx, p):
    operation = choice(p.get("operation", "now"), "Tarih işlemi", {"now", "format", "add", "difference", "weekday"})
    output_format = text(p.get("format") or "%d.%m.%Y", "Çıktı biçimi", limit=64)
    input_format = (p.get("input_format") or "").strip() or None
    if operation == "now":
        moment = datetime.now()
    else:
        moment = parse_date(p.get("value", "now"), input_format)
    if operation == "add":
        amount = integer(p.get("amount", 1), "Miktar", -100_000, 100_000)
        unit = choice(p.get("unit", "days"), "Birim", {*UNITS, "months", "years"})
        if unit == "months":
            moment = add_months(moment, amount)
        elif unit == "years":
            moment = add_months(moment, amount * 12)
        else:
            moment = moment + timedelta(seconds=amount * UNITS[unit])
    if operation == "difference":
        other = parse_date(p.get("other", "now"), input_format)
        unit = choice(p.get("unit", "days"), "Birim", set(UNITS))
        seconds = (other.replace(tzinfo=None) - moment.replace(tzinfo=None)).total_seconds()
        return math.floor(seconds / UNITS[unit]) if seconds >= 0 else -math.floor(-seconds / UNITS[unit])
    if operation == "weekday":
        return ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"][moment.weekday()]
    try:
        return moment.strftime(output_format)
    except ValueError as exc:
        raise WorkflowError("Tarih çıktı biçimi geçersiz. Örnek: %d.%m.%Y %H:%M") from exc


@handler("data.list")
def list_operation(ctx, p):
    from ..engine import compare

    items = p.get("list")
    if isinstance(items, str):
        items = [part.strip() for part in items.split(",") if part.strip()]
    if not isinstance(items, list):
        raise WorkflowError("Liste değişkeni bir liste olmalıdır (ör. ${rows}).")
    operation = choice(p.get("operation", "length"), "Liste işlemi", {
        "length", "item", "first", "last", "join", "unique", "sort", "reverse", "slice", "filter", "contains",
        "sum", "pluck", "index_of"})
    field = (p.get("field") or "").strip()

    def pick(item):
        if not field:
            return item
        if isinstance(item, dict):
            return item.get(field)
        raise WorkflowError("Alan adı yalnız kayıt (satır) listelerinde kullanılabilir.")

    if operation == "length":
        return len(items)
    if operation in {"first", "last", "item"}:
        if not items:
            raise WorkflowError("Liste boş.")
        index = 0 if operation == "first" else -1 if operation == "last" else integer(p.get("index", 0), "Sıra", -100_000, 100_000)
        try:
            return items[index]
        except IndexError as exc:
            raise WorkflowError(f"Listede {index}. öğe yok; liste {len(items)} öğeli.") from exc
    if operation == "join":
        separator = "" if p.get("separator") is None else str(p.get("separator"))
        return separator.join("" if value is None else str(value) for value in map(pick, items))
    if operation == "unique":
        seen, result = set(), []
        for item in items:
            key = repr(pick(item))
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result
    if operation == "sort":
        def key(item):
            value = pick(item)
            number_value = parse_number(value)
            return (0, number_value, "") if number_value is not None else (1, 0, str(value).casefold())
        return sorted(items, key=key, reverse=p.get("descending") is True)
    if operation == "reverse":
        return list(reversed(items))
    if operation == "slice":
        start = integer(p.get("index", 0), "Başlangıç", -100_000, 100_000)
        count = p.get("count")
        return items[start:] if count in (None, "") else items[start:start + integer(count, "Adet", 0, 100_000)]
    if operation == "filter":
        op = p.get("operator", "eq")
        return [item for item in items if compare(pick(item), op, p.get("value"))]
    if operation == "contains":
        return any(pick(item) == p.get("value") for item in items)
    if operation == "index_of":
        for index, item in enumerate(items):
            if pick(item) == p.get("value"):
                return index
        return -1
    if operation == "sum":
        return sum(_num(pick(item)) for item in items if pick(item) not in (None, ""))
    return [pick(item) for item in items]
