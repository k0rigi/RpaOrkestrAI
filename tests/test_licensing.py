"""The license gate: the Studio opens only on a fresh confirmation from orkestrai.net."""

import base64
import io
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from rpa_orkestrai import licensing as licensing_module
from rpa_orkestrai.app import create_app
from rpa_orkestrai.config import Settings
from rpa_orkestrai.licensing import (
    TOLERANCE_MESSAGE,
    LicenseError,
    LicenseService,
    LicenseUnavailable,
)

TR = timezone(timedelta(hours=3))
OTHER_COMPUTER = ("Bu hesap başka bir bilgisayarda açıldığı için bu bilgisayardaki oturum kapatıldı. "
                  "Devam etmek için yeniden giriş yapın.")


class Timer:
    """The Studio's own elapsed-time clock; the computer's date plays no part."""

    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        return self.value


class Response(io.BytesIO):
    def __init__(self, status, body):
        super().__init__(json.dumps(body).encode())
        self.status = status


class FakeOrkestrai:
    """Answers like orkestrai.net: signs the request's random value and keeps one session per account."""

    def __init__(self):
        self.key = Ed25519PrivateKey.generate()
        self.ends_on = "2027-09-27"
        self.denial = None
        self.offline = False
        self.requests = []
        self.session = None      # the account's single active session
        self.claims = {}         # extra signed fields, e.g. tolerans / aralik
        self.replayed = None     # an earlier answer sent again instead of a fresh one
        self.lose_answers = 0    # answers that are processed but never reach the Studio
        self.last = None

    @property
    def public_key(self):
        raw = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return base64.b64encode(raw).decode()

    def signed(self, device, nonce=None, *, product="rpa-orkestrai"):
        now = datetime(2026, 10, 3, 10, 0, tzinfo=TR)
        claims = {
            "surum": 1, "urun": product, "modul": "MOD_RPA", "kullanici_id": 42,
            "kullanici": "operator@ornek.com.tr", "ad_soyad": "Örnek Operatör", "firma_id": 2,
            "firma_adi": "Örnek Lojistik", "bitis": self.ends_on or None, "cihaz": device,
            "verildi": now.isoformat(), "gecerlilik": (now + timedelta(hours=1)).isoformat(),
            "tolerans": 3600, "aralik": 600, **self.claims,
        }
        if nonce is not None:
            claims["nonce"] = nonce
        payload = json.dumps(claims, ensure_ascii=False).encode()
        return {"payload": base64.b64encode(payload).decode(),
                "signature": base64.b64encode(self.key.sign(payload)).decode()}

    def token(self):
        return "oturum.{id}.{number}.{device}".format(**self.session)

    def open(self, request, timeout):
        endpoint = request.full_url.rsplit("/", 1)[-1]
        body = json.loads(request.data)
        self.requests.append((endpoint, body))
        if self.offline:
            raise URLError("offline")
        if endpoint == "cikis":
            if self.session and body["token"] == self.token():
                self.session = None
            return Response(200, {"success": True})
        if endpoint == "giris":
            if body["sifre"] != "dogru":
                return self.error(401, "HATALI_GIRIS", "Kullanıcı adı veya şifre hatalı.")
            if self.denial:
                return self.error(403, *self.denial)
            # A sign-in opens a new session and closes the account's session on any other computer.
            self.session = {"id": uuid.uuid4().hex, "number": 0, "device": body["cihaz"],
                            "instance": body.get("ornek"), "repeats": 0}
        else:
            parts = body["token"].split(".")
            if len(parts) != 4 or parts[3] != body["cihaz"]:
                return self.error(401, "OTURUM_GECERSIZ", "Oturumun süresi doldu. Yeniden giriş yapın.")
            if self.denial:
                return self.error(403, *self.denial)
            session = self.session
            if session is None or parts[1] != session["id"]:
                return self.error(401, "OTURUM_GECERSIZ", OTHER_COMPUTER, neden="BASKA_CIHAZ")
            number, instance = int(parts[2]), body.get("ornek")
            if number == session["number"]:
                session.update(number=number + 1, instance=instance)
            elif number == session["number"] - 1 and instance and instance == session["instance"]:
                pass  # the Studio that moved the session on never got the answer and asks again
            else:
                # The same session presented by another running copy.
                session["repeats"] += 1
                if number != session["number"] - 1 or session["repeats"] >= 2:
                    self.session = None
                    return self.error(401, "OTURUM_GECERSIZ", "Bu oturum aynı anda birden fazla yerde "
                                      "kullanıldığı için kapatıldı. Yeniden giriş yapın.", neden="KOPYA")
                session["instance"] = instance
        if self.lose_answers:
            self.lose_answers -= 1
            raise URLError("connection lost")
        answer = {"success": True, "lisans": self.signed(body["cihaz"], body.get("nonce")),
                  "yenileme": self.token()}
        if self.replayed is not None:
            return Response(200, self.replayed)
        self.last = answer
        return Response(200, answer)

    @staticmethod
    def error(status, code, message, ends_on=None, cause=None, **extra):
        payload = {"success": False, "kod": code, "message": message, **extra}
        if ends_on:
            payload["bitis"] = ends_on
        if cause:
            payload["neden"] = cause
        raise HTTPError("https://orkestrai.net/api/rpa/lisans", status, message, {},
                        io.BytesIO(json.dumps(payload).encode()))


