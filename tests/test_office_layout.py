"""RPA ofis yerleşim sözleşmesi 1: noktalar, yönler, yol ağı ve kalıcı yerleştirme kuralları."""

import copy
import math

import pytest
from glb_samples import layout_nodes, layout_office

from rpa_orkestrai.agents.office_layout import assign, read_layout
from rpa_orkestrai.agents.office_model import parse_glb


def layout(nodes=None, **document):
    return read_layout(parse_glb(layout_office(nodes, **document)))


def changed(target, **values):
    nodes = layout_nodes()
    node = next(item for item in nodes if item["name"] == target)
    for key, value in values.items():
        if value is None:
            node.pop(key, None)
        else:
            node[key] = value
    return nodes


def without(*names):
    return [item for item in layout_nodes() if item["name"] not in names]


def test_points_are_read_in_the_office_frame_with_feet_level_and_facing():
    result = layout()
    assert result["ok"] and result["version"] == 1 and result["capacity"] == {"work": 2, "wait": 1}
    work = result["points"]["RPA_WORK_001"]
    assert work["position"] == [-2.0, 0.0, -2.0] and math.isclose(abs(work["yaw"]), math.pi, abs_tol=1e-4)
    assert result["points"]["RPA_WAIT_001"]["yaw"] == 0.0
    assert result["seats"] == {"RPA_WORK_001": "RPA_SEAT_001"}
    assert result["labels"] == [{"name": "RPA_LABEL_Calisma", "text": "Çalışma alanı", "position": [0.0, 0.1, -3.0]}]
    assert ["RPA_NAV_001", "RPA_NAV_002"] in result["edges"] and result["camera_target"] is None
    # Labels and the origin are not places to stand on.
    assert "RPA_LABEL_Calisma" not in result["points"] and "RPA_ORIGIN" not in result["points"]


def test_model_transforms_are_applied_and_the_origin_becomes_the_office_frame():
    # The whole layout moved 100 m and turned by 90 degrees inside a parent; the office frame follows RPA_ORIGIN.
    document = parse_glb(layout_office())
    quarter = [0, math.sin(math.pi / 4), 0, math.cos(math.pi / 4)]
    document["nodes"][1].update(translation=[100, 0, 50], rotation=quarter)  # The group holding every point.
    moved = read_layout(document)
    assert moved["ok"] and moved["points"]["RPA_WORK_001"]["position"] == pytest.approx([-2, 0, -2], abs=1e-3)
    assert moved["origin_matrix"][12:15] == pytest.approx([100, 0, 50], abs=1e-3)


@pytest.mark.parametrize(("nodes", "reason"), [
    (without("RPA_ORIGIN"), "RPA_ORIGIN düğümü yok"),
    (changed("RPA_ORIGIN", extras=None), "sürümü yok"),
    (changed("RPA_ORIGIN", extras={"rpa_layout_version": 2}), "sürümü 2 bu Studio'da desteklenmiyor"),
    (without("RPA_SPAWN_01"), "RPA_SPAWN_01"),
    (without("RPA_WORK_001", "RPA_WORK_002", "RPA_SEAT_001"), "RPA_WORK_###"),
    (without("RPA_WAIT_001"), "RPA_WAIT_###"),
    (layout_nodes() + [{"name": "RPA_WROK_003", "translation": [3, 0, 3]}], "Tanınmayan yerleşim düğümü: RPA_WROK_003"),
    (layout_nodes() + [{"name": "RPA_WORK_001", "translation": [4, 0, 4]}], "birden fazla düğümde"),
    (changed("RPA_WORK_002", mesh=0), "görünmez boş bir düğüm"),
    (changed("RPA_WORK_002", translation=[2, 0.3, -2]), "zeminde değil"),
    (changed("RPA_WORK_002", rotation=[math.sin(math.pi / 4), 0, 0, math.cos(math.pi / 4)]), "yönü yatay değil"),
    (changed("RPA_WORK_002", translation=[-1.7, 0, -2]), "karakterler çakışır"),
    (changed("RPA_SEAT_001", name="RPA_SEAT_007"), "RPA_WORK_007 yok"),
    (changed("RPA_SEAT_001", translation=[-2, 1.2, -2]), "oturak yüzeyi"),
    (changed("RPA_SEAT_001", translation=[-3.5, 0.48, -2]), "uzak"),
    (changed("RPA_WORK_002", extras=None), "RPA_WORK_002 yol ağına bağlı değil"),
    (changed("RPA_WAIT_001", extras={"rpa_links": "RPA_NAV_404"}), "bilinmeyen veya yürünemeyen"),
    (changed("RPA_WAIT_001", extras={"rpa_links": "RPA_LABEL_Calisma"}), "bilinmeyen veya yürünemeyen"),
    (changed("RPA_WAIT_001", extras={"rpa_links": 7}), "rpa_links özelliği okunamadı"),
    (changed("RPA_NAV_002", extras=None), "Yol ağı kopuk"),
    (changed("RPA_ORIGIN", scale=[1, 1, 2]), "ölçeksiz"),
])
def test_contract_errors_name_the_point_and_the_rule(nodes, reason):
    result = layout(nodes)
    assert result["ok"] is False and any(reason in item for item in result["errors"]), result["errors"]


