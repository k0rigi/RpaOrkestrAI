import base64
import io
import json
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from rpa_orkestrai.app import create_app
from rpa_orkestrai.config import Settings
from rpa_orkestrai.licensing import LicenseError, LicenseService

TR = timezone(timedelta(hours=3))
START = datetime(2026, 9, 28, 10, 0, tzinfo=TR).timestamp()


class Clock:
    def __init__(self, value=START):
        self.value = value

    def __call__(self):
        return self.value


class Response(io.BytesIO):
    def __init__(self, status, body):
        super().__init__(json.dumps(body).encode())
        self.status = status


class FakeOrkestrai:
    """Signs like orkestrai.net: seven offline days, never past the company's end date."""

    def __init__(self, clock):
        self.key = Ed25519PrivateKey.generate()
        self.clock = clock
        self.ends_on = "2027-09-27"
        self.denial = None
        self.offline = False
        self.requests = []

    @property
    def public_key(self):
        raw = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return base64.b64encode(raw).decode()

    def signed(self, device, *, ends_on=None, product="rpa-orkestrai"):
        now = datetime.fromtimestamp(self.clock(), TR).replace(microsecond=0)
        ends = ends_on if ends_on is not None else self.ends_on
        valid = now + timedelta(days=7)
        if ends:
            end = datetime.fromisoformat(ends + "T23:59:59+03:00")
            valid = min(valid, end)
        payload = json.dumps({
            "surum": 1, "urun": product, "modul": "MOD_RPA", "kullanici_id": 42,
            "kullanici": "fcoruh@bsg.com.tr", "ad_soyad": "Fatih Çoruh", "firma_id": 2,
            "firma_adi": "BSG", "bitis": ends or None, "cihaz": device,
            "verildi": now.isoformat(), "gecerlilik": valid.isoformat(),
        }, ensure_ascii=False).encode()
        return {"payload": base64.b64encode(payload).decode(),
                "signature": base64.b64encode(self.key.sign(payload)).decode()}

    def open(self, request, timeout):
        body = json.loads(request.data)
        self.requests.append((request.full_url.rsplit("/", 1)[-1], body))
        if self.offline:
            raise URLError("offline")
        if request.full_url.endswith("/giris") and body["sifre"] != "dogru":
            return self.error(401, "HATALI_GIRIS", "Kullanıcı adı veya şifre hatalı.")
        if request.full_url.endswith("/yenile") and body["token"] != "yenileme-" + body["cihaz"]:
            return self.error(401, "OTURUM_GECERSIZ", "Oturumun süresi doldu.")
        if self.denial:
            return self.error(403, *self.denial)
        return Response(200, {"success": True, "lisans": self.signed(body["cihaz"]),
                              "yenileme": "yenileme-" + body["cihaz"]})

    @staticmethod
    def error(status, code, message, ends_on=None):
        payload = {"success": False, "kod": code, "message": message}
        if ends_on:
            payload["bitis"] = ends_on
        raise HTTPError("https://orkestrai.net/api/rpa/lisans", status, message, {},
                        io.BytesIO(json.dumps(payload).encode()))


@pytest.fixture
def server():
    return FakeOrkestrai(Clock())


def service(tmp_path, server, machine="machine-a"):
    return LicenseService(tmp_path, public_key=server.public_key, opener=server, clock=server.clock,
                          machine_id=lambda: machine)


def test_login_keeps_only_signed_license_and_session(tmp_path, server):
    licensing = service(tmp_path, server)
    assert licensing.status()["state"] == "login_required"
    assert licensing.allowed() is False

    status = licensing.login("fcoruh", "dogru")

    assert status["state"] == "valid" and status["online"] is True
    assert status["license"]["company"] == "BSG" and status["license"]["ends_on"] == "2027-09-27"
    assert licensing.allowed()
    stored = (tmp_path / "license.json").read_text(encoding="utf-8")
    assert "dogru" not in stored
    assert server.requests[0][1]["kullanici"] == "fcoruh"
    # Reopening offline uses the signed license without asking again.
    server.offline = True
    reopened = service(tmp_path, server)
    assert reopened.allowed()
    assert reopened.refresh()["state"] == "valid"
    assert reopened.status()["online"] is False


def test_wrong_password_is_reported_without_changing_state(tmp_path, server):
    licensing = service(tmp_path, server)
    with pytest.raises(LicenseError, match="hatalı"):
        licensing.login("fcoruh", "yanlis")
    assert licensing.status()["state"] == "login_required"


def test_offline_use_ends_after_seven_days(tmp_path, server):
    licensing = service(tmp_path, server)
    licensing.login("fcoruh", "dogru")
    server.offline = True
    server.clock.value += timedelta(days=6, hours=23).total_seconds()
    assert licensing.allowed()
    server.clock.value += timedelta(hours=2).total_seconds()
    assert not licensing.allowed()
    assert licensing.status()["state"] == "verification_required"
    server.offline = False
    assert licensing.refresh()["state"] == "valid"