@pytest.fixture
def server():
    return FakeOrkestrai()


@pytest.fixture
def timer():
    return Timer()


def service(tmp_path, server, timer=None, machine="machine-a"):
    return LicenseService(tmp_path, public_key=server.public_key, opener=server,
                          monotonic=timer or Timer(), machine_id=lambda: machine)


def test_login_asks_for_a_fresh_signed_answer_and_stores_no_license(tmp_path, server, timer):
    licensing = service(tmp_path, server, timer)
    assert licensing.status()["state"] == "login_required" and licensing.allowed() is False

    status = licensing.login("operator", "dogru")

    assert status["state"] == "valid" and status["online"] is True and licensing.allowed()
    assert status["license"] == {"user": "operator@ornek.com.tr", "full_name": "Örnek Operatör",
                                 "company": "Örnek Lojistik", "ends_on": "2027-09-27"}
    endpoint, body = server.requests[0]
    assert endpoint == "giris" and body["kullanici"] == "operator" and body["protokol"] == 2
    assert len(body["nonce"]) == 32 and body["cihaz"] == licensing.device
    # The workspace keeps only a stable installation identifier, never credentials or a session.
    stored = json.loads((tmp_path / "license.json").read_text(encoding="utf-8"))
    assert set(stored) == {"install"} and "dogru" not in json.dumps(stored)
    # Every request carries its own random value.
    licensing.refresh()
    assert server.requests[1][1]["nonce"] != body["nonce"]


def test_wrong_password_is_reported_without_changing_state(tmp_path, server):
    licensing = service(tmp_path, server)
    with pytest.raises(LicenseError, match="hatalı"):
        licensing.login("operator", "yanlis")
    assert licensing.status()["state"] == "login_required"


def test_a_restart_requires_username_and_password_and_a_fresh_license(tmp_path, server):
    running = service(tmp_path, server)
    running.login("operator", "dogru")
    path = tmp_path / "license.json"
    stored = json.loads(path.read_text())
    # Migration from 0.9.5 also forgets the saved session and username.
    stored.update(refresh=running._refresh_token, user="operator")
    path.write_text(json.dumps(stored))
    reopened = service(tmp_path, server)
    assert reopened.device == running.device
    assert reopened.status()["state"] == "login_required"
    assert not reopened.status()["remembered"] and reopened.status()["license"] is None
    before = len(server.requests)
    assert reopened.refresh()["state"] == "login_required" and not reopened.allowed()
    assert len(server.requests) == before
    assert json.loads(path.read_text()) == {"install": stored["install"]}
    assert reopened.login("operator", "dogru")["state"] == "valid"

    server.offline = True
    offline = service(tmp_path, server)
    with pytest.raises(LicenseUnavailable):
        offline.login("operator", "dogru")
    assert not offline.allowed() and offline.status()["state"] == "login_required"
    server.offline = False
    assert offline.login("operator", "dogru")["state"] == "valid"


