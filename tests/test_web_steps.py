"""Web steps on the computer's own Edge/Chrome against a local page; ambiguity never acts."""
import http.server
import platform
import threading
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
