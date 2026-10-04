"""Opt-in browser checks: RPA_UI_TESTS=1 pytest tests/test_editor_ui.py.

Uses a temporary Studio workspace and a synthetic ERP image. Never captures or
controls the user's desktop. Requires the Playwright Chromium browser locally.
"""

import base64
import io
import json
import os
import re
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
            # The screenshot is shown scaled down, so a mouse position maps to the image within one pixel.
            assert len(crops) == 1 and crops[0]["capture_id"] == "capture-2"
            assert all(abs(crops[0][key] - value) <= 1
                       for key, value in {"x": 100, "y": 100, "width": 201, "height": 81}.items())

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
            # (The window is chosen from a list; typing a name that no step gives is still possible.)
            page.locator("#inspector .window-reference select").select_option("__manual__")
            page.locator("#inspector .window-reference input").fill("${missing_window}")
            playwright.expect(page.locator("#inspector .window-reference-state")).to_contain_text("bu adımdan önce yok")
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


def test_drag_drop_library_search_and_single_step_test(tmp_path):
    from fastapi.testclient import TestClient

    playwright = pytest.importorskip("playwright.sync_api")
    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    errors = []
    with TestClient(create_app(Settings(tmp_path / "data", dotenv=False))) as client:
        response = client.post("/api/workflows", json={"name": "Sürükle bırak", "steps": [
            {"id": "count", "action": "core.set", "title": "Sayaç", "params": {"name": "sayac", "value": 1}},
            {"id": "loop", "action": "control.repeat", "title": "Üç kez", "params": {"count": 3}},
            {"id": "calc", "action": "data.calculate", "title": "Artır",
             "params": {"expression": "${sayac} + adet", "output": "sonuc"}},
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
                result = client.request(request.method, path, content=request.post_data_buffer,
                                        headers={"content-type": "application/json"})
                route.fulfill(status=result.status_code, headers=dict(result.headers), body=result.content)

            page.route("http://127.0.0.1:8765/**", handle)
            page.goto("http://127.0.0.1:8765/")
            page.get_by_role("button", name="Sürükle bırak", exact=True).click()
            playwright.expect(page.get_by_label("Önizleme (ekranı kullanmadan)")).not_to_be_checked()

            # Move the calculation into the repeat block by dragging it onto the empty branch.
            page.locator('[data-step-id="calc"]').drag_to(page.locator(".branch-placeholder").first)
            playwright.expect(page.locator('.branch [data-step-id="calc"]')).to_have_count(1)
            # Reorder: drag the counter below the loop block.
            page.locator('[data-step-id="count"]').drag_to(page.locator(".canvas-add"))
            order = page.locator(".flow-stack > .step-wrap > .step-card").evaluate_all(
                "cards => cards.map(card => card.dataset.stepId)")
            assert order == ["loop", "count"]
            # A step cannot be dropped into its own block.
            page.locator('[data-step-id="loop"]').drag_to(page.locator('.branch [data-step-id="calc"]'))
            playwright.expect(page.locator(".toast.error")).to_contain_text("kendi içine")

            # Library search and dragging a new step into the canvas.
            page.get_by_label("Adım ara").fill("excel oku")
            playwright.expect(page.locator(".library-row:visible").filter(has_text="Excel / CSV oku")).to_have_count(1)
            playwright.expect(page.locator(".library-row:visible").filter(has_text="Tuşa bas")).to_have_count(0)
            page.get_by_label("Adım ara").fill("")
            page.locator(".library-action").filter(has_text="Metin işlemi").drag_to(page.locator(".canvas-add"))
            playwright.expect(page.locator(".flow-stack > .step-wrap > .step-card")).to_have_count(3)

            # Save, then test only the calculation with a sample value.
            page.get_by_role("button", name="Kaydet", exact=True).click()
            playwright.expect(page.locator("#saved-label")).to_contain_text("kaydedildi")
            page.locator('[data-step-id="calc"]').click()
            page.get_by_role("button", name="Bu adımı test et", exact=True).click()
            dialog = page.locator("dialog.step-test-dialog")
            # Nothing before this step gives these names: the dialog says so, and a value can still be typed.
            playwright.expect(dialog).to_contain_text("${sayac} adını veren bir adım bu adımdan önce yok")
            dialog.locator(".step-test-missing summary").click()
            playwright.expect(dialog.get_by_label("${sayac}")).to_be_visible()
            dialog.get_by_label("${sayac}").fill("40")
            dialog.get_by_label("${adet}").fill("2")
            dialog.get_by_role("button", name="Testi çalıştır", exact=True).click()
            playwright.expect(dialog.locator(".step-test-values")).to_contain_text("42")
            playwright.expect(dialog.locator(".step-test-head")).to_contain_text("Tamamlandı")
            browser.close()
        saved = client.get(f"/api/workflows/{workflow_id}").json()
        assert [step["id"] for step in saved["steps"][0]["children"]] == ["calc"]
    assert not errors


def test_steps_are_not_placed_deeper_than_the_server_accepts(tmp_path):
    from fastapi.testclient import TestClient

    playwright = pytest.importorskip("playwright.sync_api")
    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings
    from rpa_orkestrai.models import MAX_DEPTH

    def chain(level):
        # Repeat blocks nested MAX_DEPTH deep; the deepest block is still empty.
        step = {"id": f"r{level}", "action": "control.repeat", "title": f"Seviye {level}", "params": {"count": 1}}
        if level < MAX_DEPTH:
            step["children"] = [chain(level + 1)]
        return step

    errors = []
    with TestClient(create_app(Settings(tmp_path / "data", dotenv=False))) as client:
        response = client.post("/api/workflows", json={"name": "Derin akış", "steps": [chain(1)]})
        assert response.status_code == 201, response.text
        workflow_id = response.json()["id"]
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))

            def handle(route):
                request = route.request
                path = urlsplit(request.url).path
                result = client.request(request.method, path, content=request.post_data_buffer,
                                        headers={"content-type": "application/json"})
                route.fulfill(status=result.status_code, headers=dict(result.headers), body=result.content)

            page.route("http://127.0.0.1:8765/**", handle)
            page.goto("http://127.0.0.1:8765/")
            page.get_by_role("button", name="Derin akış", exact=True).click()
            headings = page.locator(".branch-heading")
            playwright.expect(headings).to_have_count(MAX_DEPTH)
            note = page.locator(".library-action").filter(has_text="Çalışma notu").first

            # Inside the deepest block a step would be one level too deep: added from the library…
            headings.nth(MAX_DEPTH - 1).get_by_role("button", name="Adım ekle").click()
            note.click()
            playwright.expect(page.locator(".toast.error").last).to_contain_text(f"en fazla {MAX_DEPTH} seviye")
            # …or dropped onto the empty branch.
            note.drag_to(page.locator(".branch-placeholder"))
            playwright.expect(page.locator(".branch.empty-branch")).to_have_count(1)
            # One level up the step fits, and the flow saves.
            headings.nth(MAX_DEPTH - 2).get_by_role("button", name="Adım ekle").click()
            note.click()
            playwright.expect(page.locator(".step-card", has_text="Çalışma notu")).to_have_count(1)
            page.get_by_role("button", name="Kaydet", exact=True).click()
            playwright.expect(page.locator("#saved-label")).to_contain_text("kaydedildi")
            browser.close()
        saved = client.get(f"/api/workflows/{workflow_id}").json()
        inner = saved["steps"][0]
        for _ in range(MAX_DEPTH - 2):
            inner = inner["children"][0]
        assert [step["action"] for step in inner["children"]] == ["control.repeat", "core.log"]
    assert not errors


def test_recorded_movements_become_steps(tmp_path):
    import threading
    import time

    from fastapi.testclient import TestClient

    playwright = pytest.importorskip("playwright.sync_api")
    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings
    from rpa_orkestrai.desktop.recorder import Event

    class Source:
        def start(self, events, stop, clock):
            now = clock()
            for event in (Event("mouse_down", now, 300, 200), Event("mouse_up", now + 0.05, 300, 200),
                          Event("key", now + 0.1, key="i", text="İ"), Event("key", now + 0.2, key="enter")):
                events.put(event)
            threading.Thread(target=lambda: (time.sleep(0.4), stop.set()), daemon=True).start()

        def stop(self):
            pass

    errors = []
    with TestClient(create_app(Settings(tmp_path / "data", dotenv=False))) as client:
        records = client.app.state.records
        records.permissions, records.source_factory, records.windows_factory = (lambda: None), Source, None
        records.view_factory = None
        workflow_id = client.post("/api/workflows", json={"name": "Kayıt", "steps": []}).json()["id"]
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch()
            page = browser.new_page(viewport={"width": 980, "height": 720})
            page.on("pageerror", lambda error: errors.append(str(error)))

            def handle(route):
                request = route.request
                result = client.request(request.method, urlsplit(request.url).path, content=request.post_data_buffer,
                                        headers={"content-type": "application/json"})
                route.fulfill(status=result.status_code, headers=dict(result.headers), body=result.content)

            page.route("http://127.0.0.1:8765/**", handle)
            page.goto("http://127.0.0.1:8765/")
            page.get_by_role("button", name="Kayıt", exact=True).click()
            page.get_by_role("button", name="Hareketleri kaydet", exact=True).click()
            dialog = page.locator("dialog.record-dialog")
            dialog.get_by_label("Hazırlık süresi").select_option("3")
            dialog.get_by_role("button", name="Kaydı başlat", exact=True).click()
            playwright.expect(dialog.locator(".record-steps li")).to_have_count(3, timeout=15000)
            dialog.locator(".record-steps input").nth(2).uncheck()
            dialog.get_by_role("button", name="Akışa ekle", exact=True).click()
            playwright.expect(page.locator(".flow-stack > .step-wrap > .step-card")).to_have_count(2)
            page.get_by_role("button", name="Kaydet", exact=True).click()
            playwright.expect(page.locator("#saved-label")).to_contain_text("kaydedildi")
            browser.close()
        saved = client.get(f"/api/workflows/{workflow_id}").json()
        assert [step["action"] for step in saved["steps"]] == ["input.mouse_click", "input.type"]
        assert saved["steps"][1]["params"]["text"] == "İ"
    assert not errors


def test_connections_are_created_and_chosen_inside_the_step(tmp_path):
    from fastapi.testclient import TestClient

    playwright = pytest.importorskip("playwright.sync_api")
    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    errors, shots = [], os.environ.get("RPA_UI_SHOTS")
    url = "https://script.google.com/macros/s/AKfycb" + "u" * 40 + "/exec"
    with TestClient(create_app(Settings(tmp_path / "data", dotenv=False))) as client:
        response = client.post("/api/workflows", json={"name": "Bağlantılı akış", "steps": [
            {"id": "write", "action": "sheets.write_cell", "params": {
                "spreadsheet_id": "sheet-id", "worksheet": "Sayfa1", "cell": "B2", "value": "Tamam"}},
            {"id": "db", "action": "database.read", "params": {"table": "public.A"}},
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
                result = client.request(request.method, path, content=request.post_data_buffer,
                                        headers={"content-type": "application/json"})
                route.fulfill(status=result.status_code, headers=dict(result.headers), body=result.content)

            page.route("http://127.0.0.1:8765/**", handle)
            page.goto("http://127.0.0.1:8765/")
            # Settings no longer hold Sheets or database fields.
            page.get_by_role("button", name="Ayarlar").first.click()
            playwright.expect(page.get_by_text("Web uygulaması adresi")).to_have_count(0)
            playwright.expect(page.get_by_role("button", name="Bağlantıları yönet")).to_be_visible()
            page.goto("http://127.0.0.1:8765/")
            page.get_by_role("button", name="Bağlantılı akış", exact=True).click()
            page.locator('[data-step-id="write"]').click()
            inspector = page.locator("#inspector")
            playwright.expect(inspector.locator(".connection-field")).to_contain_text("bağlantısı gerekir")

            # Create a Sheets connection from inside the step; showing the code saves it first.
            inspector.get_by_role("button", name="Google Sheets bağlantısı oluştur").click()
            dialog = page.locator("dialog.connection-dialog")
            dialog.get_by_label("Bağlantı adı").fill("Satış tablosu")
            dialog.get_by_role("button", name="Apps Script kodunu göster").click()
            playwright.expect(dialog.get_by_label("Apps Script kodu")).to_have_value(re.compile("const RPA_TOKEN"))
            token = dialog.get_by_label("Apps Script kodu").input_value().split('RPA_TOKEN = "')[1].split('"')[0]
            dialog.get_by_label("Web uygulaması adresi").fill(url)
            if shots:
                page.screenshot(path=f"{shots}/connection-dialog.png")
            dialog.get_by_role("button", name="Kaydet", exact=True).click()
            playwright.expect(dialog).to_have_count(0)
            playwright.expect(inspector.locator(".connection-meta")).to_contain_text("Hazır")
            select = inspector.locator(".connection-field select")
            profile = client.get("/api/connections").json()[0]
            assert select.input_value() == profile["id"] and profile["name"] == "Satış tablosu"

            # A second connection is offered in the same list; the database step has its own type.
            select.select_option("__new__")
            dialog.get_by_label("Bağlantı adı").fill("İade tablosu")
            dialog.get_by_role("button", name="Bağlantıyı oluştur").click()
            playwright.expect(dialog).to_have_count(0)
            options = select.locator("option").all_inner_texts()
            assert any("İade tablosu" in text and "eksik" in text for text in options)
            playwright.expect(inspector.locator(".connection-meta")).to_contain_text("Ayarları eksik")
            select.select_option(profile["id"])
            playwright.expect(inspector.locator(".connection-meta")).to_contain_text("Hazır")
            page.locator('[data-step-id="db"]').click()
            db_options = inspector.locator(".connection-field select option").all_inner_texts()
            assert not any("tablosu" in text for text in db_options)
            if shots:
                page.screenshot(path=f"{shots}/connection-step.png")

            # The manager lists both; the workflow stores only the connection id.
            page.get_by_role("button", name="Bağlantılar", exact=True).click()
            manager = page.locator("dialog.connection-manager")
            playwright.expect(manager.locator(".connection-item")).to_have_count(2)
            playwright.expect(manager).to_contain_text("bu akışta 1 adım")
            if shots:
                page.screenshot(path=f"{shots}/connection-manager.png")
            manager.get_by_role("button", name="Kapat").click()
            page.get_by_role("button", name="Kaydet", exact=True).click()
            playwright.expect(page.locator("#saved-label")).to_contain_text("kaydedildi")
            browser.close()
        saved = client.get(f"/api/workflows/{workflow_id}").json()
        assert saved["steps"][0]["params"]["connection"] == profile["id"]
        exported = client.get(f"/api/workflows/{workflow_id}/export").text
        assert token not in exported and url not in exported
    assert not errors


def test_the_connection_manager_offers_database_only_where_an_old_step_uses_it(tmp_path):
    from fastapi.testclient import TestClient

    playwright = pytest.importorskip("playwright.sync_api")
    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    errors = []
    with TestClient(create_app(Settings(tmp_path / "data", dotenv=False))) as client:
        for name, steps in (("Sheets akışı", [{"id": "write", "action": "sheets.write_cell", "params": {}}]),
                            ("Eski veritabanı akışı", [{"id": "db", "action": "database.read",
                                                        "params": {"table": "public.A"}}])):
            assert client.post("/api/workflows", json={"name": name, "steps": steps}).status_code == 201
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))

            def handle(route):
                request = route.request
                path = urlsplit(request.url).path
                result = client.request(request.method, path, content=request.post_data_buffer,
                                        headers={"content-type": "application/json"})
                route.fulfill(status=result.status_code, headers=dict(result.headers), body=result.content)

            page.route("http://127.0.0.1:8765/**", handle)
            for name, groups in (("Sheets akışı", ["Google Sheets"]), ("Eski veritabanı akışı",
                                                                       ["Google Sheets", "Veritabanı"])):
                page.goto("http://127.0.0.1:8765/")
                page.get_by_role("button", name=name, exact=True).click()
                page.get_by_role("button", name="Bağlantılar", exact=True).click()
                manager = page.locator("dialog.connection-manager")
                playwright.expect(manager.locator(".connection-group h3")).to_have_text(groups)
                manager.get_by_role("button", name="Kapat").click()
            browser.close()
    assert not errors


def test_diagram_view_draws_branches_inserts_moves_and_shows_the_last_run(tmp_path):
    import threading

    from fastapi.testclient import TestClient

    playwright = pytest.importorskip("playwright.sync_api")
    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings
    from rpa_orkestrai.engine import Executor
    from rpa_orkestrai.models import Run, Workflow
    from rpa_orkestrai.storage import Store

    errors, shots = [], os.environ.get("RPA_UI_SHOTS")
    settings = Settings(tmp_path / "data", dotenv=False)
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/workflows", json={"name": "Diyagram", "steps": [
            {"id": "rows", "action": "core.set", "title": "Satırlar", "params": {"name": "satirlar", "value": [1, 2, 3]}},
            {"id": "loop", "action": "control.for_each", "title": "Her satır", "params": {
                "items": "${satirlar}", "item_name": "row"}, "children": [
                    {"id": "check", "action": "control.if", "title": "Büyük mü", "params": {
                        "left": "${row}", "operator": "gt", "right": 1}, "children": [
                            {"id": "log", "action": "core.log", "title": "Yaz", "params": {"message": "${row}"}}]},
                ]},
            {"id": "guard", "action": "control.try", "title": "Dene", "params": {}, "children": [
                {"id": "boom", "action": "data.calculate", "title": "Böl", "params": {
                    "expression": "1 / 0", "output": "sonuc"}}]},
        ]})
        assert response.status_code == 201, response.text
        workflow_id = response.json()["id"]
        # A finished run gives the diagram its ✓ / ✗ marks.
        store = Store(settings.data_dir)
        run = Run(workflow_id=workflow_id, workflow_name="Diyagram", department="Genel")
        Executor(settings, store, run, threading.Event(), lambda: store.save_run(run)).execute(
            Workflow.model_validate(client.get(f"/api/workflows/{workflow_id}").json()))
        run.status = "succeeded"
        store.save_run(run)
        assert run.step_stats["log"]["ok"] == 2 and run.step_stats["boom"]["errors"] == 1
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch()
            page = browser.new_page(viewport={"width": 1900, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))

            def handle(route):
                request = route.request
                path = urlsplit(request.url).path
                result = client.request(request.method, path, content=request.post_data_buffer,
                                        headers={"content-type": "application/json"})
                route.fulfill(status=result.status_code, headers=dict(result.headers), body=result.content)

            page.route("http://127.0.0.1:8765/**", handle)
            page.goto("http://127.0.0.1:8765/")
            page.get_by_role("button", name="Diyagram", exact=True).first.click()
            playwright.expect(page.locator("#step-library")).to_be_visible()
            page.get_by_role("button", name="Diyagram", exact=True).click()
            viewport = page.locator("#diagram-viewport")
            playwright.expect(viewport.locator(".dnode")).to_have_count(6)
            # The library folds away in the diagram and can be brought back.
            playwright.expect(page.locator("#step-library")).to_be_hidden()
            page.get_by_role("button", name="Kütüphane").click()
            playwright.expect(page.locator("#step-library")).to_be_visible()
            page.get_by_role("button", name="Kütüphane").click()
            for label in ("Her öğe", "Sonraki tur", "Bitince", "Doğruysa", "Değilse", "Dene", "Hata olursa"):
                playwright.expect(viewport.locator(".edge-label", has_text=label).first).to_be_visible()
            playwright.expect(viewport.locator('[data-step-id="log"] .dnode-status')).to_have_text("2")
            playwright.expect(viewport.locator('[data-step-id="boom"] .dnode-status.failed')).to_have_count(1)
            playwright.expect(viewport.locator(".diagram-run")).to_contain_text("Tamamlandı")
            if shots:
                page.screenshot(path=f"{shots}/diagram.png")

            # Nodes sit left → right: the loop body is to the right of the loop, the try after the loop.
            def box(step_id):
                return viewport.locator(f'[data-step-id="{step_id}"]').bounding_box()

            assert box("rows")["x"] < box("loop")["x"] < box("check")["x"] < box("log")["x"] < box("guard")["x"]
            assert abs(box("loop")["y"] - box("check")["y"]) < 2

            # Insert from the empty "Değilse" branch with the search popover.
            viewport.locator(".diagram-empty").first.click()
            menu = page.locator("#diagram-insert")
            menu.get_by_label("Eklenecek adımı ara").fill("bekle")
            menu.get_by_label("Eklenecek adımı ara").press("Enter")
            playwright.expect(menu).to_have_count(0)
            playwright.expect(viewport.locator(".dnode")).to_have_count(7)
            playwright.expect(page.locator("#inspector div.pane-heading")).to_have_text("Bekle")
            # Hover tools duplicate; the Delete key removes the focused node.
            viewport.locator(".dnode.selected").get_by_role("button", name="Adımı çoğalt").click()
            playwright.expect(viewport.locator(".dnode")).to_have_count(8)
            copy = viewport.locator(".dnode", has_text="(kopya)")
            copy.click()
            copy.press("Delete")
            playwright.expect(viewport.locator(".dnode")).to_have_count(7)

            # Move the first step into the try block by dropping it on a + handle inside the branch.
            playwright.expect(viewport.locator(".edge-insert")).not_to_have_count(0)
            page.get_by_role("button", name="Tümünü sığdır").click()
            # Dragging a box moves it freely; the flow order does not change.
            before = box("loop")
            page.mouse.move(before["x"] + 60, before["y"] + 20)
            page.mouse.down()
            page.mouse.move(before["x"] + 90, before["y"] + 80, steps=6)
            page.mouse.up()
            after = box("loop")
            assert after["x"] - before["x"] > 20 and after["y"] - before["y"] > 40
            playwright.expect(viewport.locator('[data-step-id="loop"].moved')).to_have_count(1)
            playwright.expect(page.locator("#diagram-tidy")).to_be_enabled()
            # Dropped on a +, a box takes that place in the flow: the first step goes into the try block.
            start = box("rows")
            handle = viewport.locator('.edge-insert[data-owner="guard"][data-branch="children"][data-index="0"]')
            goal = handle.bounding_box()
            page.mouse.move(start["x"] + 60, start["y"] + 20)
            page.mouse.down()
            page.mouse.move(goal["x"] + goal["width"] / 2, goal["y"] + goal["height"] / 2, steps=8)
            page.mouse.up()
            playwright.expect(viewport.locator(".dnode.moving")).to_have_count(0)
            zoom = viewport.locator(".zoom-level").inner_text()
            page.get_by_role("button", name="Yakınlaştır").click()
            playwright.expect(viewport.locator(".zoom-level")).not_to_have_text(zoom)
            page.get_by_role("button", name="Kaydet", exact=True).click()
            playwright.expect(page.locator("#saved-label")).to_contain_text("kaydedildi")
            # The chosen view is remembered.
            page.reload()
            page.get_by_role("button", name="Diyagram", exact=True).first.click()
            playwright.expect(page.locator("#diagram-viewport .dnode")).to_have_count(7)
            # From the run details, the failed step opens selected in the diagram.
            page.locator(".diagram-run").get_by_role("button", name="Ayrıntılar").click()
            page.get_by_role("button", name="Diyagramda göster").click()
            playwright.expect(page.locator('#diagram-viewport [data-step-id="boom"].selected')).to_have_count(1)
            playwright.expect(page.locator("#inspector div.pane-heading")).to_have_text("Hesapla")
            browser.close()
        saved = client.get(f"/api/workflows/{workflow_id}").json()
        assert [step["id"] for step in saved["steps"]] == ["loop", "guard"]
        assert [step["id"] for step in saved["steps"][1]["children"]] == ["rows", "boom"]
        # The dragged box keeps its place; the one moved in the flow is laid out automatically again.
        moved = saved["steps"][0]["offset"]
        assert moved[0] > 20 and moved[1] > 40 and saved["steps"][1]["children"][0]["offset"] is None
        otherwise = saved["steps"][0]["children"][0]["otherwise"]
        assert [step["action"] for step in otherwise] == ["core.wait"]
    assert not errors


