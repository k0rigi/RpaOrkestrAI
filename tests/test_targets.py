import io
import threading
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from rpa_orkestrai.app import create_app
from rpa_orkestrai.config import Settings
from rpa_orkestrai.desktop.targets import CaptureStore
from rpa_orkestrai.desktop.windows import WindowError, WindowInfo


def capture():
    window = WindowInfo(12, 42, "ERP", "İade", 100, 80, 200, 150)
    image = Image.new("RGB", (200, 150), "white")
    ImageDraw.Draw(image).rectangle((20, 20, 29, 39), fill="black")
    return window, image


def test_only_selected_crop_is_saved_and_capture_cannot_be_reused(tmp_path):
    store = CaptureStore()
    selected = store.add(*capture())
    assert list(tmp_path.iterdir()) == []
    result = store.crop(selected["id"], 20, 20, 20, 20, tmp_path)
    assert list(p.name for p in tmp_path.iterdir()) == [result["template"]]
    with Image.open(tmp_path / result["template"]) as image:
        assert image.size == (20, 20)
        assert image.getpixel((0, 0)) == (0, 0, 0)
        assert image.getpixel((19, 19)) == (255, 255, 255)
    with pytest.raises(WindowError, match="süresi doldu"):
        store.crop(selected["id"], 20, 20, 20, 20, tmp_path)


@pytest.mark.parametrize("rect", [(-1, 0, 20, 20), (0, 0, 400, 200), (0, 0, 4, 4), (20.5, 20, 20, 20)])
def test_crop_bounds_and_flat_templates_rejected_without_files(tmp_path, rect):
    store = CaptureStore()
    selected = store.add(*capture())
    with pytest.raises(WindowError):
        store.crop(selected["id"], *rect, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_flat_crop_and_expired_or_discarded_capture_are_not_saved(tmp_path, monkeypatch):
    clock = Mock(return_value=0)
    monkeypatch.setattr("rpa_orkestrai.desktop.targets.time.monotonic", clock)
    store = CaptureStore(ttl=1)
    selected = store.add(*capture())
    with pytest.raises(WindowError, match="ayırt edilebilir"):
        store.crop(selected["id"], 80, 80, 20, 20, tmp_path)
    clock.return_value = 2
    with pytest.raises(WindowError, match="süresi doldu"):
        store.crop(selected["id"], 20, 20, 20, 20, tmp_path)
    other = store.add(*capture())
    store.discard(other["id"])
    with pytest.raises(WindowError):
        store.crop(other["id"], 20, 20, 20, 20, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_capture_api_is_explicit_same_origin_and_blocked_during_run(tmp_path, monkeypatch):
    import base64

    window, image = capture()
    previous = WindowInfo(13, 43, "Studio", "Studio", 0, 0, 200, 150)
    windows = Mock()
    windows.list_windows.return_value = [previous, window]
    windows.backend.is_active.side_effect = lambda w: w == previous
    windows.find.return_value = window.result()
    windows.screenshot_window.return_value = (window, image)
    monkeypatch.setattr("rpa_orkestrai.desktop.windows.WindowService", Mock(return_value=windows))
    settings = Settings(tmp_path / "data", dotenv=False)
    settings.update({"template_dir": str(tmp_path / "templates")})
    body = {"application": "ERP", "title": "İade", "match": "exact"}
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/desktop/capture-window", json=body,
                           headers={"origin": "https://evil.example"}).status_code == 403
        windows.screenshot_window.assert_not_called()
        manager = client.app.state.manager
        manager._active = ("test", threading.Event())
        assert client.post("/api/desktop/capture-window", json=body).status_code == 409
        manager._active = None
        result = client.post("/api/desktop/capture-window", json=body)
        assert result.status_code == 200
        data = result.json()
        windows.focus.assert_called_once_with(previous.result())
        with Image.open(io.BytesIO(base64.b64decode(data["image"].split(",", 1)[1]))) as picture:
            assert picture.size == (data["width"], data["height"]) == (200, 150)
        crop = {"capture_id": data["id"], "x": 20, "y": 20, "width": 20, "height": 20}
        assert client.post("/api/desktop/templates", json={**crop, "x": 1.5}).status_code == 422
        assert client.post("/api/desktop/templates", json=crop,
                           headers={"origin": "https://evil.example"}).status_code == 403
        saved = client.post("/api/desktop/templates", json=crop)
        assert saved.status_code == 201
        assert (tmp_path / "templates" / saved.json()["template"]).exists()
        assert client.get("/api/runs").json() == []


def test_table_inspection_guards_stale_window_origin_and_running_flow(tmp_path, monkeypatch):
    window, _ = capture()
    previous = WindowInfo(13, 43, "Studio", "Studio", 0, 0, 200, 150)
    windows = Mock()
    windows.list_windows.return_value = [previous, window]
    windows.backend.is_active.side_effect = lambda item: item == previous
    windows.find.return_value = window.result()
    windows.current.return_value = window
    windows.inspect_table.return_value = {"rows": 12, "columns": ["Code", "Status"]}
    monkeypatch.setattr("rpa_orkestrai.desktop.windows.WindowService", Mock(return_value=windows))
    body = {"title": window.title, "x": 35, "y": 50, "window_id": window.window_id, "pid": window.pid,
            "width": window.width, "height": window.height}
    with TestClient(create_app(Settings(tmp_path / "data", dotenv=False))) as client:
        endpoint = "/api/desktop/inspect-table"
        assert client.post(endpoint, json=body, headers={"origin": "https://evil.example"}).status_code == 403
        manager = client.app.state.manager
        manager._active = ("test", threading.Event())
        assert client.post(endpoint, json=body).status_code == 409
        manager._active = None
        for changed in ({"window_id": 999}, {"pid": 999}, {"width": 999}, {"x": -1}, {"header_row": 0}, {"header_row": 1.5}):
            assert client.post(endpoint, json={**body, **changed}).status_code == 422
        windows.inspect_table.assert_not_called()
        result = client.post(endpoint, json=body)
        assert result.status_code == 200 and result.json() == windows.inspect_table.return_value
        assert windows.inspect_table.call_args.kwargs == {"x": 35, "y": 50, "header": True, "header_row": 1}
        windows.focus.assert_called_once_with(previous.result())
