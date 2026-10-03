"""Bounded workflow execution with cooperative cancellation and isolated runs."""

from __future__ import annotations

import ast
import csv
import difflib
import json
import math
import operator
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Callable

from .catalog import BY_TYPE, EXTERNAL_PREFIXES, LOCATABLE, LOOPS, TEST_PREPARE, defaults
from .config import Settings
from .desktop.windows import WindowError, validate_selector
from .errors import BreakLoop, Cancelled, ContinueLoop, JumpTo, StopWorkflow, WorkflowError
from .models import Artifact, Event, Run, Step, Workflow, now
from .storage import Store

MAX_EXECUTED_STEPS = 1_000_000
MAX_LOOP_ITEMS = 100_000
SUB_WORKFLOW_DEPTH = 5
CONTROL_SIGNALS = (BreakLoop, ContinueLoop, JumpTo, StopWorkflow, Cancelled, InterruptedError)
ARTIFACT_TYPES = {".csv": "text/csv; charset=utf-8", ".png": "image/png", ".txt": "text/plain; charset=utf-8",
                  ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def describe_error(exc: BaseException) -> str:
    """User-facing text for a failed step; never includes stack traces or credentials."""
    if isinstance(exc, (WorkflowError, WindowError)):
        return str(exc)
    if isinstance(exc, ImportError):
        return ("Gerekli otomasyon paketi veya sistem sürücüsü yüklenemedi. "
                "Kurulum rehberini ve rpa-studio doctor çıktısını kontrol edin.")
    if isinstance(exc, TimeoutError):
        return "İşlem zaman aşımına uğradı. Hedef öğeyi, bağlantıyı ve bekleme süresini kontrol edin."
    if type(exc).__name__ == "FailSafeException":
        return "Fare köşeye taşındı; PyAutoGUI acil durdurma devreye girdi."
    return (f"İşlem tamamlanamadı ({type(exc).__name__}). Son başlayan adımın parametrelerini, "
            "bağlantı ayarlarını ve sistem izinlerini kontrol edin.")




class PreviewValue:
    """An external result that is unknown in a dry run, never fabricated."""


UNKNOWN = PreviewValue()
REFERENCE = re.compile(r"\$\{([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)\}")
VARIABLE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


NAME_RULE = ("Ad harfle başlamalı; yalnız İngilizce harf, rakam ve alt çizgi içerebilir "
             "(boşluk ve ç, ğ, ı, ö, ş, ü olmaz). Örnek: erp_window")


def variable_name(value: Any) -> str:
    if not isinstance(value, str) or not VARIABLE.fullmatch(value):
        raise WorkflowError(f"Değişken adı geçersiz. {NAME_RULE}")
    return value


def resolve(value: Any, variables: dict[str, Any]) -> Any:
    def lookup(path: str) -> Any:
        current: Any = variables
        for part in path.split("."):
            if isinstance(current, PreviewValue):
                return UNKNOWN
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
                current = current[int(part)]
            else:
                raise WorkflowError(f"Değişken bulunamadı: {path}. Bu değeri üreten adım (ör. Değişken ata veya "
                                    "bir okuma adımı) daha önce çalışmalı ya da adı doğru yazılmalıdır.")
        return current

    if isinstance(value, str):
        match = REFERENCE.fullmatch(value)
        if match:
            return lookup(match.group(1))
        matches = list(REFERENCE.finditer(value))
        if any(isinstance(lookup(m.group(1)), PreviewValue) for m in matches):
            return UNKNOWN
        return REFERENCE.sub(lambda m: str(lookup(m.group(1))), value)
    if isinstance(value, list):
        return [resolve(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: resolve(item, variables) for key, item in value.items()}
    return value


def has_unknown(value: Any) -> bool:
    if isinstance(value, PreviewValue):
        return True
    if isinstance(value, dict):
        return any(has_unknown(v) for v in value.values())
    if isinstance(value, list):
        return any(has_unknown(v) for v in value)
    return False


def shown_for(expected: Any, actual: Any) -> bool:
    return actual in expected if isinstance(expected, list) else actual == expected


def active_fields(action: str, parameters: dict) -> list[dict]:
    return [f for f in BY_TYPE[action]["fields"] if not (
        action in {"control.if", "control.while"} and f["name"] == "right"
        and parameters.get("operator") in ("empty", "not_empty", "truthy")
    ) and all(
        shown_for(value, parameters.get(key)) for key, value in f.get("visible_when", {}).items()
    )]


def step_titles(steps: list[Step]) -> dict[str, str]:
    """The name each step shows in the editor, for messages about Adıma git."""
    titles: dict[str, str] = {}

    def walk(items: list[Step]) -> None:
        for item in items:
            titles[item.id] = item.title or BY_TYPE.get(item.action, {}).get("label", item.action)
            walk(item.children)
            walk(item.otherwise)

    walk(steps)
    return titles


def step_places(steps: list[Step]) -> dict[str, list[tuple[Step, str]]]:
    """For every step: the blocks around it, outermost first, as (block step, branch)."""
    places: dict[str, list[tuple[Step, str]]] = {}

    def walk(items: list[Step], around: list[tuple[Step, str]]) -> None:
        for item in items:
            places[item.id] = around
            for branch in ("children", "otherwise"):
                walk(getattr(item, branch), [*around, (item, branch)])

    walk(steps, [])
    return places


def jump_problem(source: str, target: str, places: dict[str, list[tuple[Step, str]]]) -> str | None:
    """Why Adıma git from one step to another cannot work, or None when it can."""
    if target not in places:
        return "gidilecek adım akışta yok; bağlantıyı yeniden seçin."
    if target == source:
        return "bir adım kendisine bağlanamaz."
    inside = {(block.id, branch) for block, branch in places[source]}
    for block, branch in places[target]:
        if (block.id, branch) in inside:
            continue
        # A condition's branch or a Dene block can be entered anywhere; a loop has no current row
        # until its own box starts it, and Hata olursa runs only after an error.
        if block.action in LOOPS:
            name = block.title or BY_TYPE[block.action]["label"]
            return (f"«{name}» döngüsünün içindeki bir adıma döngünün dışından gidilemez; "
                    "döngü kutusuna bağlayın.")
        if block.action == "control.try" and branch == "otherwise":
            return "Hata olursa dalındaki bir adıma bu dalın dışından gidilemez."
    return None


def jump_path(target: str, steps: list[Step]) -> list[tuple[str | None, int]] | None:
    """Where Adıma git continues within this list: [(None, index), (branch, index), …] or None."""
    for index, item in enumerate(steps):
        if item.id == target:
            return [(None, index)]
        for branch in ("children", "otherwise"):
            if item.action in LOOPS or (item.action == "control.try" and branch == "otherwise"):
                continue  # entered only by the loop itself or by an error (see jump_problem)
            inner = jump_path(target, getattr(item, branch))
            if inner is not None:
                return [(None, index), (branch, inner[0][1]), *inner[1:]]
    return None


def validate_workflow(workflow: Workflow, *, ready: bool = True, in_loop: bool = False,
                      jumps: bool = True) -> None:
    places = step_places(workflow.steps) if ready and jumps else {}

    def walk(steps: list[Step], in_loop: bool = False) -> None:
        for step in steps:
            if step.action not in BY_TYPE:
                raise WorkflowError(f"Bilinmeyen adım türü: {step.action}")
            fields = BY_TYPE[step.action]["fields"]
            allowed = {f["name"] for f in fields}
            if set(step.params) - allowed:
                raise WorkflowError(f"{step.title or step.action}: bilinmeyen parametre.")
            if ready:
                parameters = {**defaults(step.action), **step.params}
                for f in active_fields(step.action, parameters):
                    value = parameters.get(f["name"])
                    if f.get("required") and (value is None or value == ""):
                        raise WorkflowError(f"{step.title or step.action}: {f['label']} gereklidir.")
                    if isinstance(value, str) and REFERENCE.search(value):
                        continue
                    if f["type"] == "select" and str(value) not in {str(o["value"]) for o in f["options"]}:
                        raise WorkflowError(f"{step.title or step.action}: {f['label']} seçimi geçersiz.")
                    if f["type"] == "boolean" and type(value) is not bool:
                        raise WorkflowError(f"{step.title or step.action}: {f['label']} doğru/yanlış olmalıdır.")
                    if f["type"] == "number" and value is not None:
                        if (isinstance(value, bool) or not isinstance(value, (int, float))
                                or not math.isfinite(value) or value < f.get("min", -math.inf)
                                or value > f.get("max", math.inf)):
                            raise WorkflowError(f"{step.title or step.action}: {f['label']} geçerli aralıkta olmalıdır.")
                for key in ("output", "name", "item_name", "error_name"):
                    if key in parameters and not (isinstance(parameters[key], str)
                                                  and VARIABLE.fullmatch(parameters[key])):
                        label = next((f["label"] for f in fields if f["name"] == key), key)
                        raise WorkflowError(
                            f"{step.title or BY_TYPE[step.action]['label']}: “{label}” alanına yalnız bir ad yazın; "
                            f"şu an “{str(parameters[key])[:60]}” yazıyor. {NAME_RULE}")
                if parameters.get("item_name") == "loop_index":
                    raise WorkflowError("loop_index döngü sayacı için ayrılmıştır; başka bir öğe adı seçin.")
                if step.action in {"control.break", "control.continue"} and not in_loop:
                    raise WorkflowError(f"{step.title or BY_TYPE[step.action]['label']}: yalnız bir döngünün "
                                        "(Her satır için, Tekrarla, Koşul sürdükçe) içinde kullanılabilir.")
                if step.action == "control.goto" and jumps and isinstance(parameters.get("target"), str):
                    problem = jump_problem(step.id, parameters["target"], places)
                    if problem:
                        raise WorkflowError(f"{step.title or BY_TYPE[step.action]['label']}: {problem}")
                if step.action == "desktop.find_window":
                    try:
                        validate_selector(parameters["application"], parameters["title"],
                                          parameters["match"], parameters["timeout"])
                        if parameters["on_missing"] not in {"stop", "continue"}:
                            raise WindowError("Pencere bulunamadığında yapılacak işlem geçersiz.")
                    except WindowError as exc:
                        raise WorkflowError(str(exc)) from exc
            nested = in_loop or step.action in LOOPS
            walk(step.children, nested)
            walk(step.otherwise, in_loop)

    walk(workflow.steps, in_loop)
    if ready and not workflow.steps:
        raise WorkflowError("Çalıştırmadan önce akışa en az bir adım ekleyin.")


def compare(left: Any, op: str, right: Any) -> bool:
    if not isinstance(op, str):
        raise WorkflowError("Karşılaştırma işleci geçerli bir metin olmalıdır.")
    empty = left is None or isinstance(left, str) and not left.strip()
    if op == "empty":
        return empty
    if op == "not_empty":
        return not empty
    if op == "empty_or_eq":
        return empty or left == right
    if op == "one_of":
        if not isinstance(right, list) or len(right) > 1000:
            raise WorkflowError("Listedeki değerlerden biri karşılaştırması için en fazla 1000 değerlik liste kullanın.")
        return left in right
    if op == "contains":
        from .actions.common import fold

        return fold(right) in fold(left)
    if op == "truthy":
        return bool(left)
    operators = {"eq": operator.eq, "ne": operator.ne, "gt": operator.gt,
                 "gte": operator.ge, "lt": operator.lt, "lte": operator.le}
    if op not in operators:
        raise WorkflowError("Geçersiz karşılaştırma işleci.")
    try:
        return bool(operators[op](left, right))
    except TypeError as exc:
        raise WorkflowError("Karşılaştırılan değerlerin türleri uyumlu değil.") from exc


def csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    if isinstance(value, str) and (value.lstrip().startswith(("=", "+", "-", "@"))
                                   or value.startswith(("\t", "\r", "\n"))):
        return "'" + value
    return value


def snapshot(variables: dict[str, Any], limit: int = 200_000) -> dict[str, Any]:
    """JSON-safe copy of variables for a step test; large values are shortened."""
    from .actions.common import jsonable

    result = {}
    for name, value in variables.items():
        if name == "sistem":
            continue
        if isinstance(value, PreviewValue):
            result[name] = "(önizlemede bilinmiyor)"
            continue
        copied = jsonable(value)
        encoded = json.dumps(copied, ensure_ascii=False)
        result[name] = copied if len(encoded) <= limit // 4 else encoded[:2000] + " …"
    return result


class Executor:
    def __init__(self, settings: Settings, store: Store, run: Run, cancel: threading.Event,
                 save: Callable[[], None], variables: dict[str, Any] | None = None):
        self.settings, self.store, self.run = settings, store, run
        self.cancel, self._save = cancel, save
        self.config = settings.snapshot()
        self.variables: dict[str, Any] = dict(variables or {})
        if "sistem" not in self.variables:
            from .actions.environment import system_variables

            self.variables["sistem"] = system_variables()
        self.held_keys: set[str] = set()
        self.call_stack: list[str] = []
        self.locate = False  # a test that only shows where the step points
        from .connections import Connections

        self.connections = Connections(settings.data_dir, settings)
        self._secrets = [value for value in (self.config.get("database_url"), self.config.get("google_credentials_path"))
                         if value] + self.connections.secrets()
        self._last_save = 0.0
        self.resources = ExitStack()
        self._browser: Any = None
        self._desktop: Any = None
        self._windows: Any = None
        self._databases: dict[str, Any] = {}
        self._sheets: dict[tuple[str, str], Any] = {}
        self.executed = 0
        self._deadlines: list[float] = []
        # Adıma git: step names for messages, the loops now running with their turn, and how often
        # each jump was used in the current turn.
        self.titles: dict[str, str] = {}
        self.turns: list[list] = []
        self.jumps: dict[str, tuple[tuple, int]] = {}

    def check_cancelled(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()
        if self._deadlines and time.monotonic() >= min(self._deadlines):
            raise WorkflowError("Koşullu döngünün süre sınırı doldu; işlem durduruldu.")

    def log(self, message: str, *, level: str = "info", step_id: str | None = None) -> None:
        # Never persist configured credentials, even when accidentally used in a log step.
        for secret in self._secrets:
            message = message.replace(secret, "[gizlendi]")
        message = re.sub(r"(\w+://)[^\s/@]+:[^\s/@]+@", r"\1[gizlendi]@", message)
        self.run.events.append(Event(message=message[:2000], level=level, step_id=step_id))
        self.run.events = self.run.events[-1000:]
        # Long loops log every step; keep the run file current without rewriting it each time.
        if level != "info" or time.monotonic() - self._last_save >= 0.5:
            self.save()

    def save(self) -> None:
        self._last_save = time.monotonic()
        self._save()

    def wait(self, seconds: float) -> None:
        if seconds > 0 and self.cancel.wait(seconds):
            raise Cancelled()

    def save_artifact(self, name: str, data: bytes) -> Path:
        """Store a file (e.g. a screenshot) among the run's downloadable outputs."""
        suffix = Path(name).suffix.lower()
        if suffix not in ARTIFACT_TYPES or not re.fullmatch(r"[^/\\\x00-\x1f<>:\"|?*]{1,120}", name):
            raise WorkflowError("Çıktı dosya adı yol içermemeli ve .png, .csv, .txt veya .xlsx uzantılı olmalıdır.")
        if len(self.run.artifacts) >= 100:
            raise WorkflowError("Bir çalışma en fazla 100 çıktı üretebilir.")
        artifact = Artifact(name=name, department=self.run.department, rows=0)
        artifact.url = f"/api/runs/{self.run.id}/artifacts/{artifact.id}"
        destination = self.store.root / "artifacts" / self.run.id
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / f"{artifact.id}{suffix}"
        target.write_bytes(data)
        self.run.artifacts.append(artifact)
        self.save()
        return target

    def execute(self, workflow: Workflow) -> None:
        self.titles = {**step_titles(workflow.steps), **self.titles}
        self.call_stack.append(workflow.id)
        try:
            with self.resources:
                self.steps(workflow.steps)
                self.check_cancelled()
        finally:
            self.release_keys()

    def prepare(self, entries: list[dict]) -> None:
        """Before a single-step test: obtain the values the step needs from earlier read-only steps."""
        for entry in entries:
            self.check_cancelled()
            step, name, label = entry["step"], entry["variable"], entry["title"]
            try:
                if entry["kind"] == "step":
                    self.log(f"Hazırlık: {label} çalıştırılıyor (${{{name}}} için).")
                    self.steps([step.model_copy(update={"children": [], "otherwise": []})])
                elif entry["kind"] == "item":
                    items = resolve({**defaults(step.action), **step.params}["items"], self.variables)
                    if has_unknown(items):
                        self.variables[name] = UNKNOWN
                        continue
                    if not isinstance(items, list) or not items:
                        raise WorkflowError("listede hiç öğe yok; test için en az bir satır gerekir.")
                    self.variables[name] = items[0]
                    self.variables.setdefault("loop_index", 0)
                    self.log(f"Hazırlık: {label} listesindeki ilk öğe ${{{name}}} olarak kullanılıyor "
                             f"({len(items)} öğe var).")
                elif entry["kind"] == "error":
                    self.variables[name] = "Örnek hata mesajı (test)"
                else:
                    self.variables.setdefault("loop_index", 0)
            except CONTROL_SIGNALS:
                raise
            except Exception as exc:
                raise WorkflowError(f"Test hazırlığı tamamlanamadı ({label}): {describe_error(exc)}") from exc

    def show_target(self, action: str, p: dict) -> dict:
        """Move the pointer to where the step would click or type, without clicking."""
        from .actions.common import number

        desktop = self.desktop()
        if action in {"desktop.window_click", "desktop.window_fill", "window.read_field"}:
            x, y = self.windows().locate_target(p["window"], desktop, **self.window_target(p))
        elif action == "screen.click_image":
            from .actions.screen import search

            found = search(self, p)
            if found.pop("timed_out", False) or not found["found"]:
                raise WorkflowError("Görsel bekleme süresi içinde ekranda bulunamadı.")
            x = found["center_x"] + number(p.get("offset_x", 0), "Yatay fark", -10_000, 10_000)
            y = found["center_y"] + number(p.get("offset_y", 0), "Dikey fark", -10_000, 10_000)
        else:
            x, y = number(p.get("x"), "X", -100_000, 100_000), number(p.get("y"), "Y", -100_000, 100_000)
        try:
            desktop.move(x, y, duration=0.4)
        except ValueError as exc:
            raise WorkflowError("Hedef nokta ana ekranın dışında.") from exc
        self.log(f"Hedef gösterildi: fare ekranda ({round(x)}, {round(y)}) noktasına götürüldü. "
                 "Tıklama veya yazma yapılmadı.")
        return {"x": round(x), "y": round(y)}

    def release_keys(self) -> None:
        """A key held with 'Tuşu basılı tut' must never stay down after a run."""
        for key in list(self.held_keys):
            try:
                self.desktop().key_up(key)
            except Exception:
                pass
        self.held_keys.clear()

    def mark_unknown(self, step: Step, parameters: dict) -> None:
        target = parameters.get("output")
        if target:
            self.variables[variable_name(target)] = UNKNOWN
        if step.action in {"core.set", "data.append"}:
            self.variables[variable_name(parameters["name"])] = UNKNOWN
        # Results created within an unexecuted branch are unknown, not missing.
        for child in [*step.children, *step.otherwise]:
            self.mark_unknown(child, {**defaults(child.action), **child.params})

    def steps(self, steps: list[Step], entry: list[tuple[str | None, int]] | None = None) -> None:
        """Run the steps in order; entry starts at a step inside the list (after Adıma git)."""
        index, inner = (entry[0][1], entry[1:]) if entry else (0, [])
        while index < len(steps):
            step = steps[index]
            # Per-step counters let the diagram show what ran, how often and where it failed,
            # even after a long loop has rotated the event log.
            stats = self.run.step_stats.setdefault(step.id, {"runs": 0, "ok": 0, "errors": 0, "skipped": 0})
            try:
                outcome = self.step(step, inner)
            except JumpTo as jump:
                stats["ok"] += 1
                path = jump_path(jump.target, steps)
                if path is None:
                    raise  # the target lies outside this list: an enclosing list continues there
                index, inner = path[0][1], path[1:]
                continue
            except CONTROL_SIGNALS:
                raise
            except Exception as exc:
                if not getattr(exc, "rpa_step_counted", False):
                    stats["errors"] += 1
                    try:
                        exc.rpa_step_counted = True
                    except AttributeError:
                        pass
                raise
            stats[outcome] += 1
            index, inner = index + 1, []

    def enter(self, step: Step, entry: list[tuple[str | None, int]]) -> str:
        """Continue inside a condition or a Dene block at the step Adıma git leads to."""
        branch, index = entry[0]
        inner = [(None, index), *entry[1:]]
        self.check_cancelled()
        self.run.step_stats[step.id]["runs"] += 1
        if step.action in LOOPS or branch not in {"children", "otherwise"}:
            raise WorkflowError("Bir döngünün içine döngünün dışından gidilemez.")
        if step.action == "control.try":
            if branch == "otherwise":
                raise WorkflowError("Hata olursa dalındaki bir adıma bu dalın dışından gidilemez.")
            self.attempt(step, {**defaults(step.action), **step.params}, inner)
        else:
            self.steps(getattr(step, branch), inner)
        return "ok"

    def step(self, step: Step, entry: list[tuple[str | None, int]] | None = None) -> str:
        if entry:
            return self.enter(step, entry)
        self.check_cancelled()
        self.count_step()
        self.run.step_stats[step.id]["runs"] += 1
        raw = {**defaults(step.action), **step.params}
        if step.action == "control.for_each" and "item_name" not in step.params:
            # Imported pre-0.3 flows used item when this parameter was omitted.
            raw["item_name"] = "item"
        label = step.title or BY_TYPE[step.action]["label"]
        self.log(f"Başladı: {label}", step_id=step.id)
        if self.run.dry_run and step.action.startswith(EXTERNAL_PREFIXES):
            self.mark_unknown(step, raw)
            self.log(f"Önizleme: {label} harici işlem olduğu için atlandı.",
                     level="warning", step_id=step.id)
            return "skipped"
        # Resolve selectors first; inactive target fields may contain old expressions.
        selectors = {key for f in BY_TYPE[step.action]["fields"] for key in f.get("visible_when", {})}
        if step.action in {"control.if", "control.while"}:
            selectors.add("operator")
        selected = {**raw, **{key: resolve(raw[key], self.variables) for key in selectors}}
        active = active_fields(step.action, selected)
        # Raw fields (e.g. Hesapla's expression) resolve ${...} themselves, as variable references.
        p = {**resolve({f["name"]: selected[f["name"]] for f in active if not f.get("raw")}, self.variables),
             **{f["name"]: selected[f["name"]] for f in active if f.get("raw")}}
        if has_unknown(p):
            self.mark_unknown(step, raw)
            self.log(f"Önizleme: {label} için gerçek bağlantı verisi gerekiyor; adım/dal atlandı.",
                     level="warning", step_id=step.id)
            return "skipped"
        if step.action == "control.for_each":
            self.for_each(step, p)
        elif step.action == "control.while":
            self.while_loop(step, raw, p)
        elif step.action == "control.repeat":
            self.repeat(step, p)
        elif step.action == "control.try":
            self.attempt(step, p)
        elif step.action == "control.if":
            verdict = compare(p["left"], p["operator"], p.get("right"))
            self.log("Koşul: " + ("Evet" if verdict else "Değilse"), step_id=step.id)
            self.steps(step.children if verdict else step.otherwise)
        elif step.action == "control.break":
            self.log("Döngüden çıkılıyor.", step_id=step.id)
            raise BreakLoop()
        elif step.action == "control.continue":
            self.log("Sonraki tura geçiliyor.", step_id=step.id)
            raise ContinueLoop()
        elif step.action == "control.stop":
            raise StopWorkflow(p.get("status", "success") == "success", str(p.get("message") or ""))
        elif step.action == "control.goto":
            self.jump(step, label, p)
        elif step.action == "control.run_workflow":
            self.run_workflow(p)
        else:
            result = self.perform(step.action, p)
            if p.get("output"):
                self.variables[variable_name(p["output"])] = result
        self.check_cancelled()
        self.log(f"Tamamlandı: {label}", step_id=step.id)
        return "ok"

    def jump(self, step: Step, label: str, p: dict) -> None:
        from .actions.common import integer

        target = p.get("target")
        if not isinstance(target, str) or not target:
            raise WorkflowError(f"{label}: gidilecek adımı seçin.")
        limit = integer(p.get("max_jumps"), "Her turda en fazla", 1, MAX_LOOP_ITEMS)
        # Counted per turn of the loops now running: a jump taken once for every row is fine, the
        # same jump taken again and again within one turn is an endless loop.
        turn = tuple((loop, index) for loop, index in self.turns)
        previous, used = self.jumps.get(step.id, (None, 0))
        used = used + 1 if previous == turn else 1
        name = self.titles.get(target, "seçilen")
        if used > limit:
            raise WorkflowError(f"{label}: «{name}» adımına {'bu turda ' if turn else ''}{limit} kez gidildi; "
                                "sonsuz döngüye girmemek için akış durduruldu. Gerekiyorsa Her turda en fazla "
                                "sayısını artırın.")
        self.jumps[step.id] = (turn, used)
        self.log(f"«{name}» adımına gidiliyor.", step_id=step.id)
        raise JumpTo(target)

    def count_step(self) -> None:
        self.executed += 1
        if self.executed > MAX_EXECUTED_STEPS:
            raise WorkflowError("Bir çalışma en fazla 1.000.000 adım çalıştırabilir.")

    def loop_body(self, step: Step) -> bool:
        """Run one iteration; False means Döngüden çık was used."""
        try:
            self.steps(step.children)
        except ContinueLoop:
            pass
        except BreakLoop:
            return False
        except JumpTo as jump:
            if jump.target != step.id:
                raise  # out of the loop: like Döngüden çık, then the flow continues at the target
            # A connection back to the loop's own box starts its next turn.
        return True

    def repeat(self, step: Step, p: dict) -> None:
        from .actions.common import integer

        count = integer(p.get("count"), "Tekrar sayısı", 1, MAX_LOOP_ITEMS)
        sentinel = object()
        old_index = self.variables.get("loop_index", sentinel)
        # The running loops and their turns: Adıma git counts its jumps per turn.
        self.turns.append([step.id, 0])
        try:
            for index in range(count):
                self.check_cancelled()
                self.turns[-1][1] = index
                self.variables["loop_index"] = index
                self.log(f"Tekrar: {index + 1}/{count}", step_id=step.id)
                if not self.loop_body(step):
                    break
        finally:
            self.turns.pop()
            if old_index is sentinel:
                self.variables.pop("loop_index", None)
            else:
                self.variables["loop_index"] = old_index

    def attempt(self, step: Step, p: dict, entry: list[tuple[str | None, int]] | None = None) -> None:
        name = variable_name(p.get("error_name") or "error_message")
        try:
            self.steps(step.children, entry)
        except CONTROL_SIGNALS:
            raise
        except Exception as exc:
            if type(exc).__name__ == "FailSafeException":
                raise  # the emergency stop (mouse in a screen corner) always ends the run
            message = describe_error(exc)
            self.variables[name] = message
            self.log(f"Hata yakalandı: {message}", level="warning", step_id=step.id)
            self.steps(step.otherwise)

    def run_workflow(self, p: dict) -> None:
        workflow_id = p.get("workflow")
        if not isinstance(workflow_id, str) or not workflow_id:
            raise WorkflowError("Çalıştırılacak akışı seçin.")
        if workflow_id in self.call_stack:
            raise WorkflowError("Bir akış kendisini (doğrudan veya dolaylı) çağıramaz.")
        if len(self.call_stack) > SUB_WORKFLOW_DEPTH:
            raise WorkflowError("En fazla 5 seviye iç içe akış çalıştırılabilir.")
        try:
            child = self.store.workflow(workflow_id)
        except (KeyError, ValueError, OSError) as exc:
            raise WorkflowError("Çalıştırılacak akış bulunamadı; silinmiş olabilir. Adımda akışı yeniden seçin.") from exc
        validate_workflow(child)
        self.log(f"Alt akış başladı: {child.name}")
        self.titles.update(step_titles(child.steps))
        self.call_stack.append(workflow_id)
        try:
            self.steps(child.steps)
        except JumpTo as exc:
            raise WorkflowError(f"Alt akıştaki Adıma git bağlantısının hedefi bulunamadı ({child.name}).") from exc
        finally:
            self.call_stack.pop()
        self.log(f"Alt akış bitti: {child.name}")

    def for_each(self, step: Step, p: dict) -> None:
        items = p["items"]
        if not isinstance(items, list) or len(items) > MAX_LOOP_ITEMS:
            raise WorkflowError("Döngü en fazla 100.000 öğelik bir liste gerektirir.")
        name = variable_name(p["item_name"])
        sentinel = object()
        old_item = self.variables.get(name, sentinel)
        old_index = self.variables.get("loop_index", sentinel)
        # Snapshot the list: appending to the source must not extend this loop forever.
        self.turns.append([step.id, 0])
        try:
            for index, item in enumerate(list(items)):
                self.check_cancelled()
                self.turns[-1][1] = index
                self.variables[name] = item
                self.variables["loop_index"] = index
                self.log(f"Döngü: {index + 1}/{len(items)}", step_id=step.id)
                if not self.loop_body(step):
                    break
        finally:
            self.turns.pop()
            for key, old in ((name, old_item), ("loop_index", old_index)):
                if old is sentinel:
                    self.variables.pop(key, None)
                else:
                    self.variables[key] = old

    def while_loop(self, step: Step, raw: dict, p: dict) -> None:
        limit, seconds = p["max_iterations"], p["max_seconds"]
        if type(limit) is not int or not 1 <= limit <= MAX_LOOP_ITEMS:
            raise WorkflowError("Koşullu döngü tekrar sınırı 1–100.000 arasında tam sayı olmalıdır.")
        if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
                or not math.isfinite(seconds) or not 1 <= seconds <= 3600):
            raise WorkflowError("Koşullu döngü süre sınırı 1–3600 saniye olmalıdır.")
        deadline, index = time.monotonic() + seconds, 0
        sentinel = object()
        old_index = self.variables.get("loop_index", sentinel)
        self._deadlines.append(deadline)
        self.turns.append([step.id, 0])
        try:
            while True:
                self.check_cancelled()
                if time.monotonic() >= deadline:
                    raise WorkflowError("Koşullu döngünün süre sınırı doldu; işlem durduruldu.")
                operator_value = resolve(raw["operator"], self.variables)
                left = resolve(raw["left"], self.variables)
                right = None if operator_value in ("empty", "not_empty", "truthy") else resolve(raw["right"], self.variables)
                if has_unknown([left, right, operator_value]):
                    self.mark_unknown(step, raw)
                    self.log("Önizleme: döngü koşulu için gerçek bağlantı verisi gerekiyor.",
                             level="warning", step_id=step.id)
                    return
                if not compare(left, operator_value, right):
                    return
                if index >= limit:
                    raise WorkflowError("Koşullu döngünün tekrar sınırına ulaşıldı; koşul hâlâ doğru.")
                self.count_step()
                self.turns[-1][1] = index
                self.variables["loop_index"] = index
                self.log(f"Koşullu döngü: {index + 1}/{limit}", step_id=step.id)
                index += 1
                if not self.loop_body(step):
                    return
        finally:
            self.turns.pop()
            self._deadlines.pop()
            if old_index is sentinel:
                self.variables.pop("loop_index", None)
            else:
                self.variables["loop_index"] = old_index

    def browser(self) -> Any:
        if self._browser is None:
            from .integrations.browser import BrowserService

            self._browser = self.resources.enter_context(
                BrowserService(timeout_ms=int(self.settings.action_timeout * 1000))
            )
        return self._browser

    def desktop(self) -> Any:
        if self._desktop is None:
            from .desktop.controller import DesktopController

            self._desktop = DesktopController(default_timeout=self.settings.action_timeout,
                                              cancel_check=self.cancel.is_set)
        return self._desktop

    def windows(self) -> Any:
        if self._windows is None:
            from .desktop.windows import WindowService

            self._windows = WindowService(cancel=self.cancel)
        return self._windows

    def template_path(self, value: str) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise WorkflowError("Önce referans görsel seçin.")
        root = Path(self.config["template_dir"]).expanduser().resolve()
        path = (root / value).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise WorkflowError("Şablon, ayarlardaki şablon klasörü içinde mevcut bir dosya olmalıdır.")
        return path

    def window_target(self, p: dict) -> dict:
        mode = p.get("target_mode", "coordinates")
        if mode not in {"coordinates", "image", "element"}:
            raise WorkflowError("Hedef yöntemi X/Y, referans görsel veya alan kimliği olmalıdır.")
        if mode == "coordinates":
            return {"target_mode": mode, "x": p.get("x"), "y": p.get("y")}
        if mode == "element":
            return {"target_mode": mode, "element": p.get("element"), "timeout": p.get("timeout", 10)}
        return {"target_mode": mode, "template": self.template_path(p.get("template")),
                "offset_x": p.get("offset_x", 0), "offset_y": p.get("offset_y", 0),
                "confidence": p.get("confidence", 0.9), "timeout": p.get("timeout", 10)}

    def perform(self, action: str, p: dict) -> Any:
        from . import actions

        if self.locate and action in LOCATABLE:
            return self.show_target(action, p)

        handler = actions.get(action)
        if handler is not None:
            return handler(self, p)
        if action == "data.sample":
            return [
                {"order_id": "SIP-1001", "customer": "Ada Teknoloji", "amount": 4250, "currency": "TRY"},
                {"order_id": "SIP-1002", "customer": "Mavi Tasarım", "amount": 650, "currency": "TRY"},
                {"order_id": "SIP-1003", "customer": "Kuzey Lojistik", "amount": 7800, "currency": "TRY"},
                {"order_id": "SIP-1004", "customer": "Ege Üretim", "amount": 1200, "currency": "TRY"},
            ]
        if action == "core.set":
            self.variables[variable_name(p["name"])] = p["value"]
        elif action == "data.append":
            values = self.variables.setdefault(variable_name(p["name"]), [])
            if not isinstance(values, list) or len(values) >= MAX_LOOP_ITEMS:
                raise WorkflowError("Hedef en fazla 100.000 öğelik bir liste olmalıdır.")
            values.append(p["value"])
        elif action == "core.log":
            self.log(str(p["message"]))
        elif action == "core.wait":
            seconds = float(p["seconds"])
            if not math.isfinite(seconds) or not 0 <= seconds <= 300:
                raise WorkflowError("Bekleme 0–300 saniye arasında olmalıdır.")
            if not self.run.dry_run and self.cancel.wait(seconds):
                raise Cancelled()
        elif action == "data.export_csv":
            self.export_csv(p["rows"], p["filename"])
        elif action == "database.read":
            from .database.reader import ReadOnlyDatabase

            profile = self.connections.resolve(p.get("connection"), "database")
            if profile["id"] not in self._databases:
                self._databases[profile["id"]] = self.resources.enter_context(ReadOnlyDatabase(
                    profile["config"]["url"], {t: None for t in profile["config"]["allowed_tables"]},
                    max_rows=self.settings.max_rows, timeout_seconds=self.settings.action_timeout,
                ))
            frame = self._databases[profile["id"]].read_table(p["table"], columns=p["columns"], filters=p["filters"],
                                              limit=int(p["limit"]))
            return json.loads(frame.to_json(orient="records", date_format="iso"))
        elif action == "desktop.find_window":
            return self.windows().find(p["application"], p["title"], p["match"], p["timeout"], p["on_missing"])
        elif action == "desktop.window_click":
            clicks = p.get("clicks", 1)
            if type(clicks) is str and clicks in {"1", "2"}:
                clicks = int(clicks)
            if type(clicks) is not int or clicks not in {1, 2}:
                raise WorkflowError("Tıklama sayısı 1 veya 2 olmalıdır.")
            self.windows().click_target(p["window"], self.desktop(), **self.window_target(p),
                                        clicks=clicks, button=p.get("button", "left"))
        elif action == "desktop.window_fill":
            text = p["text"]
            if isinstance(text, (dict, list)) or text is None:
                raise WorkflowError("Yazılacak değer bir metin veya sayı olmalıdır; satır için ${row.value} kullanın.")
            self.windows().fill_target(p["window"], str(text), self.desktop(), clear=p["clear"],
                                       **self.window_target(p))
        elif action == "desktop.window_key":
            self.windows().press_key(p["window"], p["key"], p["modifier"], self.desktop())
        elif action == "desktop.window_wait_image":
            if p["state"] not in {"visible", "hidden"}:
                raise WorkflowError("Görselin beklenen durumu geçersiz.")
            self.windows().wait_image(p["window"], self.template_path(p["template"]), self.desktop(),
                                       confidence=p["confidence"], timeout=p["timeout"], visible=p["state"] == "visible")
        elif action == "desktop.window_write":
            self.windows().write(p["window"], p["text"], self.desktop())
        elif action == "desktop.click":
            self.desktop().click(float(p["x"]), float(p["y"]))
        elif action == "desktop.write":
            self.desktop().write(str(p["text"]))
        elif action == "desktop.hotkey":
            if not isinstance(p["keys"], list) or not all(isinstance(key, str) for key in p["keys"]):
                raise WorkflowError("Tuşlar bir metin listesi olmalıdır.")
            self.desktop().hotkey(*p["keys"])
        elif action == "desktop.press":
            self.desktop().press(p["key"])
        elif action == "desktop.click_template":
            self.desktop().click_template(self.template_path(p["template"]), region=p["region"],
                                           confidence=float(p["confidence"]))
        elif action == "desktop.ocr":
            from .desktop.vision import Vision

            return Vision.read_text(self.desktop().screenshot(p["region"]),
                                    language=self.config["ocr_language"],
                                    tesseract_cmd=self.config["tesseract_cmd"] or None,
                                    timeout=self.settings.action_timeout)
        elif action == "desktop.scan_dropdown":
            from .desktop.dropdown import DropdownIterator

            region = p["region"]
            if not isinstance(region, list) or len(region) != 4:
                raise WorkflowError("Liste bölgesi dört sayı içermelidir.")
            x, y, width, height = region
            return DropdownIterator(self.desktop()).scan(
                region=region, language=self.config["ocr_language"],
                max_scrolls=int(p["max_scrolls"]), tesseract_cmd=self.config["tesseract_cmd"] or None,
                ocr_timeout=self.settings.action_timeout,
                scroll=lambda: self.desktop().scroll(int(p["scroll_amount"]), x=x + width // 2, y=y + height // 2),
            )
        elif action == "browser.open":
            return self.browser().goto(p["url"])
        elif action == "browser.fill":
            self.browser().fill(p["selector"], str(p["value"]))
        elif action == "browser.click":
            self.browser().click(p["selector"])
        elif action == "browser.text":
            return self.browser().text(p["selector"])
        elif action.startswith("sheets."):
            from .integrations.sheets import SheetsService, normalize_spreadsheet_id

            profile = self.connections.resolve(p.get("connection"), "google_sheets")
            config = profile["config"]
            script = config["method"] == "apps_script"
            try:
                spreadsheet_id = normalize_spreadsheet_id(p["spreadsheet_id"])
            except ValueError as exc:
                raise WorkflowError("Geçerli bir Google Sheets bağlantısı veya tablo kimliği girin.") from exc
            key = (profile["id"], spreadsheet_id, p["worksheet"])
            if key not in self._sheets:
                if script:
                    from .integrations.apps_script import AppsScriptSheets

                    service = AppsScriptSheets(config["script_url"], config["script_token"], *key[1:],
                                               timeout=max(self.settings.action_timeout, 60))
                else:
                    service = SheetsService(config["credentials_path"], *key[1:],
                                            timeout=min(self.settings.action_timeout, 120))
                self._sheets[key] = self.resources.enter_context(service)
            if action == "sheets.read":
                return self._sheets[key].get_range(p["range"])
            if action == "sheets.read_cell":
                value = self._sheets[key].get_cell(p["cell"])
                if value is None or value == "":
                    if p.get("allow_empty") is True:
                        return ""
                    raise WorkflowError("Sheets hücresi boş. Hücre adresini ve veriyi kontrol edin.")
                return value
            if action == "sheets.read_rows":
                try:
                    rows = self._sheets[key].get_rows(start_row=p["start_row"], max_rows=p["max_rows"],
                                                     columns=p["columns"], key=p["key"], empty_policy=p["empty_policy"])
                except ValueError as exc:
                    raise WorkflowError("Satır sınırını, sütun eşleştirmelerini ve ana alanı kontrol edin. "
                                        "1–32 benzersiz alan, en fazla 64 sütun genişliği kullanılabilir.") from exc
                if not rows:
                    raise WorkflowError("Ana alanı dolu kayıt bulunamadı. Başlangıç satırını ve sütunları kontrol edin.")
                self.log(f"Sheets: {len(rows)} kayıt okundu.")
                return rows
            if action == "sheets.read_column":
                try:
                    rows = self._sheets[key].get_column(p["start_cell"], p["max_rows"], p["empty_policy"])
                except ValueError as exc:
                    raise WorkflowError("Başlangıç hücresi (ör. B2), satır sınırı (1–1000) ve boş hücre seçimini kontrol edin.") from exc
                if not rows:
                    raise WorkflowError("Okunacak dolu satır bulunamadı. Başlangıç hücresini ve boş hücre seçimini kontrol edin.")
                self.log(f"Sheets: {len(rows)} satır okundu.")
                return rows
            if action == "sheets.write_cell":
                self._sheets[key].update_cell(p["cell"], p["value"], raw=True)
                return None
            self._sheets[key].update_range(p["range"], p["values"])
        else:
            raise WorkflowError("Bu adım için çalıştırıcı bulunamadı.")
        return None

    def export_csv(self, rows: Any, filename: str) -> None:
        if not isinstance(rows, list) or len(rows) > 100000 or not all(isinstance(r, dict) for r in rows):
            raise WorkflowError("CSV çıktısı en fazla 100.000 nesneden oluşan bir kayıt listesi gerektirir.")
        if not isinstance(filename, str) or not re.fullmatch(r"[^/\\\x00-\x1f<>:\"|?*]{1,120}\.csv", filename,
                                                            re.IGNORECASE):
            raise WorkflowError("Çıktı adı yol içermeyen, .csv uzantılı bir dosya adı olmalıdır.")
        if len(self.run.artifacts) >= 100:
            raise WorkflowError("Bir çalışma en fazla 100 rapor üretebilir.")
        artifact = Artifact(name=filename, department=self.run.department, rows=len(rows))
        artifact.url = f"/api/runs/{self.run.id}/artifacts/{artifact.id}"
        destination = self.store.root / "artifacts" / self.run.id
        destination.mkdir(parents=True, exist_ok=True)
        headers = list(dict.fromkeys(key for row in rows for key in row))
        if not all(isinstance(key, str) for key in headers):
            raise WorkflowError("CSV sütun adları metin olmalıdır.")
        with (destination / f"{artifact.id}.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            if headers:
                writer.writerow([csv_value(key) for key in headers])
                for row in rows:
                    self.check_cancelled()
                    writer.writerow([csv_value(row.get(key, "")) for key in headers])
        self.run.artifacts.append(artifact)
        self.save()


def referenced(value: Any) -> list[str]:
    """Variable names used as ${name} or ${name.field} anywhere in a parameter value."""
    if isinstance(value, str):
        return [match.group(1) for match in re.finditer(r"\$\{([A-Za-z][A-Za-z0-9_]*)", value)]
    if isinstance(value, dict):
        value = list(value.values())
    return [name for item in value for name in referenced(item)] if isinstance(value, list) else []


def step_reads(step: Step, *, nested: bool = True) -> tuple[list[str], set[str]]:
    """Names a step (with its inner steps) reads; the second set is also written somewhere inside it."""
    scoped, assigned, found = {"sistem"}, set(), []

    def visit(item: Step, top: bool) -> None:
        parameters = {**defaults(item.action), **item.params} if item.action in BY_TYPE else dict(item.params)
        if nested:
            for key in ("item_name", "error_name"):
                if isinstance(parameters.get(key), str) and parameters[key]:
                    scoped.add(parameters[key])
            if item.action in LOOPS:
                scoped.add("loop_index")
        if not top:
            if isinstance(parameters.get("output"), str) and parameters["output"]:
                assigned.add(parameters["output"])
            if item.action in {"core.set", "data.append"} and isinstance(parameters.get("name"), str):
                assigned.add(parameters["name"])
        found.extend(referenced(parameters))
        if item.action == "data.calculate":
            from .actions.data import FUNCTIONS

            source = re.sub(r"\$\{[^}]*\}", " 0 ", str(parameters.get("expression") or ""))
            try:
                names = [node.id for node in ast.walk(ast.parse(source.strip(), mode="eval"))
                         if isinstance(node, ast.Name)]
            except (SyntaxError, ValueError):
                names = []
            reserved = set(FUNCTIONS) | {"true", "false", "doğru", "dogru", "yanlış", "yanlis", "True", "False", "None"}
            found.extend(name for name in names if name not in reserved and VARIABLE.fullmatch(name))
        if nested:
            for child in [*item.children, *item.otherwise]:
                visit(child, False)

    visit(step, True)
    return list(dict.fromkeys(name for name in found if name not in scoped)), assigned


def step_test_plan(workflow: Workflow, step_id: str, provided: Any = ()) -> dict:
    """What a single-step test prepares by itself, and what only the user can supply.

    Earlier steps that only read or compute (the window lookup, constants, a Sheets read,
    OCR of the current screen) are run for real, and a loop variable takes the first item
    of its list. A value produced by a step that acts (a click, a question to the user)
    cannot be obtained safely and is asked for.
    """
    def frames_of(target: str, steps: list[Step], trail: list) -> list | None:
        for index, item in enumerate(steps):
            here = [*trail, (steps, index)]
            if item.id == target:
                return here
            for branch in ("children", "otherwise"):
                found = frames_of(target, getattr(item, branch), [*here, branch])
                if found:
                    return found
        return None

    def levels(frames: list) -> list[tuple[list[Step], int, Step | None, str | None]]:
        # (list, index, owner, branch) from the outermost list to the one that holds the step
        result, owner, branch = [], None, None
        for entry in frames:
            if isinstance(entry, str):
                branch = entry
            else:
                steps, index = entry
                result.append((steps, index, owner, branch))
                owner = steps[index]
        return result

    def parameters(item: Step) -> dict:
        return {**defaults(item.action), **item.params} if item.action in BY_TYPE else dict(item.params)

    def produces(item: Step, name: str) -> bool:
        p = parameters(item)
        return p.get("output") == name or (item.action in {"core.set", "data.append"} and p.get("name") == name)

    def preparable(item: Step) -> bool:
        return item.action in TEST_PREPARE or (
            item.action == "window.read_field" and parameters(item).get("target_mode") == "element")

    def descendants(item: Step) -> list[Step]:
        return [item, *(d for child in [*item.children, *item.otherwise] for d in descendants(child))]

    target_frames = frames_of(step_id, workflow.steps, [])
    if target_frames is None:
        raise KeyError(step_id)
    target = target_frames[-1][0][target_frames[-1][1]]
    provided, entries, manual, details, planned = set(provided), [], [], [], set()
    flat = [item for top in workflow.steps for item in descendants(top)]
    earlier = flat[:next(index for index, item in enumerate(flat) if item.id == step_id)]

    def unknown(name: str) -> dict:
        """No earlier step gives this name: usually a typing difference, so offer the closest name."""
        names = {}
        for item in earlier:
            p = parameters(item)
            for key in ("output", "item_name", "error_name", *(("name",) if item.action in {"core.set", "data.append"} else ())):
                if isinstance(p.get(key), str) and VARIABLE.fullmatch(p[key]):
                    names[p[key].casefold()] = p[key]
        close = difflib.get_close_matches(name.casefold(), list(names), n=1, cutoff=0.6)
        return {"variable": name, "reason": "missing", "suggestion": names[close[0]] if close else None}

    def find(name: str, frames: list):
        chain = levels(frames)
        for depth in range(len(chain) - 1, -1, -1):
            steps, index, owner, branch = chain[depth]
            for position in range(index - 1, -1, -1):
                if produces(steps[position], name):
                    return "step", steps[position]
            if owner is not None:
                p = parameters(owner)
                if owner.action == "control.for_each" and p.get("item_name") == name:
                    return "item", owner
                if owner.action == "control.try" and branch == "otherwise" and p.get("error_name") == name:
                    return "error", owner
                if name == "loop_index" and owner.action in LOOPS:
                    return "index", owner
        # A value set inside an earlier block (a branch or a loop): the last such step before this one.
        for depth in range(len(chain) - 1, -1, -1):
            steps, index, _, _ = chain[depth]
            for position in range(index - 1, -1, -1):
                for item in reversed(descendants(steps[position])[1:]):
                    if produces(item, name):
                        return "step", item
        return None, None

    def need(name: str, frames: list, optional: bool = False) -> None:
        if name in provided or name == "sistem":
            return
        kind, producer = find(name, frames)
        if kind is None or (kind == "step" and not preparable(producer)):
            if not optional and name not in manual:
                manual.append(name)
                # An earlier "Başka akışı çalıştır" shares its variables, so the name may come from there.
                source = producer if kind else next(
                    (item for item in reversed(earlier) if item.action == "control.run_workflow"), None)
                details.append(unknown(name) if source is None else {
                    "variable": name, "reason": "acting",
                    "title": source.title or BY_TYPE[source.action]["label"]})
            return
        if (kind, producer.id) in planned:
            return
        planned.add((kind, producer.id))
        # Every producer lies earlier in the flow than its reader, so this recursion ends.
        producer_frames = frames_of(producer.id, workflow.steps, [])
        if kind == "step":
            for dependency in step_reads(producer, nested=False)[0]:
                need(dependency, producer_frames)
        elif kind == "item":
            for dependency in dict.fromkeys(referenced(parameters(producer).get("items"))):
                need(dependency, producer_frames)
        entries.append({"kind": kind, "variable": name, "step": producer,
                        "title": producer.title or BY_TYPE[producer.action]["label"]})

    reads, assigned = step_reads(target)
    for name in reads:
        need(name, target_frames, optional=name in assigned)
    chain = levels(target_frames)
    return {"step": target, "prepare": entries, "manual": manual, "manual_details": details,
            "in_loop": any(owner is not None and owner.action in LOOPS for _, _, owner, _ in chain),
            "locatable": target.action in LOCATABLE,
            "external": any(item.action.startswith(EXTERNAL_PREFIXES) for item in descendants(target))}


class RunManager:
    """One worker protects the shared mouse/keyboard and owns its browser thread."""

    def __init__(self, settings: Settings, store: Store):
        self.settings, self.store = settings, store
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rpa-worker")
        self._lock = threading.RLock()
        self._active: tuple[str, threading.Event] | None = None
        self._setup_cancel: threading.Event | None = None
        self._closed = False
        # The Studio sets this to its license check; nothing starts while it answers False.
        self.gate: Callable[[], bool] | None = None
        self._stop_reason: str | None = None

    def reserve_desktop(self, cancel: threading.Event | None = None) -> threading.Event:
        with self._lock:
            if self._closed or self._active or self._setup_cancel is not None:
                raise RuntimeError("Hedef seçmeden önce çalışan akışın bitmesini bekleyin veya durdurun.")
            token = cancel if cancel is not None else threading.Event()
            self._setup_cancel = token
            return token

    def release_desktop(self, token: threading.Event) -> None:
        with self._lock:
            if self._setup_cancel is token:
                self._setup_cancel = None

    @contextmanager
    def desktop_setup(self):
        """Reserve without holding the lock, so run/cancel requests return promptly."""
        token = self.reserve_desktop()
        try:
            yield
        finally:
            self.release_desktop(token)

    def start_step(self, workflow: Workflow, step_id: str, variables: dict[str, Any], *,
                   dry_run: bool = False, locate: bool = False) -> Run:
        """Test one step (with its inner steps); what it needs from earlier steps is prepared first."""
        if not isinstance(variables, dict) or len(variables) > 100:
            raise WorkflowError("Test değişkenleri en fazla 100 alanlı bir nesne olmalıdır.")
        for name in variables:
            variable_name(name)
        plan = step_test_plan(workflow, step_id, variables)
        plan["titles"] = step_titles(workflow.steps)
        if locate and not plan["locatable"]:
            raise WorkflowError("Yeri göster yalnız tıklama ve alan doldurma adımlarında kullanılabilir.")
        single = workflow.model_copy(update={"steps": [plan["step"].model_copy(deep=True)]}, deep=True)
        return self.start(single, dry_run=dry_run, variables=variables, test_step_id=step_id, plan=plan,
                          locate=locate)

    def start(self, workflow: Workflow, *, dry_run: bool = False, variables: dict[str, Any] | None = None,
              test_step_id: str | None = None, plan: dict | None = None, locate: bool = False) -> Run:
        # A tested step runs alone: its Adıma git target lies outside the copy that is run.
        validate_workflow(workflow, in_loop=bool(plan and plan["in_loop"]), jumps=plan is None)
        if self.gate is not None and not self.gate():
            raise RuntimeError("Lisans doğrulanamadığı için akış başlatılamadı.")
        with self._lock:
            if self._setup_cancel is not None:
                raise RuntimeError("Bir hedef seçimi devam ediyor. Tamamlanmasını bekleyin veya iptal edin.")
            if self._closed or self._active:
                raise RuntimeError("Zaten bir akış çalışıyor. Tamamlanmasını bekleyin veya durdurun.")
            run = Run(workflow_id=workflow.id, workflow_name=workflow.name,
                      department=workflow.department, dry_run=dry_run, test_step_id=test_step_id)
            cancel = threading.Event()
            self.store.save_run(run)
            self._active = (run.id, cancel)
            self.pool.submit(self._work, workflow.model_copy(deep=True), run, cancel, dict(variables or {}),
                             plan, locate)
            return run.model_copy(deep=True)

    def _work(self, workflow: Workflow, run: Run, cancel: threading.Event,
              variables: dict[str, Any] | None = None, plan: dict | None = None, locate: bool = False) -> None:
        runner = Executor(self.settings, self.store, run, cancel, lambda: self.store.save_run(run), variables)
        if plan:
            runner.titles = dict(plan.get("titles") or {})
        try:
            run.status = "running"
            if run.test_step_id:
                runner.log("Adım testi: yalnız seçilen adım çalıştırılıyor.")
            runner.log("Önizleme başladı; ekran, dosya ve bağlantı adımları atlanacak." if run.dry_run
                       else "Akış çalıştırılıyor.")
            if plan:
                with runner.resources:
                    runner.prepare(plan["prepare"])
                    runner.locate = locate
                    runner.execute(workflow)
            else:
                runner.execute(workflow)
            run.status = "succeeded"
        except StopWorkflow as signal:
            run.status = "succeeded" if signal.succeeded else "failed"
            if not signal.succeeded:
                run.error = signal.message or "Akış, Akışı bitir adımıyla hata sonucu verdi."
            runner.log(signal.message or "Akış bitirildi.", level="info" if signal.succeeded else "error")
        except (Cancelled, InterruptedError):
            run.status = "cancelled"
            with self._lock:
                reason, self._stop_reason = self._stop_reason, None
            if reason:
                run.error = reason
            runner.log(reason or "Çalışma kullanıcı tarafından durduruldu.", level="warning")
        except JumpTo as jump:
            if plan:
                # The tested step leads elsewhere; following it is the flow's job, not the test's.
                run.status = "succeeded"
                runner.log(f"Test: akışta bu noktada «{runner.titles.get(jump.target, 'seçilen')}» "
                           "adımına gidilir.")
            else:
                run.status = "failed"
                run.error = "Adıma git bağlantısının hedefi bulunamadı; bağlantıyı yeniden seçin."
                runner.log(run.error, level="error")
        except (BreakLoop, ContinueLoop) as signal:
            if plan and plan["in_loop"]:
                # The tested step sits in a loop: leaving the turn here is its expected result.
                run.status = "succeeded"
                runner.log("Test: akışta bu noktada döngüden çıkılır." if isinstance(signal, BreakLoop)
                           else "Test: akışta bu noktada bu satır atlanır ve sonraki satıra geçilir.")
            else:
                run.status = "failed"
                run.error = "Döngüden çık / Sonraki tura geç adımı bir döngünün içinde olmalıdır."
                runner.log(run.error, level="error")
        except Exception as exc:
            run.status = "failed"
            run.error = describe_error(exc)
            runner.log(run.error, level="error")
        finally:
            if run.test_step_id:
                run.variables = snapshot(runner.variables)
            run.finished_at = now()
            # Free the worker before the result becomes visible: whoever sees the finished run can
            # start the next one at once. The single worker thread still writes this file first.
            with self._lock:
                self._active, self._stop_reason = None, None
            self.store.save_run(run)

    def cancel(self, run_id: str) -> Run:
        with self._lock:
            run = self.store.run(run_id)
            if self._active and self._active[0] == run_id:
                self._active[1].set()
            return run

    def stop_active(self, reason: str) -> None:
        """Stop the running flow, if any, and record why (e.g. the license was withdrawn)."""
        with self._lock:
            if self._active:
                self._stop_reason = reason
                self._active[1].set()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self._active:
                self._active[1].set()
            if self._setup_cancel is not None:
                self._setup_cancel.set()
        self.pool.shutdown(wait=True, cancel_futures=False)
