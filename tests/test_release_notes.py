"""Sürüm notları: en üstteki sürüm uygulamanın sürümüdür; Studio açılışta notları alır."""

import re
from datetime import date

from fastapi.testclient import TestClient

from rpa_orkestrai import __version__
from rpa_orkestrai.app import create_app
from rpa_orkestrai.config import Settings
from rpa_orkestrai.release_notes import NOTES, SHOWN, recent


def number(version):
    return tuple(int(part) for part in version.split("."))


def test_every_release_says_what_it_brings_newest_first():
    assert NOTES[0]["version"] == __version__, "Yeni sürüm için release_notes.py en üstüne not ekleyin."
    versions = [number(item["version"]) for item in NOTES]
    assert versions == sorted(versions, reverse=True) and len(set(versions)) == len(versions)
    for item in NOTES:
        assert re.fullmatch(r"\d+\.\d+\.\d+", item["version"]) and date.fromisoformat(item["date"])
        assert item["items"] and all(isinstance(text, str) and text.strip() for text in item["items"])
    assert len(recent()) == min(SHOWN, len(NOTES))
    recent()[0]["items"].append("değişmez")
    assert "değişmez" not in NOTES[0]["items"]


def test_the_studio_receives_the_notes_at_start(tmp_path):
    with TestClient(create_app(Settings(tmp_path / "data", dotenv=False))) as client:
        notes = client.get("/api/bootstrap").json()["release_notes"]
    assert notes[0]["version"] == __version__ and notes[0]["items"] == NOTES[0]["items"]
