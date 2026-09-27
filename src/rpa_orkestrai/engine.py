"""Bounded workflow execution with cooperative cancellation and isolated runs."""

from __future__ import annotations

import csv
import json
import math
import operator
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Callable

from .catalog import BY_TYPE, EXTERNAL_PREFIXES, defaults
from .config import Settings
from .desktop.windows import WindowError, validate_selector
from .models import Artifact, Event, Run, Step, Workflow, now
from .storage import Store


class WorkflowError(ValueError):
    """An actionable, public error that does not embed connection credentials."""


class Cancelled(Exception):
    pass


class PreviewValue:
    """An external result that is unknown in a dry run, never fabricated."""


UNKNOWN = PreviewValue()
REFERENCE = re.compile(r"\$\{([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)\}")
VARIABLE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def variable_name(value: Any) -> str:
    if not isinstance(value, str) or not VARIABLE.fullmatch(value):
        raise WorkflowError("Değişken adı harfle başlamalı; yalnız harf, rakam ve alt çizgi içermelidir.")
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
                raise WorkflowError(f"Değişken bulunamadı: {path}")
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


def validate_workflow(workflow: Workflow, *, ready: bool = True) -> None:
    def walk(steps: list[Step]) -> None:
        for step in steps:
            if step.action not in BY_TYPE:
                raise WorkflowError(f"Bilinmeyen adım türü: {step.action}")
            fields = BY_TYPE[step.action]["fields"]
            allowed = {f["name"] for f in fields}
            if set(step.params) - allowed:
                raise WorkflowError(f"{step.title or step.action}: bilinmeyen parametre.")
            if ready:
                parameters = {**defaults(step.action), **step.params}
                for f in fields:
                    value = parameters.get(f["name"])
                    if f.get("required") and (value is None or value == ""):
                        raise WorkflowError(f"{step.title or step.action}: {f['label']} gereklidir.")
                for key in ("output", "name", "item_name"):
                    if key in parameters:
                        variable_name(parameters[key])
                if parameters.get("item_name") == "loop_index":
                    raise WorkflowError("loop_index döngü sayacı için ayrılmıştır; başka bir öğe adı seçin.")
                if step.action == "desktop.find_window":
                    try:
                        validate_selector(parameters["application"], parameters["title"],
                                          parameters["match"], parameters["timeout"])
                        if parameters["on_missing"] not in {"stop", "continue"}:
                            raise WindowError("Pencere bulunamadığında yapılacak işlem geçersiz.")
                    except WindowError as exc:
                        raise WorkflowError(str(exc)) from exc
            walk(step.children)
            walk(step.otherwise)

    walk(workflow.steps)
    if ready and not workflow.steps:
        raise WorkflowError("Çalıştırmadan önce akışa en az bir adım ekleyin.")


def compare(left: Any, op: str, right: Any) -> bool:
    if op == "contains":
        return str(right).casefold() in str(left).casefold()
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


