"""WhatsApp (Business Cloud API) ve Telegram: istek biçimi, anlaşılır hatalar ve gizli anahtarın korunması."""

from types import SimpleNamespace

import pytest

from rpa_orkestrai.actions import transfer
from rpa_orkestrai.connections import Connections
from rpa_orkestrai.errors import WorkflowError


@pytest.fixture
def sent(monkeypatch):
    calls, answers = [], []

    def fake(url, payload, headers, timeout):
        calls.append({"url": url, "payload": payload, "headers": headers})
        return answers.pop(0) if answers else (200, {"ok": True, "result": {"message_id": 7},
                                                      "messages": [{"id": "wamid.1"}]})

    monkeypatch.setattr(transfer, "_post_json", fake)
    return SimpleNamespace(calls=calls, answers=answers)


def create(tmp_path, **config):
    connections = Connections(tmp_path)
    item = connections.create({"name": "Kanal", "type": "webhook", "config": config})
    return connections, connections.get(item["id"])


def step(connections, profile, **params):
    ctx = SimpleNamespace(connections=connections, log=lambda *args, **kwargs: None)
    return transfer.notify_send(ctx, {"connection": profile["id"], "text": "Siparişiniz kargoda.", **params})


def test_telegram_sends_to_the_chat_and_keeps_the_token_secret(tmp_path, sent):
    connections, profile = create(tmp_path, service="telegram", token="123456:gizli-bot-anahtari", chat_id="-1001234567890")
    public = connections.list()[0]
    assert public["ready"] and public["has_token"] and "gizli-bot-anahtari" not in str(public)
    assert "123456:gizli-bot-anahtari" in connections.secrets()
    result = step(connections, profile, title="Sipariş")
    call = sent.calls[0]
    assert call["url"] == "https://api.telegram.org/bot123456:gizli-bot-anahtari/sendMessage"
    assert call["payload"] == {"chat_id": "-1001234567890", "text": "Sipariş\n\nSiparişiniz kargoda.",
                               "disable_web_page_preview": True}
    assert result["sent"] and result["chat"] == "-1001234567890"
    step(connections, profile, to="@duyurular")
    assert sent.calls[1]["payload"]["chat_id"] == "@duyurular"


@pytest.mark.parametrize("status,answer,text", [
    (400, {"ok": False, "description": "Bad Request: chat not found"}, "/start"),
    (401, {"ok": False}, "Bot anahtarı geçersiz"),
    (403, {"ok": False}, "engellemiş"),
])
def test_telegram_errors_are_explained_without_the_token(tmp_path, sent, status, answer, text):
    connections, profile = create(tmp_path, service="telegram", token="123456:gizli-bot-anahtari", chat_id="42")
    sent.answers.append((status, answer))
    with pytest.raises(WorkflowError, match=text) as error:
        step(connections, profile)
    assert "gizli-bot-anahtari" not in str(error.value)


def test_whatsapp_text_and_template_messages(tmp_path, sent):
    connections, profile = create(tmp_path, service="whatsapp", token="EAAG-gizli", phone_number_id="1098765432",
                                  to="+90 532 123 45 67")
    assert profile["config"]["to"] == "905321234567" and profile["config"]["api_version"] == "v26.0"
    result = step(connections, profile, title="Bilgi")
    call = sent.calls[0]
    assert call["url"] == "https://graph.facebook.com/v26.0/1098765432/messages"
    assert call["headers"] == {"Authorization": "Bearer EAAG-gizli"}
    assert call["payload"] == {"messaging_product": "whatsapp", "recipient_type": "individual", "to": "905321234567",
                               "type": "text", "text": {"preview_url": False, "body": "*Bilgi*\nSiparişiniz kargoda."}}
    assert result["id"] == "wamid.1" and result["to"] == "905321234567"
    connections.update(profile["id"], {"name": "Kanal", "type": "webhook", "config": {
        "service": "whatsapp", "phone_number_id": "1098765432", "mode": "template", "template_name": "siparis_kargoda",
        "template_language": "tr"}})
    template = connections.get(profile["id"])
    assert template["config"]["token"] == "EAAG-gizli"  # Same service: the saved token is kept.
    step(connections, template, to="905551112233", template_values="Ayşe\nKRG-123\n")
    assert sent.calls[1]["payload"] == {"messaging_product": "whatsapp", "to": "905551112233", "type": "template",
                                        "template": {"name": "siparis_kargoda", "language": {"code": "tr"},
                                                     "components": [{"type": "body", "parameters": [
                                                         {"type": "text", "text": "Ayşe"},
                                                         {"type": "text", "text": "KRG-123"}]}]}}


@pytest.mark.parametrize("code,text", [(131047, "24 saatte"), (132001, "Şablon bulunamadı"), (190, "Erişim anahtarı")])
def test_whatsapp_errors_are_explained(tmp_path, sent, code, text):
    connections, profile = create(tmp_path, service="whatsapp", token="EAAG-gizli", phone_number_id="1098765432",
                                  to="905321234567")
    sent.answers.append((400, {"error": {"code": code, "message": "provider text"}}))
    with pytest.raises(WorkflowError, match=text) as error:
        step(connections, profile)
    assert "provider text" not in str(error.value) and "EAAG-gizli" not in str(error.value)


def test_messaging_connections_validate_their_fields(tmp_path):
    connections = Connections(tmp_path)
    for config, message in [({"service": "telegram", "token": "1:a", "chat_id": "kanal"}, "sohbet kimliği"),
                            ({"service": "whatsapp", "token": "x", "phone_number_id": "abc"}, "rakam"),
                            ({"service": "whatsapp", "token": "x", "phone_number_id": "1", "to": "0532"}, "ülke koduyla"),
                            ({"service": "whatsapp", "token": "x", "phone_number_id": "1", "mode": "template",
                              "template_name": "Büyük Ad"}, "Şablon adını")]:
        with pytest.raises(ValueError, match=message):
            connections.create({"name": "Kanal", "type": "webhook", "config": config})
    telegram = connections.create({"name": "Bot", "type": "webhook", "config": {
        "service": "telegram", "token": "1:gizli", "chat_id": "42"}})
    # Switching to another service never carries a stored token over.
    connections.update(telegram["id"], {"config": {"service": "whatsapp", "phone_number_id": "1098765432"}})
    assert connections.get(telegram["id"])["config"]["token"] == ""
    slack = connections.create({"name": "Slack", "type": "webhook", "config": {"service": "slack",
                                                                               "url": "https://hooks.slack.com/x"}})
    ctx = SimpleNamespace(connections=connections, log=lambda *args, **kwargs: None)
    with pytest.raises(WorkflowError, match="Alıcı yalnız"):
        transfer.notify_send(ctx, {"connection": slack["id"], "text": "x", "to": "905321234567"})


def test_telegram_chat_finder_lists_recent_chats(monkeypatch):
    monkeypatch.setattr(transfer, "_post_json", lambda url, payload, headers, timeout: (200, {"ok": True, "result": [
        {"message": {"chat": {"id": 42, "first_name": "Ayşe", "last_name": "Yılmaz", "type": "private"}}},
        {"my_chat_member": {"chat": {"id": -1001, "title": "Muhasebe", "type": "supergroup"}}},
        {"message": {"chat": {"id": 42, "first_name": "Ayşe", "type": "private"}}}]}))
    assert transfer.telegram_chats("1:a") == [{"id": "42", "name": "Ayşe", "type": "private"},
                                              {"id": "-1001", "name": "Muhasebe", "type": "supergroup"}]
