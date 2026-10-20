"""Ağsız Chromium ofis doğrulaması; WebView2 / WKWebView testinin yerini almaz."""

import base64
import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
from glb_samples import layout_office, office

from rpa_orkestrai.agents.office_layout import assign, read_layout
from rpa_orkestrai.agents.office_model import SAMPLE, OfficeModelError, contract_error, parse_glb

pytestmark = pytest.mark.skipif(os.environ.get("RPA_UI_TESTS") != "1", reason="İsteğe bağlı Chromium ofis testi")
STATIC = Path(__file__).resolve().parents[1] / "src" / "rpa_orkestrai" / "static"
ATTACK = '<img src=x onerror="window.bad=true">'
PLACEMENT = {"cut_height": 0}
SESSION = {"actor": {"name": "Çalışan"}, "can_manage": False, "can_approve": False}


def model_info(model):
    if not model:
        return {"present": False, "placement": dict(PLACEMENT)}
    return {"present": True, "id": hashlib.sha256(model["bytes"]).hexdigest()[:16], "name": model["name"],
            "size": len(model["bytes"]), "imported_at": "2026-10-18T09:00:00+00:00", "placement": model["placement"],
            "layout": model["layout"]}


def stored_model(raw, name):
    """What Studio keeps after an import: the same contract check as the real service."""
    layout = read_layout(parse_glb(raw))
    if not layout["ok"]:
        raise contract_error(layout["errors"])
    return {"bytes": raw, "name": name, "placement": dict(PLACEMENT), "layout": layout}


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
                          headers={"Content-Security-Policy": f"default-src 'self'; script-src 'self' 'sha256-{digest}'; style-src 'self'; img-src 'self' data: blob:; connect-src 'self' blob:"})
        elif path == "/api/agents/session":
            route.fulfill(json=data.get("_session", SESSION))
        elif path == "/api/agents/office":
            # Keys starting with "_" steer the other test routes; the snapshot never carries them.
            route.fulfill(json={key: value for key, value in data.items() if not key.startswith("_")})
        elif path == "/api/agents/central/office":
            route.fulfill(status=503 if data.get("_human_error") else 200,
                          json={"success": True, "people": data.get("_people", [])})
        elif path == "/api/agents/tasks":
            route.fulfill(json=data.get("_tasks", []))
        elif path == "/api/agents/central/tasks" and request.method == "GET":
            route.fulfill(json={"tasks": data.get("_human_tasks", [])})
        elif path == "/api/agents/metrics":
            route.fulfill(json={"agents": data.get("_metrics", [])})
        elif path == "/api/agents/central/metrics":
            route.fulfill(json={"metrics": {"users": data.get("_human_metrics", [])}})
        elif path == "/api/agents/office/model":
            if request.method == "PUT":
                try:
                    data["_model"] = stored_model(request.post_data_buffer, unquote(request.headers.get("x-model-name", "")))
                except OfficeModelError as exc:
                    route.fulfill(status=422, json={"detail": str(exc)})
                    return
            elif request.method == "DELETE":
                data["_model"] = None
                route.fulfill(status=204, body="")
                return
            route.fulfill(json=model_info(data.get("_model")))
        elif path == "/api/agents/office/model/file":
            route.fulfill(content_type="model/gltf-binary", body=data["_model"]["bytes"])
        elif path == "/api/agents/office/model/placement":
            data["_model"]["placement"] = json.loads(request.post_data)
            route.fulfill(json=model_info(data["_model"]))
        elif path == "/api/agents/office/model/sample":
            data["_model"] = stored_model(SAMPLE.read_bytes(), "Örnek ofis (RPA yerleşim 1).glb")
            route.fulfill(json=model_info(data["_model"]))
        elif path == "/api/agents/office/model/assignments":
            body = json.loads(request.post_data)
            result = assign(data["_model"]["layout"], body["occupants"], data.get("_places", {}),
                            humans_complete=body["humans_complete"])
            data["_places"] = result["places"]
            route.fulfill(json=result)
        elif request.method == "POST" and re.fullmatch(r"/api/agents/[a-f0-9]{32}/runs", path):
            data.setdefault("_started", []).append((path.split("/")[3], json.loads(request.post_data)))
            route.fulfill(status=202, json={"id": "c" * 32, "status": "queued"})
        elif re.fullmatch(r"/api/agents/[a-f0-9]{32}/chat", path):
            chat = data.setdefault("_chat", [])
            if request.method == "POST":
                text = json.loads(request.post_data)["text"]
                chat.extend([{"role": "user", "text": text, "user": "Çalışan"}, {"role": "assistant", "text": "Bugün iki iş bitti."}])
                route.fulfill(json={"reply": chat[-1], "messages": chat})
            else:
                route.fulfill(json=chat)
        elif re.fullmatch(r"/api/agents/runs/[a-f0-9]{32}", path):
            route.fulfill(json=data.get("_run", {}))
        elif re.fullmatch(r"/api/agents/runs/[a-f0-9]{32}/(questions|approvals)/[a-f0-9]{32}/(answer|decision)", path):
            data.setdefault("_decisions", []).append((path.rsplit("/", 1)[1], json.loads(request.post_data)))
            route.fulfill(json=data.get("_run", {}))
        elif path == "/api/agents/central/tasks" and request.method == "POST":
            data.setdefault("_assigned", []).append(json.loads(request.post_data))
            route.fulfill(status=201, json={"success": True, "task": {}})
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

        def start(*, webgl=True, extra=None):
            if not webgl:
                page.add_init_script("""(() => { const original = HTMLCanvasElement.prototype.getContext;
                  HTMLCanvasElement.prototype.getContext = function(kind, ...args) {
                    return kind.includes('webgl') ? null : original.call(this, kind, ...args);
                  }; })();""")
            page.goto("http://office.test/", wait_until="networkidle")
            page.evaluate("""async (extra) => {
              window.officeOptions = {...extra, initialTab: 'office', api: async (path, options) => {
                const response = await fetch(path, options);
                if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Bağlantı hatası");
                return response.status === 204 ? null : response.json(); }, toast: (text) => (window.officeToasts ||= []).push(text),
                openRun: () => { throw new Error('Ofis çalışma başlatamaz'); }};
              await window.RpaAgents.mount(document.getElementById('test-root'), window.officeOptions);
            }""", extra or {})
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
    eventually(page, "window.officeContextLost")
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
    # Rebuilding the scene for the new population never leaves the office without its 3D view, not even for a frame.
    page.evaluate("""() => { const view = document.querySelector('.office-view'); window.officeBlank = 0;
      new MutationObserver(() => { if (!view.querySelector('canvas')) window.officeBlank++; }).observe(view, {childList: true}); }""")
    data["_human_error"] = True
    page.locator('.office-person-label[data-person="human-18"]').wait_for(state="hidden")
    assert page.evaluate("window.officeBlank") == 0
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