class Executor:
    def __init__(self, settings: Settings, store: Store, run: Run, cancel: threading.Event,
                 save: Callable[[], None]):
        self.settings, self.store, self.run = settings, store, run
        self.cancel, self.save = cancel, save
        self.config = settings.snapshot()
        self.variables: dict[str, Any] = {}
        self.resources = ExitStack()
        self._browser: Any = None
        self._desktop: Any = None
        self._windows: Any = None
        self._database: Any = None
        self._sheets: dict[tuple[str, str], Any] = {}
        self.executed = 0

    def check_cancelled(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()

    def log(self, message: str, *, level: str = "info", step_id: str | None = None) -> None:
        # Never persist configured credentials, even when accidentally used in a log step.
        for key in ("database_url", "google_credentials_path"):
            secret = self.config.get(key)
            if secret:
                message = message.replace(secret, "[gizlendi]")
        message = re.sub(r"(\w+://)[^\s/@]+:[^\s/@]+@", r"\1[gizlendi]@", message)
        self.run.events.append(Event(message=message[:2000], level=level, step_id=step_id))
        self.run.events = self.run.events[-1000:]
        self.save()

    def execute(self, workflow: Workflow) -> None:
        with self.resources:
            self.steps(workflow.steps)
            self.check_cancelled()

    def mark_unknown(self, step: Step, parameters: dict) -> None:
        target = parameters.get("output")
        if target:
            self.variables[variable_name(target)] = UNKNOWN
        if step.action in {"core.set", "data.append"}:
            self.variables[variable_name(parameters["name"])] = UNKNOWN
        # Results created within an unexecuted branch are unknown, not missing.
        for child in [*step.children, *step.otherwise]:
            self.mark_unknown(child, {**defaults(child.action), **child.params})

    def steps(self, steps: list[Step]) -> None:
        for step in steps:
            self.check_cancelled()
            self.executed += 1
            if self.executed > 10000:
                raise WorkflowError("Bir çalışma en fazla 10.000 adım çalıştırabilir.")
            raw = {**defaults(step.action), **step.params}
            label = step.title or BY_TYPE[step.action]["label"]
            self.log(f"Başladı: {label}", step_id=step.id)
            if self.run.dry_run and step.action.startswith(EXTERNAL_PREFIXES):
                self.mark_unknown(step, raw)
                self.log(f"Önizleme: {label} harici işlem olduğu için atlandı.",
                         level="warning", step_id=step.id)
                continue
            p = resolve(raw, self.variables)
            if has_unknown(p):
                self.mark_unknown(step, raw)
                self.log(f"Önizleme: {label} için gerçek bağlantı verisi gerekiyor; adım/dal atlandı.",
                         level="warning", step_id=step.id)
                continue
            if step.action == "control.for_each":
                self.for_each(step, p)
            elif step.action == "control.if":
                verdict = compare(p["left"], p["operator"], p["right"])
                self.log("Koşul: " + ("Evet" if verdict else "Değilse"), step_id=step.id)
                self.steps(step.children if verdict else step.otherwise)
            else:
                result = self.perform(step.action, p)
                if p.get("output"):
                    self.variables[variable_name(p["output"])] = result
            self.check_cancelled()
            self.log(f"Tamamlandı: {label}", step_id=step.id)

    def for_each(self, step: Step, p: dict) -> None:
        items = p["items"]
        if not isinstance(items, list) or len(items) > 1000:
            raise WorkflowError("Döngü en fazla 1.000 öğelik bir liste gerektirir.")
        name = variable_name(p["item_name"])
        sentinel = object()
        old_item = self.variables.get(name, sentinel)
        old_index = self.variables.get("loop_index", sentinel)
        # Snapshot the list: appending to the source must not extend this loop forever.
        try:
            for index, item in enumerate(list(items)):
                self.check_cancelled()
                self.variables[name] = item
                self.variables["loop_index"] = index
                self.steps(step.children)
        finally:
            for key, old in ((name, old_item), ("loop_index", old_index)):
                if old is sentinel:
                    self.variables.pop(key, None)
                else:
                    self.variables[key] = old

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
        root = Path(self.config["template_dir"]).expanduser().resolve()
        path = (root / value).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise WorkflowError("Şablon, ayarlardaki şablon klasörü içinde mevcut bir dosya olmalıdır.")
        return path

    def perform(self, action: str, p: dict) -> Any:
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
            if not isinstance(values, list) or len(values) >= 10000:
                raise WorkflowError("Hedef en fazla 10.000 öğelik bir liste olmalıdır.")
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

            if not self.config["database_url"]:
                raise WorkflowError("Önce Ayarlar bölümünden veritabanı bağlantısını tanımlayın.")
            if self._database is None:
                self._database = self.resources.enter_context(ReadOnlyDatabase(
                    self.config["database_url"], {t: None for t in self.config["allowed_tables"]},
                    max_rows=self.settings.max_rows, timeout_seconds=self.settings.action_timeout,
                ))
            frame = self._database.read_table(p["table"], columns=p["columns"], filters=p["filters"],
                                              limit=int(p["limit"]))
            return json.loads(frame.to_json(orient="records", date_format="iso"))
        elif action == "desktop.find_window":
            return self.windows().find(p["application"], p["title"], p["match"], p["timeout"], p["on_missing"])
        elif action == "desktop.window_click":
            self.windows().click(p["window"], p["x"], p["y"], self.desktop())
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
            from .integrations.sheets import SheetsService

            if not self.config["google_credentials_path"]:
                raise WorkflowError("Önce Ayarlar bölümünden Google servis hesabı dosyasını tanımlayın.")
            key = (p["spreadsheet_id"], p["worksheet"])
            if key not in self._sheets:
                self._sheets[key] = self.resources.enter_context(
                    SheetsService(self.config["google_credentials_path"], *key,
                                  timeout=min(self.settings.action_timeout, 120))
                )
            if action == "sheets.read":
                return self._sheets[key].get_range(p["range"])
            if action == "sheets.read_cell":
                value = self._sheets[key].get_cell(p["cell"])
                if value is None or value == "":
                    raise WorkflowError("Sheets hücresi boş. Hücre adresini ve veriyi kontrol edin.")
                return value
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


class RunManager:
    """One worker protects the shared mouse/keyboard and owns its browser thread."""

    def __init__(self, settings: Settings, store: Store):
        self.settings, self.store = settings, store
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rpa-worker")
        self._lock = threading.RLock()
        self._active: tuple[str, threading.Event] | None = None
        self._closed = False

    def start(self, workflow: Workflow, *, dry_run: bool = False) -> Run:
        validate_workflow(workflow)
        with self._lock:
            if self._closed or self._active:
                raise RuntimeError("Zaten bir akış çalışıyor. Tamamlanmasını bekleyin veya durdurun.")
            run = Run(workflow_id=workflow.id, workflow_name=workflow.name,
                      department=workflow.department, dry_run=dry_run)
            cancel = threading.Event()
            self.store.save_run(run)
            self._active = (run.id, cancel)
            self.pool.submit(self._work, workflow.model_copy(deep=True), run, cancel)
            return run.model_copy(deep=True)

    def _work(self, workflow: Workflow, run: Run, cancel: threading.Event) -> None:
        runner = Executor(self.settings, self.store, run, cancel, lambda: self.store.save_run(run))
        try:
            run.status = "running"
            runner.log("Önizleme başladı; harici işlemler atlanacak." if run.dry_run else "Akış çalıştırılıyor.")
            runner.execute(workflow)
            run.status = "succeeded"
        except (Cancelled, InterruptedError):
            run.status = "cancelled"
            runner.log("Çalışma kullanıcı tarafından durduruldu.", level="warning")
        except Exception as exc:
            run.status = "failed"
            if isinstance(exc, (WorkflowError, WindowError)):
                run.error = str(exc)
            elif isinstance(exc, ImportError):
                run.error = ("Gerekli otomasyon paketi veya sistem sürücüsü yüklenemedi. "
                             "Kurulum rehberini ve rpa-studio doctor çıktısını kontrol edin.")
            elif isinstance(exc, TimeoutError):
                run.error = "İşlem zaman aşımına uğradı. Hedef öğeyi, bağlantıyı ve bekleme süresini kontrol edin."
            elif type(exc).__name__ == "FailSafeException":
                run.error = "Fare köşeye taşındı; PyAutoGUI acil durdurma devreye girdi."
            else:
                run.error = (f"İşlem tamamlanamadı ({type(exc).__name__}). Son başlayan adımın parametrelerini, "
                             "bağlantı ayarlarını ve sistem izinlerini kontrol edin.")
            runner.log(run.error, level="error")
        finally:
            run.finished_at = now()
            try:
                self.store.save_run(run)
            finally:
                with self._lock:
                    self._active = None

    def cancel(self, run_id: str) -> Run:
        with self._lock:
            run = self.store.run(run_id)
            if self._active and self._active[0] == run_id:
                self._active[1].set()
            return run

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self._active:
                self._active[1].set()
        self.pool.shutdown(wait=True, cancel_futures=False)
