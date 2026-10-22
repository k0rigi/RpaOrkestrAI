"""Ofis kurma ekranı ve Ofisim sekmesi için çevrimdışı tarayıcı senaryoları."""

import json

import pytest
from test_agents_ui import ATTACK, STATIC, assert_unique_interactive_ids, pytestmark, ui  # noqa: F401

OFFICE, SECOND, NEW = "c" * 32, "d" * 32, "e" * 32


@pytest.fixture
def office_ui(ui):  # noqa: F811
    page, calls, errors, session, _ = ui
    state = {"office": None, "members": [], "candidates": [{"user_id": 11, "name": ATTACK}], "authority": True}

    def mine():
        office = state["office"]
        return {"success": True, "can_create": office is None,
                "office": office and {**office, "authority_user_id": 1 if state["authority"] else 3,
                                      "is_authority": state["authority"]},
                "members": state["members"], "candidates": state["candidates"] if state["authority"] else []}

    def join(name):
        state["office"] = {"id": OFFICE, "name": name}
        session.update(can_create_office=False, office={"id": OFFICE, "name": name},
                       can_manage=state["authority"], can_approve=state["authority"])

    def handle(route):
        request = route.request
        path = request.url.split("studio.test", 1)[1]
        body = json.loads(request.post_data) if request.post_data else None
        calls.append((request.method, path, body))
        if path == "/api/agents/central/my-office" and request.method == "POST" and session.get("offices"):
            # An authority opens another office; it opens on screen.
            new = {"id": NEW, "name": body["name"], "is_authority": True}
            session["offices"].append(new)
            session["office"] = state["office"] = {"id": NEW, "name": body["name"]}
            route.fulfill(status=201, json={"success": True, "office": state["office"]})
        elif path == "/api/agents/central/my-office" and request.method == "POST":
            join(body["name"])
            state["members"] = [{"user_id": 1, "name": "Çalışan", "authority": True}]
            route.fulfill(status=201, json={"success": True, "office": state["office"]})
        elif path == "/api/agents/central/my-offices":
            route.fulfill(json={"success": True, "can_create": True, "offices": [
                {"id": item["id"], "name": item["name"], "is_authority": True, "people": 2, "open_tasks": 1,
                 "pending_approvals": 3, "agents": 4, "on_screen": item["id"] == session["office"]["id"]}
                for item in session["offices"]]})
        elif path.endswith("/my-office/select"):
            chosen = next(item for item in session["offices"] if item["id"] == body["office_id"])
            session["office"] = state["office"] = {"id": chosen["id"], "name": chosen["name"]}
            route.fulfill(json={"office_id": chosen["id"]})
        elif path == "/api/agents/central/my-office":
            route.fulfill(json=mine())
        elif path.endswith("/my-office/name"):
            state["office"]["name"] = body["name"]
            route.fulfill(json={"success": True, "office": state["office"]})
        elif path.endswith("/my-office/members"):
            person = next(item for item in state["candidates"] if item["user_id"] == body["user_id"])
            state["candidates"].remove(person)
            state["members"].append({**person, "authority": False})
            route.fulfill(json={"success": True, "member": person})
        elif path.endswith("/remove"):
            state["members"] = [item for item in state["members"] if f"/{item['user_id']}/" not in path]
            route.fulfill(json={"success": True})
        elif path.endswith("/my-office/delete"):
            state["office"] = None
            session.update(can_create_office=True, office=None, can_manage=False, can_approve=False)
            route.fulfill(json={"success": True, "office": {"deleted": True}})
        elif path.endswith("/my-office/leave"):
            state["office"] = None
            session.update(can_create_office=True, office=None, can_manage=False, can_approve=False)
            route.fulfill(json={"success": True})
        else:
            route.fulfill(json={"success": True, "uyeler": [], "tasks": [], "approvals": []})

    page.route("**/api/agents/central/**", handle)
    page.add_script_tag(content=(STATIC / "agent-team.js").read_text(encoding="utf-8"))

    def remount():
        page.evaluate("""async () => { window.RpaAgents.unmount();
          await window.RpaAgents.mount(document.getElementById('root'), window.agentOptions); }""")

    return page, calls, session, state, join, remount


