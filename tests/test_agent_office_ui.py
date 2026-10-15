"""Ağsız Chromium ofis doğrulaması; WebView2 / WKWebView testinin yerini almaz."""

import base64
import hashlib
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("RPA_UI_TESTS") != "1", reason="İsteğe bağlı Chromium ofis testi")
STATIC = Path(__file__).resolve().parents[1] / "src" / "rpa_orkestrai" / "static"
ATTACK = '<img src=x onerror="window.bad=true">'


@pytest.fixture
def office_browser():
    playwright = pytest.importorskip("playwright.sync_api")
    calls, errors = [], []
    data = {"agents": [{"id": "a" * 32, "name": "Yönetici", "role": "manager", "department": "Genel", "status": "idle",
                        "task_id": None, "task_label": "Görev bekliyor", "queue_count": 0}],
            "departments": [{"name": name, "agent_count": 1} for name in ("Departman A", "Departman B", "Departman C", "Departman D")],
            "totals": {"agents": 1, "queued": 0, "running": 0, "waiting": 0}}
    index = (STATIC / "index.html").read_text(encoding="utf-8")
    source = re.search(r'<script type="importmap">(.*?)</script>', index).group(1)
    digest = base64.b64encode(hashlib.sha256(source.encode()).digest()).decode()
    head = index.split("<head>")[1].split("</head>")[0].replace('<script defer src="/app.js"></script>', "")
    html = '<!doctype html><html lang="tr"><head>' + head + '</head><body><main id="test-root"></main></body></html>'

    def route_request(route):
        request = route.request
        path = urlsplit(request.url).path
        calls.append((request.method, path, request.url))
        if path == "/":
            route.fulfill(content_type="text/html; charset=utf-8", body=html,
                          headers={"Content-Security-Policy": f"default-src 'self'; script-src 'self' 'sha256-{digest}'; style-src 'self'; img-src 'self' data:; connect-src 'self'"})
        elif path == "/api/agents/session":
            route.fulfill(json={"actor": {"name": "Çalışan"}, "can_manage": False, "can_approve": False})
        elif path == "/api/agents/office":
            route.fulfill(json=data)
        elif path == "/api/agents/central/office":
            route.fulfill(status=503 if data.get("_human_error") else 200,
                          json={"success": True, "people": data.get("_people", [])})
        elif path == "/api/agents/tasks":
            route.fulfill(json=data.get("_tasks", []))
        elif path == "/api/agents/central/tasks":
            route.fulfill(json={"tasks": data.get("_human_tasks", [])})
        elif path == "/api/agents/metrics":
            route.fulfill(json={"agents": data.get("_metrics", [])})
        elif path == "/api/agents/central/metrics":
            route.fulfill(json={"metrics": {"users": data.get("_human_metrics", [])}})
        elif path.startswith("/api/"):
            route.fulfill(json=[])
        else:
            local = (STATIC / path.lstrip("/")).resolve()
            if not local.is_relative_to(STATIC.resolve()) or not local.is_file():
                route.fulfill(status=404, body="")
                return
            content_type = ("text/javascript; charset=utf-8" if path.endswith(".js") else "text/css; charset=utf-8"
                            if path.endswith(".css") else "font/woff2" if path.endswith(".woff2") else "application/octet-stream")
            route.fulfill(content_type=content_type, body=local.read_bytes())

    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1480, "height": 1150}, device_scale_factor=1)
        page.set_default_timeout(10000)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("**/*", route_request)

        def start(*, webgl=True):
            if not webgl:
                page.add_init_script("""(() => { const original = HTMLCanvasElement.prototype.getContext;
                  HTMLCanvasElement.prototype.getContext = function(kind, ...args) {
                    return kind.includes('webgl') ? null : original.call(this, kind, ...args);
                  }; })();""")
            page.goto("http://office.test/", wait_until="networkidle")
            page.evaluate("""async () => {
              window.officeOptions = {initialTab: 'office', api: async (path, options) => {
                const response = await fetch(path, options); if (!response.ok) throw new Error("Bağlantı hatası"); return response.json(); }, toast: () => {},
                openRun: () => { throw new Error('Ofis çalışma başlatamaz'); }};
              await window.RpaAgents.mount(document.getElementById('test-root'), window.officeOptions);
            }""")
            page.locator('.office-view[data-mode]').wait_for()
            return page

        yield start, page, calls, errors, data
        page.evaluate("window.officeDirectCleanup?.(); window.RpaAgents?.unmount()")
        browser.close()
    assert not errors


