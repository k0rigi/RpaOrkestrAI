"""Ajanın akışsız yetenekleri ve sohbet: okuma yalnız seçilen yerlerde, gönderme onaylı, sohbet hiçbir şey yapmaz."""

import json
from types import SimpleNamespace

import pytest
from test_agent_playbooks import documents
from test_agent_runner import AGENT_TEST_SECONDS, approval_wait, finish, response
from test_agent_runner import runtime as runtime  # noqa: F401

from rpa_orkestrai.actions import mail, transfer
from rpa_orkestrai.agents.models import AgentAbilities, AgentInput, AgentLimits, AgentRunRequest, Playbook
from rpa_orkestrai.agents.providers import ProviderResponse, ScriptedProvider, ToolCall, Usage
from rpa_orkestrai.agents.runner import AgentServiceError
from rpa_orkestrai.connections import Connections
from rpa_orkestrai.models import uid


def connection(runtime, kind, **config):
    store = Connections(runtime.settings.data_dir, runtime.settings)
    defaults = {"smtp": {"host": "smtp.firma.com", "sender": "destek@firma.com", "password": "smtp-gizli-parola"},
                "webhook": {"service": "slack", "url": "https://hooks.slack.com/services/gizli"},
                "imap": {"host": "imap.firma.com", "user": "destek@firma.com", "password": "imap-gizli-parola"}}
    return store.create({"name": f"{kind} hesabı", "type": kind, "config": {**defaults[kind], **config}})["id"]


def agent_with(runtime, cards=(), **abilities):
    return runtime.service.create_agent(AgentInput(name="Destek", model="test", playbooks=list(cards),
                                                   provider_connection_id=uid(),
                                                   abilities=AgentAbilities(**abilities),
                                                   limits=AgentLimits(max_seconds=AGENT_TEST_SECONDS)))


def start(runtime, agent, *replies, inputs=None):
    runtime.state["provider"] = ScriptedProvider(list(replies))
    return runtime.service.start(agent.id, AgentRunRequest(task="Gelen e-postayı yanıtla", inputs=inputs or {}))


def results(run):
    return [event.data["untrusted_data"] for event in run.events
            if event.kind == "tool_result" and event.data.get("name") != "finish"]


def test_documents_are_read_only_inside_the_chosen_folders(runtime):
    docs = documents(runtime.business / "gelen")
    other = runtime.business.parent / "baska"
    other.mkdir()
    (other / "gizli.txt").write_text("başka klasör", encoding="utf-8")
    agent = agent_with(runtime, document_folders=[str(docs)])
    saved = runtime.done(start(runtime, agent,
                               response(ToolCall(uid(), "list_documents", {})),
                               response(ToolCall(uid(), "read_document", {"path": str(docs / "iade.txt")}),
                                        ToolCall(uid(), "read_document", {"path": str(other / "gizli.txt")})),
                               response(finish("İade süresi 14 gün."))))
    names = {tool["name"] for tool in runtime.state["provider"].requests[0]["tools"]}
    assert {"list_documents", "read_document"} <= names and "send_email" not in names
    listed, read, refused = results(saved)
    assert {item["name"] for item in listed["documents"]} >= {"iade.txt", "sss.docx", "fiyat.xlsx"}
    assert "14 gün" in read["text"] and read["parts"] == 1
    assert refused["status"] == "error" and "izinli klasör" in refused["error"]
    assert any(event.kind == "document_read" for event in saved.events)
    assert "Metni anlamak" in runtime.state["provider"].requests[0]["messages"][0]["content"]


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    def fake_send(ctx, p):
        sent.append(p)
        return {"sent": True, "to": list(p["to"]), "refused": [], "subject": p["subject"]}

    monkeypatch.setattr(mail, "send", fake_send)
    return sent


def reply_call(to="musteri@ornek.com", body="Merhaba, siparişiniz yarın kargoda."):
    return ToolCall(uid(), "send_email", {"to": [to], "subject": "Re: Sipariş", "body": body,
                                          "in_reply_to": "<a1@ornek.com>", "reason": "Müşteriye yanıt"})


