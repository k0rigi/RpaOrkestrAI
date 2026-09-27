"""Bounded asynchronous picker sessions sharing the workflow's desktop reservation."""

from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict
from uuid import uuid4

from .picker import LivePicker, native_available
from .windows import WindowError


class PickJobs:
    def __init__(self, manager, captures, *, picker_factory=LivePicker, available=native_available):
        self.manager, self.captures = manager, captures
        self.picker_factory, self.available = picker_factory, available
        self._jobs = OrderedDict()
        self._lock = threading.RLock()
        self._closed = False

    def _discard(self, job):
        result = job['public'].get('result')
        if result:
            self.captures.discard(result['capture']['id'])

    def _expire(self):
        for key, job in list(self._jobs.items()):
            if job['done'] and time.monotonic() - job['updated'] > 300:
                self._discard(job)
                del self._jobs[key]
        while len(self._jobs) >= 8:
            key = next((key for key, job in self._jobs.items() if job['done']), None)
            if key is None:
                raise RuntimeError('Hedef seçimi zaten devam ediyor.')
            self._discard(self._jobs.pop(key))

    def start(self, selector: dict, mode: str, delay: int) -> dict:
        with self._lock:
            if self._closed:
                raise RuntimeError('Uygulama kapanıyor.')
            if not self.available():
                raise WindowError('Canlı hedef seçimi için masaüstü uygulamasını açın; tarayıcıda görüntü üzerinde seçim yapabilirsiniz.')
            self._expire()
            cancel = threading.Event()
            token = self.manager.reserve_desktop(cancel)
            key = uuid4().hex
            job = {'public': {'id': key, 'status': 'starting', 'countdown': delay,
                              'message': 'Hedef seçimi hazırlanıyor.'},
                   'cancel': cancel, 'token': token, 'updated': time.monotonic(),
                   'done': False, 'discard': False}
            self._jobs[key] = job
            worker = threading.Thread(target=self._work, args=(job, selector, mode, delay),
                                      name='rpa-target-picker', daemon=True)
            job['worker'] = worker
            try:
                worker.start()
            except Exception:
                self.manager.release_desktop(token)
                del self._jobs[key]
                raise
            return copy.deepcopy(job['public'])

    def _work(self, job, selector, mode, delay):
        def progress(state):
            with self._lock:
                if job['cancel'].is_set():
                    return
                status = state.get('status', 'starting')
                job['public']['status'] = 'starting' if status == 'preparing' else status
                job['public']['countdown'] = state.get('remaining', 0)
                job['public']['message'] = state.get('message', 'Hedefi ekranda seçin. Escape ile iptal edebilirsiniz.')
                job['updated'] = time.monotonic()
        try:
            selected = self.picker_factory().pick(selector, mode, delay, cancel=job['cancel'], on_state=progress)
            with self._lock:
                if job['cancel'].is_set():
                    raise InterruptedError()
                capture = self.captures.add(selected['window'], selected['image'])
                point = selected.get('point')
                if mode == 'coordinates':
                    point = {'x': selected['x'], 'y': selected['y']}
                job['public'].update(status='completed', countdown=0, message='Hedef seçildi. Önizlemeyi kontrol edip kaydedin.',
                                     result={'capture': capture, 'rectangle': selected.get('crop'), 'point': point,
                                             'element': selected.get('element')})
        except InterruptedError:
            with self._lock:
                job['public'].update(status='cancelled', countdown=0, message='Hedef seçimi iptal edildi.')
        except Exception as exc:
            message = str(exc) if isinstance(exc, WindowError) else (
                'Hedef seçimi zaman aşımına uğradı. Yeniden deneyin.' if isinstance(exc, TimeoutError) else
                'Hedef seçimi tamamlanamadı. Ekran izinlerini ve açık ERP penceresini kontrol edin.')
            with self._lock:
                job['public'].update(status='error', countdown=0, message=message)
        finally:
            # Native picker cleanup has already restored Studio before it returns.
            self.manager.release_desktop(job['token'])
            with self._lock:
                job['done'] = True
                job['updated'] = time.monotonic()
                if job['discard']:
                    self._discard(job)
                    self._jobs.pop(job['public']['id'], None)

    def status(self, key):
        with self._lock:
            self._expire()
            if key not in self._jobs:
                raise KeyError(key)
            return copy.deepcopy(self._jobs[key]['public'])

    def cancel(self, key):
        with self._lock:
            job = self._jobs.get(key)
            if job is None:
                return
            job['cancel'].set()
            job['discard'] = True
            if job['done']:
                self._discard(job)
                del self._jobs[key]

    def close(self):
        with self._lock:
            self._closed = True
            jobs = list(self._jobs.values())
            for job in jobs:
                job['cancel'].set()
                job['discard'] = True
                self._discard(job)
        # Native calls are cooperative; do not deadlock a closing GUI loop.
        deadline = time.monotonic() + 5
        for job in jobs:
            job['worker'].join(max(0, deadline - time.monotonic()))
