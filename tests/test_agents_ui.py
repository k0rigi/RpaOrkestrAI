"""Ağsız Studio ajan ekranı: RPA_UI_TESTS=1 ile mevcut Chromium üzerinde çalışır."""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("RPA_UI_TESTS") != "1", reason="İsteğe bağlı Chromium ajan ekranı testi")
STATIC = Path(__file__).resolve().parents[1] / "src" / "rpa_orkestrai" / "static"
AID, CID, WID, RID, QID = (letter * 32 for letter in "abcde")
ATTACK = '<img src=x onerror="window.injected=true">'


@pytest.fixture
def ui():
    playwright = pytest.importorskip("playwright.sync_api")
    agents = [{"id": AID, "name": ATTACK, "description": "Açıklama", "instructions": "İşlemleri denetle",
               "department": "Genel", "role": "department", "manager_id": None, "provider_connection_id": CID,
               "model": "yerel-model", "workflows": [{"workflow_id": WID, "allow_without_approval": False,
                                                        "allowed_roots": [], "allowed_hosts": []}], "limits": {}}]
    connections = [{"id": CID, "name": "Yerel bağlantı", "provider": "ollama", "model": "yerel-model",
                    "base_url": "http://127.0.0.1:11434", "has_key": False}]
    workflows = [{"id": WID, "name": "Bilgileri oku", "department": "Genel", "description": "Açıklama",
                  "risk": "okuma", "agent_supported": True, "inputs": [], "outputs": []}]
    run = {"id": RID, "agent_id": AID, "title": "Görev", "task": ATTACK, "status": "waiting_user",
           "created_at": "2026-10-13T12:00:00+00:00", "turns": 1, "total_tokens": 20, "events": [
               {"id": "f" * 32, "kind": "assistant", "message": ATTACK, "timestamp": "2026-10-13T12:00:01+00:00", "data": {}}],
           "pending_question": {"id": QID, "question": "Hangi kayıt?", "options": ["İlk", "Son"], "expires_at": "2099-01-01T00:00:00Z"},
           "pending_approval": None, "summary": "", "result": None, "error": None}
    calls, errors = [], []
    session = {"actor": {"name": "Çalışan", "user_id": 1, "company_id": 1}, "can_manage": True, "can_approve": True}

    def handle(route):
        request = route.request
        path = urlsplit(request.url).path
        body = json.loads(request.post_data) if request.post_data else None
        calls.append((request.method, path, body))
        if path == "/":
            route.fulfill(content_type="text/html; charset=utf-8", body='<html lang="tr"><head><meta charset="UTF-8"><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/agents.css"><script src="/agents.js"></script></head><body><main id="root"></main></body></html>')
        elif path in {"/agents.js", "/agents.css", "/styles.css"}:
            route.fulfill(content_type="text/javascript; charset=utf-8" if path.endswith(".js") else "text/css; charset=utf-8", body=(STATIC / path[1:]).read_text(encoding="utf-8"))
        elif path.startswith("/fonts/"):
            route.abort()
        elif path == "/api/agents/session":
            route.fulfill(json=session)
        elif path == "/api/agents/workflows":
            route.fulfill(json=workflows)
        elif path == "/api/agents" and request.method == "GET":
            route.fulfill(json=agents)
        elif path == f"/api/agents/{AID}" and request.method == "PUT":
            agents[0] = {**body, "id": AID}
            route.fulfill(json=agents[0])
        elif path == "/api/agents/connections" and request.method == "GET":
            route.fulfill(json=connections)
        elif path == "/api/agents/connections" and request.method == "POST":
            saved = {**body, "id": "f" * 32, "has_key": False}
            connections.append(saved)
            route.fulfill(json=saved)
        elif path.endswith("/key") and request.method == "PUT":
            route.fulfill(json={"has_key": True})
        elif path == "/api/agents/runs":
            route.fulfill(json=[run])
        elif path == f"/api/agents/runs/{RID}":
            route.fulfill(json=run)
        elif path == f"/api/agents/{AID}/runs":
            route.fulfill(json=run)
        else:
            route.fulfill(status=404, json={"detail": "Test ucu bulunamadı."})

    with playwright.sync_playwright() as runner:
        browser = runner.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 960})
        page.set_default_timeout(5000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", handle)
        page.goto("http://studio.test/")
        page.evaluate("""async () => {
          window.toasts = [];
          window.agentOptions = {
            api: async (path, options) => { const response = await fetch(path, options);
              if (response.status === 204) return null; const body = await response.json();
              if (!response.ok) throw new Error(body.detail); return body; },
            toast: (text) => window.toasts.push(text), confirmDialog: async () => true,
            openRun: (id) => { window.openedRun = id; }
          };
          await window.RpaAgents.mount(document.getElementById('root'), window.agentOptions);
        }""")
        yield page, calls, errors, session, run
        page.evaluate("window.RpaAgents.unmount()")
        browser.close()
    assert not errors


def assert_unique_interactive_ids(page):
    ids = page.locator("button, input, select, textarea, summary").evaluate_all("nodes => nodes.map(node => node.id)")
    assert all(ids) and len(ids) == len(set(ids))


def test_agent_editor_keeps_user_text_safe_and_sends_exact_schema(ui):
    page, calls, _, _, _ = ui
    assert page.get_by_role("heading", name=ATTACK).count() == 1
    assert page.locator("img").count() == 0
    assert page.evaluate("window.injected || false") is False
    assert_unique_interactive_ids(page)
    page.get_by_role("button", name="Düzenle", exact=True).click()
    page.get_by_label("Model adı", exact=True).fill("benim-serbest-modelim")
    page.get_by_label("Talimatlar", exact=True).fill(ATTACK)
    assert_unique_interactive_ids(page)
    page.get_by_role("button", name="Ajanı kaydet").click()
    page.get_by_role("button", name="Görev ver").wait_for()
    saved = [body for method, path, body in calls if method == "PUT" and path == f"/api/agents/{AID}"][0]
    assert saved["model"] == "benim-serbest-modelim" and saved["instructions"] == ATTACK
    assert set(saved) == {"name", "description", "instructions", "department", "role", "manager_id",
                          "provider_connection_id", "model", "workflows", "limits", "web_access", "web_domains"}
    assert saved["web_access"] == "off" and saved["web_domains"] == []
    assert page.locator("img").count() == 0


def test_poll_preserves_question_draft_and_task_inputs(ui):
    page, calls, _, _, _ = ui
    page.get_by_role("button", name="Görev ver").click()
    page.get_by_label("Hedefiniz").fill("Kayıtları incele")
    page.get_by_text("Girdi değişkenleri (isteğe bağlı)", exact=True).click()
    page.get_by_role("button", name="Girdi ekle", exact=True).click()
    page.get_by_label("Girdi adı", exact=True).fill("count")
    page.get_by_label("Değer", exact=True).fill("3")
    page.get_by_role("button", name="Görevi başlat").click()
    answer = page.get_by_label("Yanıtınız")
    answer.wait_for()
    answer.fill("Henüz yazıyorum")
    before = len([path for _, path, _ in calls if path == "/api/agents/runs"])
    page.wait_for_timeout(2300)
    assert len([path for _, path, _ in calls if path == "/api/agents/runs"]) > before
    assert answer.input_value() == "Henüz yazıyorum"
    started = [body for method, path, body in calls if method == "POST" and path == f"/api/agents/{AID}/runs"][0]
    assert started == {"task": "Kayıtları incele", "inputs": {"count": 3}}
    assert_unique_interactive_ids(page)
    assert page.locator("img").count() == 0


def test_provider_key_is_only_sent_to_write_only_endpoint(ui):
    page, calls, _, _, _ = ui
    page.get_by_role("button", name="Bağlantılar", exact=True).click()
    page.get_by_role("button", name="Bağlantı ekle").click()
    page.get_by_label("Bağlantı adı").fill("Bulut testi")
    page.get_by_label("Sağlayıcı", exact=True).select_option("openai")
    page.get_by_label("Yeni API anahtarı").fill("private-test-key")
    page.get_by_label("Varsayılan model adı").fill("serbest-model")
    page.get_by_role("button", name="Bağlantıyı kaydet").click()
    page.get_by_role("heading", name="Bulut testi").wait_for()
    created = [body for method, path, body in calls if method == "POST" and path == "/api/agents/connections"][0]
    assert "private-test-key" not in json.dumps(created)
    keys = [body for method, path, body in calls if method == "PUT" and path.endswith("/key")]
    assert keys == [{"key": "private-test-key"}]
    assert "private-test-key" not in page.locator("body").inner_text()


def test_approval_buttons_require_server_reported_permission(ui):
    page, _, _, session, run = ui
    session["can_approve"] = False
    run["pending_question"] = None
    run["pending_approval"] = {"id": QID, "workflow_name": "Kaydet", "inputs": {"value": ATTACK},
                               "reason": "Kayıt değişecek", "expires_at": "2099-01-01T00:00:00Z"}
    run["status"] = "waiting_approval"
    page.evaluate("window.RpaAgents.mount(document.getElementById('root'), window.agentOptions)")
    page.evaluate("identity => window.RpaAgents.openRun(identity)", RID)
    page.get_by_role("heading", name="İşlem onayı gerekiyor").wait_for()
    assert page.get_by_role("button", name="Onayla", exact=True).count() == 0
    assert page.get_by_text("Bu işlemi yalnız firmanın onay yetkilisi", exact=False).count() == 1
    assert page.locator("img").count() == 0


def test_hidden_page_and_unmounted_view_stop_polling(ui):
    page, calls, _, _, _ = ui
    page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, value: true}); document.dispatchEvent(new Event('visibilitychange'))")
    before = [call for call in calls if call[1].startswith("/api/")]
    page.wait_for_timeout(2200)
    assert [call for call in calls if call[1].startswith("/api/")] == before
    page.evaluate("window.RpaAgents.unmount()")
    page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, value: false}); document.dispatchEvent(new Event('visibilitychange'))")
    page.wait_for_timeout(2200)
    assert [call for call in calls if call[1].startswith("/api/")] == before


