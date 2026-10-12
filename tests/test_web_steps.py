"""Web steps on the computer's own Edge/Chrome against a local page; ambiguity never acts."""
import http.server
import platform
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from rpa_orkestrai.actions.web import web_click, web_fill, web_open, web_read, web_select
from rpa_orkestrai.errors import WorkflowError
from rpa_orkestrai.integrations.web_session import WebSession, choose_channel, installed

PAGE = """<!doctype html><html lang="tr"><meta charset="utf-8"><title>Fatura portalı</title>
<body>
<h1>Fatura girişi</h1>
<label>Fatura No <input id="no" placeholder="Ör. INV-1"></label>
<label>Açıklama <textarea id="aciklama"></textarea></label>
<label>Durum <select id="durum"><option>Bekliyor</option><option>Onaylandı</option><option>İade edildi</option>
</select></label>
<button id="kaydet" onclick="document.getElementById('sonuc').textContent =
  'Kaydedildi: ' + document.getElementById('no').value + ' / ' + document.getElementById('durum').value;
  window.clicks = (window.clicks || 0) + 1">Kaydet</button>
<button>Sil</button><button>Sil</button>
<a href="#detay">Detaylar</a>
<p id="sonuc"></p>
</body></html>"""

pytestmark = pytest.mark.skipif(
    platform.system() not in {"Darwin", "Windows"} or not (installed("chrome") or installed("msedge")),
    reason="needs Edge or Chrome")


@pytest.fixture(scope="module")
def site():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()


@pytest.fixture
def ctx(tmp_path):
    session = WebSession(tmp_path / "profil", timeout_ms=15_000)
    logs = []
    yield SimpleNamespace(web=lambda: session, log=logs.append, logs=logs)
    session.close()


def target(by, value, **extra):
    return {"by": by, "target": value, "timeout": 3, **extra}


def test_fill_select_click_and_read_like_a_person(site, ctx):
    assert web_open(ctx, {"url": site, "headless": True}).startswith(site)
    web_fill(ctx, {**target("label", "Fatura No"), "text": "INV-1069"})
    web_fill(ctx, {**target("label", "Açıklama"), "text": "Çağrı iade ğüşıöç"})
    assert web_select(ctx, {**target("css", "#durum"), "option": "iade"}) == "İade edildi"
    web_click(ctx, target("button", "Kaydet"))
    assert web_read(ctx, target("css", "#sonuc")) == "Kaydedildi: INV-1069 / İade edildi"
    assert web_read(ctx, target("placeholder", "INV-1")) == "INV-1069"
    assert web_read(ctx, target("label", "Açıklama")) == "Çağrı iade ğüşıöç"
    assert ctx.web().page.evaluate("window.clicks") == 1


@pytest.mark.parametrize("step,params,match", [
    (web_click, target("button", "Sil"), "2 öğeyle"),
    (web_click, target("text", "Yok böyle bir şey"), "bulunamadı"),
    (web_select, {**target("css", "#durum"), "option": "Silindi"}, "bulunamadı"),
    (web_select, {**target("css", "#no"), "option": "x"}, "açılır liste"),
])
def test_ambiguous_or_missing_targets_do_nothing(site, ctx, step, params, match):
    web_open(ctx, {"url": site, "headless": True})
    with pytest.raises(WorkflowError, match=match):
        step(ctx, params)
    assert ctx.web().page.evaluate("window.clicks") is None
    assert web_read(ctx, target("css", "#sonuc")) == ""


def test_exact_match_tells_apart_similar_texts(site, ctx):
    web_open(ctx, {"url": site, "headless": True})
    # "Fatura" appears in the heading and the field label; exactly "Fatura girişi" is one element.
    with pytest.raises(WorkflowError, match="öğeyle"):
        web_read(ctx, target("text", "Fatura"))
    assert web_read(ctx, target("text", "Fatura girişi", exact=True)) == "Fatura girişi"