def test_navigation_is_required_and_never_guessed_from_the_floor():
    nodes = [item for item in layout_nodes() if not item["name"].startswith("RPA_NAV_")]
    for item in nodes:
        item.get("extras", {}).pop("rpa_links", None)
    result = layout(nodes)
    assert result["ok"] is False and any("yol ağı" in item for item in result["errors"])


def test_a_model_in_centimetres_is_refused():
    document = parse_glb(layout_office())
    document["accessors"][0].update(min=[-1000, 0, -1000], max=[1000, 0, 1000])  # A 2 km floor.
    result = read_layout(document)
    assert result["ok"] is False and any("metre olmalı" in item for item in result["errors"])


# ----- placing people ----------------------------------------------------------------------------
def people(*roles):
    return [{"id": format(index + 1, "032x"), "role": role, "department": ""} for index, role in enumerate(roles)]


def test_newcomers_take_free_work_points_then_waiting_points_and_the_rest_stay_listed():
    plan = layout()
    staff = people("department", "department", "department", "department")
    result = assign(plan, staff, {}, humans_complete=True)
    assert [result["places"].get(item["id"]) for item in staff] == ["RPA_WORK_001", "RPA_WORK_002", "RPA_WAIT_001", None]
    assert result["overflow"] == [staff[3]["id"]] and result["full"] is True


def test_places_are_kept_released_and_promoted():
    plan = layout()
    staff = people("department", "department", "department")
    first = assign(plan, staff, {}, humans_complete=True)["places"]
    # The second agent is deleted: its work point is freed and the waiting one moves up.
    second = assign(plan, [staff[0], staff[2]], first, humans_complete=True)["places"]
    assert second == {staff[0]["id"]: "RPA_WORK_001", staff[2]["id"]: "RPA_WORK_002"}
    # A newcomer never takes a kept place.
    newcomer = people("department", "department", "department", "department")[3]
    third = assign(plan, [staff[0], staff[2], newcomer], second, humans_complete=True)["places"]
    assert third[staff[0]["id"]] == "RPA_WORK_001" and third[newcomer["id"]] == "RPA_WAIT_001"


def test_a_changed_model_keeps_valid_places_and_redoes_the_rest():
    staff = people("department", "department")
    before = {staff[0]["id"]: "RPA_WORK_002", staff[1]["id"]: "RPA_WORK_009"}
    result = assign(layout(), staff, before, humans_complete=True)["places"]
    assert result == {staff[0]["id"]: "RPA_WORK_002", staff[1]["id"]: "RPA_WORK_001"}


def test_the_manager_gets_the_manager_point_and_others_never_do():
    nodes = layout_nodes() + [{"name": "RPA_MANAGER_01", "translation": [0, 0, -4], "rotation": [0, 1, 0, 0],
                               "extras": {"rpa_links": "RPA_NAV_002"}}]
    plan = layout(nodes)
    assert plan["ok"], plan["errors"]
    staff = people("department", "manager")
    result = assign(plan, staff, {staff[0]["id"]: "RPA_MANAGER_01"}, humans_complete=True)["places"]
    assert result == {staff[1]["id"]: "RPA_MANAGER_01", staff[0]["id"]: "RPA_WORK_001"}


def test_people_of_the_firm_keep_their_places_while_their_list_is_unavailable():
    plan = layout()
    agent = people("department")[0]
    human = {"id": "human-18", "role": "human", "department": ""}
    first = assign(plan, [agent, human], {}, humans_complete=True)["places"]
    kept = assign(plan, [agent], first, humans_complete=False)["places"]
    assert kept == first
    released = assign(plan, [agent], copy.deepcopy(first), humans_complete=True)["places"]
    assert released == {agent["id"]: "RPA_WORK_001"}