def test_shared_connection_has_no_address_or_key_and_honors_initial_tab(ui):
    page, calls, _, _, _ = ui
    page.evaluate("window.RpaAgents.mount(document.getElementById('root'), {...window.agentOptions, initialTab: 'connections'})")
    page.get_by_role("button", name="Bağlantı ekle").click()
    page.get_by_label("Bağlantı adı").fill("Kurum modeli")
    page.get_by_label("Sağlayıcı", exact=True).select_option("shared")
    page.get_by_label("Varsayılan model adı").fill("kurum-modeli")
    assert page.get_by_label("Yeni API anahtarı").is_hidden()
    assert page.get_by_label("Yerel sunucu adresi").is_hidden()
    assert page.get_by_text("Görev ve maskelenmiş akış sonuçları kurumunuzun ortak model sunucusuna gönderilir.", exact=True).is_visible()
    page.get_by_role("button", name="Bağlantıyı kaydet").click()
    page.get_by_role("heading", name="Kurum modeli").wait_for()
    created = [body for method, path, body in calls if method == "POST" and path == "/api/agents/connections"][0]
    assert created == {"name": "Kurum modeli", "provider": "shared", "model": "kurum-modeli", "base_url": None}
    assert not [call for call in calls if call[1].endswith("/key")]
    assert_unique_interactive_ids(page)


