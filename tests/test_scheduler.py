"""Zamanlayıcı: when a schedule is due, and how a due flow starts while the Studio is open."""

import json
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from rpa_orkestrai.config import atomic_json
from rpa_orkestrai.models import Schedule, ScheduleInput, ScheduleSettings
from rpa_orkestrai.scheduler import (
    GRACE,
    ScheduleBook,
    Scheduler,
    next_occurrence,
    planned,
    summary,
    upcoming,
)

FLOW = "a" * 32
MONDAY = datetime(2026, 10, 5, 8, 0)
assert MONDAY.weekday() == 0


def at(day_offset: int, clock: str) -> datetime:
    hour, minute = map(int, clock.split(":"))
    return (MONDAY + timedelta(days=day_offset)).replace(hour=hour, minute=minute)


def plan(**fields) -> ScheduleInput:
    return ScheduleInput(workflow_id=FLOW, **fields)


# ----- when ------------------------------------------------------------------------------------
def test_daily_and_weekly_times_come_strictly_after_the_moment():
    daily = plan(kind="daily", time="09:00")
    assert next_occurrence(daily, at(0, "08:00")) == at(0, "09:00")
    assert next_occurrence(daily, at(0, "09:00")) == at(1, "09:00")
    assert next_occurrence(daily, at(0, "23:59")) == at(1, "09:00")
    monday_wednesday = plan(kind="weekly", time="09:00", days=[0, 2])
    assert next_occurrence(monday_wednesday, at(0, "10:00")) == at(2, "09:00")
    assert next_occurrence(monday_wednesday, at(2, "10:00")) == at(7, "09:00")
    weekend = plan(kind="weekly", time="07:30", days=[5, 6])
    assert next_occurrence(weekend, at(0, "08:00")) == at(5, "07:30")


def test_interval_repeats_inside_its_window_on_the_chosen_days():
    office = plan(kind="interval", time="09:00", until="11:00", every_minutes=30, days=[0, 1, 2, 3, 4])
    assert next_occurrence(office, at(0, "08:00")) == at(0, "09:00")
    assert next_occurrence(office, at(0, "09:00")) == at(0, "09:30")
    assert next_occurrence(office, at(0, "09:10")) == at(0, "09:30")
    assert next_occurrence(office, at(0, "10:29")) == at(0, "10:30")
    # The end of the window is not a run of its own; Friday evening waits for Monday.
    assert next_occurrence(office, at(0, "10:30")) == at(1, "09:00")
    assert next_occurrence(office, at(4, "11:00")) == at(7, "09:00")
    hourly = plan(kind="interval", time="00:00", every_minutes=60, days=list(range(7)))
    assert next_occurrence(hourly, at(0, "23:30")) == at(1, "00:00")
    assert upcoming(hourly, at(0, "08:10"), 3) == [at(0, "09:00"), at(0, "10:00"), at(0, "11:00")]


def test_once_runs_at_its_time_and_never_again():
    once = plan(kind="once", date="2026-10-06", time="14:30")
    assert next_occurrence(once, at(0, "08:00")) == at(1, "14:30")
    assert next_occurrence(once, at(1, "14:30")) is None
    assert upcoming(once, at(0, "08:00")) == [at(1, "14:30")]


def test_summary_reads_like_the_studio_shows_it():
    assert summary(plan(kind="daily", time="09:00")) == "Her gün 09:00"
    assert summary(plan(kind="weekly", time="09:00", days=[0, 1, 2, 3, 4])) == "Hafta içi 09:00"
    assert summary(plan(kind="weekly", time="18:15", days=[0, 2])) == "Pzt, Çar 18:15"
    assert summary(plan(kind="interval", time="09:00", until="18:00", every_minutes=30)) == (
        "Her 30 dakikada bir, 09:00–18:00 arası, hafta içi")
    assert summary(plan(kind="interval", time="00:00", every_minutes=120, days=list(range(7)))) == (
        "Her 2 saatte bir, her gün")
    assert summary(plan(kind="once", date="2026-10-06", time="14:30")) == "Bir kez: 06.10.2026 14:30"


@pytest.mark.parametrize("fields, message", [
    ({"kind": "once"}, "tarih gereklidir"),
    ({"kind": "once", "date": "2026-02-30"}, "Geçerli bir tarih"),
    ({"kind": "weekly", "days": []}, "En az bir gün"),
    ({"kind": "daily", "days": [0, 0]}, "tekrarsız"),
    ({"kind": "daily", "days": [7]}, "tekrarsız"),
    ({"kind": "interval", "time": "10:00", "until": "09:00"}, "bitişi"),
    ({"kind": "daily", "time": "24:00"}, "pattern"),
    ({"kind": "interval", "every_minutes": 0}, "greater than or equal"),
])
def test_impossible_schedules_are_refused(fields, message):
    with pytest.raises(ValidationError, match=message):
        plan(**fields)


