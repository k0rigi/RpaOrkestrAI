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
    picks, sessions, discarded_sessions = [], {}, []
    native_plan = {"mode": "complete"}

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
            {"id": "wait-image", "action": "desktop.window_wait_image", "params": {"window": "${erp_window}"}},
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
                if path == "/api/desktop/pick/capabilities":
                    route.fulfill(json={"native": True})
                elif path == "/api/desktop/pick" and request.method == "POST":
                    payload = json.loads(request.post_data)
                    picks.append(payload)
                    pick_id = f"pick-{len(picks)}"
                    sessions[pick_id] = {"payload": payload, "polls": 0, "plan": native_plan["mode"]}
                    route.fulfill(status=202, json={"id": pick_id, "status": "starting"})
                elif path.startswith("/api/desktop/pick/"):
                    pick_id = path.rsplit("/", 1)[-1]
                    if request.method == "DELETE":
                        discarded_sessions.append(pick_id)
                        route.fulfill(status=204)
                    else:
                        session = sessions[pick_id]
                        session["polls"] += 1
                        if session["plan"] == "error":
                            route.fulfill(json={"id": pick_id, "status": "error", "message": "ERP penceresi taşındı. Yeniden seçin."})
                        elif session["polls"] == 1 or session["plan"] == "hold":
                            route.fulfill(json={"id": pick_id, "status": "countdown", "countdown": 3})
                        else:
                            mode = session["payload"]["mode"]
                            route.fulfill(json={"id": pick_id, "status": "completed", "result": {
                                "capture": {"id": f"native-{pick_id}", "image": data_url,
                                            "width": 1000, "height": 600,
                                            "window": {"width": 1000, "height": 600}},
                                "rectangle": None if mode == "coordinates" else {"x": 100, "y": 100, "width": 201, "height": 81},
                                "point": None if mode == "image_only" else {"x": 420, "y": 150},
                            }})
                elif path == "/api/desktop/capture-window":
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
                page.get_by_role("button", name="Görüntü üzerinde seç", exact=True).click()
                canvas = page.locator(".target-picker-canvas")
                playwright.expect(canvas).to_be_visible()
                bounds = canvas.bounding_box()
                assert bounds["width"] > viewport["width"] * 0.7
                save_bounds = page.get_by_role("button", name="Hedefi kaydet", exact=True).bounding_box()
                assert save_bounds["y"] + save_bounds["height"] <= viewport["height"] - 8
                return bounds

            def position(bounds, x, y):
                return bounds["x"] + x * bounds["width"] / 1000, bounds["y"] + y * bounds["height"] / 600

            bounds = open_picker()
            page.mouse.click(*position(bounds, 230, 80))
            page.get_by_role("button", name="Hedefi kaydet", exact=True).click()
            playwright.expect(page.get_by_label("Pencere içi X", exact=False)).to_have_value("230")
            playwright.expect(page.get_by_label("Pencere içi Y", exact=False)).to_have_value("80")
            assert captures[-1] == {"application": "Test ERP", "title": "ERP – Form ID", "match": "exact"}

            # Starting native selection requires confirmation, returns a review,
            # and only the explicit save changes the workflow's target.
            page.get_by_role("button", name="Ekranda seç", exact=True).click()
            playwright.expect(page.get_by_label("Hazırlık süresi", exact=True)).to_have_value("5")
            assert not picks
            page.get_by_label("Hazırlık süresi", exact=True).select_option("3")
            page.get_by_role("button", name="Tamam, geri sayımı başlat", exact=True).click()
            playwright.expect(page.get_by_role("button", name="Seçimi iptal et", exact=True)).to_be_visible()
            playwright.expect(page.locator(".target-picker-canvas")).to_be_visible()
            assert picks[-1] == {"application": "Test ERP", "title": "ERP – Form ID", "match": "exact", "mode": "coordinates", "delay": 3}
            assert page.get_by_label("Pencere içi X", exact=False).input_value() == "230"
            page.get_by_role("button", name="Hedefi kaydet", exact=True).click()
            playwright.expect(page.get_by_label("Pencere içi X", exact=False)).to_have_value("420")
            playwright.expect(page.get_by_label("Pencere içi Y", exact=False)).to_have_value("150")

            native_plan["mode"] = "hold"
            page.get_by_role("button", name="Ekranda seç", exact=True).click()
            page.get_by_role("button", name="Tamam, geri sayımı başlat", exact=True).click()
            playwright.expect(page.get_by_role("button", name="Seçimi iptal et", exact=True)).to_be_visible()
            page.get_by_role("button", name="Seçimi iptal et", exact=True).click()
            playwright.expect(page.locator(".target-picker-status")).to_contain_text("Seçim iptal edildi")
            page.keyboard.press("Escape")
            playwright.expect(page.get_by_label("Pencere içi X", exact=False)).to_have_value("420")
            native_plan["mode"] = "complete"

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

            page.get_by_role("button", name="Ekranda seç", exact=True).click()
            page.get_by_role("button", name="Tamam, geri sayımı başlat", exact=True).click()
            playwright.expect(page.locator(".target-picker-canvas")).to_be_visible()
            assert picks[-1]["mode"] == "image"
            assert len(crops) == 1  # Preview has not persisted a template.
            page.get_by_role("button", name="Hedefi kaydet", exact=True).click()
            playwright.expect(page.get_by_label("Görsel merkezinden sağa / sola", exact=True)).to_have_value("220")
            assert crops[-1] == {"capture_id": "native-pick-3", "x": 100, "y": 100, "width": 201, "height": 81}

            open_picker()
            page.keyboard.press("Escape")
            playwright.expect(page.locator("dialog")).to_have_count(0)
            page.wait_for_timeout(100)
            assert "capture-1" in discarded and "capture-3" in discarded

            native_plan["mode"] = "error"
            page.get_by_role("button", name="Ekranda seç", exact=True).click()
            page.get_by_role("button", name="Tamam, geri sayımı başlat", exact=True).click()
            playwright.expect(page.locator(".target-picker-status")).to_contain_text("ERP penceresi taşındı")
            playwright.expect(page.get_by_role("button", name="Tamam, geri sayımı başlat", exact=True)).to_be_enabled()
            page.keyboard.press("Escape")
            playwright.expect(page.get_by_label("Görsel merkezinden sağa / sola", exact=True)).to_have_value("220")
            native_plan["mode"] = "hold"
            page.get_by_role("button", name="Ekranda seç", exact=True).click()
            page.get_by_role("button", name="Tamam, geri sayımı başlat", exact=True).click()
            playwright.expect(page.get_by_role("button", name="Seçimi iptal et", exact=True)).to_be_visible()
            page.keyboard.press("Escape")
            playwright.expect(page.locator("dialog")).to_have_count(0)

            native_plan["mode"] = "complete"
            page.locator('[data-step-id="wait-image"]').click()
            page.get_by_role("button", name="Ekranda seç", exact=True).click()
            page.get_by_role("button", name="Tamam, geri sayımı başlat", exact=True).click()
            playwright.expect(page.locator(".target-picker-canvas")).to_be_visible()
            assert picks[-1]["mode"] == "image_only"
            page.get_by_role("button", name="Hedefi kaydet", exact=True).click()
            playwright.expect(page.get_by_label("Referans görsel", exact=False)).to_have_value("captured-reference.png")
            playwright.expect(page.get_by_label("Görsel merkezinden sağa / sola", exact=True)).to_have_count(0)

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
            assert saved["steps"][5]["params"]["template"] == "captured-reference.png"
            # A reference to a missing recognizer disables capture without touching ERP.
            page.get_by_label("Pencere değişkeni", exact=False).fill("${missing_window}")
            playwright.expect(page.get_by_role("button", name="Görüntü üzerinde seç", exact=True)).to_be_disabled()
            playwright.expect(page.get_by_role("button", name="Ekranda seç", exact=True)).to_be_disabled()
            page.locator(".library-action").filter(has_text="Her satır için").click()
            playwright.expect(page.get_by_label("Geçerli satır değişkeni", exact=False)).to_have_value("row")
            assert not errors, errors
            assert {f"pick-{number}" for number in range(1, 7)}.issubset(discarded_sessions)
            browser.close()