def test_withdrawn_license_closes_the_studio_and_a_restored_one_reopens_it(tmp_path, server, timer):
    reasons = []
    licensing = service(tmp_path, server, timer)
    licensing.on_locked = reasons.append
    licensing.login("operator", "dogru")
    server.denial = ("YETKI_YOK", "Bu kullanıcı için RpaOrkestrAI lisansı tanımlı değil.")

    status = licensing.refresh()

    assert status["state"] == "denied" and "tanımlı değil" in status["message"]
    assert licensing.allowed() is False and reasons == ["denied"]
    assert status["license"]["user"] == "operator@ornek.com.tr" and status["remembered"]
    # Closing and reopening does not help, with or without a connection.
    assert service(tmp_path, server).login("operator", "dogru")["state"] == "denied"
    server.offline = True
    blocked = service(tmp_path, server)
    assert blocked.refresh()["state"] == "login_required" and blocked.allowed() is False
    # Once the license is given back, the kept session continues without the password.
    server.offline, server.denial = False, None
    assert licensing.refresh()["state"] == "valid" and licensing.allowed()


def test_expired_company_license_reports_the_end_date(tmp_path, server):
    reasons = []
    licensing = service(tmp_path, server)
    licensing.on_locked = reasons.append
    licensing.login("operator", "dogru")
    server.denial = ("SURE_DOLDU", "RpaOrkestrAI kullanım süreniz 27.09.2027 tarihinde dolmuştur.", "2027-09-27")

    status = licensing.refresh()

    assert status["state"] == "expired" and "27.09.2027" in status["message"]
    assert status["license"]["ends_on"] == "2027-09-27" and reasons == ["expired"]
    assert not licensing.allowed()


def test_a_version_that_is_no_longer_served_is_told_to_update(tmp_path, server):
    licensing = service(tmp_path, server)
    licensing.login("operator", "dogru")
    assert licensing.status()["detail"] is None
    server.denial = ("YETKI_YOK", "Bu RpaOrkestrAI sürümü artık desteklenmiyor. Güncel sürümü "
                                  "https://orkestrai.net/rpa adresinden kurun.", None, "ESKI_SURUM")

    status = licensing.refresh()

    assert status["state"] == "denied" and status["detail"] == "outdated"
    assert "orkestrai.net/rpa" in status["message"] and licensing.allowed() is False
    assert service(tmp_path, server).login("operator", "dogru")["detail"] == "outdated"
    # A plain refusal carries no such detail.
    server.denial = ("YETKI_YOK", "Bu kullanıcı için RpaOrkestrAI lisansı tanımlı değil.")
    assert licensing.refresh()["detail"] is None


def test_running_studio_continues_for_a_limited_time_without_a_connection(tmp_path, server, timer):
    licensing = service(tmp_path, server, timer)
    licensing.login("operator", "dogru")
    server.offline = True

    timer.value += 59 * 60
    assert licensing.refresh()["state"] == "valid" and licensing.allowed()
    timer.value += 2 * 60
    status = licensing.status()
    assert status["state"] == "verification_required" and status["message"] == TOLERANCE_MESSAGE
    assert licensing.allowed() is False
    # The connection returns: the next check opens the Studio again.
    server.offline = False
    assert licensing.refresh()["state"] == "valid" and licensing.allowed()


def test_background_check_stops_work_when_the_time_without_an_answer_runs_out(tmp_path, server, timer):
    reasons = []
    licensing = service(tmp_path, server, timer)
    licensing.on_locked = reasons.append
    licensing.login("operator", "dogru")
    assert licensing._tick() == 600 and reasons == []      # confirmed: next check in ten minutes
    server.offline = True
    timer.value += 3500
    # Unanswered checks are repeated soon, a little later each time; the Studio is still open.
    assert [licensing._tick() for _ in range(5)] == [5, 10, 20, 30, 30] and reasons == []
    assert licensing.allowed()
    # The allowed time runs out: the Studio locks at once, running work stops a minute later.
    timer.value += 200
    licensing._tick()
    assert licensing.allowed() is False and reasons == []
    timer.value += 59
    licensing._tick()
    assert reasons == []
    timer.value += 1
    licensing._tick()
    assert reasons == ["unverified"]
    server.offline = False
    assert licensing._tick() == 600 and licensing.allowed()