# ----- where -----------------------------------------------------------------------------------
def test_book_keeps_schedules_and_settings_and_sets_a_damaged_file_aside(tmp_path):
    book = ScheduleBook(tmp_path)
    assert book.schedules() == [] and book.settings().countdown == 10 and not book.active()
    first = book.add(Schedule(workflow_id=FLOW, enabled=False))
    second = book.add(Schedule(workflow_id="b" * 32))
    book.set_settings(ScheduleSettings(countdown=0))
    assert [item.id for item in ScheduleBook(tmp_path).schedules()] == [first.id, second.id]
    assert book.settings().countdown == 0 and book.active()
    changed = book.change(first.id, lambda item: item.model_copy(update={"enabled": True}))
    assert changed.enabled and book.get(first.id).enabled
    assert book.change("missing", lambda item: item) is None
    assert book.remove_workflow("b" * 32) == 1 and book.remove(first.id) and not book.remove(first.id)
    (tmp_path / "schedules.json").write_text("{bozuk", encoding="utf-8")
    assert book.schedules() == []
    assert (tmp_path / "schedules.bozuk.json").read_text(encoding="utf-8") == "{bozuk"


def test_book_holds_at_most_one_hundred_schedules(tmp_path):
    book = ScheduleBook(tmp_path)
    for _ in range(100):
        book.add(Schedule(workflow_id=FLOW))
    with pytest.raises(ValueError, match="100"):
        book.add(Schedule(workflow_id=FLOW))


# ----- who -------------------------------------------------------------------------------------
class Desk:
    """What the Scheduler needs from the Studio, with a clock the test moves."""

    def __init__(self, tmp_path, *, countdown=0, now=None):
        self.now = now or at(0, "08:59")
        self.book = ScheduleBook(tmp_path)
        self.book.set_settings(ScheduleSettings(countdown=countdown))
        self.started, self.busy, self.allowed, self.names, self.alerts = [], False, True, {FLOW: "Fatura"}, 0
        self.failure = None
        self.scheduler = Scheduler(self.book, start_run=self.start, allowed=lambda: self.allowed,
                                   busy=lambda: self.busy, workflow_name=self.names.get,
                                   attention=self.attention, clock=lambda: self.now)

    def start(self, workflow_id):
        if self.failure:
            raise self.failure
        self.started.append(workflow_id)
        return SimpleNamespace(id=f"run-{len(self.started)}")

    def attention(self):
        self.alerts += 1

    def add(self, **fields) -> Schedule:
        return self.book.add(planned(Schedule(workflow_id=FLOW, **fields), self.now))

    def get(self, schedule: Schedule) -> Schedule:
        return self.book.get(schedule.id)


def test_a_due_schedule_starts_its_flow_and_plans_the_next_time(tmp_path):
    desk = Desk(tmp_path)
    schedule = desk.add(kind="daily", time="09:00")
    assert schedule.next_run_at == "2026-10-05T09:00"
    desk.scheduler.check()
    assert desk.started == []
    desk.now = at(0, "09:00")
    desk.scheduler.check()
    saved = desk.get(schedule)
    assert desk.started == [FLOW] and desk.alerts == 0  # no countdown: nothing to show
    assert (saved.last_status, saved.last_run_id, saved.next_run_at) == ("started", "run-1", "2026-10-06T09:00")
    desk.scheduler.check()
    assert desk.started == [FLOW]


def test_the_countdown_can_be_cancelled_or_cut_short(tmp_path):
    desk = Desk(tmp_path, countdown=30)
    schedule = desk.add(kind="daily", time="09:00")
    desk.now = at(0, "09:00")
    desk.scheduler.check()
    pending = desk.scheduler.pending()
    assert desk.alerts == 1 and desk.started == []
    assert (pending["workflow_name"], pending["schedule_id"], pending["due_at"]) == (
        "Fatura", schedule.id, "2026-10-05T09:00")
    assert 0 < pending["seconds_left"] <= 30
    assert desk.scheduler.answer("cancel")
    desk.scheduler.check()
    saved = desk.get(schedule)
    assert desk.started == [] and desk.scheduler.pending() is None
    assert (saved.last_status, saved.next_run_at) == ("cancelled", "2026-10-06T09:00")
    assert not desk.scheduler.answer("start")
    desk.now = at(1, "09:00")
    desk.scheduler.check()
    assert desk.scheduler.answer("start")
    desk.scheduler.check()
    assert desk.started == [FLOW] and desk.get(schedule).last_status == "started"


