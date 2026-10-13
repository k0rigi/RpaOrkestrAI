import os
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from rpa_orkestrai.app import create_app
from rpa_orkestrai.config import Settings

pytestmark = pytest.mark.skipif(os.environ.get("RPA_UI_TESTS") != "1", reason="İsteğe bağlı Chromium yapay zekâ adımı testi")


def test_ai_editor_loads_provider_choices_safely_and_saves_exact_step(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    connection_id = "a" * 32
    attack = '<img src=x onerror="window.injected=true">'
    errors = []
    schema = '{"type":"object","properties":{"karar":{"enum":["devam","incele"]}},"required":["karar"]}'
    with TestClient(create_app(Settings(tmp_path, dotenv=False))) as client:
        response = client.post("/api/workflows", json={"name": "Yapay zekâ kararı", "steps": [
            {"id": "soru", "action": "ai.ask", "params": {"instructions": "Kararı seç.", "input": "Veri"}},
        ]})
        assert response.status_code == 201
        workflow_id = response.json()["id"]
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch()
            page = browser.new_page(viewport={"width": 980, "height": 900})
            page.on("pageerror", lambda error: errors.append(str(error)))

            def handle(route):
                request = route.request
                url = urlsplit(request.url)
                if url.path == "/api/agents/connections":
                    route.fulfill(json=[{"id": connection_id, "name": attack, "model": "seçilen-model",
                                         "provider": "openai", "sends_to_cloud": True}])
                else:
                    result = client.request(request.method, url.path + ("?" + url.query if url.query else ""),
                                            content=request.post_data_buffer, headers={"content-type": "application/json"})
                    route.fulfill(status=result.status_code, headers=dict(result.headers), body=result.content)

            page.route("http://127.0.0.1:8765/**", handle)
            page.goto("http://127.0.0.1:8765/")
            page.get_by_role("button", name="Yapay zekâ kararı", exact=True).click()
            page.locator('[data-step-id="soru"]').first.click()
            select = page.get_by_label("Yapay zekâ bağlantısı", exact=True)
            playwright.expect(select).to_be_enabled()
            playwright.expect(select.locator("option").last).to_contain_text(attack)
            select.select_option(connection_id)
            playwright.expect(page.get_by_text("Akış sonuçları bu sağlayıcıya gönderilir; hassas veri için yerel model kullanın.", exact=True)).to_be_visible()
            instruction = page.get_by_label("Talimat", exact=False)
            assert instruction.evaluate("node => node.tagName") == "TEXTAREA"
            instruction.fill("Kararı seç.\n" + attack)
            page.locator("#json-mode-soru-schema").select_option("json")
            page.get_by_label("Sonuç JSON şeması (isteğe bağlı)", exact=True).fill(schema)
            field = select.locator("..").locator("..")
            ids = field.locator("button,select").evaluate_all("nodes => nodes.map(node => node.id)")
            assert all(ids) and len(set(ids)) == len(ids)
            assert page.evaluate("window.injected") is None
            page.get_by_role("button", name="Kaydet", exact=True).click()
            playwright.expect(page.get_by_text("Tüm değişiklikler kaydedildi", exact=True)).to_be_visible()
            browser.close()
        saved = client.get(f"/api/workflows/{workflow_id}").json()["steps"][0]["params"]
        assert saved["connection"] == connection_id and saved["instructions"] == "Kararı seç.\n" + attack
        assert saved["schema"]["required"] == ["karar"]
    assert not errors
