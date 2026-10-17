"""Ajan tanımları ve güvenilir sunucu kimliğinden ayrılan istek modelleri."""

from __future__ import annotations

import json
import math
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, field_validator, model_validator

from ..models import Model, now, uid

Identifier = Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]
RunStatus = Literal["queued", "running", "waiting_user", "waiting_approval", "succeeded", "failed", "cancelled"]
TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})
RESERVED_INPUTS = frozenset({"sistem", "sifre", "loop_index"})
JSON_LIMIT = 64 * 1024


def validate_json_value(value: Any, *, max_bytes: int = JSON_LIMIT, max_depth: int = 20) -> Any:
    """Accept JSON values only, before Pydantic can silently coerce Python objects."""
    active: set[int] = set()
    nodes = 0

    def visit(current: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if depth > max_depth or nodes > 20_000:
            raise ValueError("JSON verisi izin verilen derinlik veya öğe sınırını aşıyor.")
        kind = type(current)
        if current is None or kind in (str, bool, int):
            return
        if kind is float:
            if not math.isfinite(current):
                raise ValueError("JSON sayıları sonlu olmalıdır.")
            return
        if kind not in (dict, list):
            raise ValueError("Yalnız JSON metni, sayısı, mantıksal değeri, listesi, nesnesi veya null kullanılabilir.")
        identity = id(current)
        if identity in active:
            raise ValueError("JSON verisi döngüsel başvuru içeremez.")
        active.add(identity)
        try:
            if kind is dict:
                for key, child in current.items():
                    if type(key) is not str:
                        raise ValueError("JSON nesnesindeki alan adları metin olmalıdır.")
                    visit(child, depth + 1)
            else:
                for child in current:
                    visit(child, depth + 1)
        finally:
            active.remove(identity)

    visit(value, 0)
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, OverflowError) as exc:
        raise ValueError("JSON verisi geçerli biçimde kodlanamadı.") from exc
    if len(encoded) > max_bytes:
        raise ValueError(f"JSON verisi en fazla {max_bytes} bayt olabilir.")
    return value


def validate_inputs(value: Any, *, max_bytes: int = JSON_LIMIT) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError("Akış girdileri bir JSON nesnesi olmalıdır.")
    if len(value) > 100:
        raise ValueError("En fazla 100 girdi alanı kullanılabilir.")
    # Keep the engine's variable-name rule authoritative without an import cycle.
    from ..engine import variable_name

    for name in value:
        try:
            variable_name(name)
        except Exception as exc:
            raise ValueError("Girdi adı geçersiz; ad harfle başlamalı ve yalnız harf, rakam, alt çizgi içermelidir.") from exc
        if name in RESERVED_INPUTS:
            raise ValueError("Sistem, şifre ve döngü kapsamı değişkenleri girdi olarak kullanılamaz.")
    return validate_json_value(value, max_bytes=max_bytes)