def test_a_busy_desktop_or_missing_license_waits_then_skips(tmp_path):
    desk = Desk(tmp_path)
    schedule = desk.add(kind="daily", time="09:00")
    desk.busy = True
    desk.now = at(0, "09:00")
    desk.scheduler.check()
    assert desk.get(schedule).last_status is None and desk.get(schedule).next_run_at == "2026-10-05T09:00"
    desk.busy = False
    desk.now = at(0, "09:05")
    desk.scheduler.check()  # the desktop came free within the grace time
    assert desk.started == [FLOW]
    desk.now, desk.busy = at(1, "09:00") + GRACE + timedelta(minutes=1), True
    desk.scheduler.check()
    saved = desk.get(schedule)
    assert (saved.last_status, saved.next_run_at) == ("skipped", "2026-10-07T09:00")
    assert "başka bir akış" in saved.last_message
    desk.busy, desk.allowed = False, False
    desk.now = at(2, "09:00") + GRACE + timedelta(minutes=1)
    desk.scheduler.check()
    assert desk.get(schedule).last_message == "Lisans doğrulanamadığı için çalışmadı."
    assert desk.started == [FLOW]


def test_a_flow_that_cannot_start_or_is_gone_is_reported(tmp_path):
    desk = Desk(tmp_path)
    schedule = desk.add(kind="daily", time="09:00")
    desk.failure = RuntimeError("Masaüstünde başka bir akış çalışıyor.")
    desk.now = at(0, "09:00")
    desk.scheduler.check()
    saved = desk.get(schedule)
    assert (saved.last_status, saved.last_message, saved.enabled) == (
        "error", "Masaüstünde başka bir akış çalışıyor.", True)
    desk.names.clear()
    desk.now = at(1, "09:00")
    desk.scheduler.check()
    saved = desk.get(schedule)
    assert (saved.last_status, saved.enabled, saved.next_run_at) == ("error", False, None)
    assert "bulunamadığı" in saved.last_message


def test_once_turns_itself_off_and_disabled_schedules_never_run(tmp_path):
    desk = Desk(tmp_path)
    once = desk.add(kind="once", date="2026-10-05", time="09:00")
    off = desk.add(kind="daily", time="09:00", enabled=False)
    assert off.next_run_at is None
    desk.now = at(0, "09:00")
    desk.scheduler.check()
    assert desk.started == [FLOW]
    saved = desk.get(once)
    assert (saved.enabled, saved.next_run_at, saved.last_status) == (False, None, "started")
    assert desk.get(off).last_status is None


def test_a_time_missed_while_closed_is_reported_or_run_once(tmp_path):
    desk = Desk(tmp_path, now=at(0, "08:00"))
    missed = desk.add(kind="daily", time="09:00")
    caught = desk.add(kind="daily", time="09:30", catch_up=True)
    desk.now = at(0, "12:00")  # the Studio opens again at noon
    desk.scheduler.notice_missed()
    saved = desk.get(missed)
    assert (saved.last_status, saved.next_run_at) == ("missed", "2026-10-06T09:00")
    assert saved.last_message == "Studio kapalıyken 05.10.2026 09:00 çalışması kaçırıldı."
    assert desk.get(caught).next_run_at == "2026-10-05T12:00"
    # The catch-up waits for the desktop like any due run, counted from the opening.
    desk.busy = True
    desk.now = at(0, "12:05")
    desk.scheduler.check()
    assert desk.get(caught).last_status is None
    desk.busy = False
    desk.scheduler.check()
    assert desk.started == [FLOW]
    assert desk.get(caught).next_run_at == "2026-10-06T09:30"


def test_the_scheduler_thread_starts_and_stops_promptly(tmp_path):
    desk = Desk(tmp_path, now=datetime.now())
    desk.scheduler.tick = 0.05
    desk.scheduler.start()
    started = time.monotonic()
    desk.scheduler.stop()
    assert time.monotonic() - started < 2


# ----- the Studio ------------------------------------------------------------------------------
def studio(tmp_path):
    from fastapi.testclient import TestClient

    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    return TestClient(create_app(Settings(tmp_path / "data", dotenv=False)))