def test_researching_agent_walks_to_the_research_corner_and_manager_hands_over_tasks(office_browser):
    start, _, _, _, data = office_browser
    populated(data)
    manager, researcher, worker = data["agents"][0], data["agents"][1], data["agents"][2]
    researcher.update(activity="researching", status="running")
    page = start()
    label = page.locator(f'.office-person-label[data-person="{researcher["id"]}"]')
    assert label.get_attribute("data-activity") == "researching"
    label.locator(".office-person-speech").get_by_text("Araştırıyor", exact=True).wait_for()
    assert label.locator(".office-person-bubble").inner_text() == "⌕"
    assert "İnternette araştırıyor" in page.locator(".office-list").inner_text()
    assert page.get_by_text("Araştırma köşesi", exact=True).count() == 1
    # The hand-over balloon lasts three seconds; the event arrives with a refresh while the test already waits,
    # so a slow machine cannot miss it.
    manager.update(event={"id": "9" * 32, "kind": "delegated", "to_agent_id": worker["id"]})
    manager_label = page.locator(f'.office-person-label[data-person="{manager["id"]}"]')
    manager_label.locator(".office-person-speech").get_by_text("Görev", exact=True).wait_for()
    if os.environ.get("RPA_OFFICE_SHOT"):
        page.wait_for_timeout(2500)
        page.screenshot(path=os.environ["RPA_OFFICE_SHOT"] + "-research.png")
    interactive_ids(page)


