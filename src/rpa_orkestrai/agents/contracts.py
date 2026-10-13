"""Mevcut akış biçimini değiştirmeden girdi ve çıktı adaylarını çıkarır."""

from __future__ import annotations

from dataclasses import dataclass

from ..catalog import BY_TYPE, LOOPS, defaults
from ..errors import WorkflowError
from ..models import Step, Workflow

RESERVED = frozenset({"sistem", "sifre", "loop_index"})


@dataclass(frozen=True)
class WorkflowContract:
    required_inputs: tuple[str, ...]
    optional_inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    uncertain: bool = False

    @property
    def inputs(self) -> list[dict]:
        return ([{"name": name, "required": True} for name in self.required_inputs]
                + [{"name": name, "required": False} for name in self.optional_inputs])

    def as_dict(self) -> dict:
        return {"inputs": self.inputs, "outputs": list(self.outputs), "uncertain": self.uncertain}


def parameters(step: Step) -> dict:
    from ..engine import active_fields

    if step.action not in BY_TYPE:
        raise WorkflowError("Ajan girdisi çıkarılırken bilinmeyen adım türü bulundu.")
    raw = {**defaults(step.action), **step.params}
    if step.action == "control.for_each" and "item_name" not in step.params:
        raw["item_name"] = "item"  # Preserve the engine's imported pre-0.3 workflow behaviour.
    return {field["name"]: raw.get(field["name"]) for field in active_fields(step.action, raw)}


def reads(step: Step) -> set[str]:
    from ..engine import referenced, step_reads

    raw = parameters(step)
    result = set(referenced(raw))
    if step.action == "data.calculate":
        # step_reads also recognizes bare identifiers in the expression AST.
        found, _ = step_reads(step.model_copy(update={"params": raw}), nested=False)
        result.update(found)
    return result


def produces(step: Step) -> set[str]:
    raw = parameters(step)
    names = [raw.get("output")]
    if step.action in {"core.set", "data.append"}:
        names.append(raw.get("name"))
    return {name for name in names if isinstance(name, str) and name and name not in RESERVED}


def infer_contract(workflow: Workflow, workflows: dict[str, Workflow] | None = None) -> WorkflowContract:
    """Report conditional candidates honestly; no fabricated values or required Workflow fields."""
    required, optional, outputs = set(), set(), set()
    uncertain = False
    graph = workflows or {workflow.id: workflow}

    def visit(steps, available, *, conditional=False, stack=()):
        nonlocal uncertain
        available = set(available)
        for step in steps:
            raw = parameters(step)
            missing = reads(step) - available - RESERVED
            (optional if conditional else required).update(missing)
            if step.action == "control.run_workflow":
                child_id = raw.get("workflow")
                if not isinstance(child_id, str) or "${" in child_id:
                    raise WorkflowError("Ajan akışlarında alt akış kimliği sabit olmalıdır.")
                if child_id in stack or len(stack) > 5:
                    raise WorkflowError("Alt akışlarda döngü veya derinlik sınırı aşımı bulundu.")
                if child_id not in graph:
                    raise WorkflowError("Girdi çıkarımı için alt akış tanımı bulunamadı.")
                available = visit(graph[child_id].steps, available, conditional=conditional,
                                  stack=(*stack, child_id))
            elif step.action in {"control.if", "control.try"}:
                scoped = set(available)
                if step.action == "control.try":
                    scoped.add(raw.get("error_name") or "error_message")
                left = visit(step.children, available, conditional=True, stack=stack)
                right = visit(step.otherwise, scoped, conditional=True, stack=stack)
                available.update(left & right)
                uncertain = True
            elif step.action in LOOPS:
                scoped = set(available) | {"loop_index"}
                if step.action == "control.for_each":
                    scoped.add(raw.get("item_name") or "row")
                visit(step.children, scoped, conditional=True, stack=stack)
                uncertain = True
            elif step.action == "control.goto":
                uncertain = True
                # A jump can skip producers, so following reads are candidates, not guarantees.
                conditional = True
            made = produces(step)
            outputs.update(made)
            available.update(made)
        return available

    visit(workflow.steps, set(), stack=(workflow.id,))
    optional -= required
    return WorkflowContract(tuple(sorted(required)), tuple(sorted(optional)), tuple(sorted(outputs)), uncertain)


def infer_inputs(workflow: Workflow, workflows: dict[str, Workflow] | None = None) -> list[dict]:
    return infer_contract(workflow, workflows).inputs


def validate_inputs(value, *, max_bytes=65_536) -> dict:
    from .models import validate_inputs as validate

    return validate(value, max_bytes=max_bytes)
