"""Modelin yalnız izinli akışlar üzerinden kullanabildiği doğrulanmış araçlar."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError, field_validator

from ..errors import WorkflowError
from ..models import Model, walk_steps
from .contracts import infer_contract
from .models import Identifier, validate_inputs, validate_json_value
from .policy import AgentExecutionPolicy, prepare_workflow
from .providers import ToolCall


class Empty(Model):
    pass


class WorkflowArgument(Model):
    workflow_id: Identifier


class WorkflowRunArgument(WorkflowArgument):
    inputs: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("inputs", mode="before")
    @classmethod
    def valid_inputs(cls, value):
        return validate_inputs(value)


class RunArgument(Model):
    run_id: Identifier


class RecentArgument(WorkflowArgument):
    limit: int = Field(default=5, ge=1, le=20)


class ArtifactArgument(RunArgument):
    artifact_id: Identifier


class QuestionArgument(Model):
    question: str = Field(min_length=1, max_length=4000)
    options: list[str] | None = Field(default=None, max_length=10)

    @field_validator("options")
    @classmethod
    def short_options(cls, value):
        if value is not None and any(not item or len(item) > 200 for item in value):
            raise ValueError("Yanıt seçenekleri 1–200 karakter olmalıdır.")
        return value


class FinishArgument(Model):
    summary: str = Field(min_length=1, max_length=20_000)
    result: Any = None

    @field_validator("result", mode="before")
    @classmethod
    def bounded_result(cls, value):
        return validate_json_value(value)


class DelegateArgument(Model):
    agent_id: Identifier
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(min_length=1, max_length=16_000)
    inputs: dict[str, Any] = Field(default_factory=dict)
    priority: Literal["high", "normal", "low"] = "normal"

    @field_validator("inputs", mode="before")
    @classmethod
    def valid_inputs(cls, value):
        return validate_inputs(value)


class TaskArgument(Model):
    task_id: Identifier


class TaskFilter(Model):
    agent_id: Identifier | None = None
    status: Literal["queued", "running", "waiting_user", "waiting_approval", "succeeded", "failed", "cancelled"] | None = None


class TasksArgument(Model):
    filter: TaskFilter | None = None


class WaitArgument(Model):
    until: Literal["any", "all"] = "all"


class AnswerArgument(Model):
    question_id: Identifier
    answer: str = Field(min_length=1, max_length=4000)


TOOLS = {
    "list_workflows": (Empty, "Yalnız ajana izin verilen akışları ve beklenen girdilerini listeler."),
    "describe_workflow": (WorkflowArgument, "İzinli akışın güvenli adım ve değişken özetini verir."),
    "run_workflow": (WorkflowRunArgument, "İzinli akışı çalıştırır; gerekli kullanıcı onayını sunucu ister."),
    "get_run": (RunArgument, "İzinli akışın çalışmasının güvenli durum özetini verir."),
    "list_recent_runs": (RecentArgument, "İzinli akışın yakın geçmişteki çalışmalarını listeler."),
    "read_artifact": (ArtifactArgument, "Yalnız bu ajan çalışmasının metin, CSV veya JSON çıktısını okur."),
    "ask_user": (QuestionArgument, "Belirsizlikte kullanıcıdan yanıt bekler."),
    "finish": (FinishArgument, "Çalışmayı kısa özet ve yapılandırılmış sonuçla bitirir."),
    "list_team": (Empty, "Yöneticiye doğrudan bağlı departman ajanlarını ve kuyruklarını listeler."),
    "delegate_task": (DelegateArgument, "Görevi doğrudan bağlı departman ajanının kuyruğuna ekler."),
    "get_task": (TaskArgument, "Yöneticinin bu çalışma kapsamında devrettiği görevin durumunu verir."),
    "list_tasks": (TasksArgument, "Yöneticinin bu çalışma kapsamında devrettiği görevleri listeler."),
    "wait_tasks": (WaitArgument, "Devredilen görevlerden biri ('any') veya tümü ('all') bitene ya da bir departman "
                                 "ajanı soru sorana kadar bekler."),
    "answer_department": (AnswerArgument, "Departman ajanının yöneticiye sorduğu soruyu yanıtlar. Bilmediğin konuda "
                                          "yanıt uydurma; önce ask_user ile kullanıcıya sor."),
    "ask_manager": (QuestionArgument, "Görevi veren yöneticiye soru sorar ve yanıtını bekler."),
}
MANAGER_TOOLS = frozenset({"list_team", "delegate_task", "get_task", "list_tasks", "wait_tasks",
                           "answer_department", "ask_user", "finish"})
DEPARTMENT_TOOLS = frozenset(set(TOOLS) - MANAGER_TOOLS | {"ask_user", "finish"})


def tool_definitions(role="department", *, delegated=False) -> list[dict]:
    """Departman ajanı yöneticisine yalnız yöneticinin devrettiği görevde soru sorabilir."""
    allowed = MANAGER_TOOLS if role == "manager" else DEPARTMENT_TOOLS - (set() if delegated else {"ask_manager"})
    return [{"type": "function", "name": name, "description": description,
             "parameters": model.model_json_schema()} for name, (model, description) in TOOLS.items() if name in allowed]


class AgentTools:
    def __init__(self, service, context):
        self.service, self.context = service, context

    def execute(self, call: ToolCall):
        self.service._check(self.context)
        allowed = MANAGER_TOOLS if self.context.agent.role == "manager" else DEPARTMENT_TOOLS
        if call.name not in allowed:
            raise WorkflowError("Ajan bu aracı kullanamaz.")
        try:
            arguments = TOOLS[call.name][0].model_validate(call.arguments)
        except (ValidationError, ValueError):
            raise WorkflowError("Araç girdileri geçersiz veya izin verilen sınırların dışında.") from None
        return getattr(self, call.name)(arguments)

    def _prepared(self, workflow_id, inputs=None):
        return prepare_workflow(self.context.agent, workflow_id, self.service.store,
                                inputs or {}, actor=self.context.run.actor)

    def _description(self, prepared, *, steps=False):
        contract = infer_contract(prepared.root, prepared.workflows)
        result = {"id": prepared.root.id, "name": prepared.root.name, "description": prepared.root.description,
                  "department": prepared.root.department, "risk": prepared.risk,
                  "approval_required": prepared.approval_required, **contract.as_dict()}
        if steps:
            result["steps"] = [{"number": i, "title": step.title, "action": step.action}
                               for i, step in enumerate(walk_steps(prepared.root.steps), 1)][:200]
        return self.context.redactor.sanitize(result)

    def list_workflows(self, arguments):
        items = []
        for grant in self.context.agent.workflows:
            self.service._check(self.context)
            try:
                items.append(self._description(self._prepared(grant.workflow_id)))
            except (WorkflowError, KeyError):
                # A malformed or unsupported flow is not offered as an available tool.
                continue
        return {"workflows": items}

    def describe_workflow(self, arguments):
        return self._description(self._prepared(arguments.workflow_id), steps=True)

    def run_workflow(self, arguments):
        context, service = self.context, self.service
        prepared = self._prepared(arguments.workflow_id, arguments.inputs)
        contract = infer_contract(prepared.root, prepared.workflows)
        if set(contract.required_inputs) - set(prepared.inputs):
            raise WorkflowError("Akışın zorunlu girdileri eksik; eksik değerleri kullanıcıdan isteyin.")
        if context.run.workflow_count >= context.agent.limits.max_workflow_runs:
            service._stop(context, "Azami akış çalıştırma sayısına ulaşıldı.")
        if prepared.digest in context.failed_workflows:
            service._stop(context, "Hata veren akış aynı girdilerle yeniden çalıştırılamaz.")
        attempts = context.attempts.get(prepared.digest, 0)
        if attempts > context.agent.limits.max_retries:
            service._stop(context, "Akışın yeniden deneme sınırına ulaşıldı.")
        approval = None
        if prepared.approval_required or attempts:
            approval = service._wait_approval(context, prepared, arguments.reason)
            if approval is None:
                return {"status": "rejected", "message": "Kullanıcı onayı verilmedi; akış çalıştırılmadı."}
        policy = AgentExecutionPolicy(prepared, check_callback=lambda: service._check(context),
                                      protected_roots=[service.settings.data_dir, Path.cwd()])
        policy.redactor.merge(context.redactor)

        def launch():
            reservation = service.manager.reserve_desktop(context.cancel)
            try:
                service._check(context)
                current = service.agent_store.agent(context.agent.id)
                refreshed = prepare_workflow(current, arguments.workflow_id, service.store,
                                             prepared.inputs, actor=context.run.actor)
                if refreshed.digest != prepared.digest:
                    service._stop(context, "Akış, girdi veya izin değişti; önceki onay geçersizleşti.")
                if approval is not None:
                    service._consume_approval(context, approval, prepared.digest)
                service._check(context)
                current = service.agent_store.agent(context.agent.id)
                refreshed = prepare_workflow(current, arguments.workflow_id, service.store,
                                             prepared.inputs, actor=context.run.actor)
                if refreshed.digest != prepared.digest:
                    service._stop(context, "Onay tüketilirken akış veya izin değişti; akış başlatılmadı.")
                with service._lock:
                    service._check(context)
                    context.budget.add_workflow()
                    child = service.manager.start(prepared.root, variables=prepared.inputs, trigger="manual",
                                                  agent_context=policy, desktop_reservation=reservation)
                    context.active_workflow_id = child.id
                    context.run.workflow_run_ids.append(child.id)
                    context.run.workflow_count += 1
                    context.attempts[prepared.digest] = attempts + 1
                    service._event(context, "workflow_started", "Akış çalıştırılıyor.",
                                   {"run_id": child.id, "workflow_id": arguments.workflow_id})
                    return child
            finally:
                service.manager.release_desktop(reservation)

        service._event(context, "queue", "Akış çalıştırma sırası bekleniyor.", {"workflow_id": arguments.workflow_id})
        deadline = min(context.deadline, time.monotonic() + context.agent.limits.busy_wait_seconds)
        child = service.dispatch.start_agent(f"{context.run.id}:{context.current_call_id}", launch,
                                             cancel=context.cancel, deadline=deadline,
                                             check=lambda: service._check(context))
        if child is None:
            return {"status": "busy", "message": "Masaüstü bekleme süresinde boşalmadı; akış başlatılmadı."}
        try:
            while True:
                service._check(context)
                child = service.store.run(child.id)
                if child.finished_at and child.status in {"succeeded", "failed", "cancelled"}:
                    break
                context.cancel.wait(0.05)
        except BaseException:
            service.manager.stop_run(child.id, context.stop_reason)
            raise
        finally:
            context.redactor.merge(policy.redactor)
            context.active_workflow_id = None
            service._save(context)
        if child.status != "succeeded":
            context.failed_workflows.add(prepared.digest)
        return self._run_view(child, own=True)

    def _run_view(self, run, *, own=False):
        allowed = {grant.workflow_id for grant in self.context.agent.workflows}
        if run.workflow_id not in allowed:
            raise WorkflowError("Ajanın bu akışın çalışma kaydını görme izni yok.")
        result = {"id": run.id, "workflow_id": run.workflow_id, "status": run.status,
                  "started_at": run.started_at, "finished_at": run.finished_at}
        if own:
            result.update({"error": run.error, "variables": run.variables or {},
                           "artifacts": [{"id": item.id, "name": item.name} for item in run.artifacts]})
            try:
                result["duration_seconds"] = max(0, (datetime.fromisoformat(run.finished_at)
                                                     - datetime.fromisoformat(run.started_at)).total_seconds())
            except (TypeError, ValueError):
                result["duration_seconds"] = None
        return self.context.redactor.sanitize(result)

    def get_run(self, arguments):
        try:
            run = self.service.store.run(arguments.run_id)
        except (KeyError, ValueError):
            raise WorkflowError("Çalışma kaydı bulunamadı.") from None
        return self._run_view(run, own=run.id in self.context.run.workflow_run_ids)

    def list_recent_runs(self, arguments):
        if arguments.workflow_id not in {grant.workflow_id for grant in self.context.agent.workflows}:
            raise WorkflowError("Ajanın bu akışın çalışma geçmişine erişim izni yok.")
        runs = [run for run in self.service.store.runs() if run.workflow_id == arguments.workflow_id]
        return {"runs": [self._run_view(run, own=run.id in self.context.run.workflow_run_ids)
                         for run in runs[:arguments.limit]]}

    def read_artifact(self, arguments):
        if arguments.run_id not in self.context.run.workflow_run_ids:
            raise WorkflowError("Yalnız bu ajan çalışmasının oluşturduğu çıktı dosyası okunabilir.")
        run = self.service.store.run(arguments.run_id)
        self._run_view(run)
        artifact = next((item for item in run.artifacts if item.id == arguments.artifact_id), None)
        if artifact is None:
            raise WorkflowError("Çıktı dosyası bulunamadı.")
        suffix = Path(artifact.name).suffix.casefold()
        if suffix not in {".txt", ".csv", ".json"}:
            raise WorkflowError("Yalnız metin, CSV veya JSON çıktısı okunabilir.")
        root = self.service.store.root.resolve()
        path = root / "artifacts" / arguments.run_id / f"{arguments.artifact_id}{suffix}"
        if any(item.is_symlink() for item in (path, path.parent, path.parent.parent)):
            raise WorkflowError("Çıktı dosyası sembolik bağlantı olamaz.")
        if root not in path.resolve().parents:
            raise WorkflowError("Çıktı dosyası çalışma alanı dışında olamaz.")
        try:
            with path.open("rb") as handle:
                raw = handle.read(1_048_577)
            if len(raw) > 1_048_576:
                raise WorkflowError("Çıktı dosyası güvenli metin okuma sınırını aşıyor (1 MB).")
            # Redact before selecting a prefix; a prefix must never expose part of a secret.
            content = raw.decode("utf-8-sig")
        except (OSError, UnicodeError):
            raise WorkflowError("Çıktı UTF-8 metni olarak okunamadı.") from None
        clean = self.context.redactor.text(content)
        return {"artifact_id": artifact.id, "content": clean[:20_000],
                "truncated": len(clean) > 20_000}

    def ask_user(self, arguments):
        return self.service._wait_question(self.context, arguments.question, arguments.options)

    def ask_manager(self, arguments):
        return self.service._ask_manager(self.context, arguments.question, arguments.options)

    def finish(self, arguments):
        if self.context.agent.role == "manager" and self.context.run.delegated_task_ids:
            if not self.context.children_reported:
                tasks, questions = self.service._wait_children(self.context)
                if questions:
                    return {"status": "department_question", "tasks": tasks, "questions": questions,
                            "message": "Soruları answer_department ile yanıtlayın (bilmiyorsanız önce ask_user ile "
                                       "kullanıcıya sorun), sonra finish aracını yeniden çağırın."}
                self.context.children_reported = True
                return {"status": "children_completed", "tasks": tasks,
                        "message": "Alt görev sonuçlarını birleştirin ve finish aracını yeniden çağırın."}
        self.context.run.summary = self.context.redactor.text(arguments.summary)
        self.context.run.result = self.context.redactor.sanitize(arguments.result)
        self.context.finished = True
        return {"finished": True}

    def list_team(self, arguments):
        return {"agents": self.service._team_for(self.context)}

    def delegate_task(self, arguments):
        return self.service._delegate(self.context, arguments)

    def get_task(self, arguments):
        return self.service._delegated_task(self.context, arguments.task_id)

    def list_tasks(self, arguments):
        tasks = [self.service._delegated_task(self.context, identity)
                 for identity in self.context.run.delegated_task_ids]
        if arguments.filter:
            if arguments.filter.agent_id:
                tasks = [task for task in tasks if task["agent_id"] == arguments.filter.agent_id]
            if arguments.filter.status:
                tasks = [task for task in tasks if task["status"] == arguments.filter.status]
        return {"tasks": tasks, "questions": self.service._department_questions(self.context)}

    def wait_tasks(self, arguments):
        tasks, questions = self.service._wait_children(self.context, until=arguments.until)
        return {"tasks": tasks, "questions": questions}

    def answer_department(self, arguments):
        return self.service._answer_department(self.context, arguments.question_id, arguments.answer)


def call_fingerprint(call: ToolCall) -> str:
    return json.dumps({"name": call.name, "arguments": call.arguments}, sort_keys=True,
                      ensure_ascii=False, separators=(",", ":"), allow_nan=False)