def test_step_guide_and_tests_that_need_no_typed_values(tmp_path):
    from fastapi.testclient import TestClient

    playwright = pytest.importorskip("playwright.sync_api")
    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    errors, shots = [], os.environ.get("RPA_UI_SHOTS")
    with TestClient(create_app(Settings(tmp_path / "data", dotenv=False))) as client:
        response = client.post("/api/workflows", json={"name": "Kılavuzlu akış", "steps": [
            {"id": "window", "action": "desktop.find_window", "title": "ERP'yi tanı", "params": {
                "application": "", "title": "ERP", "match": "contains", "output": "erp_window"}},
            {"id": "rows", "action": "core.set", "title": "Satırlar", "params": {
                "name": "satirlar", "value": [{"form_id": "inv-1", "durum": "TAMAM"}]}},
            {"id": "loop", "action": "control.for_each", "title": "Her satır", "params": {
                "items": "${satirlar}", "item_name": "row"}, "children": [
                    {"id": "skip", "action": "control.if", "title": "Bekliyor değil mi?", "params": {
                        "left": "${row.durum}", "operator": "ne", "right": "BEKLIYOR"}, "children": [
                            {"id": "next", "action": "control.continue", "params": {}}]},
                    {"id": "upper", "action": "text.transform", "title": "Büyük harf", "params": {
                        "text": "${row.form_id}", "operation": "upper", "output": "kod"}},
                    {"id": "click", "action": "desktop.window_click", "title": "Ara'ya tıkla", "params": {
                        "window": "${erp_window}", "target_mode": "coordinates", "x": 40, "y": 60}},
                ]},
        ]})
        assert response.status_code == 201, response.text
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))

            def handle(route):
                request = route.request
                path = urlsplit(request.url).path
                result = client.request(request.method, path, content=request.post_data_buffer,
                                        headers={"content-type": "application/json"})
                route.fulfill(status=result.status_code, headers=dict(result.headers), body=result.content)

            page.route("http://127.0.0.1:8765/**", handle)
            page.goto("http://127.0.0.1:8765/")
            page.get_by_role("button", name="Kılavuzlu akış", exact=True).click()
            inspector = page.locator("#inspector")
            # Nothing selected: the short guide to building a flow.
            playwright.expect(inspector.locator(".quick-guide li")).to_have_count(9)
            playwright.expect(inspector.locator(".quick-guide")).to_contain_text("Not ekle")
            playwright.expect(inspector.locator(".quick-guide")).to_contain_text("Zamanla")

            # A selected step explains how it is used, and every field carries a help line.
            page.locator('[data-step-id="click"]').click()
            guide = inspector.locator(".step-guide")
            playwright.expect(guide).to_contain_text("Nasıl kullanılır?")
            playwright.expect(guide).to_contain_text("Ekranda seç")
            fields = inspector.locator(".field")
            assert fields.count() == inspector.locator(".field:has(.help)").count()
            if shots:
                page.screenshot(path=f"{shots}/step-guide.png")

            # A click step: no values to type, and the target can be shown without clicking.
            inspector.get_by_role("button", name="Bu adımı test et").click()
            dialog = page.locator("dialog.step-test-dialog")
            playwright.expect(dialog.locator(".step-test-sources")).to_contain_text("${erp_window}")
            playwright.expect(dialog.locator("textarea:visible")).to_have_count(0)
            playwright.expect(dialog.get_by_role("button", name="Yeri göster (tıklamadan)")).to_be_visible()
            playwright.expect(dialog.get_by_role("button", name="Gerçekten çalıştır")).to_be_visible()
            if shots:
                page.screenshot(path=f"{shots}/step-test-click.png")
            dialog.get_by_role("button", name="Kapat").click()

            # A data step inside the loop: the first row is taken from the list by itself.
            page.locator('[data-step-id="upper"]').click()
            inspector.get_by_role("button", name="Bu adımı test et").click()
            playwright.expect(dialog.locator(".step-test-sources")).to_contain_text("listesinin ilk satırı")
            playwright.expect(dialog.locator("textarea:visible")).to_have_count(0)
            dialog.get_by_role("button", name="Testi çalıştır").click()
            playwright.expect(dialog.locator(".step-test-head")).to_contain_text("Tamamlandı")
            playwright.expect(dialog.locator(".step-test-values")).to_contain_text("İNV-1")
            if shots:
                page.screenshot(path=f"{shots}/step-test-auto.png")
            dialog.get_by_role("button", name="Kapat").click()

            # "Sonraki tura geç" inside the tested condition is reported as the result, not as an error.
            page.locator('[data-step-id="skip"]').click()
            inspector.get_by_role("button", name="Bu adımı test et").click()
            dialog.get_by_role("button", name="Testi çalıştır").click()
            playwright.expect(dialog.locator(".step-test-head")).to_contain_text("Tamamlandı")
            playwright.expect(dialog.locator(".step-test-log")).to_contain_text("sonraki satıra geçilir")
            # Another value can still be tried by choice.
            dialog.locator(".step-test-custom summary").click()
            dialog.get_by_label("${row}").fill('{"durum": "BEKLIYOR"}')
            dialog.get_by_role("button", name="Tekrar test et").click()
            playwright.expect(dialog.locator(".step-test-log")).to_contain_text("Koşul: Değilse")
            browser.close()
    assert not errors


