"""Bireysel hesaplar ve şifre işlemleri: hesap türü imzalı lisanstan gelir, şifre orkestrai.net'te değişir."""

import json
import os
from urllib.parse import urlsplit
from urllib.request import Request

import pytest
from test_licensing import FakeOrkestrai, Response, service

from rpa_orkestrai.licensing import OPEN_PATHS, LicenseError


class AccountServer(FakeOrkestrai):
    """orkestrai.net with the account service next to the license service."""

    def __init__(self):
        super().__init__()
        self.password = "dogru"
        self.code = "ABCD-EFGH-JKLM"

    def open(self, request, timeout):
        endpoint = request.full_url.rsplit("/", 1)[-1]
        body = json.loads(request.data)
        if "/api/rpa/hesap/" in request.full_url:
            self.requests.append(("hesap/" + endpoint, body))
            if endpoint == "sifre":
                if body["sifre"] != self.password:
                    return self.error(401, "HATALI_GIRIS", "Kullanıcı adı veya mevcut şifre hatalı.")
                self.password = body["yeni_sifre"]
                return Response(200, {"success": True, "message": "Şifreniz değiştirildi."})
            if body["kod"] != self.code:
                return self.error(401, "KOD_HATALI", "E-posta veya yenileme kodu hatalı ya da kodun süresi dolmuş.")
            self.password, self.code = body["yeni_sifre"], None
            return Response(200, {"success": True, "message": "Şifreniz yenilendi."})
        if endpoint == "giris":
            if body["sifre"] != self.password:
                return self.error(401, "HATALI_GIRIS", "Kullanıcı adı veya şifre hatalı.")
            request = Request(request.full_url, data=json.dumps({**body, "sifre": "dogru"}).encode(), method="POST")
        return super().open(request, timeout)


@pytest.fixture
def server():
    return AccountServer()


def test_signed_account_type_names_a_personal_account_and_unknown_values_are_ignored(tmp_path, server):
    licensing = service(tmp_path, server)
    server.claims = {"hesap_turu": "bireysel"}
    licensing.login("operator", "dogru")
    assert licensing.status()["license"]["account_type"] == "bireysel"
    server.claims = {"hesap_turu": "yonetici"}
    licensing.refresh()
    assert licensing.status()["license"]["account_type"] == ""
    server.claims = {}
    licensing.refresh()
    assert licensing.status()["license"]["account_type"] == ""


def test_password_change_goes_to_the_account_service_and_signs_in_with_the_new_password(tmp_path, server):
    licensing = service(tmp_path, server)
    licensing.login("operator", "dogru")
    with pytest.raises(LicenseError, match="mevcut şifre hatalı"):
        licensing.change_password("yanlis", "Yepyeni2027")
    with pytest.raises(LicenseError, match="8-128"):
        licensing.change_password("dogru", "kisa")
    status = licensing.change_password("dogru", "Yepyeni2027")
    assert status["state"] == "valid" and server.password == "Yepyeni2027"
    change = [body for endpoint, body in server.requests if endpoint == "hesap/sifre"][-1]
    # The full e-mail of the signed license is used, so the right account changes.
    assert change == {"kullanici": "operator@ornek.com.tr", "sifre": "dogru", "yeni_sifre": "Yepyeni2027"}
    assert server.requests[-1][0] == "giris" and server.requests[-1][1]["kullanici"] == "operator@ornek.com.tr"
    assert "Yepyeni2027" not in (tmp_path / "license.json").read_text()


def test_password_change_needs_a_signed_in_account(tmp_path, server):
    with pytest.raises(LicenseError, match="oturum"):
        service(tmp_path, server).change_password("dogru", "Yepyeni2027")
    assert server.requests == []


def test_reset_code_sets_a_new_password_before_sign_in_and_works_once(tmp_path, server):
    licensing = service(tmp_path, server)
    assert "/api/license/reset" in OPEN_PATHS and "/api/license/password" not in OPEN_PATHS
    with pytest.raises(LicenseError, match="yenileme kodu hatalı"):
        licensing.reset_password("operator@ornek.com.tr", "YANL-ISKO-DXXX", "Yepyeni2027")
    assert licensing.status()["state"] == "login_required"
    with pytest.raises(LicenseError, match="E-posta"):
        licensing.reset_password("operator", "ABCD-EFGH-JKLM", "Yepyeni2027")
    status = licensing.reset_password(" operator@ornek.com.tr ", "ABCD-EFGH-JKLM", "Yepyeni2027")
    assert status["state"] == "valid" and server.password == "Yepyeni2027"
    with pytest.raises(LicenseError):
        licensing.reset_password("operator@ornek.com.tr", "ABCD-EFGH-JKLM", "Baska2028")