def test_a_computer_waking_from_sleep_reconnects_before_work_is_stopped(tmp_path, server, timer):
    reasons = []
    licensing = service(tmp_path, server, timer)
    licensing.on_locked = reasons.append
    licensing.login("operator", "dogru")
    # The clock jumps past the allowed time and the network is not back yet.
    timer.value += 9 * 3600
    server.offline = True
    assert licensing._tick() == 5 and licensing.allowed() is False
    timer.value += 5
    server.offline = False
    assert licensing._tick() == 600 and licensing.allowed() and reasons == []


def test_times_come_from_the_signed_license_within_bounds(tmp_path, server, timer):
    server.claims = {"tolerans": 10 ** 9, "aralik": 1}
    licensing = service(tmp_path, server, timer)
    licensing.login("operator", "dogru")
    assert (licensing._interval, licensing._tolerance) == (60, 6 * 3600)
    server.offline = True
    timer.value += 6 * 3600 + 1
    assert licensing.allowed() is False
    # Missing or malformed values fall back to the defaults.
    server.offline, server.claims = False, {"tolerans": "uzun", "aralik": None}
    licensing.refresh()
    assert (licensing._interval, licensing._tolerance) == (600, 3600)


def test_an_earlier_answer_is_not_accepted_again(tmp_path, server):
    licensing = service(tmp_path, server)
    licensing.login("operator", "dogru")
    server.replayed = server.last  # a correctly signed answer, but to an earlier request

    reopened = service(tmp_path, server)
    reopened._refresh_token = licensing._refresh_token  # simulate replay against an unverified runtime session
    status = reopened.refresh()

    assert status["state"] == "verification_required" and reopened.allowed() is False
    # An answer without the request's value (an older server) is refused as well.
    server.replayed = {"success": True, "lisans": server.signed(reopened.device), "yenileme": "oturum." + "x" * 40}
    assert reopened.refresh()["state"] == "verification_required"
    # Signing in is held to the same rule: same computer, right signature, but not this request's answer.
    server.replayed = server.last
    with pytest.raises(LicenseUnavailable, match="doğrulanamadı"):
        service(tmp_path, server).login("operator", "dogru")
    assert reopened.allowed() is False
    server.replayed = None
    assert service(tmp_path, server).login("operator", "dogru")["state"] == "valid"


def test_nothing_in_the_workspace_file_opens_the_studio(tmp_path, server, monkeypatch):
    licensing = service(tmp_path, server)
    licensing.login("operator", "dogru")
    path = tmp_path / "license.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    # What version 0.7 kept here, plus hand-edited numbers: all of it is ignored and dropped.
    stored.update({"license": server.signed(licensing.device), "skew": -10 ** 7, "last_seen": 0,
                   "verified": 10 ** 12, "valid_until": "2099-01-01T00:00:00+03:00"})
    path.write_text(json.dumps(stored), encoding="utf-8")
    server.offline = True

    reopened = service(tmp_path, server)

    assert reopened.allowed() is False and reopened.refresh()["state"] == "login_required"
    assert set(json.loads(path.read_text(encoding="utf-8"))) == {"install"}
    # The computer's date plays no part either way: a wrong clock neither opens nor locks the Studio.
    # What counts is the answer to this run's own request and the running time since then.
    def no_date():
        raise AssertionError("the computer's date must not be read")

    monkeypatch.setattr(licensing_module.time, "time", no_date)
    server.offline = False
    server.claims = {"verildi": "2001-01-01T00:00:00+03:00", "gecerlilik": "2001-01-01T01:00:00+03:00"}
    assert reopened.login("operator", "dogru")["state"] == "valid" and reopened.allowed()


