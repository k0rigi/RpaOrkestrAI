import json

import pytest
from test_licensing import FakeOrkestrai, service


def entitlement(**changes):
    return {"surum": 1, "aktif": True, "kullanici_id": 42, "firma_id": 2, "onayci_id": 42,
            "oturum_id": "ajan-oturumu", "bitis": "2099-01-01",
            "yetkiler": ["agents.use", "agents.manage", "agents.approve"], **changes}


def test_separate_signed_entitlement_and_only_designated_owner_can_approve(tmp_path):
    server = FakeOrkestrai()
    licensing = service(tmp_path, server)
    licensing.login("operator", "dogru")
    assert licensing.allowed() and not licensing.agent_allowed()
    assert licensing.status()["agents"] is False
    server.claims = {"ajan": entitlement()}
    licensing.refresh()
    assert licensing.agent_actor().can_approve and licensing.status()["agents"] is True
    assert licensing.agent_actor().user_id == 42
    server.claims = {"ajan": entitlement(onayci_id=99, yetkiler=["agents.use"])}
    licensing.refresh()
    assert licensing.agent_allowed() and not licensing.agent_actor().can_approve
    assert "ajan" not in json.dumps(licensing.status())
    assert set(json.loads((tmp_path / "license.json").read_text())) == {"install"}


def test_office_authority_and_office_come_from_the_signed_entitlement(tmp_path):
    server = FakeOrkestrai()
    server.claims = {"ajan": entitlement(ofis_id="c" * 32, ofis_adi="Claim & İade Departmanı")}
    licensing = service(tmp_path, server)
    licensing.login("operator", "dogru")
    actor = licensing.agent_actor()
    assert actor.can_approve and (actor.office_id, actor.office_name) == ("c" * 32, "Claim & İade Departmanı")
    # The office is never written into the records that carry the actor.
    assert "office" not in json.dumps(actor.model_dump())
    server.claims = {"ajan": entitlement(onayci_id=99, yetkiler=["agents.use"], ofis_id="d" * 32,
                                         ofis_adi="Lojistik Planlama ve Süreç Geliştirme Departmanı")}
    licensing.refresh()
    member = licensing.agent_actor()
    assert not member.can_approve and member.office_id == "d" * 32
    server.claims = {"ajan": entitlement(ofis_id=None, ofis_adi=None)}
    licensing.refresh()
    assert licensing.agent_actor().office_id is None and licensing.agent_actor().office_name == ""


@pytest.mark.parametrize("changes", [
    {"aktif": False}, {"aktif": "true"}, {"firma_id": 9}, {"kullanici_id": 9},
    {"onayci_id": 99}, {"oturum_id": ""}, {"bitis": "2000-01-01"}, {"bitis": "bozuk"},
    {"yetkiler": ["agents.admin"]}, {"yetkiler": [{"agents.approve": True}]},
    {"ofis_id": "OFIS", "ofis_adi": "Ad"}, {"ofis_id": "c" * 32}, {"ofis_id": "c" * 32, "ofis_adi": ""},
    {"ofis_id": "c" * 32, "ofis_adi": "x" * 121}, {"ofis_id": "c" * 32, "ofis_adi": "Satır\nkırık"},
    {"ofis_id": 7, "ofis_adi": "Ad"},
])
def test_invalid_agent_claims_never_enable_agents_or_break_rpa(tmp_path, changes):
    server = FakeOrkestrai()
    server.claims = {"ajan": entitlement(**changes)}
    licensing = service(tmp_path, server)
    licensing.login("operator", "dogru")
    assert licensing.allowed() and not licensing.agent_allowed()


def test_logout_closes_agent_identity_and_notifies_workers(tmp_path):
    server = FakeOrkestrai()
    server.claims = {"ajan": entitlement()}
    licensing = service(tmp_path, server)
    events = []
    licensing.on_locked = events.append
    licensing.login("operator", "dogru")
    assert licensing.agent_actor()
    licensing.logout()
    assert licensing.agent_actor() is None and events == ["session"]
    assert licensing.status()["agents"] is False


@pytest.mark.parametrize("agents", [False, True])
def test_studio_offers_agent_steps_only_with_the_agent_license(tmp_path, monkeypatch, agents):
    from conftest import LicensedForTests
    from fastapi.testclient import TestClient

    from rpa_orkestrai.app import create_app
    from rpa_orkestrai.config import Settings

    class Licensed(LicensedForTests):
        def agent_allowed(self):
            return agents

        def agent_actor(self):
            return None

    monkeypatch.setattr("rpa_orkestrai.app.LicenseService", Licensed)
    with TestClient(create_app(Settings(tmp_path, dotenv=False))) as client:
        bootstrap = client.get("/api/bootstrap").json()
        offered = {entry["type"] for entry in bootstrap["catalog"]}
        assert ("ai.ask" in offered) is agents
        assert ("ai.ask" in {entry["type"] for entry in client.get("/api/catalog").json()}) is agents
        # Saved flows that already use the step still open and show its fields.
        assert any(entry["type"] == "ai.ask" for entry in bootstrap["action_definitions"])
