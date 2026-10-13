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
    server.claims = {"ajan": entitlement()}
    licensing.refresh()
    assert licensing.agent_actor().can_approve
    assert licensing.agent_actor().user_id == 42
    server.claims = {"ajan": entitlement(onayci_id=99, yetkiler=["agents.use"])}
    licensing.refresh()
    assert licensing.agent_allowed() and not licensing.agent_actor().can_approve
    assert "ajan" not in json.dumps(licensing.status())
    assert set(json.loads((tmp_path / "license.json").read_text())) == {"install"}


@pytest.mark.parametrize("changes", [
    {"aktif": False}, {"aktif": "true"}, {"firma_id": 9}, {"kullanici_id": 9},
    {"onayci_id": 99}, {"oturum_id": ""}, {"bitis": "2000-01-01"}, {"bitis": "bozuk"},
    {"yetkiler": ["agents.admin"]}, {"yetkiler": [{"agents.approve": True}]},
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