def test_own_model_is_baked_to_outward_faces_and_matte_colours(office_browser):
    start, _, _, _, _ = office_browser
    page = start()
    plain = page.evaluate("""async (sample) => {
      const THREE = await import('three'), { openModel } = await import('/office.js');
      const model = await openModel(THREE, Uint8Array.from(atob(sample), (c) => c.charCodeAt(0)).buffer);
      const meshes = model.group.children, geometry = meshes[0].geometry, index = geometry.index.array;
      const position = geometry.getAttribute('position'), up = [];
      for (let i = 0; i < index.length; i += 3) {
        const [a, b, c] = [0, 1, 2].map((k) => new THREE.Vector3().fromBufferAttribute(position, index[i + k]));
        up.push(new THREE.Vector3().subVectors(b, a).cross(new THREE.Vector3().subVectors(c, a)).y);
      }
      const material = meshes[0].material, result = { meshes: meshes.length, up, color: material.color.toArray(),
        metalness: material.metalness, roughness: material.roughness, clipping: material.clippingPlanes.length,
        size: model.box.getSize(new THREE.Vector3()).toArray() };
      model.dispose();
      return result;
    }""", base64.b64encode(office()).decode())
    # Both copies merge into one mesh; the mirrored copy still faces up after its mirror is baked in.
    assert plain["meshes"] == 1 and len(plain["up"]) == 2 and all(value > 0 for value in plain["up"])
    assert plain["color"] == [1, 0, 0] and plain["metalness"] == 0 and plain["roughness"] == 0.5 and plain["clipping"] == 1
    assert plain["size"] == [5, 0, 1]


def test_paths_follow_only_the_declared_network(office_browser):
    start, _, _, _, _ = office_browser
    page = start()
    layout = read_layout(parse_glb(SAMPLE.read_bytes()))
    route = page.evaluate("""async (layout) => {
      const { shortestPath } = await import('/office.js');
      return [shortestPath(layout, 'RPA_WORK_001', 'RPA_MEET_001'), shortestPath(layout, 'RPA_WORK_001', 'RPA_ORIGIN')];
    }""", layout)
    assert route[0][0] == "RPA_WORK_001" and route[0][-1] == "RPA_MEET_001" and route[1] is None
    edges = {tuple(edge) for edge in layout["edges"]}
    assert all(tuple(sorted(pair)) in edges for pair in zip(route[0], route[0][1:]))


def eventually(page, expression, timeout=10):
    """Polls a page expression; the office page's CSP forbids the string evaluation of wait_for_function."""
    for _ in range(timeout * 10):
        if page.evaluate(expression):
            return
        page.wait_for_timeout(100)
    raise AssertionError("Beklenen durum oluşmadı: " + expression)


def open_model_panel(page):
    page.get_by_role("button", name="Ofis modeli", exact=True).click()
    return page.locator(".office-model")