def test_an_email_reply_goes_only_to_the_sender_after_a_corrected_approval(runtime, outbox):
    agent = agent_with(runtime, email_connection_id=connection(runtime, "smtp"))
    inputs = {"eposta": {"from": "musteri@ornek.com", "subject": "Sipariş", "message_id": "<a1@ornek.com>"}}
    run = start(runtime, agent, response(reply_call(to="baska@kotu.com")), response(reply_call()), response(finish()),
                inputs=inputs)
    pending = approval_wait(runtime, run)
    assert pending.pending_approval["workflow_name"] == "E-posta gönder · smtp hesabı"
    assert pending.pending_approval["inputs"]["kime"] == ["musteri@ornek.com"]
    runtime.service.approve(run.id, pending.pending_approval["id"], True,
                            {**pending.pending_approval["inputs"], "metin": "Merhaba, siparişiniz bugün kargoda."})
    saved = runtime.done(run)
    refused, sent = results(saved)
    assert "yalnız göreve verilen adreslere" in refused["error"]
    assert sent["status"] == "sent" and sent["approver_edits"]["changed_inputs"] == {
        "metin": "Merhaba, siparişiniz bugün kargoda."}
    assert outbox == [{"connection": agent.abilities.email_connection_id, "to": ["musteri@ornek.com"], "cc": [],
                       "subject": "Re: Sipariş", "body": "Merhaba, siparişiniz bugün kargoda.",
                       "in_reply_to": "<a1@ornek.com>"}]
    assert any(event.kind == "email_sent" for event in saved.events)


def test_sending_without_approval_is_the_approvers_call_and_is_recorded(runtime, outbox):
    smtp = connection(runtime, "smtp")
    runtime.state["actor"] = runtime.owner.model_copy(update={"permissions": ("agents.use", "agents.manage")})
    with pytest.raises(AgentServiceError, match="onay yetkilisi"):
        agent_with(runtime, email_connection_id=smtp, email_recipients="domains", email_domains=["ornek.com"],
                   email_without_approval=True)
    runtime.state["actor"] = runtime.owner
    agent = agent_with(runtime, email_connection_id=smtp, email_recipients="domains", email_domains=["@Ornek.com"],
                       email_without_approval=True)
    assert agent.abilities.email_domains == ["ornek.com"] and agent.ability_audit[0].ability == "email"
    saved = runtime.done(start(runtime, agent, response(reply_call(to="satis@sube.ornek.com")), response(finish())))
    assert results(saved)[0]["status"] == "sent" and not any(event.kind == "approval_requested" for event in saved.events)
    assert outbox[0]["to"] == ["satis@sube.ornek.com"]


def test_cards_apply_to_sending_too(runtime, outbox):
    smtp = connection(runtime, "smtp")
    leave = Playbook(title="Şikâyet", steps="Özetle, insana bırak.", mode="handoff")
    agent = agent_with(runtime, cards=[leave], email_connection_id=smtp, email_recipients="any",
                       email_without_approval=True)
    saved = runtime.done(start(runtime, agent, response(reply_call()),
                               response(ToolCall(uid(), "use_playbook", {"number": 1, "reason": "Şikâyet"})),
                               response(reply_call()), response(finish("Özet"))))
    first, _, third = results(saved)
    assert "use_playbook" in first["error"] and "insana bırakılır" in third["error"]
    assert not outbox and saved.handoff


def test_messages_go_to_the_agents_channel(runtime, monkeypatch):
    posted = []
    monkeypatch.setattr(transfer, "notify_send", lambda ctx, p: posted.append(p) or {"sent": True, "chat": "42"})
    hook = connection(runtime, "webhook")
    agent = agent_with(runtime, message_connection_id=hook)
    run = start(runtime, agent, response(ToolCall(uid(), "send_message", {"title": "Özet", "text": "3 fatura işlendi.",
                                                                           "reason": "Günlük özet"})), response(finish()))
    pending = approval_wait(runtime, run)
    runtime.service.approve(run.id, pending.pending_approval["id"], True)
    saved = runtime.done(run)
    assert posted == [{"connection": hook, "title": "Özet", "text": "3 fatura işlendi."}]
    assert results(saved)[0] == {"status": "sent", "chat": "42"}


