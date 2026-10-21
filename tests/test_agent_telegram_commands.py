"""Telegram'dan görev ve soru: yönlendirme tahminsizdir, Studio'daki yetkilerden geçer ve kayıtlarda Telegram'dan yazar."""

import json
import time
from types import SimpleNamespace

import pytest
from test_agent_runner import AGENT_TEST_SECONDS, finish, response, wait_for
from test_agent_runner import runtime as runtime  # noqa: F401
from test_agent_telegram import (
    CHAT,
    CONNECTION,
    LOGISTICS,
    OWNER,
    TOKEN,
    Connections,
    Telegram,
    context,
    message,
)

from rpa_orkestrai.agents.models import Actor, AgentInput, AgentLimits, AgentRunRequest
from rpa_orkestrai.agents.providers import ScriptedProvider
from rpa_orkestrai.agents.redaction import Redactor
from rpa_orkestrai.agents.runner import AgentServiceError
from rpa_orkestrai.agents.telegram_bridge import HELP, TelegramBridge, TelegramSettings
from rpa_orkestrai.agents.telegram_commands import TargetError, fold, listing, route
from rpa_orkestrai.models import uid

CLAIMS = "c" * 32


def person(name, role="department", office=None, department="Genel"):
    return SimpleNamespace(id=uid(), name=name, role=role, office_id=office, department=department)


class Team:
    def __init__(self, agents, actor=OWNER):
        self.agent_store = SimpleNamespace(agents=lambda: agents)
        self.actor, self.started, self.asked, self.error = actor, [], [], None
        self.settings = None
        self.chat = SimpleNamespace(ask=self.ask)

    @staticmethod
    def _sees_agent(viewer, agent):
        return agent.office_id == viewer.office_id

    def _authorize(self, permission="agents.use"):
        return self.actor

    def start(self, agent_id, body, *, office=None, via=None):
        if self.error:
            raise AgentServiceError(self.error, 403)
        self.started.append((agent_id, body.task, body.title, office, via))

    def ask(self, agent_id, text, *, office=None, via=None):
        self.asked.append((agent_id, text, office, via))
        return {"reply": SimpleNamespace(text="Bekleyen 2 iş var.")}


OFFICES = [person("İade yöneticisi", "manager", CLAIMS), person("Kontrol ajanı", office=CLAIMS, department="Kontrol"),
           person("Lojistik yöneticisi", "manager", LOGISTICS), person("Rota ajanı", office=LOGISTICS, department="Planlama"),
           person("Ortak ajan", office=CLAIMS), person("Ortak ajan", office=LOGISTICS)]
SINGLE = Actor(user_id=1, company_id=2, session_id="s", permissions=("agents.use",))
ONE_OFFICE = [person("Yönetici", "manager"), person("Rapor ajanı", department="Rapor")]


def test_one_office_goes_to_the_manager_unless_an_agent_is_named():
    team = Team(ONE_OFFICE, SINGLE)
    target = route(team, SINGLE, "bugünkü bekleyen işleri özetle")
    assert (target.agent_name, target.office_id, target.text) == ("Yönetici", None, "bugünkü bekleyen işleri özetle")
    assert route(team, SINGLE, "RAPOR AJANI:  haftalık tablo").agent_name == "Rapor ajanı"
    # A colon inside the text is not a name: the whole text stays the task.
    assert route(team, SINGLE, "Saat 10:00 raporunu hazırla").text == "Saat 10:00 raporunu hazırla"
    with pytest.raises(TargetError, match="boş"):
        route(team, SINGLE, "Rapor ajanı:   ")
    with pytest.raises(TargetError, match="yönetici ajan yok"):
        route(Team([person("Rapor ajanı")], SINGLE), SINGLE, "tabloyu hazırla")


def test_several_offices_need_the_office_and_never_guess_between_same_names():
    team = Team(OFFICES)
    with pytest.raises(TargetError, match="Birden fazla ofisiniz var.*Claim & İade, Lojistik"):
        route(team, OWNER, "durumu özetle")
    target = route(team, OWNER, "lojistik: yarının sevkiyatlarını planla")
    assert (target.agent_name, target.office_id, target.office_name) == ("Lojistik yöneticisi", LOGISTICS, "Lojistik")
    assert route(team, OWNER, "Lojistik: Rota ajanı: rota çıkar").agent_name == "Rota ajanı"
    # A name used in only one office finds its office by itself.
    named = route(team, OWNER, "Kontrol ajanı: iadeleri kontrol et")
    assert (named.office_id, named.text) == (CLAIMS, "iadeleri kontrol et")
    with pytest.raises(TargetError, match="birden fazla ajan"):
        route(team, OWNER, "Ortak ajan: bir iş")
    assert route(team, OWNER, "Claim & İade: Ortak ajan: bir iş").office_id == CLAIMS
    assert fold("İADE") == fold("iade") and fold("KONTROL  AJANI") == fold("Kontrol ajanı")


