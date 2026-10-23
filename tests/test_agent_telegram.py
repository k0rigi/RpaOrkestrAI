"""Telegram köprüsü: ajan soruları ve onayları Telegram'a gider; yanıt ve karar yalnız kayıtlı sohbetten döner."""

import threading
import time
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from test_agent_api import api as agent_api  # noqa: F401
from test_agent_runner import finish, response, wait_for
from test_agent_runner import runtime as runtime  # noqa: F401

from rpa_orkestrai.agents.models import Actor
from rpa_orkestrai.agents.providers import ToolCall
from rpa_orkestrai.agents.redaction import Redactor
from rpa_orkestrai.agents.runner import AgentServiceError
from rpa_orkestrai.agents.telegram_bridge import CLOSED, TelegramBridge, TelegramSettings
from rpa_orkestrai.models import uid

CHAT, TOKEN, CONNECTION = "123456789", "bot-gizli-anahtar", "b" * 32
CLAIMS, LOGISTICS, RUN, ITEM = "c" * 32, "d" * 32, "e" * 32, "f" * 32
OWNER = Actor(user_id=1, company_id=2, session_id="s", permissions=("agents.use", "agents.manage", "agents.approve"),
              office_id=CLAIMS, office_name="Claim & İade",
              offices=((CLAIMS, "Claim & İade", True), (LOGISTICS, "Lojistik", True)))


class Telegram:
    """A fake Bot API: records every call; getUpdates hands out what the test queued."""

    def __init__(self):
        self.calls, self.updates, self.lock, self.next_id = [], [], threading.Lock(), 100

    def __call__(self, token, method, payload, timeout):
        assert token == TOKEN
        with self.lock:
            self.calls.append((method, payload))
            if method == "sendMessage":
                self.next_id += 1
                return 200, {"ok": True, "result": {"message_id": self.next_id}}
            updates, self.updates = (self.updates, []) if method == "getUpdates" else ([], self.updates)
        if method == "getUpdates":
            time.sleep(0.02)
            return 200, {"ok": True, "result": updates}
        return 200, {"ok": True, "result": True}

    def sent(self, method="sendMessage"):
        with self.lock:
            return [payload for name, payload in self.calls if name == method]


class Connections:
    def get(self, identity):
        if identity != CONNECTION:
            raise KeyError(identity)
        return {"id": CONNECTION, "type": "webhook", "config": {"service": "telegram", "token": TOKEN, "chat_id": CHAT}}

    def list(self):
        return [{"id": CONNECTION, "name": "Benim botum", "type": "webhook", "service": "telegram", "chat_id": CHAT,
                 "has_token": True}, {"id": "a" * 32, "name": "Teams", "type": "webhook", "service": "teams"}]


class Service:
    def __init__(self, tmp_path, actor=OWNER):
        self.settings, self.actor, self.answers, self.decisions, self.error = SimpleNamespace(data_dir=tmp_path), actor, [], [], None

    def _authorize(self, permission="agents.use"):
        return self.actor

    def answer(self, run_id, item_id, value, *, office=None, via=None):
        assert via == "telegram"
        if self.error:
            raise AgentServiceError(self.error, 409)
        self.answers.append((run_id, item_id, value, office))

    def approve(self, run_id, item_id, approved, inputs=None, *, office=None, via=None):
        assert via == "telegram"
        self.decisions.append((run_id, item_id, approved, office))


def make(tmp_path, actor=OWNER, **settings):
    """A bridge whose background loops are off: the tests hand it each update themselves."""
    telegram, service = Telegram(), Service(tmp_path, actor)
    bridge = TelegramBridge(service, Connections, transport=telegram)
    bridge.close()
    chosen = TelegramSettings(connection_id=CONNECTION, chat_id=CHAT, **settings)
    bridge.save(actor, chosen)
    return bridge, telegram, service, chosen


def context(office=CLAIMS, actor=OWNER, secrets=()):
    return SimpleNamespace(run=SimpleNamespace(id=RUN, actor=actor, office_id=office), agent=SimpleNamespace(name="İade ajanı"),
                           redactor=Redactor(secrets))


def callback(data, chat=CHAT, sender=CHAT):
    return {"update_id": 1, "callback_query": {"id": "cb", "data": data, "from": {"id": int(sender)},
                                               "message": {"chat": {"id": int(chat)}}}}


