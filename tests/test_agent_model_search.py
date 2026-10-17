"""Model sağlayıcısının kendi web araması: ayrı istek, bizim denetimlerimiz önce, tokenlar ajanın bütçesinde."""

import io
import threading
import time
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest
from test_agent_provider_adapters import provider
from test_agent_runner import finish, response
from test_agent_runner import runtime as runtime  # noqa: F401

from rpa_orkestrai.agents import web
from rpa_orkestrai.agents.models import AgentInput, AgentLimits, AgentRunRequest
from rpa_orkestrai.agents.providers import ProviderError, ScriptedProvider, ToolCall, Usage
from rpa_orkestrai.agents.runner import AgentServiceError
from rpa_orkestrai.models import uid


def search(adapter, model="test-model", domains=None):
    return adapter.search("e-fatura geçiş tarihi", 5, domains, model=model, cancel=threading.Event(),
                          deadline=time.monotonic() + 3)


def bad_request(url="https://api.test"):
    return HTTPError(url, 400, "Bad Request", {}, io.BytesIO(b"{}"))


def test_gemini_uses_google_search_and_returns_sources_with_snippets():
    adapter, opener = provider("gemini", [{
        "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "Geçiş 1 Temmuz'da [1]."}]},
                        "groundingMetadata": {
                            "groundingChunks": [{"web": {"uri": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/x",
                                                         "title": "gib.gov.tr"}}],
                            "groundingSupports": [{"segment": {"text": "Geçiş 1 Temmuz'da"}, "groundingChunkIndices": [0]}]}}],
        "usageMetadata": {"promptTokenCount": 40, "totalTokenCount": 90}}])
    results, summary, usage = search(adapter, "gemini-3.8-flash", ["*.gib.gov.tr"])
    payload = opener.requests[0][1]
    assert payload["tools"] == [{"google_search": {}}] and "gib.gov.tr" in payload["contents"][0]["parts"][0]["text"]
    assert payload["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert results == [{"title": "gib.gov.tr", "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/x",
                        "snippet": "Geçiş 1 Temmuz'da"}]
    assert summary == "Geçiş 1 Temmuz'da [1]." and (usage.input_tokens, usage.output_tokens) == (40, 50)


def test_openai_uses_web_search_and_retries_without_filters_on_older_models():
    reply = {"output": [{"type": "web_search_call", "action": {"sources": [{"type": "url", "url": "https://gib.gov.tr/a"}]}},
                        {"type": "message", "content": [{"type": "output_text", "text": "Özet",
                                                         "annotations": [{"type": "url_citation", "url": "https://gib.gov.tr/a",
                                                                          "title": "GİB"},
                                                                         {"type": "url_citation", "url": "https://b.com",
                                                                          "title": "B"}]}]}],
             "usage": {"input_tokens": 10, "output_tokens": 5}}
    adapter, opener = provider("openai", [bad_request(), reply])
    results, summary, usage = search(adapter, domains=["gib.gov.tr"])
    first, second = opener.requests[0][1], opener.requests[1][1]
    assert first["tools"] == [{"type": "web_search", "filters": {"allowed_domains": ["gib.gov.tr"]}}]
    assert first["include"] == ["web_search_call.action.sources"] and first["store"] is False
    assert second["tools"] == [{"type": "web_search"}] and "include" not in second
    assert [item["url"] for item in results] == ["https://gib.gov.tr/a", "https://b.com"] and results[0]["title"] == "GİB"
    assert summary == "Özet" and usage.total_tokens == 15


