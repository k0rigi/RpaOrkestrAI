import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from rpa_orkestrai.agents.models import (
    Actor,
    Agent,
    AgentInput,
    AgentLimits,
    AgentRunRequest,
    AgentTask,
    ProviderConnection,
    WorkflowGrant,
    validate_inputs,
    validate_json_value,
)
from rpa_orkestrai.models import uid


def actor(**updates):
    return Actor(user_id=1, company_id=2, name="Çalışan", session_id="oturum", **updates)


@pytest.mark.parametrize("field,value", [
    ("company_id", 2), ("user_id", 1), ("revision", 3), ("grant_revisions", {}),
    ("actor", {"user_id": 1}), ("permissions", ["agents.approve"]), ("permission_audit", []),
])
def test_request_cannot_set_server_owned_fields(field, value):
    with pytest.raises(ValidationError):
        AgentInput(name="Analiz", **{field: value})
    with pytest.raises(ValidationError):
        AgentRunRequest(task="Özetle", **{field: value})


def test_actor_is_immutable_and_approval_is_a_verified_permission():
    user = actor()
    assert not user.can_approve
    owner = actor(permissions=["agents.approve"])
    assert owner.can_approve and owner.permissions == ("agents.approve",)
    with pytest.raises(ValidationError):
        owner.user_id = 99
    with pytest.raises(ValidationError):
        Actor(user_id=1, company_id=2, session_id="oturum", can_approve=True)


def test_workflow_grants_are_unique_and_manager_cannot_run_workflows():
    grant = WorkflowGrant(workflow_id=uid())
    assert not grant.allow_without_approval
    with pytest.raises(ValidationError):
        AgentInput(name="Analiz", workflows=[grant, grant])
    with pytest.raises(ValidationError):
        AgentInput(name="Yönetici", role="manager", workflows=[grant])
    with pytest.raises(ValidationError):
        AgentInput(name="Yönetici", role="manager", manager_id=uid())


def test_durations_allow_small_positive_deadlines_for_deterministic_tests():
    limits = AgentLimits(max_seconds=0.01, approval_timeout_seconds=0.01, question_timeout_seconds=0.01)
    assert limits.max_seconds == 0.01
    with pytest.raises(ValidationError):
        AgentLimits(max_seconds=0)
    with pytest.raises(ValidationError):
        AgentLimits(max_tokens=-1)


@pytest.mark.parametrize("value", [
    {"bad name": "x"}, {"1first": 1}, {"Türkçe": 1}, {"sistem": {}}, {"sifre": {}},
    {"loop_index": 1}, {"x" * 65: 1}, {1: "x"}, [], {f"a{i}": i for i in range(101)},
])
def test_invalid_input_names_and_reserved_variables_are_rejected(value):
    with pytest.raises(ValueError):
        validate_inputs(value)


@pytest.mark.parametrize("value", [
    {"value": math.inf}, {"value": math.nan}, {"value": (1, 2)}, {"value": {1, 2}},
    {"value": b"secret"}, {"value": Path("private")}, {"value": {1: "bad key"}},
])
def test_non_json_values_are_rejected_before_pydantic_coercion(value):
    with pytest.raises(ValidationError):
        AgentRunRequest(task="İncele", inputs=value)


def test_secret_mapping_is_never_coerced_or_resolved():
    class SecretMapping(dict):
        def items(self):
            raise AssertionError("Gizli değerler okunmamalı")

    with pytest.raises(ValueError):
        validate_inputs({"copied_secret": SecretMapping(password="private")})


def test_json_depth_cycles_total_byte_size_and_valid_nested_values():
    nested = []
    for _ in range(21):
        nested = [nested]
    with pytest.raises(ValueError):
        validate_json_value(nested)
    circular = []
    circular.append(circular)
    with pytest.raises(ValueError):
        validate_json_value(circular)
    with pytest.raises(ValueError):
        validate_inputs({"value": "ı" * 30}, max_bytes=50)
    with pytest.raises(ValueError):
        validate_inputs({"value": "x" * 65_536})
    value = {"rows": [{"active": True, "value": None, "quantity": 2.5}], "zero": 0}
    assert validate_inputs(value) == value


def test_model_round_trip_keeps_unicode_and_owned_revision():
    definition = Agent(name="Satın alma", company_id=2, user_id=1)
    assert Agent.model_validate_json(definition.model_dump_json()) == definition


def test_human_assignment_is_distinct_from_an_agent_and_company_is_checked():
    task = AgentTask(company_id=2, created_by=actor(), assignee_type="human", assignee_id="7", title="İncele")
    assert task.assigned_agent_id is None
    with pytest.raises(ValidationError):
        AgentTask(company_id=3, created_by=actor(), assignee_id=uid(), title="İncele")
    with pytest.raises(ValidationError):
        AgentTask(company_id=2, created_by=actor(), assignee_type="human", assignee_id="7",
                  assigned_agent_id=uid(), title="İncele")


@pytest.mark.parametrize("key", ["api_key", "password", "secret", "token"])
def test_provider_metadata_never_accepts_credentials(key):
    with pytest.raises(ValidationError):
        ProviderConnection(name="Yerel", company_id=2, provider="ollama", **{key: "private"})


@pytest.mark.parametrize("address", [
    "http://user:password@localhost:11434", "http://localhost:11434?key=private",
    "http://localhost:11434#private", "file:///private/model", "http://localhost:99999",
])
def test_provider_address_cannot_persist_embedded_credentials(address):
    with pytest.raises(ValidationError):
        ProviderConnection(name="Yerel", company_id=2, provider="ollama", base_url=address)


def test_cloud_endpoint_cannot_be_changed_and_local_metadata_accepts_valid_url():
    with pytest.raises(ValidationError):
        ProviderConnection(name="Bulut", company_id=2, provider="openai", base_url="https://other.example")
    connection = ProviderConnection(name="Yerel", company_id=2, provider="ollama",
                                    base_url="http://127.0.0.1:11434")
    assert connection.base_url == "http://127.0.0.1:11434"
