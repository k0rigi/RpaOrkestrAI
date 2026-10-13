import threading
import time

import pytest

from rpa_orkestrai.agents.models import ProviderConnection
from rpa_orkestrai.agents.providers import (
    ProviderCancelled,
    ProviderError,
    ProviderResponse,
    ProviderTimeout,
    ProviderUnavailable,
    ScriptedProvider,
    ToolCall,
    Usage,
    provider_for,
)


def complete(provider, **updates):
    options = {"model": "test-model", "max_tokens": 100, "cancel": threading.Event(),
               "deadline": time.monotonic() + 10}
    options.update(updates)
    return provider.complete([{"role": "user", "content": "Özetle"}], [], **options)


def test_scripted_tool_calls_and_usage_preserve_protocol_and_copy_requests():
    call = ToolCall(id="call-1", name="list_workflows", arguments={})
    response = ProviderResponse(tool_calls=[call], usage=Usage(input_tokens=8, output_tokens=2))
    provider = ScriptedProvider([response, ProviderResponse(text="Bitti")])
    result = complete(provider)
    assert result == response and result.usage.total_tokens == 10
    assert complete(provider).text == "Bitti"
    requests = provider.requests
    requests[0]["messages"][0]["content"] = "Değişti"
    assert provider.captured_requests[0]["messages"][0]["content"] == "Özetle"
    result.tool_calls[0].arguments["mutated"] = True
    assert response.tool_calls[0].arguments == {}
    with pytest.raises(ProviderError):
        complete(provider)


def test_callback_supports_tools_without_network_calls():
    def reply(request):
        return ProviderResponse(text=request["messages"][0]["content"], usage=Usage(1, 1))

    assert complete(ScriptedProvider([], callback=reply)).text == "Özetle"


def test_cancel_before_request_and_during_callback_discards_late_response():
    stop = threading.Event()
    stop.set()
    provider = ScriptedProvider([ProviderResponse(text="Bitti")])
    with pytest.raises(ProviderCancelled):
        complete(provider, cancel=stop)
    assert provider.requests == []
    stop.clear()

    def reply(request):
        stop.set()
        return ProviderResponse(tool_calls=[ToolCall("late", "run_workflow", {})])

    with pytest.raises(ProviderCancelled):
        complete(ScriptedProvider([], callback=reply), cancel=stop)


def test_expired_deadline_prevents_request():
    provider = ScriptedProvider([ProviderResponse(text="Bitti")])
    with pytest.raises(ProviderTimeout):
        complete(provider, deadline=time.monotonic() - 1)
    assert not provider.requests


def test_provider_errors_do_not_echo_provider_messages_or_secrets():
    secret = "test-private-api-key"

    def broken(request):
        raise RuntimeError(secret)

    with pytest.raises(ProviderError) as captured:
        complete(ScriptedProvider([], callback=broken))
    assert secret not in str(captured.value)
    assert captured.value.__suppress_context__
    assert secret not in str(ProviderError(secret))


@pytest.mark.parametrize("provider_name", ["fake", "openai", "gemini", "anthropic", "ollama", "local_openai"])
def test_saved_connections_cannot_activate_fake_or_unimplemented_providers(provider_name):
    connection = ProviderConnection(name="Bağlantı", company_id=1, provider=provider_name)
    with pytest.raises(ProviderUnavailable):
        provider_for(connection)


def test_invalid_provider_responses_are_rejected():
    with pytest.raises(ProviderError):
        ToolCall("one", "run_workflow", {"key": object()})
    with pytest.raises(ProviderError):
        Usage(input_tokens=-1)
    with pytest.raises(ProviderError):
        Usage(input_tokens=True)
    with pytest.raises(ProviderError):
        ProviderResponse(tool_calls=[ToolCall("same", "ask_user", {}), ToolCall("same", "finish", {})])
    with pytest.raises(ProviderError):
        complete(ScriptedProvider([]), max_tokens=0)
    with pytest.raises(ProviderError):
        ProviderResponse(tool_calls=[ToolCall(str(i), "finish", {"large": "x" * 60_000}) for i in range(5)])