def test_schedules_are_created_listed_changed_and_removed(tmp_path):
    with studio(tmp_path) as client:
        flow = client.post("/api/workflows", json={"name": "Günlük rapor", "steps": [{"action": "core.log"}]}).json()
        body = {"workflow_id": flow["id"], "kind": "weekly", "time": "09:00", "days": [0, 1, 2, 3, 4]}
        preview = client.post("/api/schedules/preview", json=body).json()
        assert preview["summary"] == "Hafta içi 09:00" and len(preview["upcoming"]) == 3
        created = client.post("/api/schedules", json=body)
        assert created.status_code == 201, created.text
        schedule = created.json()
        assert (schedule["workflow_name"], schedule["summary"], schedule["enabled"]) == (
            "Günlük rapor", "Hafta içi 09:00", True)
        assert schedule["next_run_at"] == schedule["upcoming"][0]
        listing = client.get("/api/schedules").json()
        assert [item["id"] for item in listing["schedules"]] == [schedule["id"]]
        assert listing["settings"] == {"countdown": 10} and listing["pending"] is None
        assert listing["autostart"]["supported"] is False  # tests run from source, not the installed app
        off = client.put(f"/api/schedules/{schedule['id']}", json={**body, "enabled": False}).json()
        assert (off["enabled"], off["next_run_at"], off["upcoming"]) == (False, None, [])
        assert client.put("/api/schedule-settings", json={"countdown": 0}).json() == {"countdown": 0}
        assert client.put("/api/schedule-settings", json={"countdown": 121}).status_code == 422
        assert client.delete(f"/api/schedules/{schedule['id']}").status_code == 204
        assert client.delete(f"/api/schedules/{schedule['id']}").status_code == 404
        assert client.get("/api/schedules").json()["schedules"] == []


def test_schedules_refuse_unknown_flows_and_past_times_and_follow_deleted_flows(tmp_path):
    with studio(tmp_path) as client:
        flow = client.post("/api/workflows", json={"name": "Akış", "steps": [{"action": "core.log"}]}).json()
        assert client.post("/api/schedules", json={"workflow_id": "f" * 32}).status_code == 404
        past = client.post("/api/schedules", json={"workflow_id": flow["id"], "kind": "once",
                                                   "date": "2020-01-01", "time": "09:00"})
        assert past.status_code == 422 and "geçmişte" in past.json()["detail"]
        # Off, it may keep a past date (a one-time schedule that already ran).
        kept = client.post("/api/schedules", json={"workflow_id": flow["id"], "kind": "once", "enabled": False,
                                                   "date": "2020-01-01", "time": "09:00"})
        assert kept.status_code == 201
        assert client.post("/api/schedules", json={"workflow_id": flow["id"], "kind": "weekly",
                                                   "days": []}).status_code == 422
        assert client.post("/api/schedules/pending/cancel").status_code == 409
        assert client.post("/api/schedules/pending/later").status_code == 404
        refused = client.put("/api/autostart", json={"enabled": True})
        assert refused.status_code == 422 and "kurulu masaüstü" in refused.json()["detail"]
        client.delete(f"/api/workflows/{flow['id']}")
        assert client.get("/api/schedules").json()["schedules"] == []


def test_a_due_schedule_runs_the_saved_flow_and_the_history_says_so(tmp_path):
    with studio(tmp_path) as client:
        flow = client.post("/api/workflows", json={"name": "Zamanlanmış", "steps": [
            {"action": "core.log", "params": {"message": "Zamanında çalıştı."}}]}).json()
        client.put("/api/schedule-settings", json={"countdown": 0})
        schedule = client.post("/api/schedules", json={"workflow_id": flow["id"], "kind": "daily",
                                                       "time": "09:00"}).json()
        # Make it due a minute ago, as if the clock just passed its time (written whole, as the book does).
        path = tmp_path / "data" / "schedules.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["schedules"][0]["next_run_at"] = (datetime.now() - timedelta(minutes=1)).isoformat(timespec="minutes")
        atomic_json(path, data)
        client.app.state.scheduler.poke()
        deadline = time.monotonic() + 15
        runs = []
        while time.monotonic() < deadline:
            runs = client.get("/api/runs").json()
            if runs and runs[0]["status"] not in {"queued", "running"}:
                break
            time.sleep(0.1)
        assert [(run["workflow_id"], run["trigger"], run["status"]) for run in runs] == [
            (flow["id"], "schedule", "succeeded")]
        saved = client.get("/api/schedules").json()["schedules"][0]
        assert (saved["id"], saved["last_status"], saved["last_run_id"]) == (schedule["id"], "started", runs[0]["id"])
        manual = client.post(f"/api/workflows/{flow['id']}/run", json={}).json()
        assert manual["trigger"] == "manual"
