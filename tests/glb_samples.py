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
