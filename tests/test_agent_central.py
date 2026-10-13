"""Merkezi hizmete gönderilen kimlik, onay ve model sınırları; gerçek ağ yok."""

import io
import json
import threading
import time
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from rpa_orkestrai.agents.central import BASE_URL, CentralApprovalBackend, CentralClient, CentralError, digest
from rpa_orkestrai.agents.models import Actor
from rpa_orkestrai.agents.providers import ProviderCancelled, ProviderError, ProviderTimeout
from rpa_orkestrai.agents.redaction import Redactor
from rpa_orkestrai.agents.shared_provider import SharedProvider, shared_prompt_bytes
from rpa_orkestrai.models import uid


def actor():
    return Actor(user_id=1, company_id=2, session_id="studio-session",
                 permissions=("agents.use", "agents.approve"))


class License:
    def __init__(self):
        self.current = actor()

    def agent_actor(self):
        return self.current

    def agent_access_token(self):
        return "secret-agent-bearer"


class Response(io.BytesIO):
    def __init__(self, request, value, *, url=None):
        super().__init__(json.dumps(value).encode())
        self.url = url or request.full_url

    def geturl(self):
        return self.url

    def getcode(self):
        return 200


def test_central_fixed_url_auth_header_only_and_tenant_rechecked():
    licensing, calls = License(), []

    def opener(request, **kwargs):
        calls.append(request)
        assert request.get_header("Authorization") == "Bearer secret-agent-bearer"
        assert "secret-agent-bearer" not in request.full_url
        return Response(request, {"success": True, "uyeler": []})

    client = CentralClient(licensing, opener=opener)
    assert client.request("GET", "/uyeler") == {"success": True, "uyeler": []}
    assert calls[0].full_url == BASE_URL + "/uyeler"
    with pytest.raises(CentralError):
        client.request("GET", "https://evil.example")
    with pytest.raises(CentralError):
        client.request("GET", "/uyeler?firma_id=8")
    with pytest.raises(CentralError):
        client.request("GET", "/uyeler", expected_actor=actor().model_copy(update={"company_id": 8}))
    assert len(calls) == 1


@pytest.mark.parametrize("mode", ["redirect", "change_user", "large", "private_error", "invalid_json"])
def test_central_untrusted_or_stale_response_is_not_returned(mode):
    licensing = License()

    def opener(request, **kwargs):
        if mode == "private_error":
            raise HTTPError(request.full_url, 403, "secret-agent-bearer", {}, io.BytesIO(b"secret-agent-bearer"))
        if mode == "change_user":
            licensing.current = actor().model_copy(update={"user_id": 8})
        response = Response(request, {"success": True, "value": "x" * 600_000 if mode == "large" else "ok"},
                            url="https://evil.example" if mode == "redirect" else None)
        if mode == "invalid_json":
            response = Response(request, {"success": False, "error": "secret-agent-bearer"})
        return response

    with pytest.raises(CentralError) as caught:
        CentralClient(licensing, opener=opener).request("GET", "/uyeler")
    assert "secret-agent-bearer" not in str(caught.value)


class ApprovalClient:
    def __init__(self):
        self.record = None
        self.requests = []

    def actor(self):
        return actor()

    def request(self, method, path, body=None, **kwargs):
        self.requests.append((method, path, body))
        if path == "/onaylar":
            self.record = {**body, "id": uid(), "preview_digest": digest(body["preview"]),
                           "status": "pending", "version": 1, "expires_at": "2026-10-13T12:00:00+00:00"}
        elif path.endswith("/karar"):
            self.record["status"] = "approved" if body["decision"] == "approve" else "rejected"
            self.record["version"] += 1
        elif path.endswith("/tuket"):
            if self.record["status"] != "approved":
                raise CentralError("Tek kullanımlık onay tekrar kullanılamaz.", 409)
            assert all(self.record[key] == value for key, value in body.items())
            self.record["status"] = "consumed"
        return {"success": True, "approval": dict(self.record)}