def test_names_are_typed_bare_and_windows_are_chosen_from_a_list(tmp_path):
    from fastapi.testclient import TestClient

    playwright = pytest.importorskip("playwright.sync_api")
    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    errors, shots = [], os.environ.get("RPA_UI_SHOTS")
    with TestClient(create_app(Settings(tmp_path / "data", dotenv=False))) as client:
        # The name was typed the way it is used later (${erp_window}); the flow must still work.
        response = client.post("/api/workflows", json={"name": "Adlar", "steps": [
            {"id": "window", "action": "desktop.find_window", "title": "CaniasBsgt31", "params": {
                "application": "", "title": "CANIAS", "match": "contains", "output": "${erp_window}"}},
            {"id": "click", "action": "desktop.window_click", "title": "Ara'ya tıkla", "params": {
                "window": "${erp_window}", "target_mode": "coordinates", "x": 40, "y": 60}},
            {"id": "note", "action": "core.log", "title": "Not", "params": {"message": "${erp_windov.title}"}},
        ]})
        assert response.status_code == 201, response.text
        workflow_id = response.json()["id"]
        assert response.json()["steps"][0]["params"]["output"] == "erp_window"
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))

            def handle(route):
                request = route.request
                path = urlsplit(request.url).path
                result = client.request(request.method, path, content=request.post_data_buffer,
                                        headers={"content-type": "application/json"})
                route.fulfill(status=result.status_code, headers=dict(result.headers), body=result.content)

            page.route("http://127.0.0.1:8765/**", handle)
            page.goto("http://127.0.0.1:8765/")
            page.get_by_role("button", name="Adlar", exact=True).click()
            inspector = page.locator("#inspector")

            # The click step finds its window: the list offers it and the picker is not blocked by it.
            page.locator('[data-step-id="click"]').click()
            choice = inspector.locator(".window-reference select")
            playwright.expect(choice).to_have_value("${erp_window}")
            assert any("CaniasBsgt31" in text for text in choice.locator("option").all_inner_texts())
            playwright.expect(inspector.locator(".window-reference-state")).to_be_hidden()
            inspector.get_by_role("button", name="Bu adımı test et").click()
            dialog = page.locator("dialog.step-test-dialog")
            playwright.expect(dialog.locator(".step-test-sources")).to_contain_text("${erp_window}")
            playwright.expect(dialog.locator("textarea:visible")).to_have_count(0)
            dialog.get_by_role("button", name="Kapat").click()

            # In the name field ${canias} becomes canias, and the line below shows how it is used.
            page.locator('[data-step-id="window"]').click()
            name = inspector.get_by_label("Pencereye verilecek ad", exact=False)
            playwright.expect(name).to_have_value("erp_window")
            name.fill("${canias}")
            playwright.expect(name).to_have_value("canias")
            playwright.expect(inspector.locator(".variable-usage")).to_contain_text("${canias}")
            name.fill("Canias penceresi")
            playwright.expect(inspector.locator(".variable-usage.invalid")).to_contain_text("Yalnız adı yazın")
            name.blur()
            playwright.expect(name).to_have_value("Canias_penceresi")
            playwright.expect(inspector.locator(".variable-usage")).to_contain_text("${Canias_penceresi}")
            if shots:
                page.screenshot(path=f"{shots}/name-field.png")

            # The click step still points at the old name: it says so and offers the list.
            page.locator('[data-step-id="click"]').click()
            playwright.expect(inspector.locator(".window-reference-state")).to_contain_text(
                "${erp_window} adını veren bir adım bu adımdan önce yok")
            if shots:
                page.screenshot(path=f"{shots}/window-missing.png")
            inspector.locator(".window-reference select").select_option("${Canias_penceresi}")
            playwright.expect(inspector.locator(".window-reference-state")).to_be_hidden()

            # A step added now starts with the window this flow named.
            page.get_by_role("button", name="Liste", exact=True).click()
            page.locator(".library-action").filter(has_text="Alanı doldur").click()
            playwright.expect(inspector.locator(".window-reference select")).to_have_value("${Canias_penceresi}")

            # A misspelt name in another step: the test explains it and suggests the close one.
            page.get_by_role("button", name="Kaydet", exact=True).click()
            playwright.expect(page.locator("#saved-label")).to_contain_text("kaydedildi")
            page.locator('[data-step-id="note"]').click()
            inspector.get_by_role("button", name="Bu adımı test et").click()
            playwright.expect(dialog).to_contain_text("${erp_windov} adını veren bir adım bu adımdan önce yok")
            playwright.expect(dialog.locator("textarea:visible")).to_have_count(0)
            if shots:
                page.screenshot(path=f"{shots}/test-missing.png")
            browser.close()
        saved = client.get(f"/api/workflows/{workflow_id}").json()
        assert saved["steps"][0]["params"]["output"] == "Canias_penceresi"
        assert saved["steps"][1]["params"]["window"] == "${Canias_penceresi}"
    assert not errors


