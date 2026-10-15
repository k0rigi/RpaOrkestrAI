"""Onaylı ajan notları: yalnız yetkili kaydeder, izin vermez ve ajanlar arasında paylaşılmaz."""

import json
from types import SimpleNamespace

import pytest
from test_agent_runner import finish, response
from test_agent_runner import runtime as runtime  # noqa: F401

from rpa_orkestrai.agents.models import AgentInput, AgentRunRequest, NoteInput
from rpa_orkestrai.agents.providers import ScriptedProvider, ToolCall
from rpa_orkestrai.agents.runner import AgentServiceError
from rpa_orkestrai.models import uid


def test_manager_saves_notes_that_reach_only_that_agent_on_the_next_task(runtime):
    first, second = runtime.agent(), runtime.agent()
    note = runtime.service.add_note(first.id, NoteInput(text="  Rapor dosyaları   Paylaşılan/Raporlar klasöründedir. "))
    assert note.text == "Rapor dosyaları Paylaşılan/Raporlar klasöründedir." and note.user_name == "Yetkili"
    assert runtime.service.get_agent(first.id).revision == first.revision  # A note is not a permission change.
    assert runtime.service.notes() == {first.id: [note], second.id: []}
    runtime.done(runtime.start(first, response(finish())))
    system = runtime.state["provider"].requests[0]["messages"][0]["content"]
    assert "Kalıcı notlar" in system and "Paylaşılan/Raporlar" in system
    runtime.done(runtime.start(second, response(finish())))
    assert "Paylaşılan/Raporlar" not in json.dumps(runtime.state["provider"].requests, ensure_ascii=False)
    updated = runtime.service.update_note(first.id, note.id, NoteInput(text="Raporlar Arşiv klasöründedir."))
    assert runtime.service.notes()[first.id] == [updated]
    runtime.service.delete_note(first.id, note.id)
    assert runtime.service.notes()[first.id] == []


def test_only_managers_change_notes_and_limits_are_enforced(runtime):
    item = runtime.agent()
    runtime.state["actor"] = runtime.owner.model_copy(update={"user_id": 7, "permissions": ("agents.use",)})
    with pytest.raises(AgentServiceError) as error:
        runtime.service.add_note(item.id, NoteInput(text="Not"))
    assert error.value.status_code == 403
    assert runtime.service.notes()[item.id] == []  # Users may still see what the agent knows.
    runtime.state["actor"] = runtime.owner
    with pytest.raises(AgentServiceError):
        runtime.service.add_note(item.id, NoteInput(text="   "))
    runtime.service.add_note(item.id, NoteInput(text="Tek kayıt"))
    with pytest.raises(AgentServiceError):
        runtime.service.add_note(item.id, NoteInput(text="Tek kayıt"))
    for index in range(8):
        runtime.service.add_note(item.id, NoteInput(text=f"{index} " + "x" * 490))
    with pytest.raises(AgentServiceError, match="4000"):
        runtime.service.add_note(item.id, NoteInput(text="y" * 490))
    other = runtime.service.create_agent(AgentInput(name="Diğer", model="test"))
    foreign_run = runtime.done(runtime.start(other, response(finish())))
    with pytest.raises(AgentServiceError):
        runtime.service.add_note(item.id, NoteInput(text="Başka ajandan", source_run_id=foreign_run.id))
    runtime.state["actor"] = runtime.owner.model_copy(update={"company_id": 9})
    with pytest.raises(AgentServiceError):
        runtime.service.update_note(item.id, runtime.service.notes().get(item.id, [None])[0] or uid(), NoteInput(text="X"))
    runtime.state["actor"] = runtime.owner
    runtime.service.delete_agent(item.id)
    assert item.id not in runtime.service.notes()
    assert not runtime.service.agent_store.path("agent_notes", item.id).exists()


def test_saved_secret_cannot_become_a_note(runtime, monkeypatch):
    from rpa_orkestrai.vault import Vault

    values = {}
    memory = SimpleNamespace(store=lambda account, value: values.update({account: value}),
                             load=lambda account: values.get(account))
    monkeypatch.setattr("rpa_orkestrai.vault.system_store", lambda: memory)
    Vault(runtime.settings.data_dir).set("saved", "gizli-parola-12345")
    item = runtime.agent()
    with pytest.raises(AgentServiceError, match="şifre"):
        runtime.service.add_note(item.id, NoteInput(text="Giriş parolası gizli-parola-12345"))


def test_agent_can_only_suggest_notes_and_suggestions_are_bounded(runtime):
    item = runtime.agent()
    calls = [ToolCall(uid(), "suggest_note", {"text": f"Kalıcı bilgi {index}"}) for index in range(6)]
    run = runtime.start(item, response(*calls), response(finish()))
    saved = runtime.done(run)
    assert saved.status == "succeeded"
    suggested = [event.data["text"] for event in saved.events if event.kind == "note_suggested"]
    assert suggested == [f"Kalıcı bilgi {index}" for index in range(5)]
    results = [event.data["untrusted_data"] for event in saved.events if event.kind == "tool_result"]
    assert results[-2]["status"] == "error"
    assert runtime.service.notes()[item.id] == []  # Nothing is stored without a manager.
    tools = {tool["name"] for tool in runtime.state["provider"].requests[0]["tools"]}
    assert "suggest_note" in tools
    assert all("title" not in json.dumps(tool["parameters"]) for tool in runtime.state["provider"].requests[0]["tools"])


def test_note_saved_mid_run_applies_from_the_next_task(runtime):
    item = runtime.agent()

    def reply(request):
        if len(provider.requests) == 1:
            runtime.service.add_note(item.id, NoteInput(text="Sonradan eklenen bilgi"))
        return None

    provider = ScriptedProvider([response(ToolCall(uid(), "list_workflows", {})), response(finish())], callback=reply)
    runtime.service._provider_factory = lambda agent: provider
    saved = runtime.done(runtime.service.start(item.id, AgentRunRequest(task="İşi yap")))
    assert saved.status == "succeeded"  # Saving a note does not stop running work.
    assert "Sonradan eklenen bilgi" not in json.dumps(provider.requests, ensure_ascii=False)