def message(text, reply_to=None, chat=CHAT, sender=CHAT, date=None):
    body = {"message_id": 900, "text": text, "chat": {"id": int(chat)}, "from": {"id": int(sender)},
            "date": int(time.time() if date is None else date)}
    if reply_to:
        body["reply_to_message"] = {"message_id": reply_to}
    return {"update_id": 2, "message": body}


def question(bridge, options=("Evet", "Hayır"), office=CLAIMS, item=ITEM, text="Kayıt silinsin mi?", secrets=()):
    bridge._send("question", context(office, secrets=secrets), {"id": item, "question": text, "options": list(options),
                                                                "expires_at": "2026-10-18T12:30:00+00:00"})


def keys(telegram):
    return [button["callback_data"] for row in telegram.sent()[-1]["reply_markup"]["inline_keyboard"] for button in row]


def test_settings_accept_only_a_telegram_bot_and_a_private_chat(tmp_path):
    bridge, telegram, service, chosen = make(tmp_path)
    public = bridge.public(OWNER)
    assert public["configured"] and public["connections"] == [{"id": CONNECTION, "name": "Benim botum", "chat_id": CHAT, "ready": True}]
    for chat in ("-1001234567890", "@kanal", "0", ""):
        with pytest.raises(ValidationError):
            TelegramSettings(connection_id=CONNECTION, chat_id=chat)
    with pytest.raises(KeyError):
        bridge.save(OWNER, TelegramSettings(connection_id="a" * 32, chat_id=CHAT))
    other = OWNER.model_copy(update={"user_id": 7})
    assert bridge.settings(other) is None and bridge.public(other)["configured"] is False
    assert bridge.test(OWNER, chosen) == {"sent": True} and telegram.sent()[-1]["chat_id"] == CHAT
    assert bridge.remove(OWNER)["configured"] is False


def test_a_question_is_answered_with_a_button_once(tmp_path):
    bridge, telegram, service, chosen = make(tmp_path)
    question(bridge, office=LOGISTICS)
    sent = telegram.sent()[-1]
    assert sent["chat_id"] == CHAT and "İade ajanı (Lojistik ofisi) soruyor" in sent["text"] and "Kayıt silinsin mi?" in sent["text"]
    first, second = keys(telegram)
    bridge.handle(callback(second), chosen, TOKEN)
    assert service.answers == [(RUN, ITEM, "Hayır", LOGISTICS)]
    assert telegram.sent("answerCallbackQuery")[-1]["text"].startswith("Yanıtınız ajana iletildi")
    assert telegram.sent("editMessageText")[-1]["text"].endswith("— Yanıtınız ajana iletildi: Hayır")
    bridge.handle(callback(first), chosen, TOKEN)
    assert len(service.answers) == 1 and telegram.sent("answerCallbackQuery")[-1]["text"] == "Bu soru veya onay artık beklemiyor."


def test_text_answers_need_a_reply_when_more_than_one_question_is_open(tmp_path):
    bridge, telegram, service, chosen = make(tmp_path)
    question(bridge, options=())
    first = telegram.sent()[-1]
    assert "reply_markup" not in first and "Yanıtınızı bu mesajı yanıtlayarak" in first["text"]
    question(bridge, options=(), item="a" * 32, text="Tutar kaç?")
    bridge.handle(message("1.250 TL"), chosen, TOKEN)
    assert service.answers == [] and "Yanıtla ile seçip yazın" in telegram.sent()[-1]["text"]
    bridge.handle(message("İkinci kayıt", reply_to=101), chosen, TOKEN)  # The first question's message.
    assert service.answers == [(RUN, ITEM, "İkinci kayıt", CLAIMS)]
    # Now only one question is open: a plain message written after it answers it.
    bridge.handle(message("1.250 TL"), chosen, TOKEN)
    assert service.answers[-1] == (RUN, "a" * 32, "1.250 TL", CLAIMS)
    assert telegram.sent()[-1]["text"].startswith("Yanıtınız ajana iletildi")


