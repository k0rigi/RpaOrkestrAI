import os
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
from test_agents_ui import ATTACK, STATIC, assert_unique_interactive_ids, ui  # noqa: F401

pytestmark = pytest.mark.skipif(os.environ.get("RPA_UI_TESTS") != "1", reason="İsteğe bağlı Chromium performans testi")


def mount(fixture):
    page, calls, _, session, _ = fixture
    session["can_manage"] = False
    row = dict(id="a" * 32, name=ATTACK, department="Destek", total=4, succeeded=2, failed=1, cancelled=1,
               terminal=4, success_rate=.5, total_seconds=120, average_seconds=30, duration_missing_count=0,
               workflow_count=2, approval_count=1, approval_wait_seconds=15, total_tokens=80,
               estimated_cost={}, unpriced_tasks=1)
    requests = []

    def handle(route):
        request = route.request
        path = urlsplit(request.url).path
        requests.append((request.method, path, parse_qs(urlsplit(request.url).query)))
        if path == "/api/agents/metrics":
            route.fulfill(json={"totals": row, "agents": [row], "departments": [dict(row, name="Destek")]})
        elif path == "/api/agents/central/metrics":
            route.fulfill(json={"success": True, "metrics": {"totals": row, "users": [dict(row, user_id=1)]}})
        elif path == "/api/agents/central/members":
            route.fulfill(json={"uyeler": [{"kullanici_id": 1, "ad_soyad": ATTACK}]})
        else:
            route.fallback()

    page.route("**/api/agents/**", handle)
    page.add_script_tag(content=(STATIC / "agent-metrics.js").read_text(encoding="utf-8"))
    page.evaluate("window.RpaAgents.mount(document.getElementById('root'), {...window.agentOptions, initialTab: 'performance'})")
    page.get_by_role("heading", name="Kurumdaki insan görevleri").wait_for()
    return page, requests


def test_metrics_are_read_only_escape_labels_and_offer_both_exports(ui):  # noqa: F811
    page, requests = mount(ui)
    assert page.locator("img").count() == 0
    assert page.evaluate("window.injected || false") is False
    assert page.locator("svg text").first.text_content() == ATTACK
    assert page.get_by_role("link", name="Ajan CSV indir").get_attribute("href").startswith("/api/agents/metrics/csv?")
    assert page.get_by_role("button", name="İnsan CSV indir").is_visible()
    assert all(method == "GET" for method, _, _ in requests)
    assert not page.get_by_text("Model fiyatları (isteğe bağlı)", exact=True).count()
    assert_unique_interactive_ids(page)


def test_custom_dates_are_sent_as_half_open_local_day_interval(ui):  # noqa: F811
    page, requests = mount(ui)
    page.get_by_label("Dönem", exact=True).select_option("custom")
    page.get_by_label("İlk gün", exact=True).fill("2026-10-01")
    page.get_by_label("Son gün", exact=True).fill("2026-10-03")
    page.get_by_role("button", name="Hesapla", exact=True).click()
    page.wait_for_function("!document.querySelector('[aria-busy=true]')")
    query = [query for _, path, query in requests if path == "/api/agents/metrics"][-1]
    offset = page.evaluate("new Date('2026-10-01T00:00:00').getTimezoneOffset()")
    local_zone = timezone(timedelta(minutes=-offset))
    assert datetime.fromisoformat(query["start"][0]).astimezone(local_zone).isoformat().startswith("2026-10-01T00:00:00")
    assert datetime.fromisoformat(query["end"][0]).astimezone(local_zone).isoformat().startswith("2026-10-04T00:00:00")
    page.get_by_label("Ajanları grupla", exact=True).select_option("departments")
    assert page.locator("svg text").first.text_content() == "Destek"
