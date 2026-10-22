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
FILE_FIELDS = {
    "file.read_text": ("path",), "file.write_text": ("path",), "file.read_table": ("path",),
    "file.write_table": ("path",), "file.read_pdf": ("path",), "file.exists": ("path",), "file.info": ("path",),
    "file.list": ("folder",), "file.wait": ("path",), "file.operation": ("source", "destination"),
    "mail.read": ("attachment_folder",), "ftp.transfer": ("local_path",), "ui.choose_file": ("folder",),
}
# Steps whose server is fixed by a named connection; the connection itself must not come from a variable.
CONNECTION_STEPS = {"http.request", "database.query", "database.execute", "mail.read", "ftp.transfer", "notify.send",
                    "mail.send"}


def _file_field_used(action, raw) -> bool:
    if action == "mail.read":
        return bool(str(raw.get("attachment_folder") or "").strip())
    if action == "ftp.transfer":
        return raw.get("operation", "download") != "list"
    return True
def _studio_application(value):
    """The Studio itself is never an agent's target: it would approve its own requests."""
    return "rpaorkestrai" in str(value or "").casefold()


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
    """A flow given to an agent may run every step it has (risky ones wait for approval unless the grant says
    otherwise). Only what would let the agent leave its grant is refused: unknown steps, the Studio as a target and
    the system variables."""
    from ..catalog import BY_TYPE
    from ..engine import variable_name

    for step in walk_steps(workflow.steps):
        if step.action not in BY_TYPE:
            raise WorkflowError("Akışta bu Studio sürümünün tanımadığı bir adım türü var; Studio'yu güncelleyin.")
        raw = parameters(step)
        if step.action == "desktop.find_window" and any(_studio_application(raw.get(key)) for key in ("application",
                                                                                                    "title")):
            raise WorkflowError("Ajan Studio penceresini hedefleyemez.")
        for key in ("output", "item_name", "error_name"):
            if raw.get(key):
                variable_name(raw[key])
            if raw.get(key) in RESERVED:
                raise WorkflowError("Ayrılmış sistem değişkenleri bir adımın hedefi olamaz.")
        if step.action in {"core.set", "data.append"} and raw.get("name") in RESERVED:
            raise WorkflowError("Ayrılmış sistem değişkenleri değiştirilemez.")
        if step.action in {"core.set", "data.append"}:
            variable_name(raw.get("name"))


def inspect_workflow(workflow_id, store):
    """Editor-only capabilities; never constructs execution permissions or approval tokens."""
    graph = _load_graph(workflow_id, store)
    for workflow in graph.values():
        _supported(workflow, None)
    return {"requires_roots": any(step.action in FILE_FIELDS for workflow in graph.values()
                                  for step in walk_steps(workflow.steps)),
            "dependencies": [key for key in graph if key != workflow_id]}


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
        if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
            _stop("Ajan dosya adımında dosya veya klasör yolu boş.")
        candidate = Path(os.path.expandvars(os.path.expanduser(raw)))
        # A pattern (rapor*.xlsx) is checked by the folder it looks in.
        if any(token in candidate.name for token in ("*", "?")):
            candidate = candidate.parent
        resolved = candidate.resolve()
        if any(part.casefold() in {"credentials", ".git", ".ssh", ".aws", ".azure"} for part in resolved.parts):
            _stop("Kimlik bilgisi veya uygulama yönetimi klasörüne ajan erişemez.")
        if any(resolved == root or root in resolved.parents for root in self.protected_roots):
            _stop("Studio dosyalarına ajan erişemez.")
        for grant in grants:
            if not grant.allowed_roots:
                continue  # No folders named for this flow: its paths are not limited.
            roots = [Path(root).expanduser().resolve() for root in grant.allowed_roots]
            if not any(resolved == root or root in resolved.parents for root in roots):
                _stop("Dosya yolu bu akış için izin verilen klasörlerin dışında.")
            # Inside named folders a link could point outside them.
            if any(item.is_symlink() for item in (candidate, *candidate.parents)):
                _stop("Ajan dosya yolunda sembolik bağlantı kullanılamaz.")
        return resolved

    def _window(self, value):
        if type(value) is not dict or value.get("found") is not True or _hash(value) not in self._known_windows:
            _stop("Ajan yalnız bu çalışmada tanıtılmış pencereyi kullanabilir.")
        if value.get("pid") == os.getpid() or _studio_application(value.get("application")):
            _stop("Ajan Studio penceresini yönetemez.")
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
            if not _file_field_used(step.action, resolved_params):
                continue
            path = self._path(value, grants)
            if step.action == "file.operation" and field == "destination" and path.is_dir():
                self._path(str(path / Path(str(resolved_params.get("source") or "x")).name), grants)
        if "window" in raw:
            self._window(resolved_params.get("window"))
        if step.action == "desktop.find_window":
            if any("rpaorkestrai" in str(resolved_params.get(key, "")).casefold() for key in ("application", "title")):
                _stop("Ajan Studio penceresini hedefleyemez.")

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
                    if value.get("pid") == os.getpid() or _studio_application(value.get("application")):
                        _stop("Ajan Studio penceresini kullanamaz.")
                    self._known_windows.add(_hash(value))

    def artifact(self, name: str, data: bytes) -> bytes:
        if any(frame[1] for frame in self._frames):
            return MASK.encode("utf-8")
        if Path(name).suffix.casefold() not in {".txt", ".csv", ".json"}:
            # Excel, PDF, images are kept as the flow made them; they cannot be masked, so a saved secret written
            # into one stops the run instead.
            if self.redactor.contains_secret(data.decode("utf-8", errors="ignore")):
                _stop("Çıktı dosyası kayıtlı bir gizli değer içeriyor; ajan bu dosyayı kaydetmedi.")
            return data
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