@pytest.mark.real_license
def test_license_screens_sign_in_lock_and_keep_unsaved_work(tmp_path):
    from fastapi.testclient import TestClient
    from test_licensing import OTHER_COMPUTER, FakeOrkestrai, Timer, service

    playwright = pytest.importorskip("playwright.sync_api")
    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    server, timer, errors = FakeOrkestrai(), Timer(), []
    settings = Settings(tmp_path / "data", dotenv=False)
    licensing = service(settings.data_dir, server, timer)
    with TestClient(create_app(settings, licensing=licensing)) as client, playwright.sync_playwright() as runner:
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
        card = page.locator(".license-card")
        password = card.locator('input[type="password"]')
        sign_in = card.get_by_role("button", name="Giriş yap", exact=True)

        # No session on this computer: the Studio asks for the orkestrai.net account.
        playwright.expect(card).to_contain_text("Şifreniz bu bilgisayara kaydedilmez")
        card.locator('input[autocomplete="username"]').fill("operator")
        password.fill("yanlis")
        sign_in.click()
        playwright.expect(card.locator(".license-message")).to_contain_text("hatalı")
        password.fill("dogru")
        sign_in.click()
        playwright.expect(page.locator(".license-screen")).to_have_count(0)
        playwright.expect(page.locator(".owner-text")).to_contain_text("Örnek Lojistik")

        created = client.post("/api/workflows", json={"name": "Sipariş girişi", "steps": [
            {"id": "note", "action": "core.log", "params": {"message": "ilk"}}]})
        assert created.status_code == 201, created.text
        page.reload()
        page.get_by_role("button", name="Sipariş girişi", exact=True).click()
        page.locator('[data-step-id="note"]').click()
        note = page.locator(".field").filter(has_text="Not").locator("input, textarea").first
        note.fill("kaydedilmemiş not")

        # The connection stays away longer than allowed: the Studio locks, the open flow is kept.
        server.offline = True
        timer.value += 3700
        page.get_by_role("button", name="Kaydet", exact=True).click()
        playwright.expect(card.get_by_role("heading")).to_have_text("Lisans doğrulanamadı")
        playwright.expect(card).to_contain_text("kaydedilmemiş değişiklikler duruyor")
        playwright.expect(card).to_contain_text("operator@ornek.com.tr")
        card.get_by_role("button", name="Yeniden dene", exact=True).click()
        playwright.expect(card.locator(".license-message")).to_contain_text("hâlâ ulaşılamıyor")
        assert client.get("/api/workflows").status_code == 403
        # The connection returns: the screen follows the background check and the editor is back.
        server.offline = False
        licensing.refresh()
        playwright.expect(page.locator(".license-screen")).to_have_count(0, timeout=10000)
        page.locator('[data-step-id="note"]').click()
        playwright.expect(page.locator(".field").filter(has_text="Not").locator("input, textarea").first
                          ).to_have_value("kaydedilmemiş not")

        # The account is opened on another computer: this one returns to the sign-in form with the reason.
        service(tmp_path / "other", server, machine="machine-b").login("operator", "dogru")
        licensing.refresh()
        page.get_by_role("button", name="Kaydet", exact=True).click()
        playwright.expect(card.locator(".license-message")).to_contain_text(OTHER_COMPUTER)
        playwright.expect(card.locator('input[autocomplete="username"]')).to_have_value("operator@ornek.com.tr")
        password.fill("dogru")
        sign_in.click()
        playwright.expect(page.locator(".license-screen")).to_have_count(0)
        page.get_by_role("button", name="Kaydet", exact=True).click()
        playwright.expect(page.locator(".toast").last).to_contain_text("kaydedildi")
        saved = client.get(f"/api/workflows/{created.json()['id']}").json()
        assert saved["steps"][0]["params"]["message"] == "kaydedilmemiş not"

        # The license is withdrawn on orkestrai.net: the closing notice, not the Studio.
        server.denial = ("YETKI_YOK", "Bu kullanıcı için RpaOrkestrAI lisansı tanımlı değil.")
        licensing.refresh()
        page.reload()
        playwright.expect(card.get_by_role("heading")).to_have_text("Lisans tanımlı değil")
        playwright.expect(card).to_contain_text("firma yöneticinize başvurun")
        # A version orkestrai.net no longer serves is told to update instead.
        server.denial = ("YETKI_YOK", "Bu RpaOrkestrAI sürümü artık desteklenmiyor. Güncel sürümü "
                                      "https://orkestrai.net/rpa adresinden kurun.", None, "ESKI_SURUM")
        licensing.refresh()
        page.reload()
        playwright.expect(card.get_by_role("heading")).to_have_text("Bu sürüm artık desteklenmiyor")
        playwright.expect(card).to_contain_text("https://orkestrai.net/rpa adresinden kurun")
        playwright.expect(card).to_contain_text("olduğu gibi kalır")

        # A restart with a remembered session waits for orkestrai.net before anything opens.
        server.denial, server.offline = None, True
        browser.close()
    reopened = service(settings.data_dir, server, timer)
    with TestClient(create_app(settings, licensing=reopened)) as client, playwright.sync_playwright() as runner:
        browser = runner.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.route("http://127.0.0.1:8765/**", lambda route: (lambda result: route.fulfill(
            status=result.status_code, headers=dict(result.headers), body=result.content))(client.request(
                route.request.method, urlsplit(route.request.url).path, content=route.request.post_data_buffer,
                headers={"content-type": "application/json"})))
        page.goto("http://127.0.0.1:8765/")
        card = page.locator(".license-card")
        playwright.expect(card.get_by_role("heading")).to_have_text("Lisans doğrulanamadı")
        playwright.expect(card).to_contain_text("internet bağlantısı")
        playwright.expect(card.locator('input[type="password"]')).to_have_count(0)
        assert client.get("/api/bootstrap").status_code == 403
        server.offline = False
        card.get_by_role("button", name="Yeniden dene", exact=True).click()
        playwright.expect(page.locator(".license-screen")).to_have_count(0)
        playwright.expect(page.get_by_role("button", name="Sipariş girişi", exact=True)).to_be_visible()
        browser.close()
    assert errors == []


