"""Notes on a flow: a titled frame around some of its steps, saved with the flow and ignored by runs."""

import json

import pytest
from pydantic import ValidationError

from rpa_orkestrai.models import WorkflowInput


def steps():
    return [
        {"id": "open", "action": "core.log", "params": {"message": "Aç"}},
        {"id": "loop", "action": "control.repeat", "params": {"count": 2}, "children": [
            {"id": "inside", "action": "core.log", "params": {"message": "Tur"}}]},
        {"id": "close", "action": "core.log", "params": {"message": "Kapat"}},
    ]


def test_notes_keep_only_steps_the_flow_has_and_go_with_their_last_step():
    flow = WorkflowInput(steps=steps(), notes=[
        {"id": "giris", "title": "Giriş", "text": "ERP açılır.", "color": "blue",
         "steps": ["open", "gone", "open", "inside"]},
        {"id": "eski", "title": "Silinen bölüm", "steps": ["gone"]},
    ])
    assert [(note.id, note.steps) for note in flow.notes] == [("giris", ["open", "inside"])]
    assert (flow.notes[0].title, flow.notes[0].text, flow.notes[0].color) == ("Giriş", "ERP açılır.", "blue")


@pytest.mark.parametrize("note", [
    {"color": "orange", "steps": ["open"]},
    {"title": "x" * 121, "steps": ["open"]},
    {"text": "x" * 4001, "steps": ["open"]},
    {"id": "../not", "steps": ["open"]},
    {"steps": ["open"], "author": "biri"},
])
def test_notes_have_bounded_fields(note):
    with pytest.raises(ValidationError):
        WorkflowInput(steps=steps(), notes=[note])


def test_a_flow_holds_at_most_one_hundred_notes():
    with pytest.raises(ValidationError):
        WorkflowInput(steps=steps(), notes=[{"steps": ["open"]}] * 101)


def test_notes_are_saved_exported_imported_and_ignored_by_runs(tmp_path):
    import time

    from fastapi.testclient import TestClient

    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    with TestClient(create_app(Settings(tmp_path / "data", dotenv=False))) as client:
        flow = client.post("/api/workflows", json={"name": "Notlu akış", "steps": steps()}).json()
        assert flow["notes"] == []
        # Without notes the exported file stays readable by Studios that do not know them.
        assert "notes" not in client.get(f"/api/workflows/{flow['id']}/export").json()
        note = {"id": "bolum", "title": "Tekrar bölümü", "text": "İki kez döner.\nSonra kapatır.", "color": "green",
                "steps": ["loop", "close"]}
        saved = client.put(f"/api/workflows/{flow['id']}", json={"name": flow["name"], "steps": steps(),
                                                                 "notes": [note]})
        assert saved.status_code == 200, saved.text
        assert client.get(f"/api/workflows/{flow['id']}").json()["notes"] == [note]
        exported = client.get(f"/api/workflows/{flow['id']}/export").json()
        assert exported["notes"] == [note]
        imported = client.post("/api/workflows/import", json=exported)
        assert imported.status_code == 201, imported.text
        assert imported.json()["notes"] == [note] and imported.json()["id"] != flow["id"]
        # Removing the steps of a note removes the note when the flow is saved.
        trimmed = client.put(f"/api/workflows/{flow['id']}", json={"name": flow["name"], "steps": steps()[:1],
                                                                   "notes": [note]}).json()
        assert trimmed["notes"] == []
        run = client.post(f"/api/workflows/{imported.json()['id']}/run", json={}).json()
        deadline = time.monotonic() + 10
        while run["status"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(0.05)
            run = client.get(f"/api/runs/{run['id']}").json()
        assert run["status"] == "succeeded", json.dumps(run["events"], ensure_ascii=False)