def interactive_ids(page):
    values = page.locator("button, input, select, textarea, summary, canvas[tabindex], svg [tabindex]").evaluate_all("items => items.map(item => item.id)")
    assert all(values) and len(values) == len(set(values))


def test_live_3d_office_uses_local_modules_theme_tokens_and_csp(office_browser):
    start, _, calls, _, data = office_browser
    populated(data)
    page = start()
    assert page.locator('.office-view[data-mode="3d"] canvas').count() == 1
    page.get_by_text("3D ofis · yerel görünüm", exact=True).wait_for()
    page.wait_for_timeout(500)
    interactive_ids(page)
    assert page.get_by_role("table").count() == 1
    assert any(path.endswith("OrbitControls.js") for _, path, _ in calls)
    assert all(urlsplit(url).netloc == "office.test" for _, _, url in calls)
    assert all(method == "GET" for method, _, _ in calls)
    target = os.environ.get("RPA_OFFICE_PREVIEW_DIR")
    if target:
        folder = Path(target)
        folder.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(folder / "ofis-canli-acik.png"), full_page=True)
    light = page.locator(".office-frame").evaluate("node => getComputedStyle(node).backgroundColor")
    page.evaluate("document.documentElement.dataset.theme = 'dark'")
    page.wait_for_timeout(250)
    assert page.locator(".office-frame").evaluate("node => getComputedStyle(node).backgroundColor") != light
    if target:
        page.screenshot(path=str(folder / "ofis-canli-koyu.png"), full_page=True)
    page.get_by_role("button", name="2D plan", exact=True).click()
    assert page.locator(".office-plan").count() == 1
    page.get_by_role("button", name="Liste", exact=True).click()
    assert page.locator(".office-frame").is_hidden()
    assert page.get_by_role("table").is_visible()


def test_webgl_failure_falls_back_to_safe_svg_and_text(office_browser):
    start, _, calls, _, data = office_browser
    data["departments"][0]["name"] = ATTACK
    data["agents"][0]["name"] = ATTACK
    page = start(webgl=False)
    assert page.locator('.office-view[data-mode="2d"] svg').count() == 1
    assert page.locator("img").count() == 0 and page.evaluate("window.bad || false") is False
    assert page.get_by_text("3D bu cihazda açılamadı; 2D plan gösteriliyor.", exact=True).is_visible()
    interactive_ids(page)
    target = os.environ.get("RPA_OFFICE_PREVIEW_DIR")
    if target:
        page.screenshot(path=str(Path(target) / "ofis-2d-yedek.png"), full_page=True)
    assert all(method == "GET" for method, _, _ in calls)


def test_office_disposes_webgl_and_stops_polling_when_hidden_or_unmounted(office_browser):
    start, _, calls, _, _ = office_browser
    page = start()
    page.evaluate("""() => {
      window.officeContextLost = false;
      document.querySelector('.office-view canvas').addEventListener('webglcontextlost', () => { window.officeContextLost = true; });
      Object.defineProperty(document, 'hidden', {configurable: true, value: true});
      document.dispatchEvent(new Event('visibilitychange'));
    }""")
    before = [call for call in calls if call[1] == "/api/agents/office"]
    page.wait_for_timeout(3200)
    assert [call for call in calls if call[1] == "/api/agents/office"] == before
    page.evaluate("window.RpaAgents.unmount()")
    page.wait_for_function("window.officeContextLost")
    assert page.locator(".office-view canvas").count() == 0
    page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, value: false}); document.dispatchEvent(new Event('visibilitychange'))")
    page.wait_for_timeout(3200)
    assert [call for call in calls if call[1] == "/api/agents/office"] == before