def test_extension_owns_polling_and_run_history_only_loads_on_runs_tab(ui):
    page, calls, _, _, _ = ui
    assert not [call for call in calls if call[1] == "/api/agents/runs"]
    page.evaluate("""async () => {
      window.extensionPolls = 0;
      window.RpaAgents.registerTab({id:'test-office', label:'Test ofis', mount: (container) => {
        container.textContent = 'Salt okunur ofis';
        const timer = setInterval(() => { window.extensionPolls++; }, 250);
        return () => clearInterval(timer);
      }});
      await window.RpaAgents.mount(document.getElementById('root'), {...window.agentOptions, initialTab:'test-office'});
    }""")
    page.wait_for_timeout(2300)
    assert page.evaluate("window.extensionPolls") > 0
    assert not [call for call in calls if call[1] == "/api/agents/runs"]
    page.get_by_role("button", name="Çalışmalar", exact=True).click()
    page.wait_for_function("document.querySelector('.agent-run-choice') !== null")
    before = len([call for call in calls if call[1] == "/api/agents/runs"])
    assert before >= 1
    page.wait_for_timeout(2200)
    assert len([call for call in calls if call[1] == "/api/agents/runs"]) > before
    page.get_by_role("button", name="Test ofis", exact=True).click()
    before = len([call for call in calls if call[1] == "/api/agents/runs"])
    page.wait_for_timeout(2300)
    assert len([call for call in calls if call[1] == "/api/agents/runs"]) == before