@pytest.mark.parametrize("model,kind", [("claude-opus-5-5", "web_search_20260209"), ("claude-haiku-5-5", "web_search_20250305")])
def test_claude_uses_the_web_search_tool_its_model_supports(model, kind):
    reply = {"stop_reason": "end_turn", "usage": {"input_tokens": 30, "output_tokens": 12},
             "content": [{"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {"query": "x"}},
                         {"type": "web_search_tool_result", "tool_use_id": "s1", "content": [
                             {"type": "web_search_result", "url": "https://gib.gov.tr/duyuru", "title": "Duyuru",
                              "encrypted_content": "gizli"}]},
                         {"type": "text", "text": "Geçiş 1 Temmuz'da.", "citations": [
                             {"type": "web_search_result_location", "url": "https://gib.gov.tr/duyuru", "title": "Duyuru",
                              "cited_text": "1 Temmuz itibarıyla"}]}]}
    adapter, opener = provider("anthropic", [reply])
    results, summary, usage = search(adapter, model, ["*.gib.gov.tr"])
    tool = opener.requests[0][1]["tools"][0]
    assert tool == {"type": kind, "name": "web_search", "max_uses": 3, "allowed_domains": ["gib.gov.tr"]}
    assert results == [{"title": "Duyuru", "url": "https://gib.gov.tr/duyuru", "snippet": "1 Temmuz itibarıyla"}]
    assert summary == "Geçiş 1 Temmuz'da." and usage.total_tokens == 42


def test_claude_falls_back_to_the_basic_tool_when_the_newer_one_is_rejected():
    reply = {"stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1}, "content": [{"type": "text", "text": "x"}]}
    adapter, opener = provider("anthropic", [bad_request(), reply])
    search(adapter, "claude-sonnet-5-5")
    assert [request[1]["tools"][0]["type"] for request in opener.requests] == ["web_search_20260209", "web_search_20250305"]


def test_local_models_have_no_search_of_their_own():
    adapter, _ = provider("ollama", [])
    with pytest.raises(ProviderError, match="kendi web araması yok"):
        search(adapter)


class SearchingProvider(ScriptedProvider):
    kind = "gemini"

    def __init__(self, replies, items, summary="Kaynaklı özet"):
        super().__init__(replies)
        self.items, self.summary, self.searches = items, summary, []

    def search(self, query, max_results, domains, *, model, cancel, deadline):
        self.searches.append((query, max_results, domains, model))
        return [dict(item) for item in self.items], self.summary, Usage(100, 20)


def model_agent(runtime, access="open", domains=()):
    runtime.service.search_settings = SimpleNamespace(get=lambda company: {"provider": "model"}, key=lambda company: None)
    return runtime.service.create_agent(AgentInput(name="Araştırmacı", model="gemini-3.8-flash", web_access=access,
                                                   web_domains=list(domains), limits=AgentLimits(max_seconds=30)))


def test_agent_search_goes_through_its_own_model_and_counts_the_tokens(runtime, monkeypatch):
    monkeypatch.setattr(web, "resolve_redirect", lambda url: url.replace("https://vertexaisearch.cloud.google.com/r/", "https://"))
    agent = model_agent(runtime, "allowlist", ["gib.gov.tr"])
    items = [{"title": "GİB", "url": "https://vertexaisearch.cloud.google.com/r/gib.gov.tr/a", "snippet": "1 Temmuz"},
             {"title": "Blog", "url": "https://blog.example.com/b", "snippet": "x"}]
    fake = SearchingProvider([response(ToolCall(uid(), "web_search", {"query": "e-fatura geçiş"})), response(finish())], items)
    runtime.state["provider"] = fake
    run = runtime.service.start(agent.id, AgentRunRequest(task="E-fatura geçiş tarihini araştır"))
    saved = runtime.done(run)
    assert fake.searches == [("e-fatura geçiş", 5, ["gib.gov.tr"], "gemini-3.8-flash")]
    event = next(event for event in saved.events if event.kind == "web_search")
    assert event.data["service"] == "model" and event.data["urls"] == ["https://gib.gov.tr/a"]
    result = next(event.data["untrusted_data"] for event in saved.events if event.kind == "tool_result")
    assert result["summary"] == "Kaynaklı özet" and [item["url"] for item in result["results"]] == ["https://gib.gov.tr/a"]
    assert saved.tokens_in >= 100 and saved.tokens_out >= 20


def test_agents_on_local_models_get_a_clear_message(runtime):
    agent = model_agent(runtime)
    saved = runtime.done(runtime.start(agent, response(ToolCall(uid(), "web_search", {"query": "x"})), response(finish())))
    result = next(event.data["untrusted_data"] for event in saved.events if event.kind == "tool_result")
    assert result["status"] == "error" and "Tavily" in result["error"] and "Ollama" in result["error"]


def test_search_test_uses_the_first_agent_with_a_capable_connection(runtime, monkeypatch):
    monkeypatch.setattr(web, "resolve_redirect", lambda url: url)
    runtime.service.search_settings = SimpleNamespace(get=lambda company: {"provider": "model"}, key=lambda company: None)
    with pytest.raises(AgentServiceError, match="bulunamadı"):
        runtime.service.test_search()
    agent = runtime.service.create_agent(AgentInput(name="Gemini ajanı", model="gemini-3.8-flash",
                                                    provider_connection_id=uid()))
    fake = SearchingProvider([], [{"title": "A", "url": "https://a.com", "snippet": ""}])
    runtime.service._provider_factory = lambda item: fake
    answer = runtime.service.test_search()
    assert "Gemini ajanı" in answer["message"] and answer["results"][0]["url"] == "https://a.com"
    assert fake.searches[0][3] == agent.model


def test_only_google_redirect_links_are_resolved():
    assert web.resolve_redirect("https://gib.gov.tr/a") == "https://gib.gov.tr/a"
    assert web.resolve_redirect("http://vertexaisearch.cloud.google.com/x") == "http://vertexaisearch.cloud.google.com/x"