def test_sustained_slow_render_switches_to_2d(office_browser):
    start, _, _, _, _ = office_browser
    page = start()
    page.evaluate("let tick = 0; window.officeSlowFrame = 0; performance.now = () => { tick += 120; return tick; }")
    for index in range(12):
        page.evaluate("""theme => {
          document.documentElement.dataset.theme = theme;
          requestAnimationFrame(() => requestAnimationFrame(() => { window.officeSlowFrame += 1; }));
        }""", "dark" if index % 2 else "light")
        # A slow CI renderer can coalesce several fixed-interval theme changes.
        # Wait for actual frame callbacks before requesting the next redraw.
        page.wait_for_function("expected => window.officeSlowFrame >= expected", arg=index + 1)
        if page.locator('.office-view[data-mode="2d"]').count():
            break
    assert page.locator('.office-view[data-mode="2d"]').count() == 1
    assert page.get_by_text("Bu cihazda daha akıcı görüntü için 2D plana geçildi.", exact=True).is_visible()


def populated(data):
    manager = data["agents"][0]
    manager["activity"] = "thinking"
    manager["status"] = "running"
    statuses = [("Belge ajanı", "running", "workflow"), ("Kontrol ajanı", "waiting_approval", "waiting_approval"),
                ("Araştırma ajanı", "waiting_user", "waiting_user"), ("Rapor ajanı", "failed", "failed")]
    for index, (name, status, activity) in enumerate(statuses):
        data["agents"].append({"id": str(index + 1) * 32, "kind": "agent", "name": name, "role": "department",
                               "department": data["departments"][index]["name"], "status": status, "activity": activity,
                               "manager_id": manager["id"], "run_id": "f" * 32, "task_id": "e" * 32,
                               "task_label": "Görev üzerinde çalışıyor", "queue_count": index})
    data["_people"] = [{"id": "human-18", "user_id": 18, "kind": "human", "role": "human", "name": "Deniz",
                        "department": "", "status": "running", "task_id": "t18", "task_label": "Görev üzerinde çalışıyor",
                        "can_view_tasks": True, "queue_count": 1},
                       {"id": "human-19", "user_id": 19, "kind": "human", "role": "human", "name": "Ekin",
                        "department": "", "status": "unknown", "task_id": None, "task_label": "Görev durumu paylaşılmıyor",
                        "can_view_tasks": False, "queue_count": 0}]


def test_characters_show_states_and_load_private_details_only_after_click(office_browser):
    start, _, calls, _, data = office_browser
    populated(data)
    identity = data["agents"][2]["id"]
    data["_tasks"] = [{"id": "e" * 32, "assigned_agent_id": identity, "title": ATTACK, "status": "waiting_approval"}]
    data["_metrics"] = [{"id": identity, "succeeded": 9, "failed": 1, "cancelled": 0, "average_seconds": 12, "total_seconds": 120}]
    page = start()
    assert page.locator(".office-person-label").count() == 7
    assert page.locator('.office-person-label[data-activity="workflow"] .office-person-bubble').inner_text() == "↻"
    assert page.locator('.office-person-label[data-status="waiting_approval"] .office-person-bubble').inner_text() == "!"
    assert page.locator('.office-person-label[data-status="waiting_user"] .office-person-bubble').inner_text() == "?"
    assert page.locator(".office-root").inner_text().find(ATTACK) == -1
    assert not any(path in ("/api/agents/tasks", "/api/agents/metrics", "/api/agents/central/tasks") for _, path, _ in calls)
    page.locator(f'.office-person-label[data-person="{identity}"]').click()
    page.get_by_text("9 tamamlandı · 1 başarısız · 0 iptal", exact=True).wait_for()
    assert page.locator(".office-detail").get_by_text(ATTACK, exact=True).count() == 1
    assert page.locator("img").count() == 0
    assert page.get_by_role("button", name="Onay kartına git", exact=True).is_visible()
    assert all(method == "GET" for method, _, _ in calls)
    interactive_ids(page)
    page.get_by_role("button", name="Kapat", exact=True).click()
    page.get_by_role("button", name="2D plan", exact=True).click()
    assert page.locator(".office-plan-person").count() == 7
    page.locator('.office-plan-person[data-person="human-19"]').focus()
    page.keyboard.press("Enter")
    assert page.get_by_text("Bu çalışanın görev ayrıntılarını görüntüleme yetkiniz yok.", exact=True).is_visible()
    assert not any(path == "/api/agents/central/tasks" for _, path, _ in calls)
    interactive_ids(page)


