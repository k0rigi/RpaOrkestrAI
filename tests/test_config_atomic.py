"""Atomic JSON writes preserve existing data and isolate concurrent writers."""

import json
import os
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from rpa_orkestrai.config import atomic_json


def test_overlapping_writers_have_independent_files_and_leave_complete_json(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    atomic_json(path, {"previous": True})
    barrier = threading.Barrier(2)
    original_dump = json.dump
    originals = [{"writer": index, "text": "Çağrı" * 5000} for index in range(2)]

    def overlapping_dump(value, stream, **kwargs):
        original_dump(value, stream, **kwargs)
        stream.flush()
        # Both writes are open at once. A shared *.tmp file fails on Windows
        # or is replaced by one writer while the other is still using it.
        barrier.wait(timeout=3)

    monkeypatch.setattr(json, "dump", overlapping_dump)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda value: atomic_json(path, value), originals))
    assert json.loads(path.read_text(encoding="utf-8")) in originals
    assert list(tmp_path.iterdir()) == [path]
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("value", [{"bad": object()}, {"bad": float("nan")}])
def test_serialization_failure_keeps_previous_data_and_removes_private_temporary(tmp_path, value):
    path = tmp_path / "settings.json"
    previous = {"saved": "Korunmalı"}
    atomic_json(path, previous)
    with pytest.raises((TypeError, ValueError)):
        atomic_json(path, value)
    assert json.loads(path.read_text(encoding="utf-8")) == previous
    assert list(tmp_path.iterdir()) == [path]


def test_replace_failure_keeps_previous_file_and_cleans_temporary(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    atomic_json(path, {"previous": True})

    def locked(_temporary, target):
        assert target == path
        raise PermissionError("Kilitli dosya")

    monkeypatch.setattr(Path, "replace", locked)
    with pytest.raises(PermissionError):
        atomic_json(path, {"replacement": True})
    assert json.loads(path.read_text(encoding="utf-8")) == {"previous": True}
    assert list(tmp_path.iterdir()) == [path]


def test_old_predictable_temporary_is_not_opened_or_overwritten(tmp_path):
    path = tmp_path / "settings.json"
    legacy = path.with_suffix(".tmp")
    legacy.write_text("Başka işlem", encoding="utf-8")
    atomic_json(path, {"new": True})
    assert legacy.read_text(encoding="utf-8") == "Başka işlem"
    assert json.loads(path.read_text(encoding="utf-8")) == {"new": True}
