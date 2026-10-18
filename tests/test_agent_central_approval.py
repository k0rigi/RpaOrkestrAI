import hashlib
import json
import threading
import time

import pytest
from test_agent_runner import approval_wait, finish, response, run_call, write_flow
from test_agent_runner import runtime as runtime
from test_agent_runner import storage_latency as storage_latency

from rpa_orkestrai.agents.models import AgentLimits
from rpa_orkestrai.agents.runner import AgentServiceError
from rpa_orkestrai.models import uid


class ApprovalBackend:
    def __init__(self, service, *, state="approved", fail=None):
        self.service, self.state, self.fail = service, state, fail
        self.requests, self.consumed, self.cancelled, self.decisions = [], [], [], []

    def unlocked(self):
        # A separate thread must acquire the service lock even during every remote request.
        acquired = threading.Event()

        def inspect():
            with self.service._lock:
                acquired.set()

        thread = threading.Thread(target=inspect, daemon=True)
        thread.start()
        assert acquired.wait(0.5), "HTTP çağrısı servis kilidini tutuyor."
        thread.join(0.5)

    def request(self, context, prepared, reason, *, expires_in):
        self.unlocked()
        if self.fail == "request":
            raise RuntimeError("server-private-key")
        result = {"id": uid(), "workflow_digest": prepared.digest,
                  "inputs_digest": hashlib.sha256(json.dumps(prepared.inputs, sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False).encode()).hexdigest(),
                  "run_id": context.run.id, "attempt": 1, "preview_digest": "a" * 64,
                  "expires_at": "2099-01-01T00:00:00+00:00"}
        if self.fail == "digest":
            result["inputs_digest"] = "b" * 64
        self.requests.append(result)
        return result

    def status(self, context, remote):
        self.unlocked()
        if self.fail == "status":
            raise RuntimeError("server-private-key")
        return {"status": self.state, "approver_user_id": 99 if self.fail != "owner" else None,
                "version": 1}

    def consume(self, context, remote, *, digest):
        self.unlocked()
        assert digest == remote["workflow_digest"]
        assert remote["id"] not in self.consumed
        self.consumed.append(remote["id"])
        if self.fail == "consume":
            raise RuntimeError("server-private-key")

    def cancel(self, context, remote):
        self.unlocked()
        self.cancelled.append(remote["id"])

    def decide(self, identity, approved, office_id=None):
        self.unlocked()
        self.decisions.append((identity, approved))
        self.state = "approved" if approved else "rejected"


@pytest.mark.parametrize("storage_latency", [0, 0.15], indirect=True)
def test_remote_owner_can_approve_for_a_non_owner_initiator(runtime, storage_latency):
    flow, target = write_flow(runtime)
    item = runtime.agent(flow)
    runtime.state["actor"] = runtime.owner.model_copy(update={"permissions": ("agents.use",)})
    backend = ApprovalBackend(runtime.service)
    runtime.service.approval_backend = backend
    started = time.monotonic()
    run = runtime.start(item, response(run_call(flow)), response(finish()))
    saved = runtime.done(run)
    if storage_latency:
        assert time.monotonic() - started >= 4
    assert saved.status == "succeeded" and target.exists()
    assert len(backend.consumed) == 1 and not backend.cancelled
    event = next(event for event in saved.events if event.kind == "approval_decision")
    assert event.data["user_id"] == 99
    task = runtime.service.get_task(saved.task_id)
    assert task.approval_wait_seconds > 0 and len(task.workflow_run_ids) == 1


@pytest.mark.parametrize("failure", ["request", "status", "digest", "owner", "consume"])
def test_remote_failure_never_falls_back_to_local_approval_or_starts_flow(runtime, failure):
    flow, target = write_flow(runtime)
    backend = ApprovalBackend(runtime.service, fail=failure)
    runtime.service.approval_backend = backend
    run = runtime.start(runtime.agent(flow), response(run_call(flow)), response(finish()))
    saved = runtime.done(run)
    assert saved.status == "failed" and not target.exists() and not runtime.store.runs()
    assert "server-private-key" not in saved.model_dump_json()
    assert saved.pending_approval is None


@pytest.mark.parametrize("state", ["rejected", "consumed", "pending"])
def test_remote_reject_replay_and_expiry_are_fail_closed(runtime, state):
    flow, target = write_flow(runtime)
    backend = ApprovalBackend(runtime.service, state=state)
    runtime.service.approval_backend = backend
    item = runtime.agent(flow, limits=AgentLimits(max_seconds=5, approval_timeout_seconds=0.12))
    run = runtime.start(item, response(run_call(flow)), response(finish()))
    saved = runtime.done(run)
    assert saved.workflow_count == 0 and not target.exists() and not backend.consumed
    assert len(backend.cancelled) == 1


def test_local_owner_decision_uses_the_central_backend(runtime):
    flow, target = write_flow(runtime)
    backend = ApprovalBackend(runtime.service, state="pending")
    runtime.service.approval_backend = backend
    run = runtime.start(runtime.agent(flow), response(run_call(flow)), response(finish()))
    pending = approval_wait(runtime, run)
    runtime.service.approve(run.id, pending.pending_approval["id"], True)
    assert backend.decisions == [(pending.pending_approval["remote_id"], True)]
    saved = runtime.done(run)
    assert saved.status == "succeeded" and target.exists() and len(backend.consumed) == 1


def test_local_non_owner_cannot_forge_a_remote_approval(runtime):
    flow, target = write_flow(runtime)
    backend = ApprovalBackend(runtime.service, state="pending")
    runtime.service.approval_backend = backend
    run = runtime.start(runtime.agent(flow), response(run_call(flow)), response(finish()))
    pending = approval_wait(runtime, run)
    runtime.state["actor"] = runtime.owner.model_copy(update={"permissions": ("agents.use",)})
    with pytest.raises(AgentServiceError):
        runtime.service.approve(run.id, pending.pending_approval["id"], True)
    runtime.service.cancel(run.id)
    assert runtime.done(run).status == "cancelled" and not target.exists()
    assert not backend.decisions and len(backend.cancelled) == 1