def test_signing_in_on_another_computer_closes_this_session(tmp_path, server):
    reasons = []
    first = service(tmp_path / "pc1", server, machine="machine-a")
    first.on_locked = reasons.append
    first.login("operator", "dogru")
    second = service(tmp_path / "pc2", server, machine="machine-b")
    assert second.login("operator", "dogru")["state"] == "valid"

    status = first.refresh()

    assert status["state"] == "login_required" and status["message"] == OTHER_COMPUTER
    assert status["remembered"] is False and first.allowed() is False and reasons == ["session"]
    assert status["license"]["user"] == "operator@ornek.com.tr"  # offered again in the sign-in form
    assert second.refresh()["state"] == "valid"
    # A copy of the workspace on another computer has a different device identity.
    copied = tmp_path / "pc3"
    copied.mkdir()
    (copied / "license.json").write_bytes((tmp_path / "pc2" / "license.json").read_bytes())
    stranger = service(copied, server, machine="machine-c")
    assert stranger.device != second.device and stranger.refresh()["state"] == "login_required"


def test_one_session_cannot_run_in_two_places(tmp_path, server):
    original = service(tmp_path / "a", server)
    original.login("operator", "dogru")
    duplicate_dir = tmp_path / "b"
    duplicate_dir.mkdir()
    (duplicate_dir / "license.json").write_bytes((tmp_path / "a" / "license.json").read_bytes())
    duplicate = service(duplicate_dir, server)
    # Simulate theft of the in-memory token to retain server session-copy protection coverage.
    duplicate._refresh_token = original._refresh_token

    assert duplicate.refresh()["state"] == "valid"   # moves the session forward
    assert original.refresh()["state"] == "valid"    # one step behind: could still be a lost answer
    assert duplicate.refresh()["state"] == "valid"
    status = original.refresh()                       # behind again: the session runs in two places

    assert status["state"] == "login_required" and "birden fazla yerde" in status["message"]
    assert duplicate.refresh()["state"] == "login_required"


def test_a_lost_answer_does_not_close_the_session(tmp_path, server, timer):
    reasons = []
    licensing = service(tmp_path, server, timer)
    licensing.on_locked = reasons.append
    licensing.login("operator", "dogru")
    # orkestrai.net moves the session on, but its answers never arrive.
    server.lose_answers = 3
    for _ in range(3):
        status = licensing.refresh()
        assert status["state"] == "valid" and status["online"] is False
    # The same running Studio asks again with what it has and simply continues.
    assert licensing.refresh() == {**status, "online": True}
    assert licensing.refresh()["state"] == "valid" and reasons == []
    # Closed before the answer arrived: next launch still requires explicit login.
    server.lose_answers = 1
    licensing.refresh()
    assert service(tmp_path, server).refresh()["state"] == "login_required"


def test_unexpected_answers_are_not_a_confirmation(tmp_path, server):
    running = service(tmp_path, server)
    running.login("operator", "dogru")
    reopened = service(tmp_path, server)
    reopened._refresh_token = running._refresh_token
    server.denial = ("COK_DENEME", "Çok fazla deneme.")
    assert reopened.refresh()["state"] == "verification_required" and reopened.allowed() is False
    server.denial = None
    original = server.signed
    server.signed = lambda device, nonce=None: original(device, nonce, product="baska-urun")
    assert reopened.refresh()["state"] == "verification_required"
    with pytest.raises(LicenseError):
        service(tmp_path / "new", server).login("operator", "dogru")


def test_unassigned_user_is_denied_at_login(tmp_path, server):
    licensing = service(tmp_path, server)
    server.denial = ("YETKI_YOK", "Bu kullanıcı için RpaOrkestrAI lisansı tanımlı değil.")
    status = licensing.login("operator", "dogru")
    assert status["state"] == "denied" and status["license"]["user"] == "operator"
    assert status["remembered"] is False


def test_logout_closes_the_session_on_the_server_and_forgets_it(tmp_path, server):
    licensing = service(tmp_path, server)
    licensing.login("operator", "dogru")
    token = server.token()

    assert licensing.logout()["state"] == "login_required"

    assert server.requests[-1] == ("cikis", {"token": token, "cihaz": licensing.device})
    assert server.session is None
    stored = json.loads((tmp_path / "license.json").read_text(encoding="utf-8"))
    assert set(stored) == {"install"}
    # Signing out also works without a connection.
    licensing.login("operator", "dogru")
    server.offline = True
    assert licensing.logout()["state"] == "login_required" and licensing.allowed() is False


