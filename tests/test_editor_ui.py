"""Opt-in browser checks: RPA_UI_TESTS=1 pytest tests/test_editor_ui.py.

Uses a temporary Studio workspace and a synthetic ERP image. Never captures or
controls the user's desktop. Requires the Playwright Chromium browser locally.
"""

import base64
import io
import json
import os
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("RPA_UI_TESTS") != "1", reason="Opt-in Chromium editor checks")


@pytest.mark.parametrize("viewport", [{"width": 1400, "height": 1000}, {"width": 980, "height": 720}])
def test_picker_coordinates_reference_offset_legacy_conversion_and_saved_loop(tmp_path, viewport):
    from fastapi.testclient import TestClient

    playwright = pytest.importorskip("playwright.sync_api")
    Image = pytest.importorskip("PIL.Image")
    ImageDraw = pytest.importorskip("PIL.ImageDraw")

    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    settings = Settings(tmp_path / "data", dotenv=False)
    templates = tmp_path / "templates"
    templates.mkdir()
    settings.update({"template_dir": str(templates)})
    screenshot = Image.new("RGB", (1000, 600), "#f4f5f8")
    draw = ImageDraw.Draw(screenshot)
    draw.rectangle((90, 90, 700, 190), fill="white", outline="#344454", width=3)
    draw.text((115, 120), "Form ID", fill="black")
    draw.rectangle((350, 110, 650, 170), outline="#455565", width=2)
    image_bytes = io.BytesIO()
    screenshot.save(image_bytes, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(image_bytes.getvalue()).decode()
    captures, crops, discarded, errors = [], [], [], []

    with TestClient(create_app(settings)) as client:
        response = client.post("/api/workflows", json={"name": "ERP satır denemesi", "steps": [
            {"id": "window", "action": "desktop.find_window", "params": {
                "application": "Test ERP", "title": "ERP – Form ID", "match": "exact", "output": "erp_window"}},
            {"id": "read", "action": "sheets.read_column", "params": {
                "spreadsheet_id": "test-sheet", "worksheet": "Sayfa1", "start_cell": "B2",
                "max_rows": 100, "empty_policy": "stop", "output": "sheet_rows"}},
            {"id": "loop", "action": "control.for_each", "params": {
                "items": "${sheet_rows}", "item_name": "row"}, "children": [
                    {"id": "fill", "action": "desktop.window_fill", "params": {
                        "window": "${erp_window}", "target_mode": "coordinates", "x": 50, "y": 70,
                        "text": "${row.value}", "clear": True}},
                ]},
            {"id": "legacy", "action": "desktop.window_write", "params": {
                "window": "${erp_window}", "text": "Mevcut değer"}},
            {"id": "legacy-loop", "action": "control.for_each", "params": {"items": "${sheet_rows}"}},
        ]})
        assert response.status_code == 201, response.text
        workflow_id = response.json()["id"]

        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch()
            page = browser.new_page(viewport=viewport)
            page.on("pageerror", lambda error: errors.append(str(error)))

            def handle(route):
                request = route.request
                path = urlsplit(request.url).path
                if path == "/api/desktop/capture-window":
                    captures.append(json.loads(request.post_data))
                    route.fulfill(json={"id": f"capture-{len(captures)}", "image": data_url,
                                        "width": 1000, "height": 600,
                                        "window": {"width": 1000, "height": 600}})
                elif path == "/api/desktop/templates":
                    crop = json.loads(request.post_data)
                    crops.append(crop)
                    assert crop["width"] >= 8 and crop["height"] >= 8
                    screenshot.crop((crop["x"], crop["y"], crop["x"] + crop["width"],
                                     crop["y"] + crop["height"])).save(templates / "captured-reference.png")
                    route.fulfill(status=201, json={"template": "captured-reference.png"})
                elif path.startswith("/api/desktop/captures/") and request.method == "DELETE":
                    discarded.append(path.rsplit("/", 1)[-1])
                    route.fulfill(status=204)
                else:
                    result = client.request(request.method, path, content=request.post_data_buffer,
                                            headers={"content-type": "application/json"})
                    route.fulfill(status=result.status_code, headers=dict(result.headers), body=result.content)

            page.route("http://127.0.0.1:8765/**", handle)
            page.goto("http://127.0.0.1:8765/")
            page.get_by_role("button", name="ERP satır denemesi", exact=True).click()
            page.locator('[data-step-id="legacy-loop"]').click()
            playwright.expect(page.get_by_label("Geçerli satır değişkeni", exact=False)).to_have_value("item")
            for name in ("item.value", "item.cell", "item.row_number"):
                playwright.expect(page.get_by_role("button", name="${" + name + "}", exact=True)).to_be_visible()
            page.locator('[data-step-id="loop"]').click()
            playwright.expect(page.get_by_label("Geçerli satır değişkeni", exact=False)).to_have_value("row")
            page.locator('[data-step-id="fill"]').click()
            playwright.expect(page.get_by_label("Pencere içi X", exact=False)).to_have_value("50")
            playwright.expect(page.get_by_label("Referans görsel", exact=False)).to_have_count(0)
            playwright.expect(page.get_by_role("button", name="${row.cell}", exact=True)).to_be_visible()
            playwright.expect(page.get_by_role("button", name="${row.row_number}", exact=True)).to_be_visible()

            def open_picker():
                page.get_by_role("button", name="ERP ekranından hedef seç", exact=True).click()
                canvas = page.locator(".target-picker-canvas")
                playwright.expect(canvas).to_be_visible()
                bounds = canvas.bounding_box()
                assert bounds["width"] > viewport["width"] * 0.7
                return bounds

            def position(bounds, x, y):
                return bounds["x"] + x * bounds["width"] / 1000, bounds["y"] + y * bounds["height"] / 600

            bounds = open_picker()
            page.mouse.click(*position(bounds, 230, 80))
            page.get_by_role("button", name="Hedefi kaydet", exact=True).click()
            playwright.expect(page.get_by_label("Pencere içi X", exact=False)).to_have_value("230")
            playwright.expect(page.get_by_label("Pencere içi Y", exact=False)).to_have_value("80")
            assert captures[-1] == {"application": "Test ERP", "title": "ERP – Form ID", "match": "exact"}

            page.get_by_label("Hedefi bulma yöntemi", exact=False).select_option("image")
            playwright.expect(page.get_by_label("Pencere içi X", exact=False)).to_have_count(0)
            bounds = open_picker()
            page.mouse.move(*position(bounds, 100, 100))
            page.mouse.down()
            page.mouse.move(*position(bounds, 301, 181), steps=4)
            page.mouse.up()
            page.mouse.click(*position(bounds, 420, 150))
            if os.environ.get("RPA_UI_SCREENSHOT"):
                page.screenshot(path=os.environ["RPA_UI_SCREENSHOT"])
            page.get_by_role("button", name="Hedefi kaydet", exact=True).click()
            playwright.expect(page.get_by_label("Referans görsel", exact=False)).to_have_value("captured-reference.png")
            playwright.expect(page.get_by_label("Görsel merkezinden sağa / sola", exact=True)).to_have_value("220")
            playwright.expect(page.get_by_label("Görsel merkezinden aşağı / yukarı", exact=True)).to_have_value("10")
            assert crops == [{"capture_id": "capture-2", "x": 100, "y": 100, "width": 201, "height": 81}]

            open_picker()
            page.keyboard.press("Escape")
            playwright.expect(page.locator("dialog")).to_have_count(0)
            page.wait_for_timeout(100)
            assert "capture-1" in discarded and "capture-3" in discarded

            page.locator('[data-step-id="legacy"]').click()
            page.get_by_role("button", name="Alanı doldur adımına dönüştür", exact=True).click()
            playwright.expect(page.get_by_label("Yazılacak değer", exact=False)).to_have_value("Mevcut değer")
            playwright.expect(page.get_by_label("Pencere içi X", exact=False)).to_have_value("")
            bounds = open_picker()
            page.mouse.click(*position(bounds, 420, 150))
            page.get_by_role("button", name="Hedefi kaydet", exact=True).click()
            page.get_by_role("button", name="Kaydet", exact=True).click()
            playwright.expect(page.locator("#saved-label")).to_contain_text("Tüm değişiklikler kaydedildi")
            saved = client.get(f"/api/workflows/{workflow_id}").json()
            fill = saved["steps"][2]["children"][0]
            assert fill["params"]["text"] == "${row.value}"
            assert fill["params"]["target_mode"] == "image"
            assert fill["params"]["offset_x"] == 220
            assert saved["steps"][3]["action"] == "desktop.window_fill"
            assert saved["steps"][3]["params"]["text"] == "Mevcut değer"
            assert "item_name" not in saved["steps"][4]["params"]
            # A reference to a missing recognizer disables capture without touching ERP.
            page.get_by_label("Pencere değişkeni", exact=False).fill("${missing_window}")
            playwright.expect(page.get_by_role("button", name="ERP ekranından hedef seç", exact=True)).to_be_disabled()
            page.locator(".library-action").filter(has_text="Her satır için").click()
            playwright.expect(page.get_by_label("Geçerli satır değişkeni", exact=False)).to_have_value("row")
            assert not errors, errors
            browser.close()
