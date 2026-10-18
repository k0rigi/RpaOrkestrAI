"""Ofisler arası iletişim: yetkili, yönettiği diğer ofisten işi yalnız o ofisin yöneticisi üzerinden ister."""

from test_agent_organization import last_tool_data, providers
from test_agent_runner import AGENT_TEST_SECONDS, finish, response
from test_agent_runner import runtime as runtime  # noqa: F401

from rpa_orkestrai.agents.models import AgentInput, AgentLimits, AgentRunRequest
from rpa_orkestrai.agents.office import snapshot
from rpa_orkestrai.agents.providers import ScriptedProvider, ToolCall
from rpa_orkestrai.models import uid

CLAIMS, LOGISTICS = "c" * 32, "d" * 32
NAMES = {CLAIMS: "Claim & İade", LOGISTICS: "Lojistik"}


def both(runtime, office, *, authority=True):  # noqa: F811
    """One authority running both offices, with `office` on screen."""
    runtime.state["actor"] = runtime.owner.model_copy(update={
        "office_id": office, "office_name": NAMES[office],
        "offices": ((CLAIMS, NAMES[CLAIMS], authority), (LOGISTICS, NAMES[LOGISTICS], authority))})


def agent(runtime, office, name, **values):  # noqa: F811
    both(runtime, office)
    return runtime.service.create_agent(AgentInput(name=name, model="test", **values,
                                                   limits=AgentLimits(max_seconds=AGENT_TEST_SECONDS)))


def contact(office="lojistik", kind="task", message="Yarınki sevkiyatları planla"):
    return ToolCall(uid(), "contact_office", {"office": office, "kind": kind, "title": "Sevkiyat", "message": message})


def test_a_manager_sends_work_to_the_other_offices_manager_and_gets_its_result(runtime):  # noqa: F811
    lojistik = agent(runtime, LOGISTICS, "Lojistik yöneticisi", role="manager")
    planner = agent(runtime, LOGISTICS, "Rota ajanı", department="Planlama", manager_id=lojistik.id)
    iade = agent(runtime, CLAIMS, "İade yöneticisi", role="manager")
    iade_provider = ScriptedProvider([response(ToolCall(uid(), "list_offices", {}), contact()),
                                      response(ToolCall(uid(), "wait_tasks", {"until": "all"})),
                                      response(finish()), response(finish("Lojistik planı alındı"))])
    lojistik_provider = ScriptedProvider([response(ToolCall(uid(), "delegate_task", {
        "agent_id": planner.id, "title": "Plan", "instructions": "Sevkiyatları planla"})),
        response(finish()), response(finish("3 sevkiyat planlandı"))])
    planner_provider = ScriptedProvider([response(finish("Plan hazır"))])
    providers(runtime, {iade.id: iade_provider, lojistik.id: lojistik_provider, planner.id: planner_provider})
    run = runtime.service.start(iade.id, AgentRunRequest(task="Lojistikten yarının planını iste"))
    # The authority looks at the other office meanwhile; nothing stops.
    both(runtime, LOGISTICS)
    saved = runtime.done(run)
    assert saved.status == "succeeded" and runtime.service.agent_store.task(saved.task_id).summary == "Lojistik planı alındı"
    requested = runtime.service.agent_store.task(saved.delegated_task_ids[0])
    assert requested.office_id == LOGISTICS and requested.assigned_agent_id == lojistik.id
    assert requested.summary == "3 sevkiyat planlandı" and requested.parent_task_id == saved.task_id
    assert requested.title == "Claim & İade ofisinden: Sevkiyat"
    planned = [task for task in runtime.service.agent_store.tasks() if task.assigned_agent_id == planner.id]
    assert len(planned) == 1 and planned[0].office_id == LOGISTICS and planned[0].summary == "Plan hazır"
    offices = last_tool_data({"messages": [message for message in iade_provider.requests[1]["messages"]
                                           if message.get("role") == "tool"][:1]})
    assert offices == {"offices": [{"office": "Lojistik", "manager": "Lojistik yöneticisi", "reachable": True}]}
    sent = next(event for event in saved.events if event.kind == "office_request")
    assert sent.data["office"] == "Lojistik" and sent.data["kind"] == "task"
    received = runtime.service.agent_store.run(requested.run_id)
    assert any(event.kind == "office_request_received" and event.data["office"] == "Claim & İade" for event in received.events)
    # The requesting manager reaches other offices; the receiving one hands work to its own departments
    # and may ask back, but does not pass the request on to a third office.
    first_tools = {tool["name"] for tool in iade_provider.requests[0]["tools"]}
    assert {"list_offices", "contact_office", "delegate_task"} <= first_tools and "ask_manager" not in first_tools
    handling_tools = {tool["name"] for tool in lojistik_provider.requests[0]["tools"]}
    assert {"delegate_task", "ask_manager"} <= handling_tools and not handling_tools & {"list_offices", "contact_office"}
    assert "list_offices" not in {tool["name"] for tool in planner_provider.requests[0]["tools"]}