def test_connections_are_drawn_cut_and_chosen_without_copying_steps(tmp_path):
    from fastapi.testclient import TestClient

    playwright = pytest.importorskip("playwright.sync_api")
    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    errors = []
    with TestClient(create_app(Settings(tmp_path / "data", dotenv=False))) as client:
        created = client.post("/api/workflows", json={"name": "Yollar", "steps": [
            {"id": "first", "title": "Hazırlık", "action": "core.log", "params": {"message": "başla"}},
            {"id": "rows", "title": "Satırlar", "action": "control.for_each", "params": {"items": [1, 2], "item_name": "row"},
             "children": [
                 {"id": "search", "title": "Ara", "action": "core.log", "params": {"message": "ara"}},
                 {"id": "cond", "title": "Bulundu mu", "action": "control.if",
                  "params": {"left": "${row}", "operator": "eq", "right": 1},
                  "children": [{"id": "yes", "title": "Aç", "action": "core.log", "params": {"message": "aç"}}],
                  "otherwise": [{"id": "no", "title": "Filtreyi değiştir", "action": "core.log", "params": {"message": "x"}}]},
                 {"id": "save", "title": "Kaydet", "action": "core.log", "params": {"message": "kaydet"}},
             ]},
            {"id": "final", "title": "Bitti", "action": "core.log", "params": {"message": "bitti"}},
        ]})
        assert created.status_code == 201, created.text
        workflow_id = created.json()["id"]

        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch()
            page = browser.new_page(viewport={"width": 1700, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.add_init_script("try { localStorage.setItem('rpa.canvasView', 'diagram'); } catch (e) {}")

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
            page.get_by_role("button", name="Yollar", exact=True).click()
            box = page.locator("#diagram-viewport .dnode").first
            playwright.expect(box).to_be_visible()

            def connect(after, target):
                port = page.locator(f'.diagram-port[data-after="{after}"]').bounding_box()
                goal = page.locator(f'#diagram-viewport [data-step-id="{target}"]').bounding_box()
                page.mouse.move(port["x"] + port["width"] / 2, port["y"] + port["height"] / 2)
                page.mouse.down()
                page.mouse.move(goal["x"] + goal["width"] / 2, goal["y"] + goal["height"] / 2, steps=8)
                page.mouse.up()

            def saved():
                page.get_by_role("button", name="Kaydet", exact=True).click()
                playwright.expect(page.get_by_text("Tüm değişiklikler kaydedildi")).to_be_visible()
                return client.get(f"/api/workflows/{workflow_id}").json()

            def block(steps, step_id):
                for item in steps:
                    if item["id"] == step_id:
                        return item
                    found = block(item.get("children", []) + item.get("otherwise", []), step_id)
                    if found:
                        return found
                return None

            # Değilse goes back to Ara instead of meeting the other branch at Kaydet.
            connect("no", "search")
            jump = page.locator("#diagram-viewport .dnode-pill.ending-goto")
            playwright.expect(jump).to_have_count(1)
            playwright.expect(jump).to_contain_text("Ara")
            playwright.expect(page.locator("#diagram-viewport path.edge.jump")).to_have_count(1)
            flow = saved()
            otherwise = block(flow["steps"], "cond")["otherwise"]
            assert [item["action"] for item in otherwise] == ["core.log", "control.goto"]
            assert otherwise[1]["params"]["target"] == "search"

            # A step inside the loop cannot be reached from outside it.
            connect("first", "save")
            playwright.expect(page.locator(".toast.error").last).to_contain_text("döngüsünün içindeki")
            assert block(saved()["steps"], "rows") and len(saved()["steps"]) == 3

            # Cutting the line after Ara ends that path: the loop moves on, and Bulundu mu is not reached.
            hit = page.locator(".edge-insert[data-owner='rows'][data-index='1']")
            hit.hover()
            cut = page.get_by_role("button", name="Bağlantıyı kaldır").and_(page.locator(".edge-remove.show"))
            cut.click()
            playwright.expect(page.locator(".toast").last).to_contain_text("sonraki tura geçer")
            playwright.expect(page.locator('#diagram-viewport .dnode.unreached[data-step-id="cond"]')).to_be_visible()
            assert [item["action"] for item in block(saved()["steps"], "rows")["children"]][:2] == [
                "core.log", "control.continue"]

            # The same choice in the settings: back to the next step, then the path ends the flow.
            page.locator('#diagram-viewport [data-step-id="search"]').click()
            choice = page.locator("#path-end")
            playwright.expect(choice).to_have_value("control.continue")
            choice.select_option("next")
            playwright.expect(page.locator('#diagram-viewport .dnode.unreached')).to_have_count(0)
            # Bitti lies under the settings panel at this zoom; the keyboard selects it all the same.
            page.locator('#diagram-viewport [data-step-id="final"]').press("Enter")
            playwright.expect(choice).to_have_value("next")
            playwright.expect(choice.locator("option[value='next']")).to_have_text("Akış biter")
            choice.select_option("control.goto")
            target = page.locator(".path-end select").nth(1)
            # Inside the loop is not offered from here; the loop box and the steps outside are.
            playwright.expect(target.locator("option", has_text="Ara")).to_be_disabled()
            target.select_option(label=next(text for text in target.locator("option").all_inner_texts()
                                            if text.startswith("1. Hazırlık")))
            flow = saved()
            assert [(item["action"], item["params"].get("target")) for item in flow["steps"]][-1] == (
                "control.goto", "first")
            playwright.expect(page.locator("#diagram-viewport path.edge.jump")).to_have_count(2)

            # In the list the jump says where it leads.
            page.get_by_role("button", name="Liste", exact=True).click()
            playwright.expect(page.locator(".step-jump").filter(has_text="«Hazırlık» adımına gider")).to_be_visible()
            # Removing a step that a jump leads to removes the jump too.
            page.locator('[data-step-id="first"] .step-tools').get_by_role("button", name="Adımı sil").click()
            page.get_by_role("button", name="Adımı sil", exact=True).last.click()
            flow = saved()
            assert all(item["action"] != "control.goto" for item in flow["steps"])
            browser.close()
    assert errors == []


def test_every_window_target_step_offers_the_on_screen_picker(tmp_path):
    from fastapi.testclient import TestClient

    playwright = pytest.importorskip("playwright.sync_api")
    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.catalog import BY_TYPE
    from rpa_orkestrai.config import Settings

    # Any step that points somewhere inside the ERP window must let the user show that place.
    pointing = sorted(action for action, spec in BY_TYPE.items()
                      if any(f["name"] == "target_mode" for f in spec["fields"]))
    assert "window.read_table" in pointing and "desktop.window_click" in pointing
    steps = [{"id": "win", "title": "Pencereyi tanı", "action": "desktop.find_window",
              "params": {"application": "ERP", "title": "Canias", "output": "erp_window"}}]
    steps += [{"id": f"s{index}", "title": BY_TYPE[action]["label"], "action": action,
               "params": {"window": "${erp_window}"}} for index, action in enumerate(pointing)]
    errors = []
    with TestClient(create_app(Settings(tmp_path / "data", dotenv=False))) as client:
        created = client.post("/api/workflows", json={"name": "Hedefler", "steps": steps})
        assert created.status_code == 201, created.text
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch()
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))

            def handle(route):
                request = route.request
                path = urlsplit(request.url).path
                if path == "/api/desktop/pick/capabilities":
                    route.fulfill(json={"native": True})
                    return
                result = client.request(request.method, path, content=request.post_data_buffer,
                                        headers={"content-type": "application/json"})
                route.fulfill(status=result.status_code, headers=dict(result.headers), body=result.content)

            page.route("http://127.0.0.1:8765/**", handle)
            page.goto("http://127.0.0.1:8765/")
            page.get_by_role("button", name="Hedefler", exact=True).click()
            inspector = page.locator("#inspector")
            for index, action in enumerate(pointing):
                page.locator(f'[data-step-id="s{index}"]').click()
                playwright.expect(inspector.get_by_role("button", name="Ekranda seç", exact=True)).to_be_visible()
                playwright.expect(inspector.get_by_role("button", name="Görüntü üzerinde seç", exact=True)).to_be_visible()
            # The window steps keep it; a step that does not point inside a window does not show it.
            page.locator('[data-step-id="win"]').click()
            playwright.expect(inspector.get_by_role("button", name="Ekranda seç", exact=True)).to_have_count(0)
            browser.close()
    assert errors == []