def test_the_sample_office_places_everyone_on_its_own_points(office_browser):
    start, _, calls, _, data = office_browser
    populated(data)
    page = start()
    page.get_by_text("3D ofis · yerel görünüm", exact=True).wait_for()
    panel = open_model_panel(page)
    panel.get_by_role("button", name="Örnek ofisi kullan").click()
    page.get_by_text("3D ofis · kendi modeliniz", exact=True).wait_for()
    panel.get_by_text("Model yerleştirildi; ajanlar çalışma noktalarında.", exact=True).wait_for()
    assert panel.get_by_text("8 çalışma noktası · 4 bekleme noktası · 9 oturma yeri", exact=False).is_visible()
    # Only the model's own areas are labelled; no rooms are generated around it.
    labels = set(page.locator(".office-room-label").all_inner_texts())
    assert labels == {"Çalışma alanı", "Yönetici odası", "Bekleme alanı", "Araştırma köşesi"}
    assert page.locator(".office-person-label").count() == 7 and page.locator(".office-capacity").is_hidden()
    manager = data["agents"][0]["id"]
    assert data["_places"][manager] == "RPA_MANAGER_01" and len(set(data["_places"].values())) == 7
    assert "Ajan · Yönetim · Yönetici noktası 01" in page.locator(".office-list").inner_text()
    assert any(path.endswith("GLTFLoader.js") for _, path, _ in calls)
    target = os.environ.get("RPA_OFFICE_PREVIEW_DIR")
    if target:
        page.wait_for_timeout(1500)
        page.screenshot(path=str(Path(target) / "ornek-ofis.png"), full_page=True)
    interactive_ids(page)
    # The same places on the next start: the mapping is kept.
    before, asked = dict(data["_places"]), len(calls)
    page.get_by_role("button", name="2D plan", exact=True).click()
    page.locator(".office-plan-path").first.wait_for(state="attached")
    assert page.locator(".office-plan-path").count() == len(data["_model"]["layout"]["edges"])
    assert page.locator(".office-plan-person").count() == 7 and data["_places"] == before
    # Switching the view neither reads the layout again nor rewrites anybody's place.
    assert not [path for _, path, _ in calls[asked:] if path.startswith("/api/agents/office/model")]
    assert set(page.locator(".office-plan-area").all_text_contents()) == labels
    if target:
        page.screenshot(path=str(Path(target) / "ornek-ofis-2d.png"), full_page=True)
    panel.get_by_label("Tavan kesiti (m, 0 = kapalı)").fill("2.5")
    panel.get_by_text("Görünüm bu bilgisayara kaydedildi.", exact=True).wait_for()
    assert data["_model"]["placement"] == {"cut_height": 2.5}
    page.on("dialog", lambda dialog: dialog.accept())
    panel.get_by_role("button", name="Varsayılan ofise dön").click()
    panel.get_by_text("Varsayılan ofise dönüldü.", exact=True).wait_for()
    assert data["_model"] is None and page.locator(".office-plan-path").count() == 0


def test_a_full_office_keeps_the_rest_in_the_list_without_overlapping(office_browser):
    start, _, _, _, data = office_browser
    populated(data)
    for index in range(10):
        data["agents"].append({"id": format(index + 100, "032x"), "kind": "agent", "name": f"Ek ajan {index}", "role": "department",
                               "department": "Departman A", "status": "idle", "task_id": None, "task_label": "Görev bekliyor", "queue_count": 0})
    data["_model"] = stored_model(SAMPLE.read_bytes(), "ornek.glb")
    page = start()
    page.get_by_text("3D ofis · kendi modeliniz", exact=True).wait_for()
    overflow = 17 - 13  # Manager point, 8 work and 4 waiting points.
    capacity = page.locator(".office-capacity")
    assert capacity.inner_text() == f"Ofis kapasitesi dolu: {overflow} çalışan yerleşemedi; listede görünür."
    assert page.locator(".office-person-label").count() == 13 and len(set(data["_places"].values())) == 13
    assert page.locator(".office-list").inner_text().count("Yer yok (ofis kapasitesi dolu)") == overflow
    assert "4 çalışan yerleşemedi (ofis kapasitesi dolu)" in page.locator(".office-summary").inner_text()