def test_existing_run_fields_replace_newly_redacted_content_without_resetting_draft(ui):
    page, _, _, _, run = ui
    original = "sonradan-taninan-gizli-deger"
    run["title"] = original
    run["task"] = original
    run["events"][0]["message"] = original
    run["events"][0]["data"] = {"output": original}
    run["pending_question"]["question"] = original
    page.evaluate("identity => window.RpaAgents.openRun(identity)", RID)
    page.get_by_label("Yanıtınız").fill("Henüz yazıyorum")
    assert original in page.locator("body").inner_text()
    run["title"] = "[gizlendi]"
    run["task"] = "[gizlendi]"
    run["events"][0]["message"] = "[gizlendi]"
    run["events"][0]["data"] = {"output": "[gizlendi]"}
    run["pending_question"]["question"] = "[gizlendi]"
    page.wait_for_function("value => !document.body.textContent.includes(value)", arg=original)
    assert page.get_by_label("Yanıtınız").input_value() == "Henüz yazıyorum"
    assert page.locator(".agent-event").count() == 1
    run["events"] = []
    page.wait_for_function("document.querySelectorAll('.agent-event').length === 0")
    assert_unique_interactive_ids(page)


def test_existing_approval_refreshes_when_preview_is_redacted(ui):
    page, _, _, _, run = ui
    original = "onayda-sonradan-maskelenen-deger"
    run["pending_question"] = None
    run["pending_approval"] = {"id": QID, "workflow_name": original, "inputs": {"value": original},
                               "reason": original, "expires_at": "2099-01-01T00:00:00Z"}
    run["status"] = "waiting_approval"
    page.evaluate("identity => window.RpaAgents.openRun(identity)", RID)
    page.get_by_role("heading", name="İşlem onayı gerekiyor").wait_for()
    assert original in page.locator("body").text_content()
    run["pending_approval"].update(workflow_name="[gizlendi]", reason="[gizlendi]", inputs={"value": "[gizlendi]"})
    page.wait_for_function("value => !document.body.textContent.includes(value)", arg=original)
    assert page.get_by_role("button", name="Onayla", exact=True).count() == 1
    assert_unique_interactive_ids(page)


def test_permission_card_is_built_from_saved_grants_and_previews_edits(ui):
    page, calls, _, _, _ = ui
    card = page.locator(".agent-card .agent-permissions")
    assert card.locator('[data-kind="can"]').inner_text().count("«Bilgileri oku» akışını çalıştırabilir") == 1
    assert "Takıldığında size sorar." in card.inner_text()
    assert "İnternete erişemez" in card.locator('[data-kind="cannot"]').text_content()
    assert "30 dk" in page.locator(".agent-card .agent-limit-line").inner_text()
    page.get_by_role("button", name="Düzenle", exact=True).click()
    preview = page.locator(".agent-preview")
    assert "«Bilgileri oku»" in preview.inner_text()
    page.get_by_label("Bilgileri oku", exact=True).uncheck()
    assert "Henüz akış izni yok" in preview.locator('[data-kind="cannot"]').inner_text()
    assert_unique_interactive_ids(page)
    assert not [call for call in calls if call[0] == "PUT"]


def test_getting_started_guides_setup_and_limit_presets_use_minutes(ui):
    page, calls, _, _, _ = ui
    assert page.locator(".agent-start").count() == 0  # Connection and a granted department agent already exist.
    assert page.get_by_text("Ajanlar nasıl çalışır?", exact=True).count() == 1
    page.route("**/api/agents/connections", lambda route: route.fulfill(json=[]))
    page.evaluate("window.RpaAgents.mount(document.getElementById('root'), window.agentOptions)")
    start = page.locator(".agent-start")
    start.wait_for()
    assert "Model bağlantısı ekleyin" in start.inner_text() and "✓ Departman ajanı" in start.inner_text()
    assert start.get_by_role("button", name="Bağlantılar", exact=True).count() == 1
    page.unroute("**/api/agents/connections")
    page.evaluate("window.RpaAgents.mount(document.getElementById('root'), window.agentOptions)")
    page.locator(".agent-card").wait_for()
    assert page.locator(".agent-start").count() == 0
    page.get_by_role("button", name="Düzenle", exact=True).click()
    page.get_by_text("Çalışma sınırları", exact=True).click()
    profile = page.get_by_label("Sınır profili", exact=True)
    assert profile.input_value() == "balanced"
    assert page.get_by_label("Görevin en uzun süresi (dakika)", exact=True).input_value() == "30"
    profile.select_option("careful")
    assert page.get_by_label("Görevin en uzun süresi (dakika)", exact=True).input_value() == "10"
    assert "10 karar adımı" in page.locator(".agent-preview").inner_text()
    page.get_by_label("Karar adımı", exact=True).fill("12")
    assert profile.input_value() == "custom"
    assert_unique_interactive_ids(page)
    page.get_by_role("button", name="Ajanı kaydet").click()
    page.get_by_role("button", name="Görev ver").wait_for()
    saved = [body for method, path, body in calls if method == "PUT" and path == f"/api/agents/{AID}"][-1]
    assert saved["limits"]["max_seconds"] == 600 and saved["limits"]["max_turns"] == 12
    assert saved["limits"]["question_timeout_seconds"] == 900