def test_merged_image_step_and_the_place_for_metin_yaz(tmp_path):
    from fastapi.testclient import TestClient

    playwright = pytest.importorskip("playwright.sync_api")
    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    errors = []
    with TestClient(create_app(Settings(tmp_path / "data", dotenv=False))) as client:
        created = client.post("/api/workflows", json={"name": "Eski akış", "steps": [
            {"id": "win", "title": "Pencereyi tanı", "action": "desktop.find_window",
             "params": {"application": "ERP", "title": "Canias", "output": "erp_window"}},
            # Saved before the merge: the old screen-wide image search.
            {"id": "old", "title": "Ekranda görsel ara / bekle", "action": "screen.find_image",
             "params": {"template": "hata.png", "state": "visible", "timeout": 4, "on_missing": "continue",
                        "relative_to": "screen", "region": [0, 0, 400, 300], "output": "hata"}},
            {"id": "type", "title": "Metin yaz", "action": "input.type", "params": {"text": "540767"}},
        ]})
        assert created.status_code == 201, created.text
        workflow_id = created.json()["id"]
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch()
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))

            def handle(route):
                request = route.request
                path = urlsplit(request.url).path
                if path == "/api/desktop/pick/capabilities":
                    route.fulfill(json={"native": True})
                    return
                result = client.request(request.method, path, content=request.post_data_buffer,
                                        headers={"content-type": "application/json"})
                route.fulfill(status=result.status_code, headers=dict(result.headers), body=result.content)

            page.route("http://127.0.0.1:8765/**", handle)
            page.goto("http://127.0.0.1:8765/")
            page.get_by_role("button", name="Eski akış", exact=True).click()
            library = page.locator("#step-library")
            # The library offers only the merged step.
            playwright.expect(library.get_by_text("Pencerede görseli bekle / ara")).to_be_visible()
            playwright.expect(library.get_by_text("Ekranda görsel ara / bekle")).to_have_count(0)
            inspector = page.locator("#inspector")

            # Metin yaz can be shown where to type.
            page.locator('[data-step-id="type"]').click()
            playwright.expect(inspector.get_by_role("button", name="Fare konumunu al (3 sn)")).to_be_visible()

            # The saved step explains the change and turns into the merged step, keeping its settings.
            page.locator('[data-step-id="old"]').click()
            playwright.expect(inspector.locator(".legacy-action-help")).to_contain_text("kütüphaneden kaldırıldı")
            inspector.get_by_role("button", name="«Pencerede görseli bekle / ara» adımına dönüştür").click()
            playwright.expect(page.locator(".toast").last).to_contain_text("Bölge ayarı kullanılmıyor")
            playwright.expect(inspector.locator(".pane-heading").first).to_have_text("Pencerede görseli bekle / ara")
            page.get_by_role("button", name="Kaydet", exact=True).click()
            playwright.expect(page.get_by_text("Tüm değişiklikler kaydedildi")).to_be_visible()
            step = next(item for item in client.get(f"/api/workflows/{workflow_id}").json()["steps"]
                        if item["id"] == "old")
            assert step["action"] == "desktop.window_wait_image"
            assert {key: step["params"][key] for key in ("window", "template", "timeout", "on_missing", "output")} == {
                "window": "${erp_window}", "template": "hata.png", "timeout": 4, "on_missing": "continue",
                "output": "hata"}
            assert "region" not in step["params"] and "relative_to" not in step["params"]
            browser.close()
    assert errors == []