def test_the_other_manager_may_ask_back_and_gets_the_answer(runtime):  # noqa: F811
    lojistik = agent(runtime, LOGISTICS, "Lojistik yöneticisi", role="manager")
    iade = agent(runtime, CLAIMS, "İade yöneticisi", role="manager")

    def iade_reply(request):
        data = last_tool_data(request)
        if data.get("status") != "department_question":
            return None
        question = data["questions"][0]
        assert question["agent_id"] == lojistik.id and question["question"] == "Hangi depo?"
        return response(ToolCall(uid(), "answer_department", {"question_id": question["question_id"], "answer": "Gebze"}),
                        finish())

    iade_provider = ScriptedProvider([response(contact(kind="question", message="Gebze stoku ne kadar?")),
                                      response(finish()), response(finish("Yanıt geldi"))], callback=iade_reply)
    lojistik_provider = ScriptedProvider([response(ToolCall(uid(), "ask_manager", {"question": "Hangi depo?", "options": []})),
                                          response(finish("Gebze: 120 koli"))])
    providers(runtime, {iade.id: iade_provider, lojistik.id: lojistik_provider})
    saved = runtime.done(runtime.service.start(iade.id, AgentRunRequest(task="Stok sor")))
    assert saved.status == "succeeded"
    assert last_tool_data(lojistik_provider.requests[1]) == {"answer": "Gebze", "from": "manager"}
    assert runtime.service.agent_store.task(saved.delegated_task_ids[0]).summary == "Gebze: 120 koli"
    assert lojistik_provider.requests[0]["messages"][1]["content"].count("Soru (Claim & İade ofisinin yöneticisinden)") == 1


def test_refused_contacts_name_the_reason_and_start_nothing(runtime):  # noqa: F811
    iade = agent(runtime, CLAIMS, "İade yöneticisi", role="manager")
    department = agent(runtime, CLAIMS, "İade ajanı", department="İade", manager_id=iade.id)
    provider = ScriptedProvider([response(contact(office="Muhasebe"), contact(office="Claim & İade"), contact()),
                                 response(finish("Bitti"))])
    providers(runtime, {iade.id: provider})
    saved = runtime.done(runtime.service.start(iade.id, AgentRunRequest(task="Dene")))
    errors = [event.data["untrusted_data"] for event in saved.events if event.kind == "tool_result"]
    messages = [item.get("error", "") for item in errors if item.get("status") == "error"]
    assert len(messages) == 3 and "list_offices" in messages[0] and "list_offices" in messages[1]
    assert "Lojistik ofisinde yönetici ajan yok" in messages[2]
    assert saved.delegated_task_ids == [] and len(runtime.service.agent_store.tasks()) == 1
    # A department agent and a plain member never get the office tools.
    providers(runtime, {department.id: ScriptedProvider([response(finish())])})
    child = runtime.done(runtime.service.start(department.id, AgentRunRequest(task="İş")))
    assert child.status == "succeeded"
    both(runtime, CLAIMS, authority=False)
    member = ScriptedProvider([response(finish())])
    providers(runtime, {iade.id: member})
    runtime.state["actor"] = runtime.state["actor"].model_copy(update={"permissions": ("agents.use",)})
    runtime.done(runtime.service.start(iade.id, AgentRunRequest(task="Üye")))
    assert not {tool["name"] for tool in member.requests[0]["tools"]} & {"list_offices", "contact_office"}


def test_the_office_shows_only_the_type_and_the_other_offices_name(runtime):  # noqa: F811
    lojistik = agent(runtime, LOGISTICS, "Lojistik yöneticisi", role="manager")
    iade = agent(runtime, CLAIMS, "İade yöneticisi", role="manager")
    seen = {}

    def lojistik_reply(request):
        both(runtime, CLAIMS)
        seen["claims"] = snapshot(runtime.service)
        both(runtime, LOGISTICS)
        seen["logistics"] = snapshot(runtime.service)
        return response(finish("Tamam"))

    providers(runtime, {iade.id: ScriptedProvider([response(contact(message="GİZLİ ayrıntı")), response(finish()),
                                                   response(finish())]),
                        lojistik.id: ScriptedProvider([], callback=lojistik_reply)})
    both(runtime, CLAIMS)
    runtime.done(runtime.service.start(iade.id, AgentRunRequest(task="Gönder")))
    sender = next(item for item in seen["claims"]["agents"] if item["id"] == iade.id)
    receiver = next(item for item in seen["logistics"]["agents"] if item["id"] == lojistik.id)
    assert sender["event"]["kind"] == "office_request" and sender["event"]["to_office"] == "Lojistik"
    assert receiver["event"]["kind"] == "office_received" and receiver["event"]["to_office"] == "Claim & İade"
    assert "GİZLİ" not in str(seen)