def test_ability_connections_must_exist_and_have_the_right_kind(runtime):
    hook = connection(runtime, "webhook")
    with pytest.raises(AgentServiceError, match="E-posta gönderme bağlantısı değil"):
        agent_with(runtime, email_connection_id=hook)
    with pytest.raises(AgentServiceError, match="bulunamadı"):
        agent_with(runtime, inbox_connection_id=uid())
    with pytest.raises(AgentServiceError, match="veri veya program"):
        agent_with(runtime, document_folders=[str(runtime.settings.data_dir)])
    with pytest.raises(ValueError, match="alan adı"):
        AgentAbilities(email_recipients="domains")
    plain = runtime.agent()
    assert "abilities" not in json.loads(runtime.service.agent_store.path("agents", plain.id).read_text())


def test_chat_answers_from_the_work_records_and_cannot_send(runtime, outbox):
    agent = agent_with(runtime, email_connection_id=connection(runtime, "smtp"),
                       document_folders=[str(documents(runtime.business / "gelen"))])
    done = runtime.done(start(runtime, agent, response(finish("Fatura işlendi."))))
    runtime.state["provider"] = provider = ScriptedProvider([
        ProviderResponse(tool_calls=[ToolCall(uid(), "work_summary", {"period": "today"}),
                                     ToolCall(uid(), "send_email", {"to": ["x@y.com"]})], usage=Usage(10, 5)),
        ProviderResponse(text="Bugün 1 görev tamamladım; bekleyen iş yok.", usage=Usage(20, 8))])
    answer = runtime.service.chat.ask(agent.id, "Bugün neler yaptın?")
    assert answer["reply"].text == "Bugün 1 görev tamamladım; bekleyen iş yok." and answer["reply"].tokens == 43
    # The screen shows how long the answer took and how many model calls it needed.
    assert answer["rounds"] == 2 and answer["seconds"] >= 0
    assert "Selamlaşma" in provider.requests[0]["messages"][0]["content"] and provider.requests[0]["max_tokens"] <= 2048
    tools = {tool["name"] for tool in provider.requests[0]["tools"]}
    assert {"work_summary", "list_tasks", "get_task", "read_document"} <= tools and "send_email" not in tools
    summary, refused = [json.loads(message["content"])["untrusted_data"] for message in provider.requests[1]["messages"]
                        if message["role"] == "tool"]
    assert summary["agents"][0]["tasks"] == 1 and summary["agents"][0]["succeeded"] == 1 and summary["now"] == []
    assert refused["status"] == "error" and not outbox
    history = runtime.service.chat.history(agent.id)
    assert [item.role for item in history] == ["user", "assistant"] and history[0].user == "Yetkili"
    runtime.state["provider"] = ScriptedProvider([ProviderResponse(
        tool_calls=[ToolCall(uid(), "get_task", {"task_id": done.task_id})], usage=Usage(1, 1)),
        ProviderResponse(text="Görev tamamlandı.", usage=Usage(1, 1))])
    runtime.service.chat.ask(agent.id, "Son görevin ne oldu?")
    detail = [json.loads(message["content"])["untrusted_data"] for message in
              runtime.state["provider"].requests[1]["messages"] if message["role"] == "tool"][0]
    assert detail["summary"] == "Fatura işlendi." and detail["status"] == "succeeded"
    assert len(runtime.state["provider"].requests[0]["messages"]) == 4  # system, the earlier exchange, the question
    runtime.service.chat.clear(agent.id)
    assert runtime.service.chat.history(agent.id) == []


def test_chat_refuses_secrets_and_one_question_at_a_time(runtime, monkeypatch):
    agent = agent_with(runtime)
    monkeypatch.setattr(runtime.service, "_new_redactor", lambda: SimpleNamespace(
        contains_secret=lambda text: "gizli-77" in text, text=lambda text: text, sanitize=lambda value: value))
    with pytest.raises(AgentServiceError, match="şifre"):
        runtime.service.chat.ask(agent.id, "Şifre gizli-77 mi?")
    runtime.service.chat._busy.add(agent.id)
    with pytest.raises(AgentServiceError, match="önceki soruyu"):
        runtime.service.chat.ask(agent.id, "Durum nedir?")
    runtime.service.chat._busy.clear()
    runtime.service.delete_agent(agent.id)
    assert not runtime.service.chat._path(agent.id).exists()
