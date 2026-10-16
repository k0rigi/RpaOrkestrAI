"""Ajanların internet araştırması: yalnız okuma, yalnız açık internet, izinli siteler ve istek sınırı."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from test_agent_runner import finish, response
from test_agent_runner import runtime as runtime  # noqa: F401

from rpa_orkestrai.agents import web
from rpa_orkestrai.agents.models import AgentInput, AgentLimits
from rpa_orkestrai.agents.providers import ToolCall
from rpa_orkestrai.errors import WorkflowError
from rpa_orkestrai.models import uid


@pytest.mark.parametrize("url,message", [
    ("http://127.0.0.1/admin", "iç ağdaki"),
    ("http://10.0.0.5/", "iç ağdaki"),
    ("http://169.254.169.254/latest/meta-data/", "iç ağdaki"),
    ("http://[::1]/", "iç ağdaki"),
    ("file:///etc/passwd", "http://"),
    ("ftp://ornek.com/x", "http://"),
    ("https://kullanici:sifre@ornek.com/", "kullanıcı adı"),
    ("https://ornek.com:8443/", "standart web portları"),
    ("https://ornek.com/?" + "a=" + "x" * 400, "veri gönderemez"),
])
def test_only_public_web_addresses_can_be_read(url, message):
    with pytest.raises(WorkflowError, match=message):
        web.check_url(url, None)


def test_allowed_sites_secrets_and_domain_rules(monkeypatch):
    monkeypatch.setattr(web.socket, "getaddrinfo", lambda host, *args, **kwargs: [(0, 0, 0, "", ("93.184.216.34", 0))])
    assert web.check_url("https://www.mevzuat.gov.tr/x", ["mevzuat.gov.tr"])
    assert web.check_url("https://ebeyanname.gib.gov.tr/", ["*.gib.gov.tr"])
    with pytest.raises(WorkflowError, match="izinli siteleri"):
        web.check_url("https://mevzuat.gov.tr.saldirgan.com/", ["mevzuat.gov.tr"])
    with pytest.raises(WorkflowError, match="şifre"):
        web.check_url("https://ornek.com/?q=gizli-parola-77", None, lambda text: "gizli-parola-77" in text)
    assert web.normalize_domain("https://www.Mevzuat.gov.tr/arama") == "mevzuat.gov.tr"
    with pytest.raises(ValueError):
        web.normalize_domain("localhost")


@pytest.fixture
def site(monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/yonlendir":
                self.send_response(302)
                self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
                self.end_headers()
                return
            if self.path == "/pdf":
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.end_headers()
                self.wfile.write(b"%PDF")
                return
            body = ("<html><head><title>Fatura Kuralları</title><script>alert(1)</script></head>"
                    "<body><h1>e-Fatura</h1><p>Fatura 7 gün içinde düzenlenir.</p></body></html>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    # The local test server stands in for a public site on a test port; every other address keeps the real rules.
    real_public, real_check = web._public, web.check_url

    def check_without_test_port(url, domains, contains_secret=None):
        parts = urlsplit(url)
        if parts.hostname == "127.0.0.1":
            real_check(parts._replace(netloc="127.0.0.1").geturl(), domains, contains_secret)
            return url
        return real_check(url, domains, contains_secret)

    monkeypatch.setattr(web, "_public", lambda host: "127.0.0.1" if host == "127.0.0.1" else real_public(host))
    monkeypatch.setattr(web, "check_url", check_without_test_port)
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_page_reader_returns_clean_text_and_refuses_redirects_inward_and_binary_files(site):
    page = web.fetch(site + "/kurallar", None)
    assert page["title"] == "Fatura Kuralları" and "Fatura 7 gün içinde düzenlenir." in page["text"]
    assert "alert" not in page["text"]
    with pytest.raises(WorkflowError, match="iç ağdaki"):
        web.fetch(site + "/yonlendir", None)
    with pytest.raises(WorkflowError, match="okunamaz"):
        web.fetch(site + "/pdf", None)


def test_page_reader_connects_only_to_the_address_it_checked(monkeypatch):
    # A name that answers with a public address for the check and a local one for the connection.
    answers = iter(["93.184.216.34", "127.0.0.1"])
    monkeypatch.setattr(web.socket, "getaddrinfo", lambda host, *args, **kwargs: [(0, 0, 0, "", (next(answers), 0))])
    opened = []
    monkeypatch.setattr(web.socket, "create_connection", lambda *args, **kwargs: opened.append(args))
    with pytest.raises(WorkflowError, match="iç ağdaki"):
        web.fetch("http://degisen.example/", None)
    assert opened == []
    # A proxy would resolve the name again; pages are always read directly.
    assert not any(isinstance(item, web.ProxyHandler) and item.proxies for item in web._page_opener().handlers)


def test_search_providers_are_normalized_and_filtered_to_allowed_sites(monkeypatch):
    calls = []

    def fake_json(url, *, headers=None, data=None, timeout=20):
        calls.append((url, headers, json.loads(data) if data else None))
        if "tavily" in url:
            return {"results": [{"title": "Mevzuat", "url": "https://www.mevzuat.gov.tr/a", "content": "<b>VUK</b> 230"},
                                {"title": "Blog", "url": "https://blog.example.com/b", "content": "x"}]}
        if "wikipedia" in url:
            return {"query": {"search": [{"title": "Elektronik fatura", "snippet": "<span>e-Fatura</span> sistemi"}]}}
        return {"web": {"results": [{"title": "Brave", "url": "https://ornek.com", "description": "d"}]}}

    monkeypatch.setattr(web, "_json", fake_json)
    results = web.search({"provider": "tavily"}, "tvly-anahtar", "fatura süresi", 5, ["mevzuat.gov.tr"])
    assert results == [{"title": "Mevzuat", "url": "https://www.mevzuat.gov.tr/a", "snippet": "VUK 230"}]
    assert calls[-1][1]["Authorization"] == "Bearer tvly-anahtar" and calls[-1][2]["include_domains"] == ["mevzuat.gov.tr"]
    assert "site:mevzuat.gov.tr" in calls[-1][2]["query"]
    wiki = web.search({"provider": "wikipedia", "language": "tr"}, None, "e-fatura", 3)
    assert wiki[0]["url"] == "https://tr.wikipedia.org/wiki/Elektronik_fatura" and wiki[0]["snippet"] == "e-Fatura sistemi"
    assert web.search({"provider": "brave"}, "k", "x", 3)[0]["title"] == "Brave"
    with pytest.raises(WorkflowError, match="kapalı"):
        web.search({"provider": "none"}, None, "x", 3)


def test_search_settings_keep_the_key_in_the_secret_store(tmp_path, monkeypatch):
    values = {}
    store = SimpleNamespace(store=lambda account, value: values.update({account: value}), load=lambda account: values.get(account),
                            remove=lambda account: values.pop(account, None))
    monkeypatch.setattr("rpa_orkestrai.vault.system_store", lambda: store)
    settings = web.SearchSettings(tmp_path)
    saved = settings.save(2, {"provider": "tavily", "key": "tvly-gizli-anahtar"})
    assert saved["has_key"] and "tvly-gizli-anahtar" not in json.dumps(saved)
    assert "tvly-gizli-anahtar" not in (tmp_path / "agent_search.json").read_text()
    assert settings.key(2) == "tvly-gizli-anahtar" and settings.secrets() == ["tvly-gizli-anahtar"]
    assert settings.get(3)["provider"] == "none"
    with pytest.raises(ValueError):
        settings.save(2, {"provider": "google"})
    assert not settings.save(2, {"provider": "wikipedia", "remove_key": True})["has_key"]


def web_agent(runtime, access="allowlist", domains=("mevzuat.gov.tr",)):
    return runtime.service.create_agent(AgentInput(name="Araştırmacı", model="test", web_access=access,
                                                   web_domains=list(domains) if access == "allowlist" else [],
                                                   limits=AgentLimits(max_seconds=30)))


def test_web_tools_reach_only_agents_with_internet_and_each_request_is_recorded(runtime, monkeypatch):
    runtime.service.search_settings = SimpleNamespace(get=lambda company: {"provider": "tavily"}, key=lambda company: "k")
    monkeypatch.setattr(web, "search", lambda config, key, query, count, domains: [
        {"title": "Mevzuat", "url": "https://www.mevzuat.gov.tr/a", "snippet": f"{query} · {domains}"}])
    closed = runtime.agent()
    run = runtime.done(runtime.start(closed, response(ToolCall(uid(), "web_search", {"query": "fatura"})), response(finish())))
    assert "web_search" not in {tool["name"] for tool in runtime.state["provider"].requests[0]["tools"]}
    error = next(event.data["untrusted_data"] for event in run.events if event.kind == "tool_result")
    assert error["status"] == "error"
    researcher = web_agent(runtime)
    saved = runtime.done(runtime.start(researcher, response(ToolCall(uid(), "web_search", {"query": "fatura süresi"})),
                                       response(finish("Kaynak: mevzuat"))))
    tools = {tool["name"] for tool in runtime.state["provider"].requests[0]["tools"]}
    assert {"web_search", "fetch_page"} <= tools
    assert "İnternet araştırması açık" in runtime.state["provider"].requests[0]["messages"][0]["content"]
    searched = next(event for event in saved.events if event.kind == "web_search")
    assert searched.data["query"] == "fatura süresi" and searched.data["urls"] == ["https://www.mevzuat.gov.tr/a"]
    result = next(event.data["untrusted_data"] for event in saved.events if event.kind == "tool_result")
    assert "mevzuat.gov.tr" in result["results"][0]["snippet"]


def test_a_task_makes_at_most_twenty_web_requests(runtime, monkeypatch):
    runtime.service.search_settings = SimpleNamespace(get=lambda company: {"provider": "wikipedia"}, key=lambda company: None)
    monkeypatch.setattr(web, "search", lambda *args: [])
    calls = [ToolCall(uid(), "web_search", {"query": f"soru {index}"}) for index in range(21)]
    agent = runtime.service.create_agent(AgentInput(name="Açık", model="test", web_access="open",
                                                    limits=AgentLimits(max_seconds=30, max_turns=40)))
    saved = runtime.done(runtime.start(agent, response(*calls), response(finish())))
    results = [event.data["untrusted_data"] for event in saved.events if event.kind == "tool_result"]
    assert sum(item.get("status") == "error" for item in results) == 1 and "en fazla 20" in results[-2]["error"]


def test_unused_web_fields_stay_out_of_the_agent_file(runtime):
    plain = runtime.agent()
    researcher = web_agent(runtime)
    store = runtime.service.agent_store
    assert "web_access" not in store.path("agents", plain.id).read_text()
    data = json.loads(store.path("agents", researcher.id).read_text())
    assert data["web_access"] == "allowlist" and data["web_domains"] == ["mevzuat.gov.tr"]
    with pytest.raises(ValueError, match="en az bir site"):
        AgentInput(name="X", web_access="allowlist")
