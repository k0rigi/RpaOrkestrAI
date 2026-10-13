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