def test_other_chats_and_senders_and_stale_messages_are_ignored(tmp_path):
    bridge, telegram, service, chosen = make(tmp_path)
    question(bridge, options=())
    before = len(telegram.calls)
    bridge.handle(message("Evet", chat="555"), chosen, TOKEN)
    bridge.handle(message("Evet", sender="555"), chosen, TOKEN)
    bridge.handle(callback("q:x:0", sender="555"), chosen, TOKEN)
    assert service.answers == [] and len(telegram.calls) == before
    bridge.handle(message("Eski yanıt", date=time.time() - 3600), chosen, TOKEN)
    # A message written before the question answers nothing and gets no reply either.
    assert service.answers == [] and len(telegram.calls) == before


def test_an_unregistered_private_chat_learns_its_id_once_and_nothing_runs(tmp_path):
    bridge, telegram, service, chosen = make(tmp_path)
    stranger = {"update_id": 3, "message": {"message_id": 5, "text": "/ajanlar", "date": int(time.time()),
                                            "chat": {"id": 555, "type": "private"}, "from": {"id": 555}}}
    bridge.handle(stranger, chosen, TOKEN)
    bridge.handle(stranger, chosen, TOKEN)
    sent = telegram.sent()
    assert len(sent) == 1 and sent[0]["chat_id"] == "555" and "Sohbet kimliğiniz: 555" in sent[0]["text"]
    assert "Görebildiğiniz" not in sent[0]["text"] and service.answers == []
    assert bridge.public(OWNER)["health"]["stranger"] == "555"
    # A group the person is in is never answered.
    group = {"update_id": 4, "message": {"message_id": 6, "text": "selam", "date": int(time.time()),
                                         "chat": {"id": -100, "type": "group"}, "from": {"id": 556}}}
    bridge.handle(group, chosen, TOKEN)
    assert len(telegram.sent()) == 1


@pytest.mark.parametrize(("status", "expected"), [(200, "listening"), (409, "error"), (0, "error")])
def test_the_settings_show_whether_the_bot_is_read_now(tmp_path, status, expected):
    calls = []

    def transport(token, method, payload, timeout):
        calls.append(method)
        if status == 0:
            raise OSError("ağ yok")
        return status, {"ok": status == 200, "result": [], "description": "Conflict"}

    service = Service(tmp_path)
    bridge = TelegramBridge(service, Connections, transport=transport)
    try:
        assert bridge.public(OWNER)["health"]["state"] == "off"
        bridge.save(OWNER, TelegramSettings(connection_id=CONNECTION, chat_id=CHAT))
        wait_for(lambda: bridge.public(OWNER)["health"]["state"], lambda state: state == expected)
        health = bridge.public(OWNER)["health"]
        assert "getUpdates" in calls and health["at"]
        if status == 409:
            assert "webhook" in health["detail"]
        if status == 0:
            assert "internet" in health["detail"]
    finally:
        bridge.close()


def test_approvals_go_only_to_an_approver_and_are_decided_with_buttons(tmp_path):
    bridge, telegram, service, chosen = make(tmp_path)
    payload = {"id": ITEM, "workflow_name": "Sipariş gir", "reason": "Yeni kayıt", "inputs": {"musteri": "ACME", "tutar": 12},
               "expires_at": "2026-10-18T12:30:00+00:00"}
    bridge._send("approval", context(LOGISTICS), payload)
    sent = telegram.sent()[-1]
    assert "Onay gerekiyor: İade ajanı (Lojistik ofisi)" in sent["text"] and "• musteri: ACME" in sent["text"]
    approve, reject = keys(telegram)
    assert approve.endswith(":y") and reject.endswith(":n")
    bridge.handle(callback(approve[:-1] + "x"), chosen, TOKEN)  # Not one of the buttons: nothing is decided.
    assert service.decisions == []
    bridge.handle(callback(reject), chosen, TOKEN)
    assert service.decisions == [(RUN, ITEM, False, LOGISTICS)]
    assert telegram.sent("editMessageText")[-1]["text"].endswith("Reddedildi; işlem başlatılmadı.")
    member = OWNER.model_copy(update={"permissions": ("agents.use",),
                                      "offices": ((CLAIMS, "Claim & İade", False), (LOGISTICS, "Lojistik", False))})
    quiet, quiet_telegram, _, _ = make(tmp_path / "uye", actor=member)
    quiet._send("approval", context(CLAIMS, actor=member), payload)
    assert quiet_telegram.sent() == []