def prepared_context():
    prepared = SimpleNamespace(root=SimpleNamespace(id=uid(), name="İzinli akış"), digest="a" * 64,
                               inputs={"metin": "sakli-deger ve normal metin"})
    context = SimpleNamespace(run=SimpleNamespace(id=uid(), actor=actor()), redactor=Redactor(["sakli-deger"]),
                              attempts={}, cancel=threading.Event(), deadline=time.monotonic() + 30)
    return prepared, context


def test_central_approval_binds_raw_inputs_without_sending_the_secret_and_consumes_once():
    client = ApprovalClient()
    backend = CentralApprovalBackend(client)
    prepared, context = prepared_context()
    remote = backend.request(context, prepared, "Gerekçe sakli-deger", expires_in=99999)
    sent = client.requests[0][2]
    assert sent["inputs_digest"] == digest(prepared.inputs)
    assert sent["workflow_digest"] == prepared.digest
    assert sent["expires_in"] == 900
    assert "sakli-deger" not in json.dumps(sent)
    backend.decide(remote["id"], True)
    assert backend.status(context, remote)["status"] == "approved"
    with pytest.raises(CentralError):
        backend.consume(context, remote, digest="b" * 64)
    backend.consume(context, remote, digest=prepared.digest)
    with pytest.raises(CentralError):
        backend.consume(context, remote, digest=prepared.digest)
    assert client.record["status"] == "consumed"


def test_another_workflow_or_preview_cannot_replace_remote_approval():
    client = ApprovalClient()
    backend = CentralApprovalBackend(client)
    prepared, context = prepared_context()
    remote = backend.request(context, prepared, "Gerekçe", expires_in=60)
    client.record["workflow_id"] = uid()
    with pytest.raises(CentralError):
        backend.status(context, remote)


class ModelClient:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.capabilities = {"success": True, "models": ["kurum-modeli"], "enabled": True,
                             "context_tokens": 8192, "max_output_tokens": 1024,
                             "reserve_tokens": 512, "estimation": "utf8_bytes"}

    def actor(self):
        return actor()

    def request(self, method, path, body=None, **kwargs):
        self.calls.append((method, path, body))
        if path == "/llm/models":
            return self.capabilities
        return {"success": True, "job": {"id": "a" * 32, "status": "succeeded", "result": self.response}}