def test_an_account_outside_every_office_opens_its_own_and_becomes_its_authority(office_ui):
    page, calls, session, _, _, remount = office_ui
    session.update(can_create_office=True, can_manage=False, can_approve=False)
    remount()
    page.get_by_role("heading", name="Ofisinizi kurun").wait_for()
    assert page.get_by_role("button", name="Ajanlar", exact=True).count() == 0
    page.get_by_label("Ofis adı").fill(" L ")
    page.get_by_role("button", name="Ofisi kur").click()
    page.get_by_text("en az 2 karakter", exact=False).wait_for()
    page.get_by_label("Ofis adı").fill("  Lojistik   Planlama ")
    page.get_by_role("button", name="Ofisi kur").click()
    page.get_by_text("Lojistik Planlama ofisi", exact=True).wait_for()
    assert [body for method, path, body in calls if method == "POST"] == [{"name": "Lojistik Planlama"}]
    assert page.locator(".agent-user").inner_text() == "Çalışan · Ofis yetkilisi"
    assert page.locator("img").count() == 0 and not page.evaluate("window.injected || false")
    assert_unique_interactive_ids(page)


def test_the_setup_screen_opens_the_office_an_authority_added_this_account_to(office_ui):
    page, _, session, state, join, remount = office_ui
    session.update(can_create_office=True, can_manage=False, can_approve=False)
    page.clock.install()
    remount()
    page.get_by_role("heading", name="Ofisinizi kurun").wait_for()
    state["authority"] = False
    join("Claim & İade Departmanı")
    page.clock.run_for(31000)
    page.get_by_text("Claim & İade Departmanı ofisi", exact=True).wait_for()
    assert page.get_by_role("heading", name="Ofisinizi kurun").count() == 0


def test_office_authority_renames_the_office_and_places_colleagues(office_ui):
    page, calls, session, state, join, remount = office_ui
    join("Claim & İade")
    state["members"] = [{"user_id": 1, "name": "Çalışan", "authority": True}, {"user_id": 12, "name": "Ayşe", "authority": False}]
    remount()
    page.get_by_role("button", name="Ofisim", exact=True).click()
    page.get_by_text("Bu ofisin yetkilisisiniz", exact=False).wait_for()
    page.get_by_role("button", name="Ofise ekle").click()
    page.locator(".agent-people li", has_text=ATTACK).wait_for()
    assert ATTACK + " ofise eklendi." in page.evaluate("window.toasts")
    page.locator(".agent-people li", has_text="Ayşe").get_by_role("button", name="Ofisten çıkar").click()
    page.locator(".agent-people li", has_text="Ayşe").wait_for(state="detached")
    page.get_by_label("Ofis adı").fill("İade Ofisi")
    page.get_by_role("button", name="Adı kaydet").click()
    page.get_by_role("heading", name="İade Ofisi").wait_for()
    posted = [(path, body) for method, path, body in calls if method == "POST"]
    assert posted == [("/api/agents/central/my-office/members", {"user_id": 11}),
                      ("/api/agents/central/my-office/members/12/remove", {}),
                      ("/api/agents/central/my-office/name", {"name": "İade Ofisi"})]
    # The authority itself can neither be removed nor leave its own office here.
    assert page.locator(".agent-people li", has_text="Ofis yetkilisi").get_by_role("button").count() == 0
    assert page.get_by_role("button", name="Ofisten ayrıl").count() == 0
    assert page.locator("img").count() == 0 and not page.evaluate("window.injected || false")
    assert_unique_interactive_ids(page)


def test_a_member_leaves_and_may_then_open_an_own_office(office_ui):
    page, calls, session, state, join, remount = office_ui
    state["authority"] = False
    join("Claim & İade")
    state["members"] = [{"user_id": 3, "name": "Yetkili", "authority": True}, {"user_id": 1, "name": "Çalışan", "authority": False}]
    remount()
    page.get_by_role("button", name="Ofisim", exact=True).click()
    page.get_by_text("Bu ofisin üyesisiniz", exact=False).wait_for()
    assert page.get_by_role("button", name="Ofise ekle").count() == 0 and page.get_by_label("Ofis adı").count() == 0
    page.get_by_role("button", name="Ofisten ayrıl").click()
    page.get_by_role("heading", name="Ofisinizi kurun").wait_for()
    assert [path for method, path, _ in calls if method == "POST"] == ["/api/agents/central/my-office/leave"]


def test_my_office_tab_is_only_for_accounts_in_an_office(office_ui):
    page, _, _, _, _, remount = office_ui
    remount()
    page.get_by_role("button", name="Organizasyon", exact=True).wait_for()
    assert page.get_by_role("button", name="Ofisim", exact=True).count() == 0


def test_a_personal_account_names_its_office_but_has_no_colleagues_to_place(office_ui):
    page, _, session, state, join, remount = office_ui
    session["individual"] = True
    join("Kişisel ofis")
    state["members"] = [{"user_id": 1, "name": "Çalışan", "authority": True}]
    remount()
    page.get_by_role("button", name="Ofisim", exact=True).click()
    page.get_by_text("ajanları kurar ve riskli işlemleri onaylarsınız", exact=False).wait_for()
    assert page.get_by_label("Ofis adı").is_visible()
    assert page.get_by_role("heading", name="Ofise çalışan ekle").count() == 0
    assert page.get_by_role("button", name="Ofise ekle").count() == 0