def studio_page(runner, client, errors, viewport=None):
    browser = runner.chromium.launch()
    page = browser.new_page(viewport=viewport or {"width": 1500, "height": 1000})
    page.on("pageerror", lambda error: errors.append(str(error)))

    def handle(route):
        request = route.request
        path = urlsplit(request.url).path
        if path == "/api/desktop/pick/capabilities":
            route.fulfill(json={"native": True})
            return
        result = client.request(request.method, path, content=request.post_data_buffer,
                                headers={"content-type": "application/json"})
        route.fulfill(status=result.status_code, headers=dict(result.headers), body=result.content)

    page.route("http://127.0.0.1:8765/**", handle)
    page.goto("http://127.0.0.1:8765/")
    return browser, page


def test_notes_frame_chosen_steps_and_steps_wait_before_the_next(tmp_path):
    from fastapi.testclient import TestClient

    playwright = pytest.importorskip("playwright.sync_api")
    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    errors = []
    log = lambda step_id, text: {"id": step_id, "title": text, "action": "core.log", "params": {"message": text}}  # noqa: E731
    with TestClient(create_app(Settings(tmp_path / "data", dotenv=False))) as client:
        created = client.post("/api/workflows", json={"name": "Notlu akış", "steps": [
            log("a", "ERP'yi aç"), log("b", "Giriş yap"), log("c", "Raporu al"),
            {"id": "loop", "title": "Satırlar", "action": "control.repeat", "params": {"count": 2},
             "children": [log("inside", "Satırı işle")]},
            log("d", "Kapat")]})
        assert created.status_code == 201, created.text
        workflow_id = created.json()["id"]
        with playwright.sync_playwright() as runner:
            browser, page = studio_page(runner, client, errors)
            page.get_by_role("button", name="Notlu akış", exact=True).click()
            canvas, inspector = page.locator("#flow-canvas"), page.locator("#inspector")
            playwright.expect(canvas.locator(".canvas-tip")).to_contain_text("Shift")

            # Click, then Shift + click: the steps between are chosen too.
            page.locator('[data-step-id="a"]').click()
            page.locator('[data-step-id="c"]').click(modifiers=["Shift"])
            playwright.expect(canvas.locator(".step-card.chosen")).to_have_count(3)
            bar = canvas.locator(".selection-bar")
            playwright.expect(bar).to_contain_text("3 adım seçili")
            bar.get_by_role("button", name="Not ekle").click()
            playwright.expect(inspector.locator(".pane-heading").first).to_have_text("Akış notu")
            inspector.locator("#note-title").fill("Giriş bölümü")
            inspector.locator("textarea.note-text").fill("ERP açılır ve oturum açılır.")
            inspector.get_by_role("radio", name="Mavi").click()
            band = canvas.locator(".note-band")
            playwright.expect(band).to_contain_text("Giriş bölümü")
            playwright.expect(band).to_contain_text("ERP açılır ve oturum açılır.")
            playwright.expect(canvas.locator(".step-card.in-note")).to_have_count(3)

            # A step waits before the next one; 0 leaves nothing behind in the saved flow.
            page.locator('[data-step-id="b"]').click()
            wait = inspector.get_by_label("Sonraki adıma geçmeden bekle (saniye)")
            wait.fill("1.5")
            playwright.expect(page.locator('[data-step-id="b"] .step-wait')).to_have_text(
                "Sonraki adıma geçmeden 1,5 sn bekler")
            page.locator('[data-step-id="c"]').click()
            inspector.get_by_label("Sonraki adıma geçmeden bekle (saniye)").fill("2")
            inspector.get_by_label("Sonraki adıma geçmeden bekle (saniye)").fill("0")
            playwright.expect(page.locator('[data-step-id="c"] .step-wait')).to_have_count(0)
            page.get_by_role("button", name="Kaydet", exact=True).click()
            playwright.expect(page.get_by_text("Tüm değişiklikler kaydedildi")).to_be_visible()
            saved = client.get(f"/api/workflows/{workflow_id}").json()
            assert [(note["title"], note["color"], note["steps"]) for note in saved["notes"]] == [
                ("Giriş bölümü", "blue", ["a", "b", "c"])]
            params = {step["id"]: step["params"] for step in saved["steps"]}
            assert params["b"]["wait_after"] == 1.5 and "wait_after" not in params["c"]

            # A step added from the library does not carry the pause at all.
            page.locator("#step-library").get_by_text("Çalışma notu", exact=True).first.click()
            page.get_by_role("button", name="Kaydet", exact=True).click()
            playwright.expect(page.get_by_text("Tüm değişiklikler kaydedildi")).to_be_visible()
            added = client.get(f"/api/workflows/{workflow_id}").json()["steps"][-1]
            assert added["action"] == "core.log" and "wait_after" not in added["params"]

            # The diagram draws the note as a frame; its header opens the note.
            canvas.get_by_role("button", name="Diyagram").click()
            frame = canvas.locator(".diagram-note")
            playwright.expect(frame).to_have_count(1)
            playwright.expect(frame).to_contain_text("Giriş bölümü")
            page.locator('#diagram-viewport [data-step-id="d"]').click()
            frame.locator(".diagram-note-head").click()
            playwright.expect(inspector.locator("#note-title")).to_have_value("Giriş bölümü")

            # Shift + drag on the background chooses a region; the loop joins the open note.
            viewport = page.locator("#diagram-viewport")
            loop_box = page.locator('#diagram-viewport [data-step-id="loop"]').bounding_box()
            inside_box = page.locator('#diagram-viewport [data-step-id="inside"]').bounding_box()
            page.keyboard.down("Shift")
            page.mouse.move(loop_box["x"] - 12, loop_box["y"] - 30)
            page.mouse.down()
            page.mouse.move(inside_box["x"] + inside_box["width"] + 8, inside_box["y"] + inside_box["height"] + 30,
                            steps=6)
            page.mouse.up()
            page.keyboard.up("Shift")
            bar = viewport.locator(".selection-bar")
            playwright.expect(bar).to_contain_text("2 adım seçili")
            bar.get_by_role("button", name="Açık nota ekle").click()
            playwright.expect(inspector.locator(".note-steps li")).to_have_count(4)
            page.locator('#diagram-viewport [data-step-id="d"]').click(modifiers=["ControlOrMeta"])
            playwright.expect(viewport.locator(".selection-bar")).to_contain_text("1 adım seçili")
            page.keyboard.press("Escape")
            playwright.expect(viewport.locator(".selection-bar")).to_have_count(0)

            # Deleting a noted step shortens the note; the last one takes the note with it.
            page.locator('#diagram-viewport [data-step-id="a"]').click()
            page.locator('#diagram-viewport [data-step-id="a"]').press("Delete")
            frame.locator(".diagram-note-head").click()
            playwright.expect(inspector.locator(".note-steps li")).to_have_count(3)
            inspector.get_by_role("button", name="Notu sil").click()
            page.get_by_role("dialog").get_by_role("button", name="Notu sil").click()
            playwright.expect(canvas.locator(".diagram-note")).to_have_count(0)
            browser.close()
    assert errors == []


