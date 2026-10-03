"""Reference images travel inside an exported flow and come back on import, never overwriting a file."""

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import rpa_orkestrai
from rpa_orkestrai import models
from rpa_orkestrai.app import create_app
from rpa_orkestrai.config import Settings

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # the signature is what an import checks


def studio(data: Path, templates: Path) -> TestClient:
    settings = Settings(data, dotenv=False)
    settings.update({"template_dir": str(templates)})
    return TestClient(create_app(settings))


def encoded(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def click(step_id: str, template: str) -> dict:
    return {"id": step_id, "action": "screen.click_image", "params": {"template": template}}


def test_an_exported_flow_brings_its_reference_images(tmp_path):
    source = tmp_path / "a-templates"
    (source / "erp").mkdir(parents=True)
    (source / "capture-1.png").write_bytes(PNG + b"1")
    (source / "erp" / "kaydet.png").write_bytes(PNG + b"2")
    (source / "kullanilmayan.png").write_bytes(PNG + b"3")
    steps = [
        {"id": "wait", "action": "desktop.window_wait_image", "params": {"window": "${erp_window}",
                                                                          "template": "capture-1.png"}},
        {"id": "loop", "action": "control.repeat", "params": {"count": 2}, "children": [click("save", "erp/kaydet.png")]},
        click("gone", "silinmis.png"),
    ]
    with studio(tmp_path / "a", source) as client:
        workflow_id = client.post("/api/workflows", json={"name": "Görselli akış", "steps": steps}).json()["id"]
        exported = client.get(f"/api/workflows/{workflow_id}/export").json()
    # Only the images the steps use and that exist; a missing image is left to be picked again.
    assert set(exported["templates"]) == {"capture-1.png", "erp/kaydet.png"}

    target = tmp_path / "b-templates"
    with studio(tmp_path / "b", target) as client:
        response = client.post("/api/workflows/import", json=exported)
        assert response.status_code == 201, response.text
        imported = response.json()
        assert "templates" not in client.get(f"/api/workflows/{imported['id']}").json()
    assert (target / "capture-1.png").read_bytes() == PNG + b"1"
    assert (target / "erp" / "kaydet.png").read_bytes() == PNG + b"2"
    assert not (target / "kullanilmayan.png").exists()
    assert imported["steps"][0]["params"]["template"] == "capture-1.png"


def test_a_flow_without_images_exports_as_before(tmp_path):
    with studio(tmp_path / "data", tmp_path / "templates") as client:
        workflow_id = client.post("/api/workflows", json={"name": "Sade", "steps": [
            {"action": "core.log", "params": {"message": "Merhaba"}}]}).json()["id"]
        exported = client.get(f"/api/workflows/{workflow_id}/export").json()
        assert "templates" not in exported
        assert client.post("/api/workflows/import", json=exported).status_code == 201


def test_an_import_never_overwrites_an_image(tmp_path):
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "capture-1.png").write_bytes(PNG + b"bu bilgisayarin")
    (templates / "capture-2.png").write_bytes(PNG + b"ayni")
    flow = {"name": "Aktarılan", "steps": [click("a", "capture-1.png"), click("b", "capture-2.png")],
            "templates": {"capture-1.png": encoded(PNG + b"baska"), "capture-2.png": encoded(PNG + b"ayni")}}
    with studio(tmp_path / "data", templates) as client:
        response = client.post("/api/workflows/import", json=flow)
        assert response.status_code == 201, response.text
    # A different image with the same name is saved beside it and the step follows; the same image is reused.
    assert (templates / "capture-1.png").read_bytes() == PNG + b"bu bilgisayarin"
    assert (templates / "capture-1-2.png").read_bytes() == PNG + b"baska"
    assert [step["params"]["template"] for step in response.json()["steps"]] == ["capture-1-2.png", "capture-2.png"]
    assert sorted(path.name for path in templates.iterdir()) == ["capture-1-2.png", "capture-1.png", "capture-2.png"]


@pytest.mark.parametrize("name", ["../kacak.png", "/tmp/kacak.png", "erp\\kacak.png", ".gizli.png", "C:/kacak.png",
                                  "notlar.txt", "erp/../../kacak.png"])
def test_an_import_refuses_names_that_could_point_elsewhere(tmp_path, name):
    templates = tmp_path / "templates"
    flow = {"name": "Şüpheli", "steps": [click("a", name)], "templates": {name: encoded(PNG)}}
    with studio(tmp_path / "data", templates) as client:
        response = client.post("/api/workflows/import", json=flow)
        assert response.status_code == 422
        assert "adı geçersiz" in response.json()["detail"]
        assert client.get("/api/workflows").json() == []
    assert not list(tmp_path.rglob("kacak.png")) and not list(tmp_path.rglob(".gizli.png"))


@pytest.mark.parametrize("content", [encoded(b"MZ\x90\x00 bir program"), "bu base64 değil!"])
def test_an_import_refuses_what_is_not_an_image(tmp_path, content):
    templates = tmp_path / "templates"
    flow = {"name": "Şüpheli", "steps": [click("a", "capture.png")], "templates": {"capture.png": content}}
    with studio(tmp_path / "data", templates) as client:
        response = client.post("/api/workflows/import", json=flow)
        assert response.status_code == 422
        assert client.get("/api/workflows").json() == []
    assert not templates.exists() or not any(templates.iterdir())


def test_a_flow_file_with_images_may_be_larger_than_other_requests(tmp_path):
    big = PNG + bytes(2_500_000)
    flow = {"name": "Büyük görselli", "steps": [click("a", "buyuk.png")], "templates": {"buyuk.png": encoded(big)}}
    with studio(tmp_path / "data", tmp_path / "templates") as client:
        assert client.post("/api/workflows/import", json=flow).status_code == 201
        # Every other request keeps the 2 MB limit.
        response = client.post("/api/workflows", json={"name": "Büyük", "description": "x" * 2_100_000})
        assert response.status_code == 413
    assert (tmp_path / "templates" / "buyuk.png").stat().st_size == len(big)


def test_the_editor_refuses_the_nesting_the_server_refuses(tmp_path):
    source = (Path(rpa_orkestrai.__file__).parent / "static" / "app.js").read_text(encoding="utf-8")
    assert f"const MAX_DEPTH = {models.MAX_DEPTH};" in source

    def nested(levels: int) -> list[dict]:
        step = {"action": "core.log", "params": {"message": "en içte"}}
        for _ in range(levels - 1):
            step = {"action": "control.repeat", "params": {"count": 1}, "children": [step]}
        return [step]

    with studio(tmp_path / "data", tmp_path / "templates") as client:
        assert client.post("/api/workflows", json={"name": "Derin", "steps": nested(models.MAX_DEPTH)}).status_code == 201
        response = client.post("/api/workflows", json={"name": "Çok derin", "steps": nested(models.MAX_DEPTH + 1)})
        assert response.status_code == 422
        assert f"en fazla {models.MAX_DEPTH} seviyede" in response.text
