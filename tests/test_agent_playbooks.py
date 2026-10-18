"""Bilgi kaynakları, süreç kartları ve taslak onayı: firma işleyişi ajanın yetkisini daraltır, hiç genişletmez."""

import hashlib
import json
import zipfile
from types import SimpleNamespace

import openpyxl
import pytest
from test_agent_runner import AGENT_TEST_SECONDS, approval_wait, finish, response, run_call, write_flow
from test_agent_runner import runtime as runtime  # noqa: F401

from rpa_orkestrai.actions.mail import build, reply_headers
from rpa_orkestrai.agents import knowledge
from rpa_orkestrai.agents.knowledge import KnowledgeBase
from rpa_orkestrai.agents.models import AgentInput, AgentLimits, Playbook, WorkflowGrant
from rpa_orkestrai.agents.providers import ToolCall
from rpa_orkestrai.agents.runner import AgentServiceError
from rpa_orkestrai.errors import WorkflowError
from rpa_orkestrai.models import Step, uid


def documents(folder):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "iade.txt").write_text("İADE POLİTİKASI\n\nÜrünler teslimattan itibaren 14 gün içinde iade edilebilir. "
                                     "Faturanın aslı gereklidir.\n\nKargo ücreti müşteriye aittir.", encoding="utf-8")
    with zipfile.ZipFile(folder / "sss.docx", "w") as archive:
        archive.writestr("word/document.xml", "<w:document><w:body><w:p><w:r><w:t>Teslimat süresi</w:t></w:r></w:p>"
                                              "<w:p><w:r><w:t xml:space=\"preserve\">Siparişler 2 iş günü içinde kargoya "
                                              "verilir &amp; takip numarası gönderilir.</w:t></w:r></w:p></w:body></w:document>")
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Fiyatlar"
    sheet.append(["Ürün", "Fiyat"])
    sheet.append(["Çelik vida M6", "12,50 TL"])
    book.save(folder / "fiyat.xlsx")
    nested = folder / "arsiv"
    nested.mkdir(exist_ok=True)
    (nested / "kampanya.html").write_text("<html><body><h1>Kampanya</h1><p>Eylülde kargo bedava.</p><script>x()</script>"
                                          "</body></html>", encoding="utf-8")
    (folder / "~$gecici.docx").write_text("kilit", encoding="utf-8")
    (folder / ".gizli.txt").write_text("gizli", encoding="utf-8")
    (folder / "resim.png").write_bytes(b"\x89PNG")
    return folder


def test_documents_are_read_split_and_found_without_turkish_letter_differences(tmp_path):
    docs = documents(tmp_path / "belgeler")
    base = KnowledgeBase(tmp_path / "cache", protected=[tmp_path / "data"])
    status = base.status([str(docs)])[0]
    assert status["exists"] and status["files"] == 4 and status["skipped"] == 1 and not status["errors"]
    found = base.search([str(docs)], "faturanin asli gerekli mi", 2)
    assert found[0]["source"] == "iade.txt" and "14 gün" in found[0]["text"]
    assert base.search([str(docs)], "vida fiyatı", 1)[0]["text"].startswith("Ürün: Çelik vida M6; Fiyat: 12,50 TL")
    assert base.search([str(docs)], "kargoya ne zaman", 1)[0]["source"] == "sss.docx"
    campaign = base.search([str(docs)], "kampanya", 1)[0]
    assert campaign["source"] == "kampanya.html" and "x()" not in campaign["text"]
    assert base.search([str(docs)], "olmayan konu zebra", 3) == []
    with pytest.raises(WorkflowError, match="anlamlı"):
        base.search([str(docs)], "ve ile", 3)
    assert knowledge.terms("İADE iade IŞIK ışık")[:4] == ["iade", "iade", "isik", "isik"]


def test_a_changed_document_is_read_again_and_the_cache_is_reused(tmp_path, monkeypatch):
    docs = documents(tmp_path / "belgeler")
    calls = []
    real = knowledge.extract
    monkeypatch.setattr(knowledge, "extract", lambda path: calls.append(path.name) or real(path))
    first = KnowledgeBase(tmp_path / "cache")
    first.search([str(docs)], "iade", 1)
    assert len(calls) == 4
    # A new Studio session reads the saved cache instead of the documents.
    second = KnowledgeBase(tmp_path / "cache")
    second.search([str(docs)], "iade", 1)
    assert len(calls) == 4
    (docs / "iade.txt").write_text("İade süresi 30 gündür.", encoding="utf-8")
    assert "30 gün" in second.search([str(docs)], "iade süresi", 1)[0]["text"]
    assert calls[-1] == "iade.txt" and len(calls) == 5