def test_scheduler_page_plans_runs_and_the_countdown_can_be_cancelled(tmp_path):
    from fastapi.testclient import TestClient

    playwright = pytest.importorskip("playwright.sync_api")
    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    errors = []
    with TestClient(create_app(Settings(tmp_path / "data", dotenv=False))) as client:
        created = client.post("/api/workflows", json={"name": "Sabah raporu", "steps": [
            {"id": "a", "action": "core.log", "params": {"message": "Rapor"}}]})
        assert created.status_code == 201, created.text
        workflow_id = created.json()["id"]
        with playwright.sync_playwright() as runner:
            browser, page = studio_page(runner, client, errors)
            page.get_by_role("button", name="Zamanlayıcı").click()
            playwright.expect(page.get_by_text("Henüz zamanlama yok")).to_be_visible()
            # Started from source: the login item belongs to the installed app.
            playwright.expect(page.locator("#autostart-toggle")).to_be_disabled()
            page.get_by_role("button", name="Yeni zamanlama").click()
            dialog = page.locator("dialog[open]")
            dialog.get_by_role("button", name="Belirli günler").click()
            dialog.locator('input[type="time"]').first.fill("09:00")
            playwright.expect(dialog.locator(".schedule-preview")).to_contain_text("Hafta içi 09:00")
            playwright.expect(dialog.locator(".schedule-preview li")).to_have_count(3)
            dialog.get_by_role("button", name="Cmt").click()
            playwright.expect(dialog.locator(".schedule-preview")).to_contain_text("Pzt, Sal, Çar, Per, Cum, Cmt 09:00")
            for day in ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt"):
                dialog.get_by_role("button", name=day, exact=True).click()
            playwright.expect(dialog.locator(".schedule-preview")).to_contain_text("En az bir gün seçin")
            dialog.get_by_role("button", name="Hafta içi").click()
            dialog.get_by_role("button", name="Zamanlamayı oluştur").click()
            row = page.locator(".schedule-table tbody tr")
            playwright.expect(row).to_have_count(1)
            playwright.expect(row).to_contain_text("Sabah raporu")
            playwright.expect(row).to_contain_text("Hafta içi 09:00")
            playwright.expect(page.locator("#schedule-count")).to_have_text("1")
            [schedule] = client.get("/api/schedules").json()["schedules"]
            assert (schedule["workflow_id"], schedule["kind"], schedule["days"], schedule["time"]) == (
                workflow_id, "weekly", [0, 1, 2, 3, 4], "09:00")

            # Every 30 minutes within working hours.
            row.get_by_role("button", name="Zamanlamayı düzenle").click()
            dialog = page.locator("dialog[open]")
            dialog.get_by_role("button", name="Belirli aralıklarla").click()
            dialog.get_by_label("Kaç dakikada bir?").fill("30")
            dialog.get_by_label("Bitiş saati (isteğe bağlı)").fill("08:00")
            playwright.expect(dialog.locator(".schedule-preview")).to_contain_text("Bitiş saati başlangıç")
            dialog.get_by_label("Bitiş saati (isteğe bağlı)").fill("18:00")
            playwright.expect(dialog.locator(".schedule-preview")).to_contain_text(
                "Her 30 dakikada bir, 09:00–18:00 arası, hafta içi")
            # Who goes first when flows meet, how late it may start, how long it may take.
            dialog.get_by_text("Çakışma ve süre ayarları").click()
            dialog.get_by_label("Öncelik").select_option("high")
            dialog.get_by_label("En uzun çalışma süresi (dakika)").fill("20")
            playwright.expect(dialog.locator(".schedule-preview")).to_contain_text("süresi henüz bilinmiyor")
            dialog.get_by_role("button", name="Kaydet").click()
            playwright.expect(row).to_contain_text("Her 30 dakikada bir")
            playwright.expect(row).to_contain_text("Yüksek öncelik · en uzun 20 dk")
            plan = page.locator(".schedule-plan")
            playwright.expect(plan).to_contain_text("Önümüzdeki 24 saat")
            playwright.expect(plan.locator(".plan-lane")).to_have_count(1)
            row.get_by_role("checkbox").uncheck()
            playwright.expect(row).to_contain_text("Kapalı")
            playwright.expect(page.locator(".schedule-plan")).to_have_count(0)
            playwright.expect(page.locator("#schedule-count")).to_be_hidden()
            page.locator("#countdown-seconds").fill("25")
            page.locator("#countdown-seconds").press("Tab")
            playwright.expect(page.locator(".toast").last).to_contain_text("25 saniyelik")
            assert client.get("/api/schedules").json()["settings"] == {"countdown": 25}

            # The editor schedules the open flow.
            page.get_by_role("button", name="Genel bakış").click()
            page.get_by_role("button", name="Sabah raporu", exact=True).click()
            page.get_by_role("button", name="Zamanla", exact=True).click()
            dialog = page.locator("dialog[open]")
            playwright.expect(dialog.get_by_role("combobox").first).to_have_value(workflow_id)
            playwright.expect(dialog).to_contain_text("1 zamanlaması daha var")
            dialog.get_by_role("button", name="Vazgeç").click()

            # A due run counts down over any page; İptal et stops it.
            answers = []
            pending = {"schedule_id": schedule["id"], "workflow_id": workflow_id, "workflow_name": "Sabah raporu",
                       "due_at": "2026-10-05T09:00", "seconds_left": 9}

            def countdown(route):
                if route.request.method == "POST":
                    answers.append(urlsplit(route.request.url).path.rsplit("/", 1)[-1])
                    pending.clear()
                    route.fulfill(json={"pending": None})
                else:
                    route.fulfill(json={"pending": dict(pending) or None})

            page.route("http://127.0.0.1:8765/api/schedules/pending**", countdown)
            panel = page.locator("#schedule-countdown")
            playwright.expect(panel).to_contain_text("Sabah raporu", timeout=8000)
            playwright.expect(panel).to_contain_text("9 sn sonra başlıyor")
            panel.get_by_role("button", name="İptal et").click()
            playwright.expect(panel).to_have_count(0)
            assert answers == ["cancel"]
            playwright.expect(page.locator(".toast").last).to_contain_text("iptal edildi")
            browser.close()
    assert errors == []
