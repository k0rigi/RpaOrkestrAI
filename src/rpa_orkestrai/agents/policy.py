"""Ajan kararından bağımsız akış yetkisi, sabitleme ve yürütme korumaları."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import WorkflowError
from ..models import Workflow, walk_steps
from .contracts import RESERVED, parameters, produces, reads, validate_inputs
from .redaction import MASK, Redactor
from .risk import WRITE, workflow_risk

WORKFLOW_ID = re.compile(r"^[a-f0-9]{32}$")
# These handlers lack a enforceable resource boundary. Human-run flows are unaffected.
UNSUPPORTED = frozenset({
    "system.command", "system.run_file", "system.open", "system.close_app", "web.script",
    "http.request", "database.query", "file.zip", "screen.screenshot", "desktop.ocr",
    "desktop.click", "desktop.write", "desktop.hotkey", "desktop.press", "desktop.click_template",
    "desktop.scan_dropdown", "clipboard.get", "clipboard.set", "input.mouse_click", "input.mouse_move",
    "input.drag", "input.scroll", "input.type", "input.hotkey", "input.press", "input.key_state",
})
FILE_FIELDS = {
    "file.read_text": ("path",), "file.write_text": ("path",), "file.read_table": ("path",),
    "file.write_table": ("path",), "file.read_pdf": ("path",), "file.exists": ("path",),
    "file.list": ("folder",), "file.wait": ("path",), "file.operation": ("source", "destination"),
}
UNSAFE_APPLICATIONS = frozenset({"terminal", "iterm", "iterm2", "cmd", "powershell", "pwsh",
                                 "windowsterminal", "wt", "conhost", "bash", "zsh", "sh",
                                 "safari", "google chrome", "chrome", "chromium", "msedge",
                                 "microsoft edge", "firefox", "explorer", "finder"})


def _unsafe_application(value):
    name = str(value).strip().casefold().removesuffix(".exe").removesuffix(".app")
    return name in UNSAFE_APPLICATIONS or "rpaorkestrai" in name


def _stop(message: str):
    # Lazy import keeps policy independent of the engine and its optional desktop imports.
    from ..errors import AgentPolicyStop

    raise AgentPolicyStop(message)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _hash(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _load_graph(workflow_id: str, store, *, allowed: set[str] | None = None) -> dict[str, Workflow]:
    graph = {}
    traversed = 0

    def visit(identity, stack=()):
        nonlocal traversed
        traversed += 1
        if traversed > 2000:
            raise WorkflowError("Alt akış bağlantıları ajan inceleme sınırını aşıyor.")
        if not isinstance(identity, str) or not WORKFLOW_ID.fullmatch(identity):
            raise WorkflowError("Ajan akışlarında alt akış kimliği sabit ve geçerli olmalıdır.")
        if allowed is not None and identity not in allowed:
            raise WorkflowError("Ajanın bu akışı veya alt akışı çalıştırma izni yok.")
        if identity in stack or len(stack) > 5:
            raise WorkflowError("Alt akışlarda döngü veya derinlik sınırı aşımı bulundu.")
        if identity in graph:
            workflow = graph[identity]
        else:
            try:
                workflow = store.workflow(identity).model_copy(deep=True)
            except (KeyError, ValueError, OSError):
                raise WorkflowError("İzin verilen akış veya alt akış bulunamadı.") from None
        graph[identity] = workflow
        for step in walk_steps(workflow.steps):
            if step.action == "control.run_workflow":
                visit(step.params.get("workflow"), (*stack, identity))

    visit(workflow_id)
    return graph


def _graph_fingerprint(workflow_id, graph):
    included = {}

    def visit(identity):
        if identity in included:
            return
        item = graph[identity]
        included[identity] = item.model_dump(mode="json")
        for step in walk_steps(item.steps):
            if step.action == "control.run_workflow":
                visit(step.params["workflow"])

    visit(workflow_id)
    return _hash(included)


def workflow_fingerprint(workflow_id: str, store) -> str:
    return _graph_fingerprint(workflow_id, _load_graph(workflow_id, store))


@dataclass(frozen=True)
class PreparedWorkflow:
    root: Workflow
    workflows: dict[str, Workflow]
    inputs: dict[str, Any]
    digest: str
    risk: str
    approval_required: bool
    workflow_fingerprints: dict[str, str]
    grants: dict[str, Any]
    agent_id: str
    agent_revision: int
    actor: dict[str, Any]


def _supported(workflow, grant):
    from ..catalog import BY_TYPE
    from ..engine import variable_name

    for step in walk_steps(workflow.steps):
        if step.action not in BY_TYPE:
            raise WorkflowError("Akışta ajan tarafından desteklenmeyen adım türü var.")
        if step.action in UNSUPPORTED or step.action.startswith(("web.", "browser.")):
            raise WorkflowError(f"“{BY_TYPE[step.action]['label']}” adımının hedef sınırı ajan için güvenle "
                                "doğrulanamıyor; bu akış elle çalıştırılabilir.")
        raw = parameters(step)
        if step.action == "desktop.find_window":
            application = raw.get("application")
            if not isinstance(application, str) or not application.strip() or "${" in application:
                raise WorkflowError("Ajanın Pencereyi tanı adımında uygulama adı sabit ve dolu olmalıdır.")
            if _unsafe_application(application):
                raise WorkflowError("Ajan kabuk, tarayıcı, dosya yöneticisi veya Studio penceresini yönetemez.")
        if step.action in FILE_FIELDS and not grant.allowed_roots:
            raise WorkflowError("Dosya adımları için ajanın akış izninde izin verilen klasörleri belirtin.")
        if step.action in {"screen.read_text", "screen.wait_text", "screen.find_image", "screen.click_image"}:
            if raw.get("relative_to") != "window":
                raise WorkflowError("Ajanın ekran adımı yalnız tanıtılmış bir pencere içinde çalışabilir.")
        if step.action == "control.try" and raw.get("screenshot"):
            raise WorkflowError("Ajan akışlarında hata ekranı otomatik kaydedilemez; gizli veri içerebilir.")
        if step.action == "file.list" and raw.get("recursive"):
            raise WorkflowError("Ajanın dosya listesinde alt klasörleri tarama bu sürümde desteklenmiyor.")
        for key in ("output", "item_name", "error_name"):
            if raw.get(key):
                variable_name(raw[key])
            if raw.get(key) in RESERVED:
                raise WorkflowError("Ayrılmış sistem değişkenleri bir adımın hedefi olamaz.")
        if step.action in {"core.set", "data.append"} and raw.get("name") in RESERVED:
            raise WorkflowError("Ayrılmış sistem değişkenleri değiştirilemez.")
        if step.action in {"core.set", "data.append"}:
            variable_name(raw.get("name"))


def prepare_workflow(agent, workflow_id: str, store, inputs, *, actor=None) -> PreparedWorkflow:
    if agent.role == "manager":
        raise WorkflowError("Yönetici ajan akış çalıştıramaz; görevi departman ajanına devretmelidir.")
    if actor is not None and actor.company_id != agent.company_id:
        raise WorkflowError("Başka firmanın ajanı kullanılamaz.")
    validated = json.loads(canonical(validate_inputs(inputs)))
    grants = {grant.workflow_id: grant.model_copy(deep=True) for grant in agent.workflows}
    graph = _load_graph(workflow_id, store, allowed=set(grants))
    for identity, workflow in graph.items():
        _supported(workflow, grants[identity])
    fingerprints = {identity: _graph_fingerprint(identity, graph) for identity in graph}
    risk = workflow_risk(graph[workflow_id], graph)
    approval = any(workflow_risk(workflow, graph) == WRITE and not (
        grants[identity].allow_without_approval
        and agent.grant_revisions.get(identity) == fingerprints[identity]
    ) for identity, workflow in graph.items())
    actor_info = ({"user_id": actor.user_id, "company_id": actor.company_id, "session_id": actor.session_id}
                  if actor is not None else {"user_id": agent.user_id, "company_id": agent.company_id})
    digest = _hash({"agent_id": agent.id, "revision": agent.revision, "actor": actor_info,
                    "workflows": fingerprints, "inputs": validated,
                    "grants": {key: grant.model_dump(mode="json") for key, grant in grants.items()}})
    return PreparedWorkflow(graph[workflow_id].model_copy(deep=True), graph, validated, digest, risk, approval,
                            fingerprints, grants, agent.id, agent.revision, actor_info)


class AgentExecutionPolicy:
    def __init__(self, prepared: PreparedWorkflow, *, check_callback=None, secrets=(), protected_roots=(),
                 window_validator=None):
        self.prepared = prepared
        self.check_callback = check_callback
        self.window_validator = window_validator
        self.redactor = Redactor(secrets)
        self.tainted: set[str] = set()
        self._frames: list[tuple[str, bool, set[str]]] = []
        self._known_windows: set[str] = set()
        package_root = Path(__file__).resolve().parents[1]
        self.protected_roots = [package_root, *(Path(root).expanduser().resolve() for root in protected_roots)]
        self._steps = {}
        for identity, workflow in prepared.workflows.items():
            for step in walk_steps(workflow.steps):
                self._steps.setdefault(_hash(step.model_dump(mode="json")), []).append(identity)

    def check(self) -> None:
        if self.check_callback:
            self.check_callback()

    def authorize_workflow(self, workflow_id: str) -> Workflow:
        self.check()
        if workflow_id not in self.prepared.workflows:
            _stop("Ajanın bu alt akışı çalıştırma izni yok.")
        return self.prepared.workflows[workflow_id].model_copy(deep=True)

    def remember_secret(self, value) -> None:
        self.redactor.remember(value)

    def _remember_tree(self, value, depth=0) -> None:
        if depth > 20:
            return
        if type(value) is str:
            self.remember_secret(value)
        elif type(value) in (int, float):
            self.remember_secret(str(value))
        elif type(value) is dict:
            for part in value.values():
                self._remember_tree(part, depth + 1)
        elif type(value) in (list, tuple):
            for part in value:
                self._remember_tree(part, depth + 1)

    def sanitize(self, value):
        return self.redactor.sanitize(value)

    def mask(self, message: str) -> str:
        if any(frame[1] for frame in self._frames):
            return "Gizli veri içeren adımın ayrıntısı gizlendi."
        return self.redactor.text(message)

    def snapshot(self, variables: dict) -> dict:
        clean = {key: value for key, value in variables.items() if key not in RESERVED and key not in self.tainted}
        result = self.sanitize(clean)
        return result if isinstance(result, dict) else {"bilgi": result}

    def _path(self, raw, grants):
        if not isinstance(raw, str) or not raw or any(token in raw for token in ("*", "?", "\x00")):
            _stop("Ajan dosya adımı açık bir dosya veya klasör yolu gerektirir.")
        candidate = Path(os.path.expandvars(os.path.expanduser(raw)))
        if not candidate.is_absolute():
            _stop("Ajan dosya yolu mutlak olmalıdır.")
        resolved = candidate.resolve()
        if any(part.casefold() in {"credentials", ".git", ".ssh", ".aws", ".azure"} for part in resolved.parts):
            _stop("Kimlik bilgisi veya uygulama yönetimi klasörüne ajan erişemez.")
        if any(resolved == root or root in resolved.parents for root in self.protected_roots):
            _stop("Studio dosyalarına ajan erişemez.")
        for grant in grants:
            roots = [Path(root).expanduser().resolve() for root in grant.allowed_roots]
            if not any(resolved == root or root in resolved.parents for root in roots):
                _stop("Dosya yolu bu akış için izin verilen klasörlerin dışında.")
        # Handlers may traverse symlinks after this guard. Reject them rather than granting their targets.
        if any(item.is_symlink() for item in (candidate, *candidate.parents)):
            _stop("Ajan dosya yolunda sembolik bağlantı kullanılamaz.")
        return resolved

    def _window(self, value):
        if type(value) is not dict or value.get("found") is not True or _hash(value) not in self._known_windows:
            _stop("Ajan yalnız bu çalışmada tanıtılmış pencereyi kullanabilir.")
        if value.get("pid") == os.getpid() or _unsafe_application(value.get("application", "")):
            _stop("Ajan kabuk, tarayıcı, dosya yöneticisi veya Studio penceresini yönetemez.")
        if self.window_validator is None:
            _stop("Pencere güvenliği doğrulanamadı; ajan masaüstü işlemi durduruldu.")
        self.window_validator(value)

    def before_step(self, step, resolved_params, variables):
        self.check()
        identities = self._steps.get(_hash(step.model_dump(mode="json")))
        if not identities:
            _stop("Adım onaylanan akış tanımında bulunmuyor.")
        grants = [self.prepared.grants[identity] for identity in identities]
        raw = parameters(step)
        sensitive = bool(reads(step) & (self.tainted | {"sifre"})) or any(frame[1] for frame in self._frames)
        self._frames.append((step.id, sensitive, produces(step)))
        if sensitive:
            self._remember_tree(resolved_params)
        for field in FILE_FIELDS.get(step.action, ()):
            value = resolved_params.get(field)
            if field == "destination" and resolved_params.get("operation") in {"delete", "create_folder"}:
                continue
            path = self._path(value, grants)
            if step.action == "file.operation" and field == "source" and path.is_dir() \
                    and resolved_params.get("operation") != "create_folder":
                _stop("Ajanın klasör taşıma, kopyalama veya silme işlemi bu sürümde desteklenmiyor.")
            if step.action == "file.list" and path.is_dir() and any(item.is_symlink() for item in path.iterdir()):
                _stop("Listelenecek klasörde sembolik bağlantı var; ajan işlemi durduruldu.")
            if step.action == "file.operation" and field == "destination" and path.is_dir():
                self._path(str(path / Path(resolved_params["source"]).name), grants)
        if "window" in raw:
            self._window(resolved_params.get("window"))
        if step.action == "desktop.find_window":
            if any("rpaorkestrai" in str(resolved_params.get(key, "")).casefold() for key in ("application", "title")):
                _stop("Ajan Studio penceresini hedefleyemez.")
        if step.action == "mail.send":
            attachments = resolved_params.get("attachments")
            if attachments:
                _stop("Ajan e-postasına dosya ekleme bu sürümde desteklenmiyor.")

    def after_step(self, step, result, variables):
        if not self._frames or self._frames[-1][0] != step.id:
            return
        _, sensitive, outputs = self._frames.pop()
        if sensitive:
            self.tainted.update(outputs)
            for key in outputs:
                self._remember_tree(variables.get(key))
            self._remember_tree(result)
        if step.action in {"desktop.find_window", "window.move"}:
            for key in outputs:
                value = variables.get(key)
                if type(value) is dict and value.get("found") is True:
                    if value.get("pid") == os.getpid() or _unsafe_application(value.get("application", "")):
                        _stop("Ajan kabuk, tarayıcı, dosya yöneticisi veya Studio penceresini kullanamaz.")
                    self._known_windows.add(_hash(value))

    def artifact(self, name: str, data: bytes) -> bytes:
        if Path(name).suffix.casefold() not in {".txt", ".csv", ".json"}:
            _stop("Ajan yalnız temizlenebilir metin, CSV veya JSON çıktısı oluşturabilir.")
        if any(frame[1] for frame in self._frames):
            return MASK.encode("utf-8")
        try:
            content = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            _stop("Çıktı UTF-8 metni olarak doğrulanamadı.")
        if Path(name).suffix.casefold() == ".json":
            try:
                return json.dumps(self.sanitize(json.loads(content)), ensure_ascii=False, allow_nan=False).encode("utf-8")
            except (ValueError, TypeError, RecursionError):
                _stop("JSON çıktısı güvenli biçimde temizlenemedi.")
        return self.redactor.text(content).encode("utf-8")

    def finish(self, executor):
        return self.snapshot(executor.variables)