def test_unreadable_and_missing_sources_are_reported(tmp_path):
    folder = tmp_path / "belgeler"
    folder.mkdir()
    (folder / "bozuk.pdf").write_bytes(b"%PDF-bozuk")
    (folder / "bos.docx").write_bytes(b"zip degil")
    base = KnowledgeBase(tmp_path / "cache")
    status = base.status([str(folder), str(tmp_path / "yok")])
    assert status[0]["files"] == 2 and {item["name"] for item in status[0]["errors"]} == {"bozuk.pdf", "bos.docx"}
    assert status[1]["exists"] is False


def test_studio_folders_cannot_be_sources_and_paths_must_be_absolute(runtime):
    with pytest.raises(ValueError, match="tam yol"):
        AgentInput(name="Ajan", knowledge_sources=["belgeler"])
    for source in (runtime.settings.data_dir, runtime.settings.data_dir / "alt", runtime.settings.data_dir.parent):
        with pytest.raises(AgentServiceError, match="veri veya program"):
            runtime.service.create_agent(AgentInput(name="Ajan", model="test", knowledge_sources=[str(source)]))


def agent_with(runtime, *flows, cards=(), sources=(), bypass=False):
    grants = [WorkflowGrant(workflow_id=flow.id, allow_without_approval=bypass, allowed_roots=[str(runtime.business)])
              for flow in flows]
    return runtime.service.create_agent(AgentInput(
        name="Müşteri hizmetleri", model="test", workflows=grants, playbooks=list(cards),
        knowledge_sources=[str(item) for item in sources], limits=AgentLimits(max_seconds=AGENT_TEST_SECONDS)))


def tool_results(run):
    return [event.data["untrusted_data"] for event in run.events if event.kind == "tool_result"]


def test_knowledge_tool_is_offered_only_with_sources_and_each_search_is_recorded(runtime):
    docs = documents(runtime.business / "belgeler")
    agent = agent_with(runtime, sources=[docs])
    search = ToolCall(uid(), "search_knowledge", {"query": "iade süresi kaç gün"})
    saved = runtime.done(runtime.start(agent, response(search), response(finish("14 gün (iade.txt)"))))
    request = runtime.state["provider"].requests[0]
    assert "search_knowledge" in {tool["name"] for tool in request["tools"]}
    assert "Firma bilgi kaynakları tanımlı" in request["messages"][0]["content"]
    event = next(event for event in saved.events if event.kind == "knowledge_search")
    assert event.data["query"] == "iade süresi kaç gün" and event.data["sources"][0] == "iade.txt"
    assert "14 gün" in tool_results(saved)[0]["results"][0]["text"]
    plain = runtime.agent()
    saved = runtime.done(runtime.start(plain, response(ToolCall(uid(), "search_knowledge", {"query": "iade"})),
                                       response(finish())))
    assert "search_knowledge" not in {tool["name"] for tool in runtime.state["provider"].requests[0]["tools"]}
    assert tool_results(saved)[0]["status"] == "error"


def test_without_a_fitting_card_nothing_changes_and_the_work_is_left_to_a_person(runtime):
    flow, target = write_flow(runtime)
    agent = agent_with(runtime, flow, cards=[Playbook(title="Bilgi talebi", steps="Bilgi kaynağından yanıtla.")], bypass=True)
    handoff = ToolCall(uid(), "finish", {"summary": "Fiyat itirazı; uyan kart yok.", "handoff": True})
    saved = runtime.done(runtime.start(agent, response(run_call(flow)), response(handoff)))
    assert not target.exists() and saved.workflow_count == 0
    assert "use_playbook" in tool_results(saved)[0]["error"]
    assert "1. Bilgi talebi" in runtime.state["provider"].requests[0]["messages"][0]["content"]
    assert saved.handoff and any(event.kind == "handoff" for event in saved.events)
    listed = runtime.service.handoffs()
    assert [item["run_id"] for item in listed] == [saved.id] and listed[0]["agent_name"] == "Müşteri hizmetleri"
    resolved = runtime.service.resolve_handoff(saved.id)
    assert resolved.handoff_resolved_at and resolved.handoff_resolved_by == "Yetkili"
    assert runtime.service.handoffs() == []
    assert runtime.service.playbook_stats(agent.id)["kartsiz"]["handoffs"] == 1
    # Unused fields stay out of the agent and run files, so earlier versions can still read them.
    plain = runtime.agent()
    assert not {"playbooks", "knowledge_sources"} & set(json.loads(
        runtime.service.agent_store.path("agents", plain.id).read_text()))
    other = runtime.done(runtime.start(plain, response(finish())))
    assert not {"handoff", "playbook_id", "handoff_resolved_at"} & set(json.loads(
        runtime.service.agent_store.path("agent_runs", other.id).read_text()))


