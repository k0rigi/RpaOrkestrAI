"""İnsan görevleri ve uzaktaki onay kartları için çevrimdışı tarayıcı senaryoları."""

import json

import pytest
from test_agents_ui import ATTACK, STATIC, assert_unique_interactive_ids, pytestmark, ui  # noqa: F401


@pytest.fixture
def team(ui):  # noqa: F811
    page, calls, errors, session, run = ui
    task = {"id": "9" * 32, "title": ATTACK, "instructions": ATTACK, "summary": "", "status": "queued",
            "version": 1, "assignee_user_id": 2, "priority": "normal", "created_at": "2026-10-13T12:00:00Z"}
    approval = {"id": "8" * 32, "status": "pending", "requester_user_id": 2, "version": 1,
                "preview": {"workflow_name": "Güncelle", "inputs": {"metin": ATTACK}},
                "reason": ATTACK, "attempt": 1, "expires_at": "2099-01-01T00:00:00Z"}

    def handle(route):
        path = route.request.url.split("studio.test", 1)[1]
        body = json.loads(route.request.post_data) if route.request.post_data else None
        calls.append((route.request.method, path, body))
        if path.endswith("/members"):
            route.fulfill(json={"success": True, "uyeler": [{"kullanici_id": 2, "ad_soyad": ATTACK, "onayci": False}]})
        elif path == "/api/agents/tasks":
            route.fulfill(json=[])
        elif path.endswith("/tasks"):
            if route.request.method == "POST":
                task.update(body)
                route.fulfill(json={"task": task})
            else:
                route.fulfill(json={"tasks": [task]})
        elif "/tasks/" in path:
            if path.endswith("/status"):
                task["status"] = body["status"]
            route.fulfill(json={"task": task})
        elif path.endswith("/approvals"):
            route.fulfill(json={"approvals": [approval]})
        elif "/approvals/" in path:
            if path.endswith("/decision"):
                approval["status"] = "approved" if body["approved"] else "rejected"
            route.fulfill(json={"approval": approval})
        else:
            route.fulfill(status=404, json={"detail": "Bilinmeyen test ucu"})

    page.route("**/api/agents/central/**", handle)
    page.route("**/api/agents/tasks", handle)
    page.add_script_tag(content=(STATIC / "agent-team.js").read_text(encoding="utf-8"))
    page.evaluate("window.RpaAgents.mount(document.getElementById('root'), window.agentOptions)")
    return page, calls, session, task, approval


def test_team_human_task_uses_server_contract_and_owner_cannot_report_someone_elses_work(team):
    page, calls, _, _, _ = team
    page.get_by_role("button", name="Görevler", exact=True).click()
    page.get_by_role("button", name="Görevi aç").wait_for()
    page.get_by_role("button", name="Görevi aç").click()
    page.get_by_role("button", name="İptal et", exact=True).wait_for()
    assert page.get_by_role("button", name="Göreve başla", exact=True).count() == 0
    assert page.locator("img").count() == 0
    assert_unique_interactive_ids(page)
    page.get_by_role("button", name="İnsan çalışana görev ata", exact=True).click()
    page.get_by_label("Görev başlığı").fill("Kontrol")
    page.get_by_label("Yapılacak iş").fill("Listeyi doğrula")
    page.get_by_role("button", name="Görevi ata", exact=True).click()
    page.get_by_role("heading", name="Kontrol", exact=True).first.wait_for()
    created = [body for method, path, body in calls if method == "POST" and path == "/api/agents/central/tasks"][-1]
    assert set(created) == {"request_id", "title", "instructions", "assignee_user_id", "priority"}
    assert created["priority"] == "normal" and created["assignee_user_id"] == 2


def test_remote_approval_preview_is_text_and_only_owner_has_decision(team):
    page, calls, session, _, _ = team
    page.get_by_role("button", name="Onaylar", exact=True).click()
    page.get_by_role("button", name="Onayı incele", exact=True).click()
    page.get_by_role("button", name="Onayla", exact=True).wait_for()
    assert page.locator("img").count() == 0
    assert json.loads(page.locator("pre").inner_text())["metin"] == ATTACK
    assert_unique_interactive_ids(page)
    page.get_by_role("button", name="Onayla", exact=True).click()
    page.get_by_text("Onaylandı", exact=True).first.wait_for()
    assert [body for method, path, body in calls if path.endswith("/decision")] == [{"approved": True}]
    session["can_approve"] = False
    page.evaluate("window.RpaAgents.mount(document.getElementById('root'), window.agentOptions)")
    page.get_by_role("button", name="Onaylar", exact=True).click()
    page.get_by_role("button", name="Onayı incele", exact=True).click()
    page.get_by_role("heading", name="Güncelle", exact=True).wait_for()
    assert page.get_by_role("button", name="Onayla", exact=True).count() == 0


def test_organization_explains_communication_and_flags_incomplete_setup(team):
    page, _, _, _, _ = team
    page.get_by_role("button", name="Organizasyon", exact=True).click()
    checks = page.locator(".agent-org-checks")
    checks.wait_for()
    # The only agent is independent and has a working connection and a granted workflow.
    assert "Kurulum tutarlı" in checks.inner_text()
    assert page.get_by_text("Bağımsız ajanlar", exact=True).is_visible()
    assert "Departmanlar birbiriyle doğrudan konuşmaz" in page.locator(".agent-root").inner_text()
    assert page.locator("img").count() == 0
    assert_unique_interactive_ids(page)


def test_approval_card_names_the_requester(team):
    page, _, _, _, _ = team
    page.get_by_role("button", name="Onaylar", exact=True).click()
    page.get_by_text("İsteyen: " + ATTACK, exact=True).wait_for()
    assert page.locator("img").count() == 0


def test_department_office_names_the_office_its_authority_and_its_people(team):
    page, _, session, _, _ = team
    session["office"] = {"id": "c" * 32, "name": "Claim & İade Departmanı"}
    page.evaluate("""async () => { window.RpaAgents.unmount();
      await window.RpaAgents.mount(document.getElementById('root'), window.agentOptions); }""")
    page.get_by_text("Claim & İade Departmanı ofisi", exact=True).wait_for()
    assert page.locator(".agent-user").inner_text() == "Çalışan · Ofis yetkilisi"
    page.get_by_role("button", name="Organizasyon", exact=True).click()
    page.get_by_text("Claim & İade Departmanı çalışanları", exact=True).wait_for()
    page.get_by_text("Diğer departmanların ofisleri burada görünmez", exact=False).wait_for()
    assert_unique_interactive_ids(page)
