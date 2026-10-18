"""Kendi ofisini kurma: ofisi olmayan lisanslı hesap bir ofis kurar; yetkili adı ve çalışanları yönetir."""

import json

import pytest
from test_agent_api import api as agent_api  # noqa: F401
from test_agent_licensing import entitlement
from test_licensing import FakeOrkestrai, service

from rpa_orkestrai.agents.central import PATH
from rpa_orkestrai.agents.models import Actor, visible

OFFICE = "c" * 32


def test_signed_claim_lets_only_an_account_outside_every_office_open_one(tmp_path):
    server = FakeOrkestrai()
    server.claims = {"ajan": entitlement(yetkiler=["agents.use"], ofis_kurabilir=True)}
    licensing = service(tmp_path, server)
    licensing.login("operator", "dogru")
    actor = licensing.agent_actor()
    assert actor.can_create_office and actor.office_id is None and not actor.can_approve
    assert "create" not in json.dumps(actor.model_dump())
    for claims in (entitlement(ofis_id=OFFICE, ofis_adi="Claim & İade", ofis_kurabilir=True),
                   entitlement(yetkiler=["agents.use"], ofis_kurabilir="true"), entitlement()):
        server.claims = {"ajan": claims}
        licensing.refresh()
        assert licensing.agent_actor() is not None and not licensing.agent_actor().can_create_office


def test_records_from_before_offices_stay_with_their_creator_until_an_office_is_opened():
    member = Actor(user_id=7, company_id=2, session_id="s", permissions=("agents.use",))
    newcomer = member.model_copy(update={"can_create_office": True})
    authority = member.model_copy(update={"office_id": OFFICE, "office_name": "Claim & İade"})
    # A firm without offices is one team: everybody sees the firm's records.
    assert visible(member, 2, None, 1) and not visible(member, 3, None, 1)
    # An account that has not opened its office yet sees only what it created itself.
    assert visible(newcomer, 2, None, 7) and not visible(newcomer, 2, None, 1) and not visible(newcomer, 2, OFFICE, 7)
    assert visible(authority, 2, OFFICE, 1) and visible(authority, 2, None, 7) and not visible(authority, 2, None, 1)


def test_session_tells_the_screen_to_open_an_office_first(agent_api):  # noqa: F811
    agent_api.licensing.actor = agent_api.licensing.actor.model_copy(
        update={"permissions": ("agents.use",), "can_create_office": True})
    session = agent_api.client.get("/api/agents/session").json()
    assert session["can_create_office"] is True and session["office"] is None and session["can_manage"] is False


@pytest.mark.parametrize("path", ["/ofisim", "/ofisim/ad", "/ofisim/ayril", "/ofisim/uyeler", "/ofisim/uyeler/11/cikar"])
def test_central_client_allows_the_office_paths(path):
    assert PATH.fullmatch(path)


@pytest.mark.parametrize("path", ["/ofisim/uyeler/0/cikar", "/ofisim/uyeler/11", "/ofisim/sil", "/ofisimler",
                                  "/ofisim/uyeler/11/cikar/tumu", "/ofisim/ad/"])
def test_central_client_refuses_other_office_paths(path):
    assert not PATH.fullmatch(path)


@pytest.fixture
def central(agent_api, monkeypatch):  # noqa: F811
    calls, refreshes, answers = [], [], {}

    def respond(method, path, body, **kwargs):
        calls.append((method, path, body, kwargs["expected_actor"].user_id))
        return answers.get((method, path), {"success": True})

    monkeypatch.setattr(agent_api.app.state.agent_central, "request", respond)
    agent_api.licensing.refresh = lambda: refreshes.append(1)
    return agent_api, calls, refreshes, answers


def test_opening_and_leaving_an_office_ask_for_the_new_signed_rights_at_once(central):
    api, calls, refreshes, answers = central
    api.licensing.actor = api.licensing.actor.model_copy(update={"permissions": ("agents.use",), "can_create_office": True})
    answers[("POST", "/ofisim")] = {"success": True, "office": {"id": OFFICE, "name": "Lojistik"}}
    created = api.client.post("/api/agents/central/my-office", json={"name": "Lojistik"})
    assert created.status_code == 201 and created.json()["office"]["id"] == OFFICE
    assert calls[-1] == ("POST", "/ofisim", {"name": "Lojistik"}, 1) and refreshes == [1]
    for body in ({"name": "L"}, {"name": "L" * 121}, {"name": "Lojistik", "firma_id": 3}, {}):
        assert api.client.post("/api/agents/central/my-office", json=body).status_code == 422
    left = api.client.post("/api/agents/central/my-office/leave", json={})
    assert left.status_code == 200 and calls[-1][:3] == ("POST", "/ofisim/ayril", {}) and refreshes == [1, 1]
    assert len(calls) == 2


def test_reading_the_office_refreshes_the_rights_only_when_the_office_changed(central):
    api, _, refreshes, answers = central
    answers[("GET", "/ofisim")] = {"success": True, "office": None, "can_create": False, "members": [], "candidates": []}
    assert api.client.get("/api/agents/central/my-office").status_code == 200 and refreshes == []
    # An office authority added this account meanwhile.
    answers[("GET", "/ofisim")] = {"success": True, "office": {"id": OFFICE, "name": "Claim & İade", "authority_user_id": 3,
                                                               "is_authority": False}, "can_create": False,
                                   "members": [], "candidates": []}
    assert api.client.get("/api/agents/central/my-office").json()["office"]["id"] == OFFICE and refreshes == [1]
    api.licensing.actor = api.licensing.actor.model_copy(update={"office_id": OFFICE, "office_name": "Claim & İade"})
    api.client.get("/api/agents/central/my-office")
    assert refreshes == [1]


def test_only_the_office_authority_renames_the_office_and_places_colleagues(central):
    api, calls, refreshes, _ = central
    client = api.client
    assert client.post("/api/agents/central/my-office/name", json={"name": "İade Ofisi"}).status_code == 200
    assert client.post("/api/agents/central/my-office/members", json={"user_id": 11}).status_code == 200
    assert client.post("/api/agents/central/my-office/members/11/remove", json={}).status_code == 200
    assert [call[:3] for call in calls] == [("POST", "/ofisim/ad", {"name": "İade Ofisi"}),
                                            ("POST", "/ofisim/uyeler", {"user_id": 11}),
                                            ("POST", "/ofisim/uyeler/11/cikar", {})]
    for path, body in (("/members", {"user_id": "11"}), ("/members", {"user_id": 0}), ("/members/0/remove", {}),
                       ("/members/x/remove", {})):
        assert client.post("/api/agents/central/my-office" + path, json=body).status_code == 422
    api.licensing.actor = api.licensing.actor.model_copy(update={"permissions": ("agents.use",)})
    for path, body in (("/name", {"name": "Başka"}), ("/members", {"user_id": 12}), ("/members/11/remove", {})):
        assert client.post("/api/agents/central/my-office" + path, json=body).status_code == 403
    assert len(calls) == 3 and refreshes == []
