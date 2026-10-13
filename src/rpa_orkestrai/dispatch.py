"""Coordinate scheduled reservations and agent requests for the single desktop worker."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable

from .errors import Cancelled


class RunDispatch:
    def __init__(self, manager):
        self.manager = manager
        self._condition = threading.Condition(threading.RLock())
        self._scheduled: threading.Event | None = None
        self._queue: deque[str] = deque()
        self._closed = False
        self.schedule_due: Callable[[], bool] = lambda: False

    def reserve_schedule(self) -> bool:
        with self._condition:
            if self._closed or self._scheduled is not None:
                return False
            try:
                self._scheduled = self.manager.reserve_desktop()
            except RuntimeError:
                return False
            return True

    def release_schedule(self) -> None:
        with self._condition:
            token, self._scheduled = self._scheduled, None
            if token is not None:
                self.manager.release_desktop(token)
            self._condition.notify_all()

    def start_schedule(self, workflow):
        with self._condition:
            token = self._scheduled
            if token is None:
                raise RuntimeError("Zamanlamanın çalıştırma sırası bulunamadı.")
            try:
                return self.manager.start(workflow, trigger="schedule", desktop_reservation=token)
            finally:
                self.release_schedule()

    def start_agent(self, key: str, start: Callable, *, cancel: threading.Event,
                    deadline: float, check: Callable[[], None]):
        """Wait without reserving the screen; return None when the busy deadline expires."""
        with self._condition:
            if key in self._queue:
                raise RuntimeError("Ajan çalışması zaten sırada.")
            self._queue.append(key)
        try:
            while True:
                check()
                if cancel.is_set():
                    raise Cancelled()
                with self._condition:
                    if self._closed:
                        raise Cancelled()
                    if time.monotonic() >= deadline:
                        return None
                    if (self._queue[0] == key and self._scheduled is None
                            and not self.schedule_due() and not self.manager.busy()):
                        try:
                            return start()
                        except RuntimeError:
                            # A manual request may have acquired the worker after busy().
                            if not self.manager.busy():
                                raise
                    self._condition.wait(min(0.1, max(0, deadline - time.monotonic())))
        finally:
            with self._condition:
                if key in self._queue:
                    self._queue.remove(key)
                self._condition.notify_all()

    def queue(self) -> list[str]:
        with self._condition:
            return list(self._queue)

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self.release_schedule()
            self._condition.notify_all()