def test_review_card_always_asks_even_with_a_bypass_and_a_handoff_card_never_changes(runtime):
    flow, target = write_flow(runtime)
    review = Playbook(title="Sipariş değişikliği", steps="Değişikliği kaydet.", mode="review")
    agent = agent_with(runtime, flow, cards=[review], bypass=True)
    choose = ToolCall(uid(), "use_playbook", {"number": 1, "reason": "Müşteri sipariş değişikliği istiyor"})
    run = runtime.start(agent, response(choose), response(run_call(flow)), response(finish()))
    pending = approval_wait(runtime, run)
    assert pending.pending_approval["playbook_title"] == "Sipariş değişikliği"
    runtime.service.approve(run.id, pending.pending_approval["id"], True)
    saved = runtime.done(run)
    assert saved.status == "succeeded" and target.exists() and saved.playbook_id == review.id
    assert runtime.service.playbook_stats(agent.id)[review.id] == {"approved": 1}
    target.unlink()
    leave = Playbook(title="Şikâyet", steps="Özetle ve yöneticiye bırak.", mode="handoff")
    second = agent_with(runtime, flow, cards=[leave], bypass=True)
    choose = ToolCall(uid(), "use_playbook", {"number": 1, "reason": "Şikâyet"})
    saved = runtime.done(runtime.start(second, response(choose), response(run_call(flow)), response(finish("Özet"))))
    assert not target.exists() and "insana bırakılır" in tool_results(saved)[1]["error"]
    assert saved.handoff and saved.playbook_id == leave.id


def test_a_card_limits_which_flow_may_make_changes(runtime):
    flow, target = write_flow(runtime)
    other, _ = write_flow(runtime)
    card = Playbook(title="Kayıt", steps="Yalnız kayıt akışını kullan.", workflow_ids=[other.id])
    agent = agent_with(runtime, flow, other, cards=[card], bypass=True)
    choose = ToolCall(uid(), "use_playbook", {"number": 1, "reason": "Kayıt"})
    saved = runtime.done(runtime.start(agent, response(choose), response(run_call(flow)), response(finish())))
    assert not target.exists() and "kartında kullanılmaz" in tool_results(saved)[1]["error"]
    with pytest.raises(ValueError, match="izinli akışları"):
        AgentInput(name="Ajan", playbooks=[Playbook(title="X", steps="Y", workflow_ids=[uid()])])
    with pytest.raises(ValueError, match="farklı"):
        AgentInput(name="Ajan", playbooks=[Playbook(title="Konu", steps="A"), Playbook(title="konu", steps="B")])


def text_flow(runtime):
    target = runtime.business / "yanit.txt"
    flow = runtime.workflow(Step(action="file.write_text", params={"path": str(target), "text": "${metin}",
                                                                   "mode": "append"}))
    return flow, target


def test_the_approver_corrects_the_draft_and_exactly_that_runs(runtime):
    flow, target = text_flow(runtime)
    agent = agent_with(runtime, flow)
    run = runtime.start(agent, response(run_call(flow, inputs={"metin": "Taslak yanıt", "adet": 2})), response(finish()))
    pending = approval_wait(runtime, run)
    key = pending.pending_approval["id"]
    for inputs, message in [({"metin": "x"}, "eklenemez"), ({"metin": 5, "adet": 2}, "türü"),
                            ({"metin": "x", "adet": 2, "yeni": 1}, "eklenemez")]:
        with pytest.raises(AgentServiceError, match=message):
            runtime.service.approve(run.id, key, True, inputs)
    with pytest.raises(AgentServiceError, match="onaylarken"):
        runtime.service.approve(run.id, key, False, {"metin": "x", "adet": 2})
    runtime.service.approve(run.id, key, True, {"metin": "Düzeltilmiş yanıt", "adet": 2})
    saved = runtime.done(run)
    assert saved.status == "succeeded" and target.read_text(encoding="utf-8") == "Düzeltilmiş yanıt"
    decision = next(event for event in saved.events if event.kind == "approval_decision")
    assert decision.data["edited"] and decision.data["changes"] == {
        "metin": {"before": "Taslak yanıt", "after": "Düzeltilmiş yanıt"}}
    edits = tool_results(saved)[0]["approver_edits"]
    assert edits["changed_inputs"] == {"metin": "Düzeltilmiş yanıt"} and "suggest_note" in edits["message"]
    assert runtime.service.playbook_stats(agent.id)["kartsiz"] == {"edited": 1}