class Actor(Model):
    """Populated only from verified claims; never used as an incoming API body."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)

    user_id: int = Field(ge=1)
    company_id: int = Field(ge=1)
    name: str = Field(default="", max_length=200)
    session_id: str = Field(min_length=1, max_length=200)
    permissions: tuple[str, ...] = Field(default_factory=tuple, max_length=100)

    @property
    def can_approve(self) -> bool:
        return "agents.approve" in self.permissions


class AgentLimits(Model):
    max_turns: int = Field(default=20, ge=1, le=1000)
    max_workflow_runs: int = Field(default=10, ge=0, le=1000)
    max_seconds: float = Field(default=1800, gt=0, le=86_400)
    max_tokens: int = Field(default=50_000, ge=1, le=10_000_000)
    max_retries: int = Field(default=1, ge=0, le=10)
    max_tasks: int = Field(default=20, ge=1, le=1000)
    busy_wait_seconds: float = Field(default=60, ge=0, le=3600)
    approval_timeout_seconds: float = Field(default=900, gt=0, le=86_400)
    question_timeout_seconds: float = Field(default=900, gt=0, le=86_400)


class WorkflowGrant(Model):
    workflow_id: Identifier
    allow_without_approval: bool = False
    allowed_roots: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(
        default_factory=list, max_length=100,
    )
    allowed_hosts: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(
        default_factory=list, max_length=100,
    )


MAX_PLAYBOOKS = 30
MAX_KNOWLEDGE_SOURCES = 50


class Playbook(Model):
    """Süreç kartı: a topic and how the firm handles it. It narrows what the agent may do, never widens it."""

    id: Identifier = Field(default_factory=uid)
    title: str = Field(min_length=1, max_length=120)
    when: str = Field(default="", max_length=1000)
    steps: str = Field(min_length=1, max_length=2000)
    workflow_ids: list[Identifier] = Field(default_factory=list, max_length=20)
    # act: the flow grants decide; review: every change is presented for approval; handoff: no changes, a person takes over.
    mode: Literal["act", "review", "handoff"] = "act"

    @field_validator("title", "when", "steps")
    @classmethod
    def trimmed(cls, value: str) -> str:
        return value.strip()


class AgentInput(Model):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    instructions: str = Field(default="", max_length=16_000)
    role: Literal["manager", "department"] = "department"
    department: str = Field(default="Genel", min_length=1, max_length=120)
    manager_id: Identifier | None = None
    provider_connection_id: Identifier | None = None
    model: str = Field(default="", max_length=200)
    workflows: list[WorkflowGrant] = Field(default_factory=list, max_length=500)
    limits: AgentLimits = Field(default_factory=AgentLimits)
    # Internet research: off, only the listed sites, or the open web. Read-only search and page reading.
    web_access: Literal["off", "allowlist", "open"] = "off"
    web_domains: list[Annotated[str, Field(min_length=3, max_length=255)]] = Field(default_factory=list, max_length=50)
    # Firm documents (files or folders on this computer) the agent searches before answering.
    knowledge_sources: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(
        default_factory=list, max_length=MAX_KNOWLEDGE_SOURCES)
    playbooks: list[Playbook] = Field(default_factory=list, max_length=MAX_PLAYBOOKS)

    @field_validator("knowledge_sources")
    @classmethod
    def clean_sources(cls, value: list[str]) -> list[str]:
        from .knowledge import normalize_source

        cleaned = []
        for item in value:
            source = normalize_source(item)
            if source not in cleaned:
                cleaned.append(source)
        return cleaned

    @field_validator("web_domains")
    @classmethod
    def clean_domains(cls, value: list[str]) -> list[str]:
        from .web import normalize_domain

        cleaned = []
        for item in value:
            domain = normalize_domain(item)
            if domain not in cleaned:
                cleaned.append(domain)
        return cleaned

    @model_validator(mode="after")
    def unique_grants(self) -> AgentInput:
        identities = [grant.workflow_id for grant in self.workflows]
        if len(identities) != len(set(identities)):
            raise ValueError("Bir akışın izni yalnız bir kez tanımlanabilir.")
        if self.role == "manager" and self.workflows:
            raise ValueError("Yönetici ajan akış çalıştırma iznine sahip olamaz.")
        if self.role == "manager" and self.manager_id is not None:
            raise ValueError("Yönetici ajan başka bir yöneticiye bağlanamaz.")
        if self.web_access == "allowlist" and not self.web_domains:
            raise ValueError("Yalnız izinli siteler seçildiğinde en az bir site yazın (ör. mevzuat.gov.tr).")
        titles = [card.title.casefold() for card in self.playbooks]
        if len(titles) != len(set(titles)):
            raise ValueError("Süreç kartlarının başlıkları birbirinden farklı olmalıdır.")
        if len({card.id for card in self.playbooks}) != len(self.playbooks):
            raise ValueError("Süreç kartı kimlikleri tekrarlanamaz.")
        granted = set(identities)
        for card in self.playbooks:
            if not set(card.workflow_ids) <= granted:
                raise ValueError(f"«{card.title}» kartındaki akışlar ajanın izinli akışları arasında olmalıdır.")
        return self


class PermissionChange(Model):
    timestamp: str = Field(default_factory=now)
    user_id: int = Field(ge=1)
    workflow_id: Identifier
    allow_without_approval: bool
    workflow_revision: str | None = Field(default=None, max_length=128)


class Agent(AgentInput):
    id: Identifier = Field(default_factory=uid)
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
    company_id: int = Field(ge=1)
    user_id: int = Field(ge=1)
    revision: int = Field(default=1, ge=1)
    grant_revisions: dict[Identifier, Annotated[str, Field(max_length=128)]] = Field(default_factory=dict)
    permission_audit: list[PermissionChange] = Field(default_factory=list, max_length=1000)


MAX_NOTES = 30
MAX_NOTE_CHARACTERS = 500
MAX_NOTES_TOTAL = 4000


class NoteInput(Model):
    text: str = Field(min_length=1, max_length=MAX_NOTE_CHARACTERS)
    source_run_id: Identifier | None = None


class AgentNote(Model):
    """Approved knowledge only: it is shown to the model, but never grants permissions."""

    id: Identifier = Field(default_factory=uid)
    text: str = Field(min_length=1, max_length=MAX_NOTE_CHARACTERS)
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
    user_id: int = Field(ge=1)
    user_name: str = Field(default="", max_length=200)
    source_run_id: Identifier | None = None


class AgentNotes(Model):
    """Kept outside Agent so a note neither changes the permission revision nor old agent files."""

    id: Identifier
    company_id: int = Field(ge=1)
    notes: list[AgentNote] = Field(default_factory=list, max_length=MAX_NOTES)


class AgentEvent(Model):
    id: Identifier = Field(default_factory=uid)
    timestamp: str = Field(default_factory=now)
    kind: str = Field(min_length=1, max_length=80)
    message: str = Field(default="", max_length=20_000)
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data", mode="before")
    @classmethod
    def bounded_data(cls, value: Any) -> Any:
        return validate_json_value(value)


class AgentRunRequest(Model):
    task: str = Field(min_length=1, max_length=16_000)
    title: str = Field(default="", max_length=200)
    inputs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("inputs", mode="before")
    @classmethod
    def bounded_inputs(cls, value: Any) -> dict[str, Any]:
        return validate_inputs(value)


# Kept local to this package; the workflow RunRequest remains unchanged.
RunRequest = AgentRunRequest


class AgentRun(AgentRunRequest):
    id: Identifier = Field(default_factory=uid)
    agent_id: Identifier
    actor: Actor
    agent_revision: int = Field(ge=1)
    task_id: Identifier | None = None
    parent_run_id: Identifier | None = None
    root_run_id: Identifier | None = None
    delegated_task_ids: list[Identifier] = Field(default_factory=list, max_length=1000)
    status: RunStatus = "queued"
    created_at: str = Field(default_factory=now)
    started_at: str | None = None
    finished_at: str | None = None
    events: list[AgentEvent] = Field(default_factory=list, max_length=2000)
    workflow_run_ids: list[Identifier] = Field(default_factory=list, max_length=1000)
    turns: int = Field(default=0, ge=0)
    workflow_count: int = Field(default=0, ge=0)
    tokens_in: int = Field(default=0, ge=0)
    tokens_out: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    approval_wait_seconds: float = Field(default=0, ge=0)
    team_usage: dict[str, int | float] = Field(default_factory=dict)
    error: str | None = Field(default=None, max_length=2000)
    summary: str = Field(default="", max_length=20_000)
    result: Any = None
    pending_question: dict[str, Any] | None = None
    pending_approval: dict[str, Any] | None = None
    # The süreç kartı last chosen and whether the agent left the work to a person.
    playbook_id: Identifier | None = None
    handoff: bool = False
    handoff_resolved_at: str | None = None
    handoff_resolved_by: str | None = Field(default=None, max_length=200)

    @field_validator("result", "pending_question", "pending_approval", mode="before")
    @classmethod
    def bounded_json(cls, value: Any) -> Any:
        return validate_json_value(value)


class AgentTask(Model):
    """Task identity is distinct from the human, agent and machine doing the work."""

    id: Identifier = Field(default_factory=uid)
    company_id: int = Field(ge=1)
    parent_task_id: Identifier | None = None
    created_by: Actor
    assigned_agent_id: Identifier | None = None
    assignee_type: Literal["human", "agent"] = "agent"
    assignee_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(default="", max_length=16_000)
    run_id: Identifier | None = None
    root_run_id: Identifier | None = None
    agent_name: str = Field(default="", max_length=120)
    department: str = Field(default="", max_length=120)
    provider_connection_id: Identifier | None = None
    model: str = Field(default="", max_length=200)
    priority: Literal["high", "normal", "low"] = "normal"
    status: RunStatus = "queued"
    created_at: str = Field(default_factory=now)
    started_at: str | None = None
    finished_at: str | None = None
    workflow_run_ids: list[Identifier] = Field(default_factory=list, max_length=1000)
    tokens_in: int = Field(default=0, ge=0)
    tokens_out: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    approval_wait_seconds: float = Field(default=0, ge=0)
    events: list[AgentEvent] = Field(default_factory=list, max_length=2000)
    approvals: list[AgentEvent] = Field(default_factory=list, max_length=1000)
    error: str | None = Field(default=None, max_length=2000)
    summary: str = Field(default="", max_length=20_000)
    result: Any = None

    @field_validator("result", mode="before")
    @classmethod
    def bounded_result(cls, value: Any) -> Any:
        return validate_json_value(value)

    @model_validator(mode="after")
    def consistent_assignment(self) -> AgentTask:
        if self.created_by.company_id != self.company_id:
            raise ValueError("Görevi oluşturan kişi aynı firmaya ait olmalıdır.")
        if self.assignee_type == "human" and self.assigned_agent_id is not None:
            raise ValueError("İnsan çalışan görevine ajan kimliği atanamaz.")
        if self.assignee_type == "agent" and self.assigned_agent_id not in (None, self.assignee_id):
            raise ValueError("Atanan ajan kimlikleri birbiriyle tutarlı olmalıdır.")
        return self


class ProviderConnection(Model):
    """Only metadata belongs in JSON; a key is never a model field."""

    id: Identifier = Field(default_factory=uid)
    name: str = Field(min_length=1, max_length=120)
    provider: Literal["fake", "openai", "gemini", "anthropic", "ollama", "local_openai", "shared"]
    model: str = Field(default="", max_length=200)
    base_url: str | None = Field(default=None, max_length=2000)
    company_id: int = Field(ge=1)
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)

    @model_validator(mode="after")
    def endpoint_has_no_credentials(self) -> ProviderConnection:
        if self.base_url is None:
            return self
        if self.provider not in {"ollama", "local_openai"}:
            raise ValueError("Bulut sağlayıcısının adresi değiştirilemez.")
        try:
            parsed = urlsplit(self.base_url)
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                    or parsed.query or parsed.fragment or parsed.port == 0):
                raise ValueError
        except ValueError:
            raise ValueError("Model sunucusu adresi geçersiz; adres şifre, sorgu veya parça içeremez.") from None
        return self
