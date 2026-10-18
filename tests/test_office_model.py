"""Kendi 3D ofis modeli: GLB yalnız bu bilgisayarda, ofise özel saklanır ve açılmadan önce denetlenir."""

from urllib.parse import quote

import pytest
from glb_samples import container, office
from test_agent_api import api as agent_api  # noqa: F401

from rpa_orkestrai.agents import office_model
from rpa_orkestrai.agents.models import Actor
from rpa_orkestrai.agents.office_model import OfficeModelError, OfficeModels, Placement, inspect_glb

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


def test_valid_models_and_optional_fallback_extensions_are_accepted(monkeypatch):
    assert inspect_glb(office()) == {"meshes": 1}
    # meshopt and KTX2 with a plain fallback load without their decoders; only "required" refuses them.
    assert inspect_glb(scene(extensionsUsed=["EXT_meshopt_compression", "KHR_texture_basisu"]))
    monkeypatch.setattr(office_model, "MODEL_LIMIT", len(office()) - 1)
    with pytest.raises(OfficeModelError, match="100 MB"):
        inspect_glb(office())


def test_a_model_belongs_to_one_office_on_this_computer(tmp_path):
    claims = Actor(user_id=1, company_id=2, session_id="s", office_id="c" * 32, office_name="Claim & İade")
    models = OfficeModels(tmp_path)
    saved = models.save(claims, office(), "C:\\Kullanıcılar\\Ben\\..\\Ofis Planı\x07.glb")
    assert saved["present"] and saved["name"] == "Ofis Planı.glb" and saved["placement"] == DEFAULT
    assert models.file(claims).read_bytes() == office()
    for other in (claims.model_copy(update={"office_id": "d" * 32}), Actor(user_id=1, company_id=2, session_id="s"),
                  Actor(user_id=1, company_id=3, session_id="s")):
        assert models.describe(other) == {"present": False, "placement": DEFAULT}
        with pytest.raises(KeyError):
            models.file(other)
        with pytest.raises(KeyError):
            models.place(other, Placement())
    placed = models.place(claims, Placement(scale=1.5, rotation=90, offset_x=-3, cut_height=3.2, hide_room=False))
    assert placed["id"] == saved["id"] and placed["placement"]["rotation"] == 90
    # A new model starts from the default placement; the old offsets would not fit it.
    again = models.save(claims, office(2.0), "ikinci.glb")
    assert again["id"] != saved["id"] and again["placement"] == DEFAULT
    models.delete(claims)
    assert models.describe(claims)["present"] is False
    assert list((tmp_path / "office_models").iterdir()) == []


def test_a_damaged_record_counts_as_no_model(tmp_path):
    actor = Actor(user_id=1, company_id=2, session_id="s")
    models = OfficeModels(tmp_path)
    models.save(actor, office(), "ofis.glb")
    model, meta = models.root / "firma-2.glb", models.root / "firma-2.json"
    model.write_bytes(office()[:-4])
    assert models.describe(actor)["present"] is False
    models.save(actor, office(), "ofis.glb")
    meta.write_text('{"name": "ofis.glb"}', encoding="utf-8")
    assert models.describe(actor)["present"] is False


def test_model_routes_are_licensed_scoped_and_validated(agent_api):  # noqa: F811
    client = agent_api.client
    assert client.get("/api/agents/office/model").json() == {"present": False, "placement": DEFAULT}
    assert client.get("/api/agents/office/model/file").status_code == 404
    refused = client.put("/api/agents/office/model", content=b"bozuk dosya", headers=GLB)
    assert refused.status_code == 422 and "GLB" in refused.json()["detail"]
    saved = client.put("/api/agents/office/model", content=office(),
                       headers={**GLB, "X-Model-Name": quote("Depo ve ofis.glb")})
    assert saved.status_code == 200 and saved.json()["name"] == "Depo ve ofis.glb"
    file = client.get("/api/agents/office/model/file")
    assert file.content == office() and file.headers["content-type"] == "model/gltf-binary"
    assert file.headers["cache-control"] == "no-store"
    for body in ({"scale": 0}, {"rotation": 45}, {"cut_height": -1}, {"offset_x": 501}, {"scale": 2, "renk": "kırmızı"}):
        assert client.put("/api/agents/office/model/placement", json=body).status_code == 422
    placed = client.put("/api/agents/office/model/placement", json={"scale": 2, "rotation": 270, "hide_room": False})
    assert placed.status_code == 200 and placed.json()["placement"] == {**DEFAULT, "scale": 2, "rotation": 270,
                                                                        "hide_room": False}
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
    assert client.put("/api/agents/office/model", content=office(), headers=GLB).status_code == 403


def test_only_the_model_import_takes_a_large_body_and_textures_may_use_blob_addresses(agent_api):  # noqa: F811
    client = agent_api.client
    large = b"x" * 3_000_000
    assert client.put("/api/agents/office/model", content=large, headers=GLB).status_code == 422
    assert client.put("/api/agents/office/model/placement", content=large,
                      headers={"Content-Type": "application/json"}).status_code == 413
    assert client.post("/api/agents/office/model", content=large, headers=GLB).status_code == 413
    policy = client.get("/").headers["Content-Security-Policy"]
    assert "img-src 'self' data: blob:;" in policy and "connect-src 'self' blob:;" in policy