def test_shared_model_returns_tools_and_accountable_usage_without_fallback():
    client = ModelClient({"text": "", "tool_calls": [{"id": "call1", "name": "finish", "arguments": {"summary": "Bitti"}}],
                          "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14}})
    result = SharedProvider(client).complete([{"role": "user", "content": "Görev"}], [], model="kurum-modeli",
                                              max_tokens=500, cancel=threading.Event(), deadline=time.monotonic() + 5)
    assert result.tool_calls[0].name == "finish" and result.usage.total_tokens == 14
    assert [call[1] for call in client.calls] == ["/llm/models", "/llm/jobs"]


def test_shared_model_does_not_accept_missing_token_usage():
    client = ModelClient({"text": "Bitti", "tool_calls": [], "usage": {}})
    with pytest.raises(ProviderError):
        SharedProvider(client).complete([], [], model="kurum-modeli", max_tokens=500,
                                        cancel=threading.Event(), deadline=time.monotonic() + 5)
    assert client.calls[-1][0] == "DELETE"


@pytest.mark.parametrize("usage", [
    {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    {"input_tokens": 0, "output_tokens": 1, "total_tokens": True},
    {"input_tokens": 0, "output_tokens": 1, "total_tokens": 1.0},
])
def test_shared_model_rejects_unaccountable_usage_before_returning_tools(usage):
    client = ModelClient({"text": "", "tool_calls": [{"id": "call1", "name": "finish", "arguments": {"summary": "Bitti"}}],
                          "usage": usage})
    with pytest.raises(ProviderError):
        SharedProvider(client).complete([], [], model="kurum-modeli", max_tokens=500,
                                        cancel=threading.Event(), deadline=time.monotonic() + 5)
    assert client.calls[-1][0] == "DELETE"


@pytest.mark.parametrize("change", [
    {"enabled": False}, {"models": ["different-model"]}, {"estimation": "unknown"},
    {"context_tokens": True}, {"max_output_tokens": 0}, {"reserve_tokens": 8192},
])
def test_shared_capability_validation_prevents_posting_business_messages(change):
    client = ModelClient({})
    client.capabilities.update(change)
    with pytest.raises(ProviderError):
        SharedProvider(client).complete([{"role": "user", "content": "Görev verisi"}], [], model="kurum-modeli",
                                        max_tokens=128, cancel=threading.Event(), deadline=time.monotonic() + 5)
    assert [call[1] for call in client.calls] == ["/llm/models"]
    assert client.calls[0][2] is None


def test_shared_limits_are_cached_but_cancel_and_deadline_still_apply():
    client, cancel = ModelClient({}), threading.Event()
    provider = SharedProvider(client)
    limits = provider.request_limits("kurum-modeli", cancel=cancel, deadline=time.monotonic() + 5)
    assert limits is provider.request_limits("kurum-modeli", cancel=cancel, deadline=time.monotonic() + 5)
    assert len(client.calls) == 1
    cancel.set()
    with pytest.raises(ProviderCancelled):
        provider.request_limits("kurum-modeli", cancel=cancel, deadline=time.monotonic() + 5)
    cancel.clear()
    with pytest.raises(ProviderTimeout):
        provider.request_limits("kurum-modeli", cancel=cancel, deadline=time.monotonic() - 1)


def test_shared_estimator_uses_converted_unicode_messages_and_omits_call_ids():
    messages = [{"role": "assistant", "content": "Türkçe", "tool_calls": [
        {"id": "private-call-id", "name": "finish", "arguments": {"summary": "Bitti"}}]},
        {"role": "tool", "name": "finish", "tool_call_id": "private-call-id", "content": "Sonuç"}]
    expected = {"messages": [
        {"role": "assistant", "content": "Türkçe", "tool_calls": [
            {"type": "function", "function": {"name": "finish", "arguments": {"summary": "Bitti"}}}]},
        {"role": "tool", "tool_name": "finish", "content": "Sonuç"}], "tools": []}
    assert shared_prompt_bytes(messages, []) == len(json.dumps(
        expected, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))


def test_shared_direct_request_does_not_silently_reduce_output_or_truncate_context():
    client = ModelClient({})
    with pytest.raises(ProviderError):
        SharedProvider(client).complete([{"role": "user", "content": "x" * 8000}], [], model="kurum-modeli",
                                        max_tokens=1024, cancel=threading.Event(), deadline=time.monotonic() + 5)
    assert [call[1] for call in client.calls] == ["/llm/models"]


def shared_success():
    return {"text": "Bitti", "tool_calls": [], "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14}}


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_shared_submission_retries_transient_failure_with_same_id_and_payload(status, monkeypatch):
    client = ModelClient(shared_success())
    original, submitted = client.request, []

    def flaky(method, path, body=None, **kwargs):
        if method == "POST":
            submitted.append(json.loads(json.dumps(body)))
            if len(submitted) == 1:
                raise CentralError("Geçici hata", status)
        return original(method, path, body, **kwargs)

    monkeypatch.setattr(client, "request", flaky)
    result = SharedProvider(client).complete([], [], model="kurum-modeli", max_tokens=128,
                                              cancel=threading.Event(), deadline=time.monotonic() + 5)
    assert result.text == "Bitti"
    assert len(submitted) == 2 and submitted[0] == submitted[1]
    assert len(submitted[0]["request_id"]) == 32


@pytest.mark.parametrize("status,attempts", [(401, 1), (403, 1), (404, 1), (409, 1), (422, 1), (429, 3), (503, 3)])
def test_shared_submission_failure_has_bounded_attempts(status, attempts, monkeypatch):
    client = ModelClient(shared_success())
    original, submitted = client.request, []

    def failure(method, path, body=None, **kwargs):
        if method == "POST":
            submitted.append(body["request_id"])
            raise CentralError("private-upstream-error", status)
        return original(method, path, body, **kwargs)

    monkeypatch.setattr(client, "request", failure)
    with pytest.raises(ProviderError) as caught:
        SharedProvider(client).complete([], [], model="kurum-modeli", max_tokens=128,
                                        cancel=threading.Event(), deadline=time.monotonic() + 5)
    assert len(submitted) == attempts and len(set(submitted)) == 1
    assert "private-upstream-error" not in str(caught.value)


@pytest.mark.parametrize("path", ["/llm/models", "/llm/jobs/" + "a" * 32])
def test_shared_read_only_capabilities_and_job_status_retry(path, monkeypatch):
    client = ModelClient(shared_success())
    original, reads = client.request, []

    def flaky(method, current, body=None, **kwargs):
        if method == "POST" and path != "/llm/models":
            return {"success": True, "job": {"id": "a" * 32, "status": "queued"}}
        if method == "GET" and current == path:
            reads.append(current)
            if len(reads) < 3:
                raise CentralError("Geçici ağ hatası", 503)
        return original(method, current, body, **kwargs)

    monkeypatch.setattr(client, "request", flaky)
    result = SharedProvider(client).complete([], [], model="kurum-modeli", max_tokens=128,
                                              cancel=threading.Event(), deadline=time.monotonic() + 5)
    assert result.text == "Bitti" and len(reads) == 3


@pytest.mark.parametrize("mode", ["cancel", "deadline", "actor"])
def test_shared_backoff_stops_on_cancel_deadline_or_changed_actor(mode, monkeypatch):
    client, cancel = ModelClient(shared_success()), threading.Event()
    original, submitted, timer = client.request, [], None
    deadline = time.monotonic() + (0.02 if mode == "deadline" else 5)

    def failure(method, path, body=None, **kwargs):
        nonlocal timer
        if method == "POST":
            submitted.append(body["request_id"])
            if mode == "cancel":
                timer = threading.Timer(0.02, cancel.set)
                timer.start()
            elif mode == "actor":
                monkeypatch.setattr(client, "actor", lambda: actor().model_copy(update={"session_id": "new-session"}))
            raise CentralError("Kuyruk dolu", 429)
        return original(method, path, body, **kwargs)

    monkeypatch.setattr(client, "request", failure)
    expected = {"cancel": ProviderCancelled, "deadline": ProviderTimeout, "actor": ProviderError}[mode]
    try:
        with pytest.raises(expected):
            SharedProvider(client).complete([], [], model="kurum-modeli", max_tokens=128, cancel=cancel, deadline=deadline)
    finally:
        if timer:
            timer.cancel()
            timer.join()
    assert len(submitted) == 1


@pytest.mark.parametrize("operation", ["karar", "tuket"])
def test_model_retry_policy_does_not_repeat_approval_decision_or_consumption(operation, monkeypatch):
    client = ApprovalClient()
    backend = CentralApprovalBackend(client)
    prepared, context = prepared_context()
    remote = backend.request(context, prepared, "Gerekçe", expires_in=60)
    original, attempts = client.request, []

    def unavailable(method, path, body=None, **kwargs):
        if method == "POST" and path.endswith("/" + operation):
            attempts.append(path)
            raise CentralError("Geçici yanıt kaybı", 503)
        return original(method, path, body, **kwargs)

    monkeypatch.setattr(client, "request", unavailable)
    with pytest.raises(CentralError):
        if operation == "karar":
            backend.decide(remote["id"], True)
        else:
            backend.consume(context, remote, digest=prepared.digest)
    assert len(attempts) == 1


def _shared_thread(client, label, *, cancel=None, timeout=5):
    outcome = {}

    def work():
        try:
            outcome["response"] = SharedProvider(client).complete(
                [{"role": "user", "content": label}], [], model="kurum-modeli", max_tokens=128,
                cancel=cancel or threading.Event(), deadline=time.monotonic() + timeout)
        except BaseException as exc:
            outcome["error"] = exc

    thread = threading.Thread(target=work)
    thread.start()
    return thread, outcome


def _wait_model_queue(count):
    from rpa_orkestrai.agents.shared_provider import _MODEL_CONDITION, _MODEL_WAITERS

    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        with _MODEL_CONDITION:
            if sum(len(waiting) for waiting in _MODEL_WAITERS.values()) == count:
                return
        threading.Event().wait(0.005)
    pytest.fail("Model sırası beklenen uzunluğa ulaşmadı.")


class BlockingModelClient(ModelClient):
    def __init__(self, *, first_failure=False):
        super().__init__(shared_success())
        self.first_started, self.release_first = threading.Event(), threading.Event()
        self.submitted = []
        self.first_failure = first_failure
        self.current_actor = actor()

    def actor(self):
        return self.current_actor

    def request(self, method, path, body=None, **kwargs):
        if method == "POST":
            label = body["messages"][0]["content"]
            self.submitted.append(label)
            if label == "first":
                self.first_started.set()
                if not self.release_first.wait(3):
                    raise AssertionError("Testin ilk isteği serbest bırakılmadı.")
                if self.first_failure:
                    raise CentralError("İstek gönderilemedi", 403)
        return super().request(method, path, body, **kwargs)


@pytest.mark.parametrize("first_failure", [False, True])
def test_shared_session_fifo_is_global_across_provider_instances_and_releases_failed_slot(first_failure):
    client = BlockingModelClient(first_failure=first_failure)
    workers = [_shared_thread(client, "first")]
    try:
        assert client.first_started.wait(2)
        workers.append(_shared_thread(client, "second"))
        _wait_model_queue(2)
        workers.append(_shared_thread(client, "third"))
        _wait_model_queue(3)
        assert client.submitted == ["first"]
    finally:
        client.release_first.set()
        for thread, _outcome in workers:
            thread.join(3)
    assert all(not thread.is_alive() for thread, _ in workers)
    assert client.submitted == ["first", "second", "third"]
    assert ("error" in workers[0][1]) is first_failure
    assert all("response" in outcome for _, outcome in workers[1:])
    _wait_model_queue(0)


@pytest.mark.parametrize("mode", ["cancel", "deadline", "session", "license"])
def test_shared_waiting_slot_cancels_before_post_and_does_not_block_successor(mode, monkeypatch):
    active, waiting = BlockingModelClient(), ModelClient(shared_success())
    cancel = threading.Event()
    workers = [_shared_thread(active, "first")]
    try:
        assert active.first_started.wait(2)
        workers.append(_shared_thread(waiting, "waiting", cancel=cancel, timeout=0.12 if mode == "deadline" else 5))
        _wait_model_queue(2)
        if mode == "cancel":
            cancel.set()
        elif mode == "session":
            monkeypatch.setattr(waiting, "actor", lambda: actor().model_copy(update={"session_id": "new-session"}))
        elif mode == "license":
            def locked():
                raise CentralError("Lisans kapalı", 403)
            monkeypatch.setattr(waiting, "actor", locked)
        workers[1][0].join(1)
        assert not workers[1][0].is_alive()
        expected = {"cancel": ProviderCancelled, "deadline": ProviderTimeout}.get(mode, ProviderError)
        assert isinstance(workers[1][1].get("error"), expected)
        assert not waiting.calls  # No capabilities or business request while waiting.
        _wait_model_queue(1)
        workers.append(_shared_thread(active, "successor"))
        _wait_model_queue(2)
    finally:
        active.release_first.set()
        for thread, _outcome in workers:
            thread.join(3)
    assert active.submitted == ["first", "successor"]
    assert "response" in workers[-1][1]
    _wait_model_queue(0)


def test_shared_fifo_does_not_block_different_signed_sessions():
    active, other = BlockingModelClient(), ModelClient(shared_success())
    other.actor = lambda: actor().model_copy(update={"user_id": 9, "session_id": "another-session"})
    first, outcome = _shared_thread(active, "first")
    try:
        assert active.first_started.wait(2)
        second, completed = _shared_thread(other, "independent")
        second.join(1)
        assert not second.is_alive() and "response" in completed
        assert not outcome
    finally:
        active.release_first.set()
        first.join(3)
    _wait_model_queue(0)