def test_a_model_without_the_contract_is_refused_and_the_office_stays(office_browser, tmp_path):
    start, _, _, _, data = office_browser
    populated(data)
    page = start()
    page.get_by_text("3D ofis · yerel görünüm", exact=True).wait_for()
    panel = open_model_panel(page)
    plain = tmp_path / "depo.glb"
    plain.write_bytes(office())
    with page.expect_file_chooser() as chooser:
        panel.get_by_role("button", name="Model seç (.glb)").click()
    chooser.value.set_files(str(plain))
    message = panel.locator(".office-model-status")
    message.get_by_text("yerleşim sözleşmesine uymuyor", exact=False).wait_for()
    assert "RPA_ORIGIN" in message.inner_text() and data.get("_model") is None
    assert page.get_by_text("3D ofis · yerel görünüm", exact=True).is_visible()
    good = tmp_path / "Ofis planı.glb"
    good.write_bytes(layout_office())
    with page.expect_file_chooser() as chooser:
        panel.get_by_role("button", name="Model seç (.glb)").click()
    chooser.value.set_files(str(good))
    page.get_by_text("3D ofis · kendi modeliniz", exact=True).wait_for()
    # Two work points and one waiting point for seven people: four stay in the list.
    assert page.locator(".office-person-label").count() == 3
    assert data["_model"]["name"] == "Ofis planı.glb"


def test_work_is_managed_from_the_3d_office(office_browser):
    start, _, _, _, data = office_browser
    populated(data)
    data["_session"] = {**SESSION, "can_manage": True, "can_approve": True}
    manager, approver, asker = data["agents"][0], data["agents"][2], data["agents"][3]
    page = start()
    page.get_by_text("3D ofis · yerel görünüm", exact=True).wait_for()
    detail = page.locator(".office-detail")
    # A question the agent waits for is answered with one of its options.
    data["_run"] = {"id": "f" * 32, "pending_question": {"id": "a" * 32, "question": ATTACK, "options": ["Evet", "Hayır"]}}
    page.locator(f'.office-person-label[data-person="{asker["id"]}"]').click()
    detail.get_by_text(ATTACK, exact=True).wait_for()
    detail.get_by_role("button", name="Evet", exact=True).click()
    eventually(page, "(window.officeToasts || []).includes('Yanıtınız ajana iletildi.')")
    assert data["_decisions"][-1] == ("answer", {"answer": "Evet"})
    # The approver decides the waiting approval from its card.
    data["_run"] = {"id": "f" * 32, "pending_approval": {"id": "b" * 32, "workflow_name": "Sipariş gir", "reason": "Kayıt yazılacak",
                                                          "inputs": {"musteri": ATTACK}}}
    page.locator(f'.office-person-label[data-person="{approver["id"]}"]').click()
    detail.get_by_text("Onay bekleniyor", exact=True).wait_for()
    assert detail.get_by_text(f"musteri: {ATTACK}", exact=True).is_visible()
    detail.get_by_role("button", name="Onayla", exact=True).click()
    eventually(page, "(window.officeToasts || []).includes('İşlem onaylandı.')")
    assert data["_decisions"][-1] == ("decision", {"approved": True})
    # A task for the manager, and a question to it from the toolbar.
    page.locator(f'.office-person-label[data-person="{manager["id"]}"]').click()
    detail.get_by_role("button", name="Görev ver", exact=True).click()
    detail.get_by_label("Yönetici ne yapsın?", exact=False).fill("Bugünkü iadeleri topla")
    detail.get_by_role("button", name="Görevi başlat", exact=True).click()
    eventually(page, "(window.officeToasts || []).some((text) => text.endsWith('görevi aldı.'))")
    assert data["_started"] == [(manager["id"], {"task": "Bugünkü iadeleri topla"})]
    page.get_by_role("button", name="Yöneticiye yaz", exact=True).click()
    detail.get_by_label("Sorunuz", exact=False).fill("Bugün ne bitti?")
    detail.get_by_role("button", name="Sor", exact=True).click()
    detail.get_by_text("Bugün iki iş bitti.", exact=True).wait_for()
    # A task for a person of the office.
    page.locator('.office-person-label[data-person="human-18"]').click()
    detail.get_by_role("button", name="Görev ata", exact=True).click()
    detail.get_by_label("Görev başlığı").fill("Kontrol")
    detail.get_by_label("Yapılacak iş").fill("İade listesini doğrula")
    detail.get_by_role("button", name="Görevi ata", exact=True).click()
    eventually(page, "(window.officeToasts || []).some((text) => text.endsWith('için görev oluşturuldu.'))")
    created = data["_assigned"][-1]
    assert (created["assignee_user_id"], created["title"], created["priority"]) == (18, "Kontrol", "normal")
    assert re.fullmatch(r"[a-f0-9]{32}", created["request_id"])
    assert page.locator("img").count() == 0 and not page.evaluate("window.bad || false")
    interactive_ids(page)


