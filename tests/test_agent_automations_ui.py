"""Otomasyon sekmesi ve girdi düzenleyicisi: Chromium'da, ağsız."""

import json
from urllib.parse import urlsplit

from test_agents_ui import AID, ATTACK, RID, STATIC, assert_unique_interactive_ids, pytestmark  # noqa: F401
from test_agents_ui import ui as ui  # noqa: F401


def automation_routes(page, calls):
    items = []

    def handle(route):
        request = route.request
        path = urlsplit(request.url).path
        body = json.loads(request.post_data) if request.post_data else None
        calls.append((request.method, path, body))
        if path == "/api/agents/automations" and request.method == "GET":
            route.fulfill(json=items)
        elif path == "/api/agents/automations" and request.method == "POST":
            item = {**body, "id": "a1" * 16, "summary": "Hafta içi 08:30", "next_run_at": "2026-10-19T08:30",
                    "last_status": None, "last_run_at": None, "last_run_id": None, "last_message": None}
            items.append(item)
            route.fulfill(status=201, json=item)
        elif path.endswith("/run"):
            items[0].update(last_status="started", last_run_id=RID)
            route.fulfill(json=items[0])
        elif request.method == "PUT":
            items[0].update(body)
            route.fulfill(json=items[0])
        else:
            items.clear()
            route.fulfill(status=204, body="")

    page.route("**/api/agents/automations**", handle)
    page.add_script_tag(content=(STATIC / "agent-automations.js").read_text(encoding="utf-8"))
    page.evaluate("window.RpaAgents.mount(document.getElementById('root'), {...window.agentOptions, initialTab: 'automations'})")
    page.get_by_role("heading", name="Otomasyonlar", exact=True).wait_for()
    return items


def test_owner_creates_a_weekday_automation_with_named_inputs_and_runs_it(ui):
    page, calls, _, _, _ = ui
    items = automation_routes(page, calls)
    page.get_by_role("button", name="Otomasyon ekle", exact=True).click()
    page.get_by_label("Otomasyon adı", exact=True).fill("Sabah özeti")
    page.get_by_label("Görev", exact=True).fill(ATTACK)
    page.get_by_label("Ne sıklıkla?", exact=True).select_option("weekly")
    page.get_by_label("Saat (aralıkta başlangıç)", exact=True).fill("08:30")
    assert "tetikleme_zamani" in page.locator(".agent-automation-form .agent-notice").inner_text()
    page.get_by_text("Girdi değişkenleri (isteğe bağlı)", exact=True).click()
    page.get_by_role("button", name="Girdi ekle", exact=True).click()
    page.get_by_label("Girdi adı", exact=True).fill("donem")
    page.get_by_label("Değer", exact=True).fill("2026-09")
    page.get_by_label("Ne zaman çalışsın?", exact=True).select_option("folder")
    assert page.get_by_label("Klasörün tam yolu", exact=True).is_visible()
    assert "dosya_adi" in page.locator(".agent-automation-form .agent-notice").inner_text()
    page.get_by_label("Ne zaman çalışsın?", exact=True).select_option("schedule")
    assert_unique_interactive_ids(page)
    page.get_by_role("button", name="Otomasyonu kaydet", exact=True).click()
    page.get_by_text("Hafta içi 08:30", exact=True).wait_for()
    created = [body for method, path, body in calls if method == "POST" and path == "/api/agents/automations"][0]
    assert created["agent_id"] == AID and created["task"] == ATTACK and created["inputs"] == {"donem": "2026-09"}
    assert created["trigger"]["kind"] == "schedule" and created["trigger"]["schedule_kind"] == "weekly"
    assert created["trigger"]["days"] == [0, 1, 2, 3, 4] and created["trigger"]["time"] == "08:30"
    page.get_by_role("button", name="Şimdi çalıştır", exact=True).click()
    page.get_by_role("heading", name="Görev", exact=True).wait_for()  # The started task opens in Çalışmalar.
    assert any(path.endswith("/run") for _, path, _ in calls)
    assert page.locator("img").count() == 0
    assert items and items[0]["last_run_id"] == RID


def test_invalid_input_name_is_explained_before_sending(ui):
    page, calls, _, _, _ = ui
    page.get_by_role("button", name="Görev ver").click()
    page.get_by_label("Hedefiniz").fill("Kayıtları incele")
    page.get_by_text("Girdi değişkenleri (isteğe bağlı)", exact=True).click()
    page.get_by_role("button", name="Girdi ekle", exact=True).click()
    page.get_by_label("Girdi adı", exact=True).fill("1hatalı ad")
    page.get_by_label("Değer", exact=True).fill("x")
    page.get_by_role("button", name="Görevi başlat").click()
    page.wait_for_function("window.toasts.some(text => text.includes('Girdi adı geçersiz'))")
    assert not [call for call in calls if call[0] == "POST" and call[1] == f"/api/agents/{AID}/runs"]