def test_waiting_work_is_announced_on_every_tab_and_opens_the_run(ui):
    page, calls, _, _, _ = ui
    office = {"agents": [{"id": AID, "name": "Araştırma", "status": "waiting_user", "run_id": RID}], "departments": [], "totals": {}}
    page.route("**/api/agents/office", lambda route: route.fulfill(json=office))
    page.evaluate("window.RpaAgents.mount(document.getElementById('root'), {...window.agentOptions, initialTab: 'connections'})")
    banner = page.locator(".agent-attention")
    banner.get_by_role("button", name="Araştırma: yanıtınızı bekliyor").click()
    page.get_by_label("Yanıtınız").wait_for()
    assert not [call for call in calls if call[0] != "GET" and call[1] != f"/api/agents/{AID}/runs"]
    office["agents"] = []
    banner.wait_for(state="hidden", timeout=8000)


def test_run_timeline_reads_as_sentences_and_hides_technical_records(ui):
    page, _, _, _, run = ui
    run["pending_question"] = None
    run["status"] = "running"
    run["started_at"] = "2026-10-13T12:00:00+00:00"
    run["events"] = [
        {"id": "1" * 32, "kind": "provider_request", "message": "", "timestamp": "2026-10-13T12:00:01+00:00", "data": {"payload": {}}},
        {"id": "2" * 32, "kind": "tool_call", "message": "Ajan aracı çağrıldı.", "timestamp": "2026-10-13T12:00:02+00:00",
         "data": {"id": "c1", "name": "run_workflow", "arguments": {"workflow_id": WID, "reason": ATTACK}}},
        {"id": "3" * 32, "kind": "manager_question", "message": "Yöneticiye soru soruldu.", "timestamp": "2026-10-13T12:00:03+00:00",
         "data": {"id": "q", "question": "Hangi dönem?"}},
    ]
    page.evaluate("identity => window.RpaAgents.openRun(identity)", RID)
    timeline = page.locator(".agent-timeline")
    timeline.get_by_text("Akış çalıştırma isteği", exact=True).wait_for()
    assert "«Bilgileri oku» · Gerekçe: " + ATTACK in timeline.inner_text()
    assert page.locator(".agent-event.technical").is_hidden()
    assert page.get_by_text("Ajan yöneticisine soru sordu ve yanıtını bekliyor", exact=False).is_visible()
    assert "Karar adımı · 1 / 20" in page.locator(".agent-usage").inner_text()
    page.get_by_label("Teknik kayıtları göster", exact=True).check()
    assert page.locator(".agent-event.technical").is_visible()
    assert page.locator("img").count() == 0
    assert_unique_interactive_ids(page)


