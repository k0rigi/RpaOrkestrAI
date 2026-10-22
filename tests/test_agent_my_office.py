"""Kendi ofisini kurma: ofisi olmayan lisanslı hesap bir ofis kurar; yetkili adı ve çalışanları yönetir."""

import json

import pytest
from test_agent_api import api as agent_api  # noqa: F401
from test_agent_licensing import entitlement
from test_licensing import FakeOrkestrai, service

from rpa_orkestrai.agents.central import PATH, CentralClient, CentralError
from rpa_orkestrai.agents.models import Actor, reachable, same_account, visible
from rpa_orkestrai.licensing import LicenseError

OFFICE = "c" * 32


def test_signed_claim_says_who_may_open_an_office(tmp_path):
    server = FakeOrkestrai()
    server.claims = {"ajan": entitlement(yetkiler=["agents.use"], ofis_kurabilir=True)}
    licensing = service(tmp_path, server)
    licensing.login("operator", "dogru")
    actor = licensing.agent_actor()
    assert actor.can_create_office and actor.office_id is None and not actor.can_approve
    assert "create" not in json.dumps(actor.model_dump())
    # An office authority may open another office; a plain member or a malformed flag may not.
    server.claims = {"ajan": entitlement(ofis_id=OFFICE, ofis_adi="Claim & İade", ofis_kurabilir=True)}
    licensing.refresh()
    assert licensing.agent_actor().can_create_office and licensing.agent_actor().office_id == OFFICE
    for claims in (entitlement(yetkiler=["agents.use"], ofis_kurabilir="true"), entitlement()):
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


@pytest.mark.parametrize("path", ["/ofisim", "/ofisim/ad", "/ofisim/ayril", "/ofisim/sil", "/ofisim/uyeler",
                                  "/ofisim/uyeler/11/cikar"])
def test_central_client_allows_the_office_paths(path):
    assert PATH.fullmatch(path)