def test_named_sheet_columns_and_nested_conditions_can_be_edited_without_json(tmp_path):
    from fastapi.testclient import TestClient

    playwright = pytest.importorskip("playwright.sync_api")
    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    errors = []
    with TestClient(create_app(Settings(tmp_path / "data", dotenv=False))) as client:
        response = client.post("/api/workflows", json={"name": "Duruma göre işlem", "steps": [
            {"id": "window", "action": "desktop.find_window", "params": {
                "application": "Test ERP", "title": "ERP – Form ID", "output": "erp_window"}},
            {"id": "rows", "action": "sheets.read_rows", "params": {
                "spreadsheet_id": "test-sheet", "worksheet": "Sayfa1", "start_row": 2,
                "columns": {"form_id": "B", "status": "C"}, "key": "form_id", "output": "sheet_rows"}},
            {"id": "loop", "action": "control.for_each", "params": {
                "items": "${sheet_rows}", "item_name": "row"}},
        ]})
        assert response.status_code == 201, response.text
        workflow_id = response.json()["id"]
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))

            def handle(route):
                request = route.request
                path = urlsplit(request.url).path
                if path == "/api/desktop/pick/capabilities":
                    route.fulfill(json={"native": False})
                    return
                result = client.request(request.method, path, content=request.post_data_buffer,
                                        headers={"content-type": "application/json"})
                route.fulfill(status=result.status_code, headers=dict(result.headers), body=result.content)

            page.route("http://127.0.0.1:8765/**", handle)
            page.goto("http://127.0.0.1:8765/")
            page.get_by_role("button", name="Duruma göre işlem", exact=True).click()
            page.locator('[data-step-id="rows"]').click()
            playwright.expect(page.get_by_label("Alan adı 1", exact=True)).to_have_value("form_id")
            playwright.expect(page.get_by_label("Sütun 1", exact=True)).to_have_value("B")
            playwright.expect(page.get_by_label("Alan adı 2", exact=True)).to_have_value("status")
            playwright.expect(page.locator(".column-mapping-field textarea")).to_have_count(0)
            page.get_by_label("Alan adı 2", exact=True).fill("form_id")
            playwright.expect(page.locator(".column-mapping-field .field-error")).to_contain_text("farklı")
            page.locator('[data-step-id="loop"]').click()
            page.locator('[data-step-id="rows"]').click()
            playwright.expect(page.get_by_label("Alan adı 2", exact=True)).to_have_value("form_id")
            page.get_by_label("Alan adı 2", exact=True).fill("status")
            page.get_by_role("button", name="Sütun ekle", exact=True).click()
            page.get_by_label("Alan adı 3", exact=True).fill("quantity")
            page.get_by_label("Sütun 3", exact=True).fill("D")
            playwright.expect(page.locator(".column-mapping-field .field-error")).to_be_empty()

            page.locator('[data-step-id="loop"]').click()
            for name in ("row.form_id", "row.status", "row.quantity", "row.row_number"):
                playwright.expect(page.get_by_role("button", name="${" + name + "}", exact=True)).to_be_visible()
            playwright.expect(page.get_by_role("button", name="${row.value}", exact=True)).to_have_count(0)
            page.get_by_role("button", name="Her satırda yapılacak adımı ekle", exact=True).click()
            page.locator(".library-action").filter(has_text="Koşul sürdükçe tekrarla").click()
            playwright.expect(page.get_by_role("button", name="Her tekrarda yapılacak adımı ekle", exact=True)).to_be_visible()
            playwright.expect(page.locator(".branch-heading").filter(has_text="KOŞUL SÜRDÜKÇE")).to_be_visible()
            page.get_by_role("button", name="Her tekrarda yapılacak adımı ekle", exact=True).click()
            page.locator(".library-action").filter(has_text="Alanı doldur").click()
            playwright.expect(page.get_by_label("Yazılacak değer", exact=False)).to_have_value("${row.form_id}")
            playwright.expect(page.get_by_role("button", name="Ekranda seç", exact=True)).to_be_disabled()
            playwright.expect(page.get_by_role("button", name="Görüntü üzerinde seç", exact=True)).to_be_enabled()

            page.locator('[data-step-id="loop"]').click()
            page.get_by_role("button", name="Her satırda yapılacak adımı ekle", exact=True).click()
            page.locator(".library-action").filter(has_text="Koşul").filter(has_not_text="sürdükçe").click()
            page.get_by_label("Sol değer", exact=True).fill("${row.status}")
            page.get_by_label("Karşılaştırma", exact=False).select_option("empty")
            playwright.expect(page.get_by_label("Sağ değer", exact=True)).to_have_count(0)
            page.get_by_label("Karşılaştırma", exact=False).select_option("empty_or_eq")
            page.get_by_label("Sağ değer değer türü", exact=True).select_option("text")
            page.get_by_label("Sağ değer", exact=True).fill("Bekliyor")
            page.get_by_role("button", name="Kaydet", exact=True).click()
            playwright.expect(page.locator("#saved-label")).to_contain_text("Tüm değişiklikler kaydedildi")
            saved = client.get(f"/api/workflows/{workflow_id}").json()
            assert saved["steps"][1]["params"]["columns"] == {"form_id": "B", "status": "C", "quantity": "D"}
            loop = saved["steps"][2]
            assert loop["children"][0]["action"] == "control.while"
            assert loop["children"][0]["children"][0]["params"]["text"] == "${row.form_id}"
            assert loop["children"][1]["action"] == "control.if"
            assert loop["children"][1]["params"] == {"left": "${row.status}", "operator": "empty_or_eq", "right": "Bekliyor"}
            assert not errors, errors
            browser.close()