def test_steps_need_an_open_page_and_safe_addresses(tmp_path):
    session = WebSession(tmp_path / "profil", timeout_ms=5_000)
    ctx = SimpleNamespace(web=lambda: session, log=lambda message: None)
    with pytest.raises(WorkflowError, match="Web sayfası aç"):
        web_click(ctx, target("text", "Kaydet"))
    for url in ("ftp://site", "javascript:alert(1)", "https://kullanici:sifre@site.com"):
        with pytest.raises(WorkflowError):
            web_open(ctx, {"url": url})
    with pytest.raises(WorkflowError, match="geçersiz"):
        choose_channel("firefox")


# ----- 0.9.21 web scripting steps ------------------------------------------------------------
from rpa_orkestrai.actions.web import (  # noqa: E402
    web_download,
    web_navigate,
    web_press,
    web_read_table,
    web_screenshot,
    web_script,
    web_tab,
    web_upload,
    web_wait,
)

PORTAL = """<!doctype html><html lang="tr"><meta charset="utf-8"><title>Portal</title><body>
<h1>Siparişler</h1>
<p id="durum">Yükleniyor…</p>
<script>setTimeout(() => { document.getElementById('durum').textContent = 'Hazır';
  const p = document.createElement('p'); p.id = 'gec'; p.textContent = 'Geç gelen'; document.body.append(p); }, 600);</script>
<table id="liste"><thead><tr><th>No</th><th>Müşteri</th><th>Tutar</th></tr></thead>
<tbody><tr><td>S-1</td><td>Ağaç Ltd</td><td>10,50</td></tr><tr><td>S-2</td><td>Işık AŞ</td><td>7</td></tr></tbody></table>
<label>Fatura dosyası <input type="file" id="dosya" multiple onchange="document.getElementById('secilen').textContent =
  [...this.files].map(f => f.name).join(',')"></label><p id="secilen"></p>
<label>Arama <input id="ara" onkeydown="if (event.key === 'Enter') document.getElementById('aranan').textContent = this.value"></label>
<p id="aranan"></p>
<a href="/rapor.csv">Raporu indir</a>
<a href="/detay" target="_blank">Detayı yeni sekmede aç</a>
<button onclick="window.open('/detay')">Açılır pencere</button>
<iframe id="cerceve" srcdoc="<button onclick=&quot;this.textContent='Onaylandı'&quot;>Onayla</button>"></iframe>
</body></html>"""
DETAIL = "<!doctype html><title>Detay S-1</title><h1>Sipariş detayı</h1>"