def test_the_agent_list_shows_every_office_managers_first():
    text = listing(Team(OFFICES), OWNER)
    assert text.splitlines()[0] == "Claim & İade ofisi" and "  • İade yöneticisi (yönetici)" in text
    assert text.index("Lojistik yöneticisi") < text.index("Rota ajanı (Planlama)")


def bridge_for(tmp_path, team):
    telegram = Telegram()
    team.settings = SimpleNamespace(data_dir=tmp_path)
    bridge = TelegramBridge(team, Connections, transport=telegram)
    bridge.close()  # The tests hand each update over themselves.
    chosen = TelegramSettings(connection_id=CONNECTION, chat_id=CHAT)
    bridge.save(OWNER, chosen)
    return bridge, telegram, chosen


def test_tasks_and_questions_from_telegram_reach_the_named_office_and_say_where_they_went(tmp_path):
    team = Team(OFFICES)
    bridge, telegram, chosen = bridge_for(tmp_path, team)
    bridge.handle(message("/gorev Lojistik: Yarının sevkiyatlarını planla"), chosen, TOKEN)
    manager = OFFICES[2]
    assert team.started == [(manager.id, "Yarının sevkiyatlarını planla", "Yarının sevkiyatlarını planla", LOGISTICS,
                             "telegram")]
    assert telegram.sent()[-1]["text"].startswith("📋 Görev Lojistik yöneticisi (Lojistik ofisi) ajanına verildi")
    bridge.handle(message("/sor@RpaBot Lojistik: kaç iş bekliyor?"), chosen, TOKEN)
    reply = wait_for(lambda: telegram.sent(), lambda value: value[-1]["text"].startswith("💬"))[-1]
    assert reply["text"] == "💬 Lojistik yöneticisi (Lojistik ofisi):\n\nBekleyen 2 iş var."
    assert team.asked == [(manager.id, "kaç iş bekliyor?", LOGISTICS, "telegram")]
    assert {"chat_id": CHAT, "action": "typing"} in telegram.sent("sendChatAction")
    # A plain message with nothing waiting for an answer is a question too.
    bridge.handle(message("Claim & İade: durum nedir?"), chosen, TOKEN)
    wait_for(lambda: team.asked, lambda value: len(value) == 2)
    assert team.asked[-1][:3] == (OFFICES[0].id, "durum nedir?", CLAIMS)


def test_wrong_old_or_refused_commands_start_nothing_and_say_why(tmp_path):
    team = Team(OFFICES)
    bridge, telegram, chosen = bridge_for(tmp_path, team)
    bridge.handle(message("/gorev bir iş"), chosen, TOKEN)
    assert "Birden fazla ofisiniz var" in telegram.sent()[-1]["text"]
    bridge.handle(message("/gorev Lojistik: eski iş", date=time.time() - 3600), chosen, TOKEN)
    assert "Studio kapalıyken gönderildi" in telegram.sent()[-1]["text"]
    before = len(telegram.calls)
    bridge.handle(message("/gorev Lojistik: başkasının işi", chat="555", sender="555"), chosen, TOKEN)
    assert len(telegram.calls) == before  # another chat gets no answer at all
    team.error = "Bu ajan işlemi için kullanıcı yetkiniz yok."
    bridge.handle(message("/gorev Lojistik: yetkisiz iş"), chosen, TOKEN)
    assert telegram.sent()[-1]["text"] == "Görev verilemedi: Bu ajan işlemi için kullanıcı yetkiniz yok."
    assert team.started == []
    bridge.handle(message("/ajanlar"), chosen, TOKEN)
    assert telegram.sent()[-1]["text"].startswith("Claim & İade ofisi")
    bridge.handle(message("/start"), chosen, TOKEN)
    assert telegram.sent()[-1]["text"] == HELP


