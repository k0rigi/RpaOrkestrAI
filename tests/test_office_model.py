"""Kendi 3D ofis modeli: GLB yalnız bu bilgisayarda, ofise özel saklanır ve açılmadan önce denetlenir."""

import json
from urllib.parse import quote

import pytest
from glb_samples import container, layout_office, office
from test_agent_api import api as agent_api  # noqa: F401

from rpa_orkestrai.agents import office_model
from rpa_orkestrai.agents.models import Actor
from rpa_orkestrai.agents.office_model import (
    SAMPLE_NAME,
    OfficeModelError,
    OfficeModels,
    Placement,
    inspect_glb,
    parse_glb,
)

GLB = {"Content-Type": "model/gltf-binary"}
DEFAULT = Placement().model_dump()


def scene(**document):
    return container({"asset": {"version": "2.0"}, "meshes": [{"primitives": []}], **document})


@pytest.mark.parametrize(("data", "reason"), [
    (b"PK\x03\x04" + b"\0" * 40, "GLB biçiminde değil"),
    (office()[:-4], "eksik veya bozuk"),
    (office().replace(b"glTF\x02", b"glTF\x01", 1), "eksik veya bozuk"),
    (scene(asset={"version": "1.0"}), "glTF 2.0"),
    (scene(extensionsUsed=["KHR_draco_mesh_compression"]), "Draco"),
    (scene(extensionsRequired=["EXT_meshopt_compression"]), "meshopt"),
    (scene(extensionsRequired=["KHR_texture_basisu"]), "KTX2"),
    (scene(images=[{"uri": "doku.png"}]), "dış dosyalara"),
    (scene(buffers=[{"uri": "data:application/octet-stream;base64,AA==", "byteLength": 1}]), "dış dosyalara"),
    (scene(meshes=[]), "şekil"),
])
def test_unusable_files_are_refused_with_a_reason(data, reason):
    with pytest.raises(OfficeModelError, match=reason):
        inspect_glb(data)


def test_valid_containers_and_optional_fallback_extensions_are_read(monkeypatch):
    assert parse_glb(office())["asset"]["version"] == "2.0"
    # meshopt and KTX2 with a plain fallback load without their decoders; only "required" refuses them.
    assert parse_glb(scene(extensionsUsed=["EXT_meshopt_compression", "KHR_texture_basisu"]))
    monkeypatch.setattr(office_model, "MODEL_LIMIT", len(office()) - 1)
    with pytest.raises(OfficeModelError, match="100 MB"):
        parse_glb(office())


def test_a_model_without_the_layout_contract_is_refused_with_its_reasons():
    with pytest.raises(OfficeModelError) as error:
        inspect_glb(office())
    message = str(error.value)
    assert "yerleşim sözleşmesine uymuyor" in message and "RPA_ORIGIN" in message
    assert inspect_glb(layout_office())["layout"]["capacity"] == {"work": 2, "wait": 1}


def test_a_model_belongs_to_one_office_on_this_computer(tmp_path):
    claims = Actor(user_id=1, company_id=2, session_id="s", office_id="c" * 32, office_name="Claim & İade")
    models = OfficeModels(tmp_path)
    saved = models.save(claims, layout_office(), "C:\\Kullanıcılar\\Ben\\..\\Ofis Planı\x07.glb")
    assert saved["present"] and saved["name"] == "Ofis Planı.glb" and saved["placement"] == DEFAULT
    assert saved["layout"]["ok"] and models.file(claims).read_bytes() == layout_office()
    for other in (claims.model_copy(update={"office_id": "d" * 32}), Actor(user_id=1, company_id=2, session_id="s"),
                  Actor(user_id=1, company_id=3, session_id="s")):
        assert models.describe(other) == {"present": False, "placement": DEFAULT}
        with pytest.raises(KeyError):
            models.file(other)
        with pytest.raises(KeyError):
            models.place(other, Placement())
    placed = models.place(claims, Placement(cut_height=3.2))
    assert placed["id"] == saved["id"] and placed["placement"] == {"cut_height": 3.2}
    # A new model starts from the default view settings.
    again = models.save(claims, layout_office(extras={"surum": 2}), "ikinci.glb")
    assert again["id"] != saved["id"] and again["placement"] == DEFAULT
    models.delete(claims)
    assert models.describe(claims)["present"] is False
    assert list((tmp_path / "office_models").iterdir()) == []


def test_a_damaged_record_counts_as_no_model(tmp_path):
    actor = Actor(user_id=1, company_id=2, session_id="s")
    models = OfficeModels(tmp_path)
    models.save(actor, layout_office(), "ofis.glb")
    model, meta = models.root / "firma-2.glb", models.root / "firma-2.json"
    model.write_bytes(layout_office()[:-4])
    assert models.describe(actor)["present"] is False
    models.save(actor, layout_office(), "ofis.glb")
    meta.write_text('{"name": "ofis.glb"}', encoding="utf-8")
    assert models.describe(actor)["present"] is False