def test_waiting_application_message_from_orkestrai_is_shown_at_sign_in(tmp_path, server):
    server.password = "baska"
    message = "Başvurunuz alındı; ödemeniz onaylandığında hesabınız açılır ve bu e-posta ile şifrenizle giriş yapabilirsiniz."

    def waiting(request, timeout):
        return server.error(403, "BASVURU_BEKLIYOR", message)

    server.open = waiting
    with pytest.raises(LicenseError, match="ödemeniz onaylandığında"):
        service(tmp_path, server).login("ayse@ornek.test", "Guclu2026")


@pytest.mark.skipif(os.environ.get("RPA_UI_TESTS") != "1", reason="Opt-in Chromium license screens")
def test_personal_account_screens_reset_and_change_the_password(tmp_path, server):
    from fastapi.testclient import TestClient
    from test_licensing import Timer

    playwright = pytest.importorskip("playwright.sync_api")
    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    errors = []
    server.claims = {"hesap_turu": "bireysel"}
    settings = Settings(tmp_path / "data", dotenv=False)
    licensing = service(settings.data_dir, server, Timer())
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
        playwright.expect(card.get_by_role("link", name="orkestrai.net/rpa")).to_have_attribute(
            "href", "https://orkestrai.net/rpa/#bireysel")
        card.locator('input[autocomplete="username"]').fill("operator@ornek.com.tr")
        card.get_by_role("button", name="Şifre yenileme kodum var").click()
        reset = page.locator("dialog")
        playwright.expect(reset.locator('input[type="email"]')).to_have_value("operator@ornek.com.tr")
        reset.locator('input[autocomplete="one-time-code"]').fill("YANL-ISKO-DXXX")
        reset.locator('input[autocomplete="new-password"]').nth(0).fill("Yepyeni2027")
        reset.locator('input[autocomplete="new-password"]').nth(1).fill("Yepyeni2028")
        reset.get_by_role("button", name="Şifreyi yenile ve giriş yap").click()
        playwright.expect(reset.locator(".license-message")).to_contain_text("aynı değil")
        reset.locator('input[autocomplete="new-password"]').nth(1).fill("Yepyeni2027")
        reset.get_by_role("button", name="Şifreyi yenile ve giriş yap").click()
        playwright.expect(reset.locator(".license-message")).to_contain_text("yenileme kodu hatalı")
        reset.locator('input[autocomplete="one-time-code"]').fill("ABCD-EFGH-JKLM")
        reset.get_by_role("button", name="Şifreyi yenile ve giriş yap").click()
        playwright.expect(page.locator(".license-screen")).to_have_count(0)
        assert server.password == "Yepyeni2027"

        page.get_by_role("button", name="Ayarlar").first.click()
        panel = page.locator(".license-facts")
        playwright.expect(panel).to_contain_text("Bireysel hesap")
        playwright.expect(panel).not_to_contain_text("Örnek Lojistik")
        playwright.expect(page.get_by_role("link", name="Lisansı uzat")).to_have_attribute(
            "href", "https://orkestrai.net/rpa/#bireysel")
        page.get_by_role("button", name="Şifreyi değiştir").click()
        change = page.locator("dialog")
        change.locator('input[autocomplete="current-password"]').fill("yanlis")
        change.locator('input[autocomplete="new-password"]').nth(0).fill("Sonraki2028")
        change.locator('input[autocomplete="new-password"]').nth(1).fill("Sonraki2028")
        change.get_by_role("button", name="Şifreyi değiştir").click()
        playwright.expect(change.locator(".license-message")).to_contain_text("mevcut şifre hatalı")
        change.locator('input[autocomplete="current-password"]').fill("Yepyeni2027")
        change.get_by_role("button", name="Şifreyi değiştir").click()
        playwright.expect(page.locator(".toast").last).to_contain_text("Şifreniz değiştirildi")
        assert server.password == "Sonraki2028" and licensing.status()["state"] == "valid"
        browser.close()
    assert not errors
