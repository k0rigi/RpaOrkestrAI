"""Testler için küçük, geçerli GLB (glTF 2.0 ikili) örnekleri."""

import json
import struct

JSON_CHUNK, BIN_CHUNK = 0x4E4F534A, 0x004E4942


def container(document: dict, binary: bytes = b"") -> bytes:
    payload = json.dumps(document).encode("utf-8")
    payload += b" " * (-len(payload) % 4)
    chunks = struct.pack("<II", len(payload), JSON_CHUNK) + payload
    if binary:
        binary += b"\0" * (-len(binary) % 4)
        chunks += struct.pack("<II", len(binary), BIN_CHUNK) + binary
    return b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks


def office(scale: float = 1.0, **document) -> bytes:
    """An upward triangle twice, as exported and mirrored, with an old specular-glossiness material (as SimLab writes)."""
    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 0, -1)
    normals = struct.pack("<9f", 0, 1, 0, 0, 1, 0, 0, 1, 0)
    binary = positions + normals + struct.pack("<3H", 0, 1, 2) + b"\0\0"
    value = {
        "asset": {"version": "2.0", "generator": "RpaOrkestrAI test"},
        "extensionsUsed": ["KHR_materials_pbrSpecularGlossiness"],
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"children": [1, 2], "scale": [scale] * 3}, {"mesh": 0},
                  {"mesh": 0, "translation": [5, 0, 0], "scale": [-1, 1, 1]}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2, "material": 0}]}],
        "materials": [{"name": "Zemin", "extensions": {"KHR_materials_pbrSpecularGlossiness": {
            "diffuseFactor": [1, 0, 0, 1], "specularFactor": [.5, 0, 0], "glossinessFactor": .5}}}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 36}, {"buffer": 0, "byteOffset": 36, "byteLength": 36},
                        {"buffer": 0, "byteOffset": 72, "byteLength": 6}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
                       "min": [0, 0, -1], "max": [1, 0, 0]},
                      {"bufferView": 1, "componentType": 5126, "count": 3, "type": "VEC3"},
                      {"bufferView": 2, "componentType": 5123, "count": 3, "type": "SCALAR"}],
        **document,
    }
    return container(value, binary)


def layout_nodes() -> list[dict]:
    """The layout points of a small office that follows the RPA layout contract 1; tests change them."""
    north = [0, 1, 0, 0]  # Turned by π: the person faces -Z.
    return [
        {"name": "RPA_ORIGIN", "extras": {"rpa_layout_version": 1}},
        {"name": "RPA_SPAWN_01", "translation": [0, 0, 4], "rotation": north, "extras": {"rpa_links": "RPA_NAV_001"}},
        {"name": "RPA_NAV_001", "translation": [0, 0, 2]},
        {"name": "RPA_NAV_002", "translation": [0, 0, -1], "extras": {"rpa_links": ["RPA_NAV_001"]}},
        {"name": "RPA_WORK_001", "translation": [-2, 0, -2], "rotation": north, "extras": {"rpa_links": "RPA_NAV_002"}},
        {"name": "RPA_WORK_002", "translation": [2, 0, -2], "rotation": north, "extras": {"rpa_links": "RPA_NAV_002"}},
        {"name": "RPA_SEAT_001", "translation": [-2, 0.48, -2], "rotation": north},
        {"name": "RPA_WAIT_001", "translation": [-2, 0, 2], "extras": {"rpa_links": "RPA_NAV_001"}},
        {"name": "RPA_MEET_001", "translation": [2, 0, 1], "rotation": north, "extras": {"rpa_links": "RPA_NAV_001"}},
        {"name": "RPA_LABEL_Calisma", "translation": [0, 0.1, -3], "extras": {"rpa_label": "Çalışma alanı"}},
    ]


def layout_office(nodes: list[dict] | None = None, **document) -> bytes:
    """A 10 x 10 m floor and the given layout points (all of them children of one plain group node)."""
    positions = struct.pack("<12f", -5, 0, -5, 5, 0, -5, 5, 0, 5, -5, 0, 5)
    normals = struct.pack("<12f", *(0, 1, 0) * 4)
    binary = positions + normals + struct.pack("<6H", 0, 2, 1, 0, 3, 2)
    anchors = layout_nodes() if nodes is None else nodes
    value = {
        "asset": {"version": "2.0", "generator": "RpaOrkestrAI test"},
        "scene": 0, "scenes": [{"nodes": [0, 1]}],
        "nodes": [{"name": "Zemin", "mesh": 0}, {"name": "Yerlesim", "children": list(range(2, 2 + len(anchors)))}, *anchors],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1}, "indices": 2}]}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 48}, {"buffer": 0, "byteOffset": 48, "byteLength": 48},
                        {"buffer": 0, "byteOffset": 96, "byteLength": 12}],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 4, "type": "VEC3", "min": [-5, 0, -5], "max": [5, 0, 5]},
                      {"bufferView": 1, "componentType": 5126, "count": 4, "type": "VEC3"},
                      {"bufferView": 2, "componentType": 5123, "count": 6, "type": "SCALAR"}],
        **document,
    }
    return container(value, binary)