def test_an_authority_switches_offices_from_the_header_and_opens_another_office(office_ui):
    page, calls, session, _, join, remount = office_ui
    join("Satın Alma")
    session.update(can_create_office=True, offices=[{"id": OFFICE, "name": "Satın Alma", "is_authority": True},
                                                    {"id": SECOND, "name": ATTACK, "is_authority": True}])
    remount()
    picker = page.get_by_label("Ofis", exact=True)
    assert picker.input_value() == OFFICE
    picker.select_option(SECOND)
    page.wait_for_function("document.getElementById('agent-office-picker')?.value === 'dddddddddddddddddddddddddddddddd'")
    assert [body for _, path, body in calls if path.endswith("/my-office/select")] == [{"office_id": SECOND}]
    page.get_by_role("button", name="Ofisim", exact=True).click()
    page.get_by_role("heading", name="Ofislerim").wait_for()
    rows = page.locator(".agent-office-list li")
    rows.nth(1).get_by_text("Ekranda", exact=True).wait_for()
    assert "4 ajan · 2 kişi · 1 açık görev · 3 onay bekliyor" in rows.nth(0).inner_text()
    rows.nth(0).get_by_role("button", name="Bu ofise geç").click()
    page.wait_for_function("document.getElementById('agent-office-picker')?.value === 'cccccccccccccccccccccccccccccccc'")
    page.get_by_role("button", name="Ofisim", exact=True).click()
    page.get_by_label("Yeni ofisin adı").fill("  Muhasebe   Departmanı ")
    page.get_by_role("button", name="Yeni ofis kur").click()
    page.wait_for_function("document.getElementById('agent-office-picker')?.value === 'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'")
    assert [body for method, path, body in calls if method == "POST" and path == "/api/agents/central/my-office"] == [
        {"name": "Muhasebe Departmanı"}]
    assert page.locator("img").count() == 0 and not page.evaluate("window.injected || false")
    assert_unique_interactive_ids(page)


def test_a_member_sees_one_office_without_a_picker_or_new_office_form(office_ui):
    page, _, session, state, join, remount = office_ui
    state["authority"] = False
    join("Satın Alma")
    session.update(offices=[{"id": OFFICE, "name": "Satın Alma", "is_authority": False}])
    remount()
    page.get_by_text("Satın Alma ofisi", exact=True).wait_for()
    assert page.locator("#agent-office-picker").count() == 0
    page.get_by_role("button", name="Ofisim", exact=True).click()
    page.get_by_text("Bu ofisin üyesisiniz", exact=False).wait_for()
    assert page.get_by_role("button", name="Yeni ofis kur").count() == 0
    assert page.get_by_role("heading", name="Ofislerim").count() == 0


def test_an_authority_deletes_its_office_after_typing_its_name(office_ui):
    page, calls, session, state, join, remount = office_ui
    join("Claim & İade")
    state["members"] = [{"user_id": 1, "name": "Çalışan", "authority": True}, {"user_id": 12, "name": "Ayşe", "authority": False}]
    remount()
    page.get_by_role("button", name="Ofisim", exact=True).click()
    zone = page.locator(".agent-danger-zone")
    zone.get_by_text("Ofiste 1 çalışan daha var", exact=False).wait_for()
    zone.get_by_label("Onaylamak için ofisin adını aynen yazın", exact=False).fill("Claim")
    zone.get_by_role("button", name="Ofisi sil").click()
    page.wait_for_function("(window.toasts || []).includes('Silmek için ofisin adını aynen yazın.')")
    assert not [path for method, path, _ in calls if path.endswith("/my-office/delete")]
    zone.get_by_label("Onaylamak için ofisin adını aynen yazın", exact=False).fill("  Claim   & İade ")
    zone.get_by_role("button", name="Ofisi sil").click()
    page.get_by_role("heading", name="Ofisinizi kurun").wait_for()
    assert [(path, body) for method, path, body in calls if path.endswith("/my-office/delete")] == [
        ("/api/agents/central/my-office/delete", {"name": "Claim & İade"})]
    assert "Claim & İade ofisi silindi." in page.evaluate("window.toasts")


def test_a_member_has_no_delete_section(office_ui):
    page, calls, session, state, join, remount = office_ui
    state["authority"] = False
    join("Claim & İade")
    remount()
    page.get_by_role("button", name="Ofisim", exact=True).click()
    page.get_by_text("Bu ofisin üyesisiniz", exact=False).wait_for()
    assert page.locator(".agent-danger-zone").count() == 0
