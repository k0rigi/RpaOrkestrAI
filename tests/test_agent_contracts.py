"""Girdi çıkarımı, koşullu kapsam ve JSON sınırları."""

import pytest

from rpa_orkestrai.agents.contracts import infer_contract, validate_inputs
from rpa_orkestrai.models import Step, Workflow


def test_read_before_write_and_top_level_producers():
    flow = Workflow(steps=[Step(action="core.log", params={"message": "${before}"}),
                           Step(action="core.set", params={"name": "before", "value": 1}),
                           Step(action="core.set", params={"name": "value", "value": 4}),
                           Step(action="data.calculate", params={"expression": "value + other", "output": "total"}),
                           Step(action="core.log", params={"message": "${total}"})])
    contract = infer_contract(flow)
    assert contract.required_inputs == ("before", "other")
    assert set(contract.outputs) == {"before", "value", "total"}


def test_inactive_parameters_and_reserved_sources_are_not_inputs():
    flow = Workflow(steps=[Step(action="control.if", params={"left": "${known}", "operator": "truthy",
                                                            "right": "${unused}"}),
                           Step(action="core.set", params={"name": "value", "value": "${sifre.key}"})])
    assert infer_contract(flow).required_inputs == ("known",)


def test_loop_scopes_and_conditional_output_are_not_definite():
    loop = Step(action="control.for_each", params={"items": "${rows}", "item_name": "row"}, children=[
        Step(action="core.set", params={"name": "result", "value": "${row.name}-${extra}-${loop_index}"})])
    flow = Workflow(steps=[loop, Step(action="core.log", params={"message": "${result}"})])
    contract = infer_contract(flow)
    assert contract.required_inputs == ("result", "rows")
    assert contract.optional_inputs == ("extra",)
    assert contract.uncertain


def test_both_branches_produce_same_name_and_fixed_child_is_inlined():
    child = Workflow(steps=[Step(action="core.set", params={"name": "child_value", "value": "${source}"})])
    condition = Step(action="control.if", params={"left": True},
                     children=[Step(action="core.set", params={"name": "answer", "value": 1})],
                     otherwise=[Step(action="core.set", params={"name": "answer", "value": 2})])
    root = Workflow(steps=[condition, Step(action="control.run_workflow", params={"workflow": child.id}),
                           Step(action="core.log", params={"message": "${answer}-${child_value}"})])
    contract = infer_contract(root, {root.id: root, child.id: child})
    assert contract.required_inputs == ("source",)
    assert not contract.optional_inputs


@pytest.mark.parametrize("value", [{"sifre": 1}, {"sistem": {}}, {"loop_index": 2}, {"a-b": 1},
                                   {"value": float("nan")}, {"value": float("inf")}, {"value": object()},
                                   {"value": {1: "a"}}, {"value": (1, 2)}, []])
def test_invalid_agent_inputs_are_rejected(value):
    with pytest.raises(ValueError):
        validate_inputs(value)


def test_input_count_size_and_depth_are_bounded():
    with pytest.raises(ValueError):
        validate_inputs({f"field{i}": i for i in range(101)})
    with pytest.raises(ValueError):
        validate_inputs({"value": "ü" * 40_000})
    deep = {}
    for _ in range(25):
        deep = {"value": deep}
    with pytest.raises(ValueError):
        validate_inputs(deep)
    accepted = {"number": 1, "text": "Türkçe", "value": [True, None, {"x": 4.2}]}
    assert validate_inputs(accepted) == accepted