def test_human_connection_failure_clears_stale_people_without_breaking_agent_scene(office_browser):
    start, _, calls, _, data = office_browser
    populated(data)
    data["_human_tasks"] = [{"id": "t18", "assignee_user_id": 18, "title": "Kişisel görev", "status": "running"}]
    page = start()
    page.locator('.office-person-label[data-person="human-18"]').click()
    page.locator(".office-detail").get_by_text("Kişisel görev", exact=True).wait_for()
    data["_human_error"] = True
    page.locator('.office-person-label[data-person="human-18"]').wait_for(state="hidden")
    assert page.locator('.office-view[data-mode="3d"] canvas').count() == 1
    assert page.locator(".office-person-label").count() == 5
    assert page.locator(".office-detail").is_hidden()
    assert page.locator(".office-human-warning").is_visible()
    assert page.locator(".office-root").inner_text().find("Kişisel görev") == -1
    assert all(method == "GET" for method, _, _ in calls)


def test_human_permission_revocation_removes_open_business_details(office_browser):
    start, _, calls, _, data = office_browser
    populated(data)
    data["_human_tasks"] = [{"id": "t18", "assignee_user_id": 18, "title": "Kişisel görev", "status": "running"}]
    page = start()
    page.locator('.office-person-label[data-person="human-18"]').click()
    page.locator(".office-detail").get_by_text("Kişisel görev", exact=True).wait_for()
    data["_people"][0].update(can_view_tasks=False, task_id=None, status="unknown", task_label="Görev durumu paylaşılmıyor")
    page.get_by_text("Bu çalışanın görev ayrıntılarını görüntüleme yetkiniz yok.", exact=True).wait_for()
    assert "Kişisel görev" not in page.locator(".office-detail").inner_text()
    assert all(method == "GET" for method, _, _ in calls)


def test_reduced_motion_and_hidden_state_pause_character_drawing(office_browser):
    start, page, _, _, data = office_browser
    populated(data)
    page.emulate_media(reduced_motion="reduce")
    page.add_init_script("""(() => { window.officeDraws = 0;
      for (const type of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) {
        if (!type) continue;
        for (const key of ['drawArrays','drawElements']) { const original = type.prototype[key];
          type.prototype[key] = function(...args) { window.officeDraws++; return original.apply(this,args); };
        }
      }
    })();""")
    start()
    page.wait_for_timeout(500)
    before = page.evaluate("window.officeDraws")
    assert before > 0
    page.wait_for_timeout(400)
    assert page.evaluate("window.officeDraws") == before
    page.emulate_media(reduced_motion="no-preference")
    page.wait_for_timeout(450)
    assert page.evaluate("window.officeDraws") > before
    page.evaluate("Object.defineProperty(document, 'hidden', {configurable: true, value: true}); document.dispatchEvent(new Event('visibilitychange'))")
    before = page.evaluate("window.officeDraws")
    page.wait_for_timeout(450)
    assert page.evaluate("window.officeDraws") == before