def test_the_end_of_a_telegram_task_is_written_back_with_secrets_masked(tmp_path):
    bridge, telegram, _ = bridge_for(tmp_path, Team(OFFICES))
    run = context(LOGISTICS)
    run.redactor = Redactor(("gizli-77",))
    bridge._send("finished", run, {"status": "succeeded", "title": "Sevkiyat planı", "summary": "Şifre gizli-77 ile 3 plan"})
    text = telegram.sent()[-1]["text"]
    assert text.startswith("✅ Görev bitti: İade ajanı (Lojistik ofisi)\nSevkiyat planı") and "gizli-77" not in text
    bridge._send("finished", run, {"status": "failed", "title": "Sevkiyat planı", "error": "Süre doldu."})
    assert "❌ Görev tamamlanamadı" in telegram.sent()[-1]["text"] and "Neden: Süre doldu." in telegram.sent()[-1]["text"]


def manager(runtime):  # noqa: F811
    return runtime.service.create_agent(AgentInput(name="Yönetici", role="manager", model="test",
                                                   provider_connection_id=uid(),
                                                   limits=AgentLimits(max_seconds=AGENT_TEST_SECONDS)))


def test_a_telegram_task_runs_like_a_studio_task_is_marked_and_reports_its_result(runtime):  # noqa: F811
    head = manager(runtime)
    telegram = Telegram()
    bridge = TelegramBridge(runtime.service, Connections, transport=telegram)
    runtime.service.notifier = bridge
    chosen = TelegramSettings(connection_id=CONNECTION, chat_id=CHAT)
    bridge.save(runtime.owner, chosen)
    try:
        runtime.state["provider"] = ScriptedProvider([response(finish("Rapor hazır: 4 bekleyen iş"))])
        bridge.handle(message("/gorev Bekleyen işleri raporla"), chosen, TOKEN)
        run = wait_for(lambda: [item for item in runtime.service.agent_store.runs() if item.via == "telegram"],
                       lambda value: bool(value))[0]
        saved = runtime.done(run)
        assert saved.status == "succeeded" and saved.agent_id == head.id
        assert any(event.kind == "telegram" and event.message == "Görev Telegram'dan verildi." for event in saved.events)
        assert runtime.service.agent_store.task(saved.task_id).via == "telegram"
        done = wait_for(lambda: telegram.sent(), lambda value: value[-1]["text"].startswith("✅"))[-1]["text"]
        assert done.startswith("✅ Görev bitti: Yönetici\nBekleyen işleri raporla") and "Rapor hazır: 4 bekleyen iş" in done
        # A task given in the Studio keeps the file earlier versions read: no "via" at all.
        runtime.state["provider"] = ScriptedProvider([response(finish())])
        studio = runtime.done(runtime.service.start(head.id, AgentRunRequest(task="Studio işi")))
        folder = runtime.settings.data_dir
        assert "via" not in json.loads(next(folder.rglob(f"{studio.id}.json")).read_text(encoding="utf-8"))
        assert json.loads(next(folder.rglob(f"{saved.id}.json")).read_text(encoding="utf-8"))["via"] == "telegram"
        # A question from Telegram is in the agent's question history, marked as such.
        runtime.state["provider"] = ScriptedProvider([response(text="Bugün 4 iş bekliyor.")])
        bridge.handle(message("Kaç iş bekliyor?"), chosen, TOKEN)
        answer = wait_for(lambda: telegram.sent(), lambda value: value[-1]["text"].startswith("💬"))[-1]["text"]
        assert answer == "💬 Yönetici:\n\nBugün 4 iş bekliyor."
        history = runtime.service.chat.history(head.id)
        assert [(item.role, item.via) for item in history] == [("user", "telegram"), ("assistant", "telegram")]
    finally:
        bridge.close()


def test_answers_given_on_telegram_say_so_in_the_run(runtime):  # noqa: F811
    from rpa_orkestrai.agents.providers import ToolCall

    telegram = Telegram()
    bridge = TelegramBridge(runtime.service, Connections, transport=telegram)
    runtime.service.notifier = bridge
    chosen = TelegramSettings(connection_id=CONNECTION, chat_id=CHAT)
    bridge.save(runtime.owner, chosen)
    try:
        run = runtime.start(runtime.agent(), response(ToolCall(uid(), "ask_user", {"question": "Hangisi?", "options": []})),
                            response(finish()))
        wait_for(lambda: telegram.sent(), lambda value: any("Hangisi?" in item["text"] for item in value))
        bridge.handle(message("A seçeneği"), chosen, TOKEN)
        saved = runtime.done(run)
        answered = next(event for event in saved.events if event.kind == "user_answer")
        assert answered.message == "Kullanıcı soruyu Telegram'dan yanıtladı." and answered.data["via"] == "telegram"
        assert answered.data["answer"] == "A seçeneği"
    finally:
        bridge.close()