def test_a_model_imported_before_the_contract_stays_off_until_replaced(tmp_path):
    actor = Actor(user_id=1, company_id=2, session_id="s")
    models = OfficeModels(tmp_path)
    models.root.mkdir(parents=True)
    # Written by 0.9.36/0.9.37: no layout, a scale and offsets.
    record = {"name": "depo.glb", "size": len(office()), "sha256": "a" * 64, "imported_at": "2026-10-18T10:00:00+00:00",
              "placement": {"scale": 2, "rotation": 90, "offset_x": 1, "cut_height": 3, "hide_room": True}}
    (models.root / "firma-2.glb").write_bytes(office())
    (models.root / "firma-2.json").write_text(json.dumps(record), encoding="utf-8")
    described = models.describe(actor)
    assert described["present"] is False and described["rejected"]["name"] == "depo.glb"
    assert any("RPA_ORIGIN" in item for item in described["rejected"]["errors"])
    with pytest.raises(KeyError):
        models.file(actor)
    # A file that already follows the contract is accepted once it is checked.
    (models.root / "firma-2.glb").write_bytes(layout_office())
    (models.root / "firma-2.json").write_text(json.dumps({**record, "size": len(layout_office())}), encoding="utf-8")
    upgraded = models.describe(actor)
    assert upgraded["present"] is True and upgraded["placement"] == {"cut_height": 3}
    models.delete(actor)
    assert list(models.root.iterdir()) == []


def test_model_routes_are_licensed_scoped_and_validated(agent_api):  # noqa: F811
    client = agent_api.client
    assert client.get("/api/agents/office/model").json() == {"present": False, "placement": DEFAULT}
    assert client.get("/api/agents/office/model/file").status_code == 404
    refused = client.put("/api/agents/office/model", content=b"bozuk dosya", headers=GLB)
    assert refused.status_code == 422 and "GLB" in refused.json()["detail"]
    unbound = client.put("/api/agents/office/model", content=office(), headers=GLB)
    assert unbound.status_code == 422 and "yerleşim sözleşmesine uymuyor" in unbound.json()["detail"]
    saved = client.put("/api/agents/office/model", content=layout_office(),
                       headers={**GLB, "X-Model-Name": quote("Depo ve ofis.glb")})
    assert saved.status_code == 200 and saved.json()["name"] == "Depo ve ofis.glb"
    file = client.get("/api/agents/office/model/file")
    assert file.content == layout_office() and file.headers["content-type"] == "model/gltf-binary"
    assert file.headers["cache-control"] == "no-store"
    for body in ({"cut_height": -1}, {"cut_height": 101}, {"scale": 2}, {"cut_height": 2, "renk": "kırmızı"}):
        assert client.put("/api/agents/office/model/placement", json=body).status_code == 422
    placed = client.put("/api/agents/office/model/placement", json={"cut_height": 2.8})
    assert placed.status_code == 200 and placed.json()["placement"] == {"cut_height": 2.8}
    # Another office of the same firm on this computer sees its own (empty) office.
    agent_api.licensing.actor = agent_api.licensing.actor.model_copy(update={"office_id": "d" * 32, "office_name": "Lojistik"})
    assert client.get("/api/agents/office/model").json()["present"] is False
    assert client.delete("/api/agents/office/model").status_code == 204
    agent_api.licensing.actor = agent_api.licensing.actor.model_copy(update={"office_id": None, "office_name": ""})
    assert client.get("/api/agents/office/model").json()["present"] is True
    assert client.delete("/api/agents/office/model").status_code == 204
    assert client.get("/api/agents/office/model").json()["present"] is False
    agent_api.licensing.agents = False
    assert client.get("/api/agents/office/model").status_code == 403
    assert client.put("/api/agents/office/model", content=layout_office(), headers=GLB).status_code == 403


def test_the_bundled_sample_office_follows_the_contract_and_places_people(agent_api):  # noqa: F811
    client = agent_api.client
    assert client.post("/api/agents/office/model/assignments", json={"occupants": []}).status_code == 404
    sample = client.post("/api/agents/office/model/sample", json={})
    assert sample.status_code == 200
    info = sample.json()
    assert info["name"] == SAMPLE_NAME and info["layout"]["capacity"] == {"work": 8, "wait": 4}
    assert len(info["layout"]["seats"]) == 9 and {item["text"] for item in info["layout"]["labels"]} == {
        "Çalışma alanı", "Yönetici odası", "Bekleme alanı", "Araştırma köşesi"}
    people = [{"id": "a" * 32, "role": "manager"}] + [{"id": format(index, "032x"), "role": "department"} for index in range(1, 14)]
    placed = client.post("/api/agents/office/model/assignments", json={"occupants": people}).json()
    assert placed["places"]["a" * 32] == "RPA_MANAGER_01" and placed["full"] is True and len(placed["overflow"]) == 1
    assert sorted(placed["places"].values())[:2] == ["RPA_MANAGER_01", "RPA_WAIT_001"]
    for body in ({"occupants": [{"id": "x"}]}, {"occupants": [{"id": "b" * 32}, {"id": "b" * 32}]},
                 {"occupants": [{"id": "b" * 32, "role": "admin"}]}):
        assert client.post("/api/agents/office/model/assignments", json=body).status_code == 422


def test_only_the_model_import_takes_a_large_body_and_textures_may_use_blob_addresses(agent_api):  # noqa: F811
    client = agent_api.client
    large = b"x" * 3_000_000
    assert client.put("/api/agents/office/model", content=large, headers=GLB).status_code == 422
    assert client.put("/api/agents/office/model/placement", content=large,
                      headers={"Content-Type": "application/json"}).status_code == 413
    assert client.post("/api/agents/office/model", content=large, headers=GLB).status_code == 413
    policy = client.get("/").headers["Content-Security-Policy"]
    assert "img-src 'self' data: blob:;" in policy and "connect-src 'self' blob:;" in policy