def test_background_check_waits_for_login_after_restart(tmp_path, server):
    service(tmp_path, server).login("operator", "dogru")
    licensing = service(tmp_path, server)
    count = len(server.requests)
    licensing._tick()
    assert licensing.status()["state"] == "login_required" and not licensing.allowed()
    assert len(server.requests) == count
    licensing.login("operator", "dogru")
    assert licensing._tick() == 600 and licensing.allowed()


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

        wrong = client.post("/api/license/login", json={"username": "operator", "password": "yanlis"})
        assert wrong.status_code == 422 and "hatalı" in wrong.json()["detail"]
        assert client.post("/api/license/login",
                           json={"username": "operator", "password": "dogru"}).json()["state"] == "valid"
        assert client.get("/api/bootstrap").status_code == 200

        server.offline = True
        unavailable = client.post("/api/license/logout")
        assert unavailable.json()["state"] == "login_required"
        failed = client.post("/api/license/login", json={"username": "operator", "password": "dogru"})
        assert failed.status_code == 503
        assert client.post("/api/license/quit").status_code == 409


@pytest.mark.real_license
def test_a_running_flow_stops_when_the_license_is_withdrawn(tmp_path, server):
    settings = Settings(tmp_path / "data", dotenv=False)
    licensing = service(settings.data_dir, server)
    with TestClient(create_app(settings, licensing=licensing)) as client:
        client.post("/api/license/login", json={"username": "operator", "password": "dogru"})
        workflow = client.post("/api/workflows", json={"name": "Uzun", "steps": [
            {"action": "control.repeat", "params": {"count": 200}, "children": [
                {"action": "core.wait", "params": {"seconds": 0.2}}]}]}).json()
        run = client.post(f"/api/workflows/{workflow['id']}/run", json={"dry_run": False}).json()

        server.denial = ("YETKI_YOK", "Bu kullanıcı için RpaOrkestrAI lisansı tanımlı değil.")
        assert licensing.refresh()["state"] == "denied"

        # The API is closed at once, and the flow ends at its next step instead of running on.
        assert client.get(f"/api/runs/{run['id']}").status_code == 403
        store = client.app.state.manager.store
        deadline = time.monotonic() + 10
        while store.run(run["id"]).status in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(0.05)
        finished = store.run(run["id"])
        assert finished.status == "cancelled" and "Lisans" in finished.error
        # Nothing new starts either, even for code that bypasses the HTTP layer.
        with pytest.raises(RuntimeError, match="Lisans doğrulanamadığı"):
            client.app.state.manager.start(store.workflow(workflow["id"]))


@pytest.mark.real_license
def test_a_running_flow_stops_when_the_connection_stays_away_too_long(tmp_path, server, timer):
    settings = Settings(tmp_path / "data", dotenv=False)
    licensing = service(settings.data_dir, server, timer)
    with TestClient(create_app(settings, licensing=licensing)) as client:
        client.post("/api/license/login", json={"username": "operator", "password": "dogru"})
        workflow = client.post("/api/workflows", json={"name": "Uzun", "steps": [
            {"action": "control.repeat", "params": {"count": 200}, "children": [
                {"action": "core.wait", "params": {"seconds": 0.2}}]}]}).json()
        run = client.post(f"/api/workflows/{workflow['id']}/run", json={"dry_run": False}).json()
        store = client.app.state.manager.store

        # Within the allowed time the flow keeps running without a connection.
        server.offline = True
        timer.value += 3000
        licensing._tick()
        assert client.get(f"/api/runs/{run['id']}").json()["status"] in {"queued", "running"}
        # Past it the Studio locks and the flow stops; it cannot outlast the license check.
        timer.value += 700
        licensing._tick()
        assert client.get("/api/workflows").status_code == 403
        timer.value += 60
        licensing._tick()
        deadline = time.monotonic() + 10
        while store.run(run["id"]).status in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(0.05)
        finished = store.run(run["id"])
        assert finished.status == "cancelled" and "uzun süredir doğrulanamadığı" in finished.error
