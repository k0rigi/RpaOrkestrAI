import threading
import time
from datetime import datetime

import pytest

from rpa_orkestrai.config import Settings
from rpa_orkestrai.dispatch import RunDispatch
from rpa_orkestrai.engine import RunManager
from rpa_orkestrai.errors import Cancelled
from rpa_orkestrai.models import Schedule, ScheduleSettings, Step, Workflow
from rpa_orkestrai.scheduler import ScheduleBook, Scheduler
from rpa_orkestrai.storage import Store


def test_countdown_reserves_worker_and_cancel_releases_it(tmp_path):
    store = Store(tmp_path)
    flow = store.save_workflow(Workflow(steps=[Step(action="core.log", params={"message": "Tamam"})]))
    manager = RunManager(Settings(tmp_path, dotenv=False), store)
    dispatch = RunDispatch(manager)
    book = ScheduleBook(tmp_path)
    book.set_settings(ScheduleSettings(countdown=30))
    book.add(Schedule(workflow_id=flow.id, next_run_at="2026-10-01T09:00"))
    scheduler = Scheduler(book, start_run=lambda key: dispatch.start_schedule(store.workflow(key)),
                          allowed=lambda: True, busy=manager.busy, workflow_name=lambda key: flow.name,
                          clock=lambda: datetime(2026, 10, 1, 9), reserve=dispatch.reserve_schedule,
                          release=dispatch.release_schedule)
    try:
        scheduler.check()
        assert manager.busy() and scheduler.pending()
        with pytest.raises(RuntimeError):
            manager.start(flow)
        called = []
        result = dispatch.start_agent("a", lambda: called.append(True), cancel=threading.Event(),
                                      deadline=time.monotonic() + 0.03, check=lambda: None)
        assert result is None and not called
        scheduler.answer("cancel")
        scheduler.check()
        assert not manager.busy()
    finally:
        scheduler.stop()
        dispatch.close()
        manager.close()


def test_scheduled_start_consumes_only_its_reservation(tmp_path):
    manager = RunManager(Settings(tmp_path, dotenv=False), Store(tmp_path))
    dispatch = RunDispatch(manager)
    try:
        assert dispatch.reserve_schedule()
        run = dispatch.start_schedule(Workflow(steps=[Step(action="core.log", params={"message": "Tamam"})]))
        assert run.trigger == "schedule"
        with pytest.raises(RuntimeError):
            dispatch.start_schedule(Workflow())
    finally:
        dispatch.close()
        manager.close()


def test_agent_wait_cancel_does_not_cancel_somebody_elses_reservation(tmp_path):
    manager = RunManager(Settings(tmp_path, dotenv=False), Store(tmp_path))
    dispatch = RunDispatch(manager)
    token = manager.reserve_desktop()
    cancel = threading.Event()
    cancel.set()
    try:
        with pytest.raises(Cancelled):
            dispatch.start_agent("a", lambda: pytest.fail("Çalıştırılmamalı"), cancel=cancel,
                                 deadline=time.monotonic() + 1, check=lambda: None)
        assert manager.busy() and not token.is_set() and dispatch.queue() == []
    finally:
        manager.release_desktop(token)
        dispatch.close()
        manager.close()