@pytest.mark.parametrize("path", ["/ofisim/uyeler/0/cikar", "/ofisim/uyeler/11", "/ofisim/sil/tumu", "/ofisimler",
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


def test_an_office_is_deleted_only_without_its_agents_here_and_its_model_goes_too(central):
    from rpa_orkestrai.agents.models import AgentInput

    api, calls, refreshes, _ = central
    actor = api.licensing.actor = api.licensing.actor.model_copy(update={"office_id": OFFICE, "office_name": "Lojistik"})
    service = api.app.state.agents
    agent = service.create_agent(AgentInput(name="Rota ajanı", model="test"))
    refused = api.client.post("/api/agents/central/my-office/delete", json={"name": "Lojistik"})
    assert refused.status_code == 409 and "1 ajan var" in refused.json()["detail"] and calls == []
    service.delete_agent(agent.id)
    models = service.settings.data_dir / "office_models"
    models.mkdir(parents=True, exist_ok=True)
    for name in (f"ofis-{OFFICE}.glb", f"ofis-{OFFICE}.json", f"ofis-{OFFICE}.places.json", f"ofis-{'d' * 32}.glb"):
        (models / name).write_bytes(b"x")
    for body in ({"name": "L"}, {}, {"name": "Lojistik", "ofis_id": OFFICE}):
        assert api.client.post("/api/agents/central/my-office/delete", json=body).status_code == 422
    deleted = api.client.post("/api/agents/central/my-office/delete", json={"name": "Lojistik"})
    assert deleted.status_code == 200 and calls[-1] == ("POST", "/ofisim/sil", {"name": "Lojistik"}, actor.user_id)
    assert refreshes == [1]
    assert sorted(path.name for path in models.iterdir()) == [f"ofis-{'d' * 32}.glb"]  # another office's model stays
    api.licensing.actor = actor.model_copy(update={"permissions": ("agents.use",)})
    assert api.client.post("/api/agents/central/my-office/delete", json={"name": "Lojistik"}).status_code == 403


SECOND = "d" * 32


def offices_claim(**changes):
    return entitlement(ofis_id=OFFICE, ofis_adi="Claim & İade", ofis_kurabilir=True,
                       ofisler=[{"id": OFFICE, "ad": "Claim & İade", "yetkili": True},
                                {"id": SECOND, "ad": "İade Analiz", "yetkili": True}], **changes)


def test_an_authority_switches_between_its_signed_offices_and_the_choice_is_remembered(tmp_path):
    server = FakeOrkestrai()
    server.claims = {"ajan": offices_claim()}
    licensing = service(tmp_path, server)
    licensing.login("operator", "dogru")
    actor = licensing.agent_actor()
    assert actor.office_id == OFFICE and [item[0] for item in actor.offices] == [OFFICE, SECOND]
    licensing.select_office(SECOND)
    assert (licensing.agent_actor().office_id, licensing.agent_actor().office_name) == (SECOND, "İade Analiz")
    with pytest.raises(LicenseError):
        licensing.select_office("e" * 32)
    # The next Studio start on this computer opens the same office.
    again = service(tmp_path, server)
    again.login("operator", "dogru")
    assert again.agent_actor().office_id == SECOND
    # An office the account lost falls back to its first office.
    server.claims = {"ajan": entitlement(ofis_id=OFFICE, ofis_adi="Claim & İade",
                                         ofisler=[{"id": OFFICE, "ad": "Claim & İade", "yetkili": True}])}
    again.refresh()
    assert again.agent_actor().office_id == OFFICE


@pytest.mark.parametrize("listed", [
    "liste", [{"id": "ofis", "ad": "A", "yetkili": True}], [{"id": SECOND, "ad": "A", "yetkili": True}],
    [{"id": OFFICE, "ad": "", "yetkili": True}], [{"id": OFFICE, "ad": "A\nB", "yetkili": True}],
    [{"id": OFFICE, "ad": "A", "yetkili": "evet"}], [{"id": OFFICE, "ad": "A", "yetkili": True}] * 2,
    [{"id": format(index, "032x"), "ad": "A", "yetkili": True} for index in range(51)],
])
def test_malformed_office_lists_never_enable_agents(tmp_path, listed):
    server = FakeOrkestrai()
    server.claims = {"ajan": entitlement(ofis_id=OFFICE, ofis_adi="Claim & İade", ofisler=listed)}
    licensing = service(tmp_path, server)
    licensing.login("operator", "dogru")
    assert licensing.allowed() and not licensing.agent_allowed()


def test_acting_for_another_office_keeps_the_account_and_its_rights_there():
    actor = Actor(user_id=7, company_id=2, session_id="s", permissions=("agents.use", "agents.manage", "agents.approve"),
                  office_id=OFFICE, office_name="A", offices=((OFFICE, "A", True), (SECOND, "B", True)))
    other = actor.in_office(SECOND)
    assert (other.office_id, other.office_name) == (SECOND, "B") and other.can_approve and same_account(actor, other)
    assert actor.in_office(OFFICE) is actor and actor.in_office("e" * 32) is None and actor.in_office(None) is None
    member = actor.model_copy(update={"offices": ((OFFICE, "A", True), (SECOND, "B", False))}).in_office(SECOND)
    assert member.permissions == ("agents.use",)
    # Lists show the office on screen; background work reaches every office of the account.
    assert not visible(actor, 2, SECOND, 1) and reachable(actor, 2, SECOND, 1)
    assert not reachable(actor, 2, "e" * 32, 7) and not reachable(actor, 3, SECOND, 7)


def test_central_requests_name_the_office_of_their_work():
    current = Actor(user_id=1, company_id=2, session_id="s", permissions=("agents.use",), office_id=OFFICE,
                    office_name="A", offices=((OFFICE, "A", True), (SECOND, "B", True)))
    sent = []

    class Licence:
        def agent_actor(self):
            return current

        def agent_access_token(self):
            return "belirtec"

    class Answer:
        def __init__(self, request):
            self.request = request

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def geturl(self):
            return self.request.full_url

        def getcode(self):
            return 200

        def read(self, _limit):
            return b'{"success": true}'

    def opener(request, **_kwargs):
        sent.append(request.get_header("X-rpa-ofis"))
        return Answer(request)

    client = CentralClient(Licence(), opener=opener)
    client.request("GET", "/uyeler")
    client.request("GET", "/uyeler", expected_actor=current.in_office(SECOND))
    assert sent == [OFFICE, SECOND]
    lost = current.model_copy(update={"office_id": "e" * 32})
    with pytest.raises(CentralError):
        client.request("GET", "/uyeler", expected_actor=lost)
    assert len(sent) == 2


def test_my_offices_adds_the_local_agent_count_and_select_switches_the_screen(central):
    api, calls, _, answers = central
    api.licensing.actor = api.licensing.actor.model_copy(update={
        "office_id": OFFICE, "office_name": "A", "offices": ((OFFICE, "A", True), (SECOND, "B", True))})
    created = api.client.post("/api/agents", json={"name": "Analiz", "model": "test"})
    assert created.status_code == 201
    answers[("GET", "/ofislerim")] = {"success": True, "can_create": True, "offices": [
        {"id": OFFICE, "name": "A", "is_authority": True, "people": 2, "open_tasks": 1, "pending_approvals": 0},
        {"id": SECOND, "name": "B", "is_authority": True, "people": 1, "open_tasks": 0, "pending_approvals": 3}]}
    listed = api.client.get("/api/agents/central/my-offices").json()["offices"]
    assert [(item["agents"], item["on_screen"]) for item in listed] == [(1, True), (0, False)]
    session = api.client.get("/api/agents/session").json()
    assert session["offices"] == [{"id": OFFICE, "name": "A", "is_authority": True},
                                  {"id": SECOND, "name": "B", "is_authority": True}]
    chosen = []
    api.licensing.select_office = lambda office: chosen.append(office)
    assert api.client.post("/api/agents/central/my-office/select", json={"office_id": SECOND}).status_code == 200
    assert api.client.post("/api/agents/central/my-office/select", json={"office_id": "x"}).status_code == 422

    def refuse(_office):
        raise ValueError("yok")

    api.licensing.select_office = refuse
    assert api.client.post("/api/agents/central/my-office/select", json={"office_id": "e" * 32}).status_code == 403
    assert chosen == [SECOND]
    # A new office opens on screen at once.
    api.licensing.select_office = lambda office: chosen.append(office)
    answers[("POST", "/ofisim")] = {"success": True, "office": {"id": "f" * 32, "name": "C"}}
    assert api.client.post("/api/agents/central/my-office", json={"name": "Yeni Ofis"}).status_code == 201
    assert chosen == [SECOND, "f" * 32]