def test_offline_license_never_outlives_the_company_end_date(tmp_path, server):
    server.ends_on = "2026-10-01"
    licensing = service(tmp_path, server)
    licensing.login("fcoruh", "dogru")
    server.offline = True
    server.clock.value = datetime(2026, 10, 1, 23, 0, tzinfo=TR).timestamp()
    assert licensing.allowed()
    server.clock.value = datetime(2026, 10, 2, 9, 0, tzinfo=TR).timestamp()
    status = licensing.status()
    assert status["state"] == "expired"
    assert "01.10.2026" in status["message"]


def test_rolling_the_clock_back_requires_online_verification(tmp_path, server):
    licensing = service(tmp_path, server)
    licensing.login("fcoruh", "dogru")
    server.clock.value += 3600
    assert licensing.allowed()
    server.clock.value -= 2 * 3600
    assert not licensing.allowed()
    assert licensing.status()["state"] == "verification_required"


def test_wrong_local_clock_uses_server_time(tmp_path, server):
    local = Clock(START + timedelta(days=30).total_seconds())
    licensing = LicenseService(tmp_path, public_key=server.public_key, opener=server, clock=local,
                               machine_id=lambda: "machine-a")
    assert licensing.login("fcoruh", "dogru")["state"] == "valid"
    assert licensing.allowed()


def test_expired_company_license_is_remembered_and_renewal_is_picked_up(tmp_path, server):
    licensing = service(tmp_path, server)
    licensing.login("fcoruh", "dogru")
    server.denial = ("SURE_DOLDU", "RpaOrkestrAI kullanım süreniz 27.09.2027 tarihinde dolmuştur.", "2027-09-27")

    status = licensing.refresh()

    assert status["state"] == "expired" and "27.09.2027" in status["message"]
    assert not licensing.allowed()
    server.offline = True
    assert service(tmp_path, server).status()["state"] == "expired"
    server.offline, server.denial = False, None
    assert service(tmp_path, server).refresh()["state"] == "valid"


def test_unassigned_user_is_denied_and_revoked_session_needs_login(tmp_path, server):
    licensing = service(tmp_path, server)
    server.denial = ("YETKI_YOK", "Bu kullanıcı için RpaOrkestrAI lisansı tanımlı değil.")
    status = licensing.login("fcoruh", "dogru")
    assert status["state"] == "denied" and status["license"]["user"] == "fcoruh"
    assert status["remembered"] is False

    server.denial = None
    licensing.login("fcoruh", "dogru")
    server.denial = ("OTURUM_GECERSIZ", "Oturumun süresi doldu.")
    assert licensing.refresh()["state"] == "login_required"
    assert licensing.status()["remembered"] is False


def test_license_is_bound_to_the_computer_and_signature(tmp_path, server):
    service(tmp_path, server).login("fcoruh", "dogru")
    assert service(tmp_path, server, machine="machine-b").status()["state"] == "login_required"

    stored = json.loads((tmp_path / "license.json").read_text(encoding="utf-8"))
    payload = json.loads(base64.b64decode(stored["license"]["payload"]))
    payload["gecerlilik"] = "2099-01-01T00:00:00+03:00"
    stored["license"]["payload"] = base64.b64encode(json.dumps(payload).encode()).decode()
    (tmp_path / "license.json").write_text(json.dumps(stored), encoding="utf-8")
    assert service(tmp_path, server).status()["state"] == "login_required"


def test_license_for_another_product_is_rejected(tmp_path, server):
    licensing = service(tmp_path, server)
    original = server.signed

    def other_product(device, **kwargs):
        return original(device, product="baska-urun")

    server.signed = other_product
    with pytest.raises(LicenseError):
        licensing.login("fcoruh", "dogru")
    assert licensing.status()["state"] == "login_required"


def test_logout_forgets_the_session(tmp_path, server):
    licensing = service(tmp_path, server)
    licensing.login("fcoruh", "dogru")
    assert licensing.logout()["state"] == "login_required"
    assert json.loads((tmp_path / "license.json").read_text(encoding="utf-8"))["refresh"] is None


@pytest.mark.real_license
def test_studio_api_requires_a_license(tmp_path, server):
    settings = Settings(tmp_path / "data", dotenv=False)
    licensing = service(settings.data_dir, server)
    with TestClient(create_app(settings, licensing=licensing)) as client:
        blocked = client.get("/api/bootstrap")
        assert blocked.status_code == 403
        assert blocked.json()["license"]["state"] == "login_required"
        assert client.get("/api/workflows").status_code == 403
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/license").json()["can_quit"] is False

        wrong = client.post("/api/license/login", json={"username": "fcoruh", "password": "yanlis"})
        assert wrong.status_code == 422 and "hatalı" in wrong.json()["detail"]
        assert client.post("/api/license/login",
                           json={"username": "fcoruh", "password": "dogru"}).json()["state"] == "valid"
        assert client.get("/api/bootstrap").status_code == 200

        server.offline = True
        unavailable = client.post("/api/license/logout")
        assert unavailable.json()["state"] == "login_required"
        failed = client.post("/api/license/login", json={"username": "fcoruh", "password": "dogru"})
        assert failed.status_code == 503
        assert client.post("/api/license/quit").status_code == 409
