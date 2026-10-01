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
            page.locator('[data-step-id="rows"]').drag_to(page.locator('[data-step-id="boom"]'), target_position={"x": 5, "y": 30})
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
        otherwise = saved["steps"][0]["children"][0]["otherwise"]
        assert [step["action"] for step in otherwise] == ["core.wait"]
    assert not errors