def test_secrets_are_masked_closed_items_reject_late_answers_and_switches_are_kept(tmp_path):
    bridge, telegram, service, chosen = make(tmp_path)
    question(bridge, text="Şifre gizli-deger123 ile girilsin mi?", secrets=("gizli-deger123",))
    assert "gizli-deger123" not in telegram.sent()[-1]["text"]
    token = keys(telegram)[0]
    bridge._send("closed", context(), {"id": ITEM})
    assert telegram.sent("editMessageText")[-1]["text"].endswith(CLOSED)
    bridge.handle(callback(token), chosen, TOKEN)
    assert service.answers == [] and telegram.sent("answerCallbackQuery")[-1]["text"] == "Bu soru veya onay artık beklemiyor."
    silent, silent_telegram, _, _ = make(tmp_path / "kapali", questions=False)
    question(silent)
    assert silent_telegram.sent() == []


def test_without_telegram_set_up_nothing_is_sent_or_read_from_telegram(tmp_path):
    telegram, service = Telegram(), Service(tmp_path)
    bridge = TelegramBridge(service, Connections, transport=telegram)
    bridge.start_if_configured()  # Nobody set Telegram up on this computer: the channel does not even start.
    assert bridge._threads == []
    bridge.notify("closed", context(), {"id": ITEM})
    time.sleep(0.3)
    bridge.close()
    assert telegram.calls == []


def test_a_refused_answer_is_explained_on_telegram(tmp_path):
    bridge, telegram, service, chosen = make(tmp_path)
    question(bridge)
    service.error = "Soru artık yanıt beklemiyor veya süresi doldu."
    bridge.handle(callback(keys(telegram)[0]), chosen, TOKEN)
    assert telegram.sent("answerCallbackQuery")[-1]["text"] == "Yanıt iletilemedi: Soru artık yanıt beklemiyor veya süresi doldu."


def test_an_agents_question_is_answered_from_telegram_and_the_run_continues(runtime, tmp_path):  # noqa: F811
    telegram = Telegram()
    bridge = TelegramBridge(runtime.service, Connections, transport=telegram)
    runtime.service.notifier = bridge
    chosen = TelegramSettings(connection_id=CONNECTION, chat_id=CHAT)
    bridge.save(runtime.owner, chosen)
    try:
        run = runtime.start(runtime.agent(), response(ToolCall(uid(), "ask_user", {"question": "Hangisi?", "options": ["A", "B"]})),
                            response(finish("Seçim yapıldı")))
        sent = wait_for(lambda: telegram.sent(), lambda value: bool(value))
        assert "Hangisi?" in sent[-1]["text"]
        token = sent[-1]["reply_markup"]["inline_keyboard"][1][0]["callback_data"]
        with telegram.lock:
            telegram.updates.append(callback(token))
        saved = runtime.done(run)
        assert saved.status == "succeeded" and any(event.kind == "user_answer" for event in saved.events)
        assert wait_for(lambda: telegram.sent("editMessageText"), lambda value: bool(value))[-1]["text"].endswith("B")
    finally:
        bridge.close()


def test_settings_routes_are_licensed_and_validated(agent_api, monkeypatch):  # noqa: F811
    bridge = agent_api.app.state.telegram
    monkeypatch.setattr(bridge, "connections", Connections)
    monkeypatch.setattr(bridge, "transport", Telegram())  # Saving starts listening: never the real Telegram.
    client = agent_api.client
    assert client.get("/api/agents/telegram").json()["configured"] is False
    assert client.put("/api/agents/telegram", json={"connection_id": CONNECTION, "chat_id": "-100"}).status_code == 422
    assert client.put("/api/agents/telegram", json={"connection_id": "a" * 32, "chat_id": CHAT}).status_code == 404
    saved = client.put("/api/agents/telegram", json={"connection_id": CONNECTION, "chat_id": CHAT, "approvals": False})
    assert saved.status_code == 200 and saved.json()["approvals"] is False and TOKEN not in saved.text
    assert client.delete("/api/agents/telegram").json()["configured"] is False
    agent_api.licensing.agents = False
    assert client.get("/api/agents/telegram").status_code == 403