@pytest.fixture(scope="module")
def portal():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/rapor.csv":
                body, kind = "no;tutar\nS-1;10,50\n".encode("utf-8"), "text/csv"
                extra = {"Content-Disposition": 'attachment; filename="rapor.csv"'}
            else:
                body, kind, extra = (DETAIL if self.path == "/detay" else PORTAL).encode("utf-8"), "text/html", {}
            self.send_response(200)
            self.send_header("Content-Type", f"{kind}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            for key, value in extra.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()


@pytest.fixture
def web(tmp_path):
    session = WebSession(tmp_path / "profil", timeout_ms=15_000)
    logs, artifacts = [], []

    def save(name, data):
        target = tmp_path / name
        target.write_bytes(data)
        artifacts.append(target)
        return target

    yield SimpleNamespace(web=lambda: session, log=lambda message, **kw: logs.append(message), logs=logs,
                          save_artifact=save, artifacts=artifacts)
    session.close()


def test_wait_then_read_a_table_as_rows(portal, web):
    web_open(web, {"url": portal, "headless": True})
    assert web_wait(web, {"condition": "visible", "by": "css", "target": "#gec", "wait": 5}) is True
    assert web_read(web, target("css", "#durum")) == "Hazır"
    rows = web_read_table(web, target("text", "Müşteri", exact=True))
    assert rows == [{"No": "S-1", "Müşteri": "Ağaç Ltd", "Tutar": "10,50"},
                    {"No": "S-2", "Müşteri": "Işık AŞ", "Tutar": "7"}]
    assert web_wait(web, {"condition": "hidden", "by": "text", "target": "Yükleniyor", "wait": 2}) is True
    assert web_wait(web, {"condition": "url", "url_text": "/olmayan", "wait": 0.5, "on_missing": "continue"}) is False
    with pytest.raises(WorkflowError, match="adresi"):
        web_wait(web, {"condition": "url", "url_text": "/olmayan", "wait": 0.5})


def test_upload_download_press_and_frame(portal, web, tmp_path):
    web_open(web, {"url": portal, "headless": True})
    first, second = tmp_path / "fatura 1.pdf", tmp_path / "fatura 2.pdf"
    first.write_bytes(b"%PDF-1")
    second.write_bytes(b"%PDF-2")
    web_upload(web, {**target("label", "Fatura dosyası"), "files": f"{first}\n{second}"})
    assert web_read(web, target("css", "#secilen")) == "fatura 1.pdf,fatura 2.pdf"
    with pytest.raises(WorkflowError, match="bulunamadı"):
        web_upload(web, {**target("label", "Fatura dosyası"), "files": str(tmp_path / "yok.pdf")})
    with pytest.raises(WorkflowError, match="dosya seçme alanı"):
        web_upload(web, {**target("label", "Arama"), "files": str(first)})
    saved = web_download(web, {**target("text", "Raporu indir"), "folder": str(tmp_path / "indirilen")})
    assert saved.endswith("rapor.csv") and Path(saved).read_text(encoding="utf-8").startswith("no;tutar")
    again = web_download(web, {**target("text", "Raporu indir"), "folder": str(tmp_path / "indirilen")})
    assert again.endswith("rapor (2).csv")  # never overwritten unless asked
    web_fill(web, {**target("label", "Arama"), "text": "S-2"})
    web_press(web, {"key": "Enter", **target("label", "Arama")})
    assert web_read(web, target("css", "#aranan")) == "S-2"
    web_click(web, {**target("button", "Onayla"), "frame": "#cerceve"})
    assert web_read(web, {**target("button", "Onaylandı"), "frame": "#cerceve"}) == "Onaylandı"


def test_new_tab_is_followed_and_tabs_can_be_switched(portal, web):
    web_open(web, {"url": portal, "headless": True})
    web_click(web, target("text", "Detayı yeni sekmede aç"))
    assert web_read(web, target("css", "h1")) == "Sipariş detayı"
    assert any("yeni sekmeye geçildi" in line for line in web.logs)
    assert web_tab(web, {"action": "title", "match": "portal"}) == portal
    assert web_read(web, target("css", "h1")) == "Siparişler"
    web_tab(web, {"action": "last"})
    web_tab(web, {"action": "close"})
    assert web_read(web, target("css", "h1")) == "Siparişler"
    with pytest.raises(WorkflowError, match="Tek sekme"):
        web_tab(web, {"action": "close"})
    assert web_navigate(web, {"action": "reload"}) == portal
    # A tab opened by the page's own script is followed too.
    web_click(web, target("button", "Açılır pencere"))
    assert web_read(web, target("css", "h1")) == "Sipariş detayı"


def test_script_receives_input_and_returns_values(portal, web):
    web_open(web, {"url": portal, "headless": True})
    code = ("const rows = [...document.querySelectorAll('#liste tbody tr')];\n"
            "return rows.filter(r => r.cells[0].innerText === girdi.no).map(r => ({musteri: r.cells[1].innerText}));")
    assert web_script(web, {"code": code, "input": {"no": "S-2"}}) == [{"musteri": "Işık AŞ"}]
    assert web_script(web, {"code": "await new Promise(r => setTimeout(r, 50)); return `${1 + 1}`;"}) == "2"
    with pytest.raises(WorkflowError, match="JavaScript"):
        web_script(web, {"code": "throw new Error('kasıtlı hata');"})
    shot = web_screenshot(web, {"filename": "portal"})
    assert shot.endswith("portal.png") and web.artifacts[0].read_bytes().startswith(b"\x89PNG")


# ----- Tarayıcıda seç -------------------------------------------------------------------------
from rpa_orkestrai.integrations.web_picker import WebPicks  # noqa: E402

PICK_PAGE = """<!doctype html><html lang="tr"><meta charset="utf-8"><title>Seçim</title><body>
<label>Fatura No <input id="f-1"></label>
<button><span>Kaydet</span></button>
<div><button>Sil</button></div><div><button>Sil</button></div>
<a href="/baska">Başka sayfa</a>
<iframe id="odeme" srcdoc="<button>Öde</button>"></iframe>
</body></html>"""


@pytest.fixture(scope="module")
def pick_site():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = PICK_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/"
    server.shutdown()


def pick(tmp_path, url, action):
    manager = SimpleNamespace(reserve_desktop=lambda cancel: "token", release_desktop=lambda token: None)
    picks = WebPicks(manager, tmp_path / "profil", timeout_ms=10_000, headless=True, on_ready=action)
    job = picks.start(url)
    deadline = __import__("time").monotonic() + 60
    while (state := picks.status(job["id"]))["status"] in {"starting", "waiting"}:
        assert __import__("time").monotonic() < deadline, state
        __import__("time").sleep(0.1)
    return state


@pytest.mark.parametrize("click,expected", [
    (lambda page: page.locator("span", has_text="Kaydet").click(), {"by": "button", "target": "Kaydet"}),
    (lambda page: page.locator("#f-1").click(), {"by": "label", "target": "Fatura No"}),
    (lambda page: page.frame_locator("#odeme").get_by_text("Öde").click(),
     {"by": "button", "target": "Öde", "frame": "iframe#odeme"}),
])
def test_picking_returns_the_target_a_person_would_name(tmp_path, pick_site, click, expected):
    state = pick(tmp_path, pick_site, click)
    assert state["status"] == "completed", state
    result = state["result"]
    assert {key: result[key] for key in expected} == expected and result["exact"] is True


def test_picking_one_of_two_same_buttons_falls_back_to_a_unique_css_path(tmp_path, pick_site, ctx):
    state = pick(tmp_path, pick_site, lambda page: page.get_by_role("button", name="Sil").nth(1).click())
    assert state["status"] == "completed", state
    result = state["result"]
    assert result["by"] == "css" and "nth-of-type(2)" in result["target"]
    # The saved target finds exactly that button in a run.
    web_open(ctx, {"url": pick_site, "headless": True})
    item = ctx.web().single(__import__("rpa_orkestrai.integrations.web_session", fromlist=["Target"]).Target(
        by="css", value=result["target"], exact=True, timeout_ms=2000))
    assert item.evaluate("e => e.parentElement === document.querySelectorAll('div')[1]")


def test_closing_the_browser_cancels_the_pick(tmp_path, pick_site):
    state = pick(tmp_path, pick_site, lambda page: page.context.close())
    assert state["status"] == "cancelled"


def test_switching_selection_off_lets_the_person_browse_first(tmp_path, pick_site):
    def browse_then_pick(page):
        page.get_by_role("button", name="Seçimi kapat").click()
        page.get_by_text("Başka sayfa").click()
        page.wait_for_url("**/baska")
        # Still off on the new page: signing in or clicking here is not a pick.
        page.get_by_role("button", name="Seçimi aç").wait_for()
        page.locator("span", has_text="Kaydet").click()
        page.get_by_role("button", name="Seçimi aç").click()
        page.get_by_role("button", name="Seçimi kapat").wait_for()
        page.locator("#f-1").click()

    state = pick(tmp_path, pick_site, browse_then_pick)
    assert state["status"] == "completed", state
    assert state["result"]["target"] == "Fatura No" and state["result"]["url"].endswith("/baska")
