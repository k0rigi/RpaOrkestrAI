"""Zamanlayıcı: flows that run by themselves while the Studio is open.

Schedules live in data/schedules.json. A background thread looks at them every few seconds. A due
flow first shows a countdown in the Studio (with İptal and Şimdi başlat), then starts like a run
started by hand: the license gate, the single desktop worker and the run history all apply. Times
are wall-clock local times, as the person set them.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from .config import atomic_json
from .models import Schedule, ScheduleInput, ScheduleSettings

LOGGER = logging.getLogger(__name__)
SHORT_DAYS = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
WEEKDAYS, WEEKEND, EVERY_DAY = [0, 1, 2, 3, 4], [5, 6], list(range(7))
# A due run waits this long for a free desktop or a license answer before it counts as skipped.
GRACE = timedelta(minutes=10)


# ----- when ----------------------------------------------------------------------------------
def at(day: date, hour_minute: str) -> datetime:
    hour, minute = (int(part) for part in hour_minute.split(":"))
    return datetime(day.year, day.month, day.day, hour, minute)


def next_occurrence(schedule: ScheduleInput, after: datetime) -> datetime | None:
    """The first time strictly after `after` (naive local time) the schedule is due; None if never again."""
    if schedule.kind == "once":
        due = at(date.fromisoformat(schedule.date), schedule.time)
        return due if due > after else None
    step = timedelta(minutes=schedule.every_minutes)
    for offset in range(9):
        day = after.date() + timedelta(days=offset)
        if schedule.kind in {"weekly", "interval"} and day.weekday() not in schedule.days:
            continue
        start = at(day, schedule.time)
        if schedule.kind in {"daily", "weekly"}:
            if start > after:
                return start
            continue
        # Every N minutes from the window start until its end (or midnight), on the chosen days.
        end = at(day, schedule.until) if schedule.until else datetime.combine(day + timedelta(days=1),
                                                                              datetime.min.time())
        due = start if after < start else start + (math.floor((after - start) / step) + 1) * step
        if due < end:
            return due
    return None


def upcoming(schedule: ScheduleInput, after: datetime, count: int = 3) -> list[datetime]:
    times: list[datetime] = []
    while len(times) < count:
        due = next_occurrence(schedule, times[-1] if times else after)
        if due is None:
            break
        times.append(due)
    return times


def day_words(days: list[int]) -> str:
    chosen = sorted(days)
    if chosen == EVERY_DAY:
        return "her gün"
    if chosen == WEEKDAYS:
        return "hafta içi"
    if chosen == WEEKEND:
        return "hafta sonu"
    return ", ".join(SHORT_DAYS[day] for day in chosen)


def summary(schedule: ScheduleInput) -> str:
    """How the Studio shows the schedule, e.g. "Hafta içi 09:00"."""
    if schedule.kind == "once":
        return f"Bir kez: {date.fromisoformat(schedule.date).strftime('%d.%m.%Y')} {schedule.time}"
    if schedule.kind == "daily":
        return f"Her gün {schedule.time}"
    if schedule.kind == "weekly":
        words = day_words(schedule.days)
        return f"{words[0].upper()}{words[1:]} {schedule.time}"
    minutes = schedule.every_minutes
    every = f"Her {minutes // 60} saatte bir" if minutes % 60 == 0 else f"Her {minutes} dakikada bir"
    window = f", {schedule.time}–{schedule.until or '24:00'} arası" if schedule.until or schedule.time != "00:00" else ""
    return f"{every}{window}, {day_words(schedule.days)}"


def shown(moment: datetime) -> str:
    return moment.strftime("%d.%m.%Y %H:%M")


# ----- where ---------------------------------------------------------------------------------
class ScheduleBook:
    """data/schedules.json: the countdown setting and the schedules, read and written whole."""

    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / "schedules.json"
        self._lock = threading.RLock()

    def _read(self) -> tuple[ScheduleSettings, list[Schedule]]:
        if not self.path.exists():
            return ScheduleSettings(), []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return (ScheduleSettings(**{k: v for k, v in data.items() if k != "schedules"}),
                    [Schedule(**item) for item in data.get("schedules", [])])
        except (OSError, ValueError, TypeError) as exc:
            # A damaged file is kept aside, never silently overwritten with an empty list.
            broken = self.path.with_suffix(".bozuk.json")
            self.path.replace(broken)
            LOGGER.warning("Zamanlama dosyası okunamadı, %s olarak ayrıldı: %s", broken.name, exc)
            return ScheduleSettings(), []

    def _write(self, settings: ScheduleSettings, schedules: list[Schedule]) -> None:
        atomic_json(self.path, {**settings.model_dump(), "schedules": [item.model_dump() for item in schedules]})

    def settings(self) -> ScheduleSettings:
        with self._lock:
            return self._read()[0]

    def set_settings(self, settings: ScheduleSettings) -> ScheduleSettings:
        with self._lock:
            _, schedules = self._read()
            self._write(settings, schedules)
            return settings

    def schedules(self) -> list[Schedule]:
        with self._lock:
            return self._read()[1]

    def get(self, schedule_id: str) -> Schedule | None:
        return next((item for item in self.schedules() if item.id == schedule_id), None)

    def change(self, schedule_id: str, edit: Callable[[Schedule], Schedule | None]) -> Schedule | None:
        """Apply edit to one schedule under the lock; edit returns the new version or None to delete it."""
        with self._lock:
            settings, schedules = self._read()
            for index, item in enumerate(schedules):
                if item.id == schedule_id:
                    changed = edit(item.model_copy(deep=True))
                    if changed is None:
                        del schedules[index]
                    else:
                        schedules[index] = changed
                    self._write(settings, schedules)
                    return changed
            return None

    def add(self, schedule: Schedule) -> Schedule:
        with self._lock:
            settings, schedules = self._read()
            if len(schedules) >= 100:
                raise ValueError("En fazla 100 zamanlama oluşturulabilir.")
            schedules.append(schedule)
            self._write(settings, schedules)
            return schedule

    def remove(self, schedule_id: str) -> bool:
        with self._lock:
            settings, schedules = self._read()
            kept = [item for item in schedules if item.id != schedule_id]
            if len(kept) == len(schedules):
                return False
            self._write(settings, kept)
            return True

    def remove_workflow(self, workflow_id: str) -> int:
        with self._lock:
            settings, schedules = self._read()
            kept = [item for item in schedules if item.workflow_id != workflow_id]
            if len(kept) != len(schedules):
                self._write(settings, kept)
            return len(schedules) - len(kept)

    def active(self) -> bool:
        return any(item.enabled for item in self.schedules())


def planned(schedule: Schedule, moment: datetime) -> Schedule:
    """The schedule with its next due time from `moment` on; a disabled one has none."""
    due = next_occurrence(schedule, moment) if schedule.enabled else None
    return schedule.model_copy(update={"next_run_at": due.isoformat(timespec="minutes") if due else None})


# ----- who -----------------------------------------------------------------------------------
class Scheduler:
    """The thread that starts due flows. Everything it needs from the Studio comes in as a callable."""

    def __init__(self, book: ScheduleBook, *, start_run: Callable[[str], object], allowed: Callable[[], bool],
                 busy: Callable[[], bool], workflow_name: Callable[[str], str | None],
                 attention: Callable[[], None] | None = None, clock: Callable[[], datetime] = datetime.now,
                 tick: float = 5.0):
        self.book, self.start_run, self.allowed, self.busy = book, start_run, allowed, busy
        self.workflow_name, self.attention, self.clock, self.tick = workflow_name, attention, clock, tick
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._pending: dict | None = None
        self._answer: str | None = None  # "cancel" or "start" from the countdown in the Studio

    # The countdown the Studio shows.
    def pending(self) -> dict | None:
        with self._lock:
            if not self._pending:
                return None
            left = max(0, math.ceil(self._pending["deadline"] - time.monotonic()))
            return {key: value for key, value in self._pending.items() if key != "deadline"} | {"seconds_left": left}

    def answer(self, choice: str) -> bool:
        with self._lock:
            if not self._pending:
                return False
            self._answer = choice
        self._wake.set()
        return True

    def start(self) -> None:
        if self._thread is None:
            self.notice_missed()
            self._thread = threading.Thread(target=self._loop, daemon=True, name="rpa-scheduler")
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=10)

    def poke(self) -> None:
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.check()
            except Exception:
                LOGGER.exception("Zamanlayıcı denetimi başarısız oldu.")
            self._wake.wait(1.0 if self._pending else self.tick)
            self._wake.clear()

    def notice_missed(self) -> None:
        """At start: a time that passed while the Studio was closed is missed, or run once (catch_up)."""
        moment = self.clock()
        for schedule in self.book.schedules():
            due = datetime.fromisoformat(schedule.next_run_at) if schedule.next_run_at else None
            if not schedule.enabled or (due is not None and due >= moment):
                continue
            if due is None:
                self.book.change(schedule.id, lambda item: planned(item, moment))
                continue
            if schedule.catch_up:
                # Due now: the wait for the license answer and a free desktop counts from the opening.
                self.book.change(schedule.id, lambda item: item.model_copy(
                    update={"next_run_at": moment.isoformat(timespec="minutes")}))
                continue

            def missed(item: Schedule, due: datetime = due) -> Schedule:
                item = planned(item, moment)
                item.last_status = "missed"
                item.last_message = f"Studio kapalıyken {shown(due)} çalışması kaçırıldı."
                return item

            self.book.change(schedule.id, missed)

    def check(self) -> None:
        if self._pending:
            self._countdown()
            return
        moment = self.clock()
        due_now = sorted((item for item in self.book.schedules() if item.enabled and item.next_run_at
                          and datetime.fromisoformat(item.next_run_at) <= moment),
                         key=lambda item: item.next_run_at)
        for schedule in due_now:
            due = datetime.fromisoformat(schedule.next_run_at)
            name = self.workflow_name(schedule.workflow_id)
            if name is None:
                self._record(schedule.id, "error", "Akış bulunamadığı için zamanlama durduruldu.", disable=True)
                continue
            waited_too_long = moment - due > GRACE
            if not self.allowed():
                if waited_too_long:
                    self._record(schedule.id, "skipped", "Lisans doğrulanamadığı için çalışmadı.")
                continue
            if self.busy():
                if waited_too_long:
                    self._record(schedule.id, "skipped", "O sırada başka bir akış çalıştığı için atlandı.")
                continue
            countdown = self.book.settings().countdown
            with self._lock:
                self._answer = None
                self._pending = {"schedule_id": schedule.id, "workflow_id": schedule.workflow_id,
                                 "workflow_name": name, "due_at": schedule.next_run_at,
                                 "deadline": time.monotonic() + countdown}
            if countdown and self.attention:
                try:
                    self.attention()
                except Exception:
                    LOGGER.exception("Studio penceresi öne getirilemedi.")
            self._countdown()
            return  # one at a time: the desktop has a single worker

    def _countdown(self) -> None:
        with self._lock:
            pending, choice = self._pending, self._answer
            if pending is None:
                return
            if choice != "cancel" and choice != "start" and time.monotonic() < pending["deadline"]:
                return
            self._pending, self._answer = None, None
        if choice == "cancel":
            self._record(pending["schedule_id"], "cancelled", "Geri sayımda iptal edildi.")
            return
        try:
            run = self.start_run(pending["workflow_id"])
        except Exception as exc:  # the license, a busy desktop or an invalid flow: said in the history
            self._record(pending["schedule_id"], "error", str(exc)[:500] or "Akış başlatılamadı.")
            return
        self._record(pending["schedule_id"], "started", None, run_id=getattr(run, "id", None))

    def _record(self, schedule_id: str, status: str, message: str | None, *, run_id: str | None = None,
                disable: bool = False) -> None:
        moment = self.clock()

        def edit(item: Schedule) -> Schedule:
            if disable or (item.kind == "once" and status in {"started", "skipped", "cancelled", "error"}):
                item.enabled = False  # a one-time schedule is done once its time has come
            item = planned(item, moment)
            item.last_status, item.last_message = status, message
            item.last_run_at = moment.isoformat(timespec="seconds")
            if run_id:
                item.last_run_id = run_id
            return item

        self.book.change(schedule_id, edit)