def note_routes(page, calls):
    notes = {AID: [{"id": "9" * 32, "text": "Raporlar Paylaşılan klasöründedir.", "user_name": ATTACK,
                    "updated_at": "2026-10-13T12:00:00+00:00", "created_at": "2026-10-13T12:00:00+00:00", "user_id": 1}]}

    def handle(route):
        request = route.request
        path = urlsplit(request.url).path
        body = json.loads(request.post_data) if request.post_data else None
        calls.append((request.method, path, body))
        if path == "/api/agents/notes":
            route.fulfill(json=notes)
        elif request.method == "POST":
            note = {"id": "8" * 32, "text": body["text"], "user_name": "Yetkili", "user_id": 1,
                    "updated_at": "2026-10-14T12:00:00+00:00", "created_at": "2026-10-14T12:00:00+00:00"}
            notes[AID].append(note)
            route.fulfill(status=201, json=note)
        elif request.method == "PUT":
            notes[AID][0]["text"] = body["text"]
            route.fulfill(json=notes[AID][0])
        else:
            notes[AID] = [item for item in notes[AID] if not path.endswith(item["id"])]
            route.fulfill(status=204, body="")

    page.route("**/api/agents/notes", handle)
    page.route(f"**/api/agents/{AID}/notes**", handle)
    page.evaluate("window.RpaAgents.mount(document.getElementById('root'), window.agentOptions)")
    page.locator(".agent-card").wait_for()
    return notes


def test_agent_notes_are_listed_edited_and_removed_only_from_the_card(ui):
    page, calls, _, _, _ = ui
    note_routes(page, calls)
    assert "Onaylanmış 1 kalıcı notu bilir" in page.locator(".agent-permissions").inner_text()
    page.get_by_text("Bildikleri (1 not)", exact=True).click()
    assert page.get_by_text("Raporlar Paylaşılan klasöründedir.", exact=True).is_visible()
    page.get_by_role("button", name="Not ekle", exact=True).click()
    page.get_by_label("Yeni not", exact=True).fill("  Faturalar   her ay 5'inde kesilir. ")
    page.get_by_role("button", name="Notu kaydet", exact=True).click()
    page.get_by_text("Bildikleri (2 not)", exact=True).wait_for()
    added = [body for method, path, body in calls if method == "POST" and path == f"/api/agents/{AID}/notes"][0]
    assert added == {"text": "Faturalar her ay 5'inde kesilir."}
    page.get_by_role("button", name="Düzenle", exact=True).first.click()
    page.get_by_label("Notu düzenle", exact=True).fill("Raporlar Arşiv klasöründedir.")
    page.get_by_role("button", name="Notu kaydet", exact=True).click()
    page.get_by_text("Raporlar Arşiv klasöründedir.", exact=True).wait_for()
    page.get_by_role("button", name="Sil", exact=True).first.click()
    page.get_by_text("Bildikleri (1 not)", exact=True).wait_for()
    assert page.locator("img").count() == 0
    assert_unique_interactive_ids(page)


def test_answer_and_agent_suggestion_can_become_notes(ui):
    page, calls, _, _, run = ui
    note_routes(page, calls)
    run["events"].append({"id": "7" * 32, "kind": "note_suggested", "message": "Ajan kalıcı not önerdi.",
                          "timestamp": "2026-10-13T12:00:02+00:00", "data": {"text": "Onaylar Muhasebe'den alınır."}})
    page.route(f"**/api/agents/runs/{RID}/questions/**", lambda route: (
        calls.append((route.request.method, urlsplit(route.request.url).path, json.loads(route.request.post_data))),
        route.fulfill(json=run)))
    page.evaluate("identity => window.RpaAgents.openRun(identity)", RID)
    page.get_by_label("Yanıtınız").fill("Son kayıt")
    page.get_by_label("Bu bilgiyi ajanın kalıcı notu olarak da sakla", exact=True).check()
    assert page.get_by_label("Not metni", exact=True).input_value() == "Hangi kayıt? → Son kayıt"
    page.get_by_label("Not metni", exact=True).fill("Her zaman son kaydı kullan.")
    page.get_by_role("button", name="Yanıtla", exact=True).click()
    page.wait_for_function("window.toasts.some(text => text.startsWith('Not kaydedildi'))")
    posts = [(path, body) for method, path, body in calls if method == "POST"]
    assert posts[0][0] == f"/api/agents/runs/{RID}/questions/{QID}/answer"
    assert posts[1] == (f"/api/agents/{AID}/notes", {"text": "Her zaman son kaydı kullan.", "source_run_id": RID})
    page.get_by_role("button", name="Not olarak sakla", exact=True).click()
    page.get_by_text("Bu bilgi ajanın notlarında kayıtlı.", exact=True).wait_for()
    assert [body for method, path, body in calls if method == "POST" and path.endswith("/notes")][-1] == {
        "text": "Onaylar Muhasebe'den alınır.", "source_run_id": RID}
    assert_unique_interactive_ids(page)
