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
    index = (STATIC / "index.html").read_text()
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
                const response = await fetch(path, options); return response.json(); }, toast: () => {},
                openRun: () => { throw new Error('Ofis çalışma başlatamaz'); }};
              await window.RpaAgents.mount(document.getElementById('test-root'), window.officeOptions);
            }""")
            page.locator('.office-view[data-mode]').wait_for()
            return page

        yield start, page, calls, errors, data
        page.evaluate("window.RpaAgents?.unmount()")
        browser.close()
    assert not errors


def interactive_ids(page):
    values = page.locator("button, input, select, textarea, summary, canvas[tabindex]").evaluate_all("items => items.map(item => item.id)")
    assert all(values) and len(values) == len(set(values))


def test_empty_3d_office_uses_local_modules_theme_tokens_and_csp(office_browser):
    start, _, calls, _, _ = office_browser
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
        page.screenshot(path=str(folder / "ofis-bos-acik.png"), full_page=True)
    light = page.locator(".office-frame").evaluate("node => getComputedStyle(node).backgroundColor")
    page.evaluate("document.documentElement.dataset.theme = 'dark'")
    page.wait_for_timeout(250)
    assert page.locator(".office-frame").evaluate("node => getComputedStyle(node).backgroundColor") != light
    if target:
        page.screenshot(path=str(folder / "ofis-bos-koyu.png"), full_page=True)
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
    page.evaluate("let tick = 0; performance.now = () => { tick += 120; return tick; }")
    for index in range(12):
        page.evaluate("theme => document.documentElement.dataset.theme = theme", "dark" if index % 2 else "light")
        page.wait_for_timeout(80)
    assert page.locator('.office-view[data-mode="2d"]').count() == 1
    assert page.get_by_text("Bu cihazda daha akıcı görüntü için 2D plana geçildi.", exact=True).is_visible()