def test_without_rights_the_panel_offers_no_decisions(office_browser):
    start, _, calls, _, data = office_browser
    populated(data)
    data["_run"] = {"id": "f" * 32, "pending_approval": {"id": "b" * 32, "workflow_name": "Sipariş gir", "inputs": {}}}
    page = start()
    page.locator('.office-person-label[data-status="waiting_approval"]').click()
    page.locator(".office-detail").get_by_role("button", name="Görev ver", exact=True).wait_for()
    assert page.get_by_role("button", name="Onayla", exact=True).count() == 0
    page.locator('.office-person-label[data-person="human-18"]').click()
    page.get_by_role("button", name="Görevler ekranına git", exact=True).wait_for()
    assert page.get_by_role("button", name="Görev ata", exact=True).count() == 0
    assert all(method == "GET" for method, _, _ in calls)


def test_the_show_plays_the_chain_of_work_with_the_offices_own_agents_and_starts_nothing(office_browser):
    start, _, calls, _, data = office_browser
    populated(data)
    page = start(extra={"showStep": 1500})  # The real show waits 4.5 s per turn.
    page.get_by_text("3D ofis · yerel görünüm", exact=True).wait_for()
    manager, first = data["agents"][0], data["agents"][1]
    manager_label = page.locator(f'.office-person-label[data-person="{manager["id"]}"]')
    first_label = page.locator(f'.office-person-label[data-person="{first["id"]}"]')
    asked = len(calls)
    page.get_by_role("button", name="Gösterimi oynat", exact=True).click()
    page.get_by_text("Gösterim oynatılıyor · gerçek iş yapılmıyor", exact=True).wait_for()
    manager_label.locator(".office-person-speech").get_by_text("Görev", exact=True).wait_for()
    before = first_label.evaluate("node => node.style.transform")
    first_label.locator(".office-person-speech").get_by_text("Araştırıyor", exact=True).wait_for(timeout=15_000)
    page.wait_for_timeout(1500)
    # The department really walks: its label follows the character to the research corner.
    assert first_label.evaluate("node => node.style.transform") != before
    first_label.locator(".office-person-speech").get_by_text("Soru", exact=True).wait_for(timeout=15_000)
    manager_label.locator(".office-person-speech").get_by_text("Yanıt", exact=True).wait_for(timeout=10_000)
    page.get_by_role("button", name="Gösterimi durdur", exact=True).click()
    page.get_by_role("button", name="Gösterimi oynat", exact=True).wait_for()
    assert first_label.get_attribute("data-activity") == "workflow"  # back to what the agent really does
    # Only the office's own reads: no task, chat or answer was sent.
    assert all(method == "GET" for method, _, _ in calls[asked:])
    assert "gosterim" not in page.locator(".office-feed").inner_text().casefold()


def test_the_show_explains_what_it_needs_without_a_team(office_browser):
    start, _, _, _, _ = office_browser
    page = start()
    page.get_by_role("button", name="Gösterimi oynat", exact=True).click()
    page.get_by_text("Gösterim için ofiste bir yönetici ajan ve en az bir departman ajanı olmalı", exact=False).wait_for()
