from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import pytest
from test_agent_api import api  # noqa: F401

from rpa_orkestrai.agents.metrics import (
    MetricSettings,
    MetricSettingsStore,
    ModelPrice,
    calculate,
    csv_export,
    interval,
)
from rpa_orkestrai.agents.models import Actor, AgentEvent, AgentTask

ACTOR = Actor(user_id=1, company_id=2, name="Kişi", session_id="oturum")
FIRST = "2026-10-01T00:00:00+00:00"
LAST = "2026-11-01T00:00:00+00:00"
AGENT = "a" * 32
CONNECTION = "c" * 32


def task(**values):
    data = dict(company_id=2, created_by=ACTOR, assignee_id=AGENT, assigned_agent_id=AGENT,
                title="Gizli görev başlığı", instructions="Özel iş verisi", agent_name="Analiz", department="Kontrol",
                created_at="2026-10-12T12:00:00Z", started_at="2026-10-12T12:01:00Z",
                finished_at="2026-10-12T12:03:00Z", status="succeeded", provider_connection_id=CONNECTION, model="model")
    data.update(values)
    return AgentTask(**data)


def test_metrics_count_records_without_parent_double_counting():
    child = task(total_tokens=30, tokens_in=20, tokens_out=10, workflow_run_ids=["f" * 32],
                 approval_wait_seconds=15, approvals=[AgentEvent(kind="approval_requested")])
    parent = task(assignee_id="b" * 32, assigned_agent_id="b" * 32, total_tokens=10, tokens_in=8, tokens_out=2,
                  department="Yönetim", agent_name="Yönetici")
    failed = task(status="failed", finished_at="2026-10-12T12:02:00Z")
    cancelled = task(status="cancelled", started_at=None, finished_at=None)
    pending = task(status="waiting_approval", finished_at=None)
    report = calculate([child, parent, failed, cancelled, pending], company_id=2, start=FIRST, end=LAST)
    totals = report["totals"]
    assert (totals["total"], totals["succeeded"], totals["failed"], totals["cancelled"], totals["terminal"]) == (5, 2, 1, 1, 4)
    assert totals["success_rate"] == .5
    assert totals["total_seconds"] == 300 and totals["average_seconds"] == 75
    assert totals["duration_missing_count"] == 1
    assert totals["total_tokens"] == 40 and totals["workflow_count"] == 1
    assert totals["approval_count"] == 1 and totals["approval_wait_seconds"] == 15
    assert len(report["agents"]) == 2 and len(report["departments"]) == 2
    assert "Gizli görev" not in str(report) and "Özel iş" not in str(report)


@pytest.mark.parametrize("days", [1, 7, 31])
def test_day_week_month_boundaries_and_company_scope(days):
    first = datetime(2026, 10, 1, tzinfo=timezone.utc)
    end = first + timedelta(days=days)
    other = Actor(user_id=9, company_id=3, session_id="diğer")
    records = [task(created_at=first.isoformat()), task(created_at=end.isoformat()),
               task(created_at=(first - timedelta(microseconds=1)).isoformat()),
               task(created_by=other, company_id=3),
               task(assignee_type="human", assignee_id="1", assigned_agent_id=None)]
    assert calculate(records, company_id=2, start=first.isoformat(), end=end.isoformat())["totals"]["total"] == 1


def test_timezone_offset_and_invalid_interval():
    start, end = interval("2026-10-13T00:00:00+03:00", "2026-10-14T00:00:00+03:00")
    assert start.hour == 21 and start.day == 12 and (end - start).days == 1
    for first, last in [(LAST, FIRST), (FIRST, FIRST), ("2026-10-01", LAST), (FIRST, "2028-01-01T00:00:00Z")]:
        with pytest.raises(ValueError):
            interval(first, last)


def test_prices_use_historical_connection_and_model_do_not_mix_currencies():
    settings = MetricSettings(prices=[ModelPrice(connection_id=CONNECTION, model="model", currency="USD",
                                                input_per_million=2, output_per_million=4)])
    report = calculate([task(tokens_in=1_000_000, tokens_out=500_000, total_tokens=1_500_000),
                        task(model="eski", tokens_in=10, total_tokens=10)],
                       company_id=2, start=FIRST, end=LAST, settings=settings)
    assert report["totals"]["estimated_cost"] == {"USD": 4}
    assert report["totals"]["unpriced_tasks"] == 1


def test_csv_neutralizes_spreadsheet_formulas_and_omits_job_content():
    report = calculate([task(agent_name="=HYPERLINK(1)", department=" +malicious")], company_id=2, start=FIRST, end=LAST)
    exported = csv_export(report)
    assert "'=HYPERLINK(1)" in exported and "' +malicious" in exported
    assert "Gizli görev" not in exported and "Özel iş" not in exported
    assert "Tamamlanan" in exported


def test_settings_are_company_scoped_and_symlink_safe(tmp_path):
    store = MetricSettingsStore(tmp_path)
    store.save(2, MetricSettings())
    assert store.get(3).prices == []
    store.path(2).unlink()
    try:
        store.path(2).symlink_to(tmp_path / "unrelated.json")
    except (OSError, NotImplementedError):
        pytest.skip("Bu test ortamı sembolik bağlantı oluşturmaya izin vermiyor.")
    with pytest.raises(ValueError):
        store.get(2)


def test_metrics_api_license_csv_and_price_permissions(api):  # noqa: F811
    api.app.state.agents.agent_store.save_task(task())
    query = {"start": FIRST, "end": LAST}
    response = api.client.get("/api/agents/metrics", params=query)
    assert response.status_code == 200 and response.json()["totals"]["succeeded"] == 1
    exported = api.client.get("/api/agents/metrics/csv", params=query)
    assert exported.status_code == 200 and "Tamamlanan" in exported.text
    assert "Gizli görev" not in exported.text
    api.licensing.actor = api.licensing.actor.model_copy(update={"permissions": ("agents.use",)})
    assert api.client.put("/api/agents/metrics/settings", json={"prices": []}).status_code == 403
    api.licensing.agents = False
    assert api.client.get("/api/agents/metrics", params=query).status_code == 403


def test_oversize_or_nonfinite_price_never_persists():
    with pytest.raises(ValueError):
        ModelPrice(connection_id=CONNECTION, model="m", currency="USD", input_per_million=float("nan"), output_per_million=1)


def test_central_metrics_only_accepts_valid_dates_without_tenant_override():
    from test_agent_central import License, Response

    from rpa_orkestrai.agents.central import CentralClient, CentralError

    requests = []

    def opener(request, **kwargs):
        requests.append(request)
        return Response(request, {"success": True, "metrics": {}})

    client = CentralClient(License(), opener=opener)
    path = "/metrics?" + urlencode({"start": FIRST, "end": LAST})
    assert client.request("GET", path)["success"]
    for unsafe in (path + "&firma_id=8", path + "&start=" + FIRST, path + "#oops", "/metrics?start=x&end=y"):
        with pytest.raises(CentralError):
            client.request("GET", unsafe)
    assert len(requests) == 1