def test_a_masked_secret_cannot_be_edited_but_stays_intact_when_approved(runtime, monkeypatch):
    from rpa_orkestrai.vault import Vault

    values = {}
    memory = SimpleNamespace(store=lambda account, value: values.update({account: value}),
                             load=lambda account: values.get(account))
    monkeypatch.setattr("rpa_orkestrai.vault.system_store", lambda: memory)
    secret = "kayitli-gizli-deger-77"
    Vault(runtime.settings.data_dir).set("erp", secret)
    flow, target = text_flow(runtime)
    agent = agent_with(runtime, flow)
    run = runtime.start(agent, response(run_call(flow, inputs={"metin": f"Kod {secret}", "not": "Kısa"})),
                        response(finish()))
    pending = approval_wait(runtime, run)
    shown = pending.pending_approval["inputs"]["metin"]
    assert secret not in shown and "[gizlendi]" in shown
    key = pending.pending_approval["id"]
    with pytest.raises(AgentServiceError, match="gizli"):
        runtime.service.approve(run.id, key, True, {"metin": "Kod değişti", "not": "Kısa"})
    with pytest.raises(AgentServiceError, match="şifre"):
        runtime.service.approve(run.id, key, True, {"metin": shown, "not": f"Şifre {secret}"})
    # The unchanged (masked) value means "as proposed": the real value runs.
    runtime.service.approve(run.id, key, True, {"metin": shown, "not": "Kısa"})
    saved = runtime.done(run)
    assert target.read_text(encoding="utf-8") == f"Kod {secret}"
    assert not next(event for event in saved.events if event.kind == "approval_decision").data.get("edited")


class CentralApprovals:
    """Each request has its own state, as on the central server."""

    def __init__(self):
        self.states, self.requests, self.decisions, self.cancelled, self.consumed = {}, [], [], [], []

    def request(self, context, prepared, reason, *, expires_in):
        identity = uid()
        self.states[identity] = "pending"
        remote = {"id": identity, "workflow_digest": prepared.digest, "run_id": context.run.id, "attempt": 1,
                  "inputs_digest": hashlib.sha256(json.dumps(
                      prepared.inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()}
        self.requests.append((remote, reason))
        return remote

    def status(self, context, remote):
        return {"status": self.states[remote["id"]], "approver_user_id": 1}

    def decide(self, identity, approved, office_id=None):
        self.decisions.append((identity, approved))
        self.states[identity] = "approved" if approved else "rejected"
        return {"id": identity, "status": self.states[identity]}

    def consume(self, context, remote, *, digest):
        assert digest == remote["workflow_digest"]
        self.consumed.append(remote["id"])
        self.states[remote["id"]] = "consumed"

    def cancel(self, context, remote):
        self.cancelled.append(remote["id"])
        self.states[remote["id"]] = "cancelled"


def test_a_corrected_draft_is_recorded_and_decided_centrally_before_it_runs(runtime):
    flow, target = text_flow(runtime)
    backend = CentralApprovals()
    runtime.service.approval_backend = backend
    agent = agent_with(runtime, flow)
    run = runtime.start(agent, response(run_call(flow, inputs={"metin": "Taslak"})), response(finish()))
    pending = approval_wait(runtime, run)
    runtime.service.approve(run.id, pending.pending_approval["id"], True, {"metin": "Düzeltildi"})
    saved = runtime.done(run)
    assert saved.status == "succeeded" and target.read_text(encoding="utf-8") == "Düzeltildi"
    (first, _), (second, reason) = backend.requests
    assert reason.endswith("(düzenlendi)") and backend.decisions == [(second["id"], True)]
    assert backend.cancelled == [first["id"]] and backend.consumed == [second["id"]]


def test_reply_headers_keep_the_conversation_together():
    assert reply_headers("<a1@x.com>") == ("<a1@x.com>", "<a1@x.com>")
    assert reply_headers("a1@x.com") == ("<a1@x.com>", "<a1@x.com>")
    assert reply_headers("<r1@x> <r2@x> <a1@x.com>") == ("<a1@x.com>", "<r1@x> <r2@x> <a1@x.com>")
    assert reply_headers("") == ("", "")
    for bad in ("bozuk", "<a@x>\r\nBcc: z@y"):
        with pytest.raises(WorkflowError):
            reply_headers(bad)
    message, _ = build({"sender": "destek@firma.com"}, {"to": "musteri@ornek.com", "subject": "Re: Sipariş",
                                                        "body": "Merhaba", "in_reply_to": "<a1@x.com>"})
    assert message["In-Reply-To"] == "<a1@x.com>" and message["References"] == "<a1@x.com>"
    plain, _ = build({"sender": "destek@firma.com"}, {"to": "musteri@ornek.com", "subject": "Bilgi", "body": "x"})
    assert plain["In-Reply-To"] is None