def test_office_navigation_only_opens_existing_work_and_task_screens(office_browser):
    start, _, calls, _, data = office_browser
    populated(data)
    page = start()
    page.evaluate("""async () => {
      window.RpaAgents.unmount(); window.officeNavigation = [];
      const {mountOffice} = await import('/office.js');
      window.officeDirectCleanup = mountOffice(document.getElementById('test-root'), {
        ...window.officeOptions, openAgentRun: id => window.officeNavigation.push(['run', id]),
        openTab: name => window.officeNavigation.push(['tab', name]) });
    }""")
    page.locator('.office-person-label[data-status="waiting_approval"]').wait_for()
    page.locator('.office-person-label[data-status="waiting_approval"]').click()
    page.get_by_role("button", name="Onay kartına git", exact=True).click()
    assert page.evaluate("window.officeNavigation") == [["run", "f" * 32]]
    assert page.get_by_role("button", name="Onayla", exact=True).count() == 0
    page.locator('.office-person-label[data-person="human-18"]').click()
    page.get_by_role("button", name="Görevler ekranına git", exact=True).click()
    assert page.evaluate("window.officeNavigation")[-1] == ["tab", "tasks"]
    assert all(method == "GET" for method, _, _ in calls)


def test_list_and_svg_keyboard_focus_survives_status_refresh(office_browser):
    start, _, _, _, data = office_browser
    populated(data)
    page = start()
    page.get_by_role("button", name="Liste", exact=True).click()
    page.locator('.office-table button[data-person="human-18"]').focus()
    page.wait_for_timeout(3200)
    assert page.evaluate("document.activeElement.dataset.person") == "human-18"
    page.get_by_role("button", name="2D plan", exact=True).click()
    page.locator('.office-plan-person[data-person="human-18"]').focus()
    page.wait_for_timeout(3200)
    assert page.evaluate("document.activeElement.dataset.person") == "human-18"
    page.keyboard.press("Enter")
    assert page.locator(".office-detail").is_visible()


def test_department_question_walks_to_manager_and_shows_only_message_type(office_browser):
    start, _, _, _, data = office_browser
    populated(data)
    manager, asker = data["agents"][0], data["agents"][1]
    manager["activity"] = "reviewing"
    asker.update(activity="asking_manager", event={"id": "1" * 32, "kind": "question", "to_agent_id": manager["id"]})
    page = start()
    label = page.locator(f'.office-person-label[data-person="{asker["id"]}"]')
    assert label.get_attribute("data-activity") == "asking_manager"
    assert label.locator(".office-person-bubble").inner_text() == "?"
    label.locator(".office-person-speech").get_by_text("Soru", exact=True).wait_for()
    assert page.locator(f'.office-person-label[data-person="{manager["id"]}"] .office-person-bubble').inner_text() == "✎"
    assert "Yöneticiye soru soruyor" in page.locator(".office-list").inner_text()
    assert "Belge ajanı → Yönetici: soru sordu" in page.locator(".office-feed").inner_text()
    if os.environ.get("RPA_OFFICE_SHOT"):
        page.wait_for_timeout(4000)
        page.screenshot(path=os.environ["RPA_OFFICE_SHOT"] + "-question.png")
    # The manager answers: only the type travels, and the department returns to its desk.
    asker.update(activity="thinking", event=None)
    manager.update(activity="thinking", event={"id": "2" * 32, "kind": "answered", "to_agent_id": asker["id"]})
    manager_label = page.locator(f'.office-person-label[data-person="{manager["id"]}"]')
    manager_label.locator(".office-person-speech").get_by_text("Yanıt", exact=True).wait_for()
    assert label.locator(".office-person-speech").is_hidden()
    feed = page.locator(".office-feed-list li").first
    assert feed.inner_text().endswith("Yönetici → Belge ajanı: soruyu yanıtladı")
    assert "Hangi" not in page.locator(".office-feed").inner_text()
    if os.environ.get("RPA_OFFICE_SHOT"):
        page.screenshot(path=os.environ["RPA_OFFICE_SHOT"] + "-answer.png")
    asker.update(activity="asking_manager", event={"id": "3" * 32, "kind": "question", "to_agent_id": manager["id"]})
    page.get_by_role("button", name="2D plan", exact=True).click()
    page.locator(".office-plan-link").wait_for()
    assert page.locator(".office-plan-link-label").text_content() == "Soru"
    interactive_ids(page)
