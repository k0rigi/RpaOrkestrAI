"""Builds the bundled sample office (static/office-models/ornek-ofis.glb) that follows the RPA layout contract 1.

The model is generated, not drawn: every run writes the same bytes. Units are metres, +Y is up and the floor of
the office is Y=0 at RPA_ORIGIN. The anchors, seats and the path network are listed in docs/ofis-modeli.md.

    python scripts/make_sample_office.py
"""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "src" / "rpa_orkestrai" / "static" / "office-models" / "ornek-ofis.glb"
NORTH = math.pi  # Facing -Z (towards the north wall); a node's local +Z is the direction the character faces.
SOUTH = 0.0

MATERIALS = {
    "zemin": ((0.85, 0.82, 0.77, 1), 0.9), "halı_çalışma": ((0.56, 0.64, 0.72, 1), 1.0),
    "halı_bekleme": ((0.72, 0.64, 0.54, 1), 1.0), "parke": ((0.80, 0.70, 0.55, 1), 0.7),
    "duvar": ((0.95, 0.94, 0.91, 1), 0.95), "masa": ((0.78, 0.64, 0.48, 1), 0.6), "metal": ((0.27, 0.27, 0.29, 1), 0.5),
    "ekran": ((0.10, 0.11, 0.13, 1), 0.3), "koltuk": ((0.23, 0.36, 0.57, 1), 0.8), "cam": ((0.62, 0.83, 1.0, 0.25), 0.1),
    "kanepe": ((0.48, 0.56, 0.42, 1), 0.9), "raf": ((0.54, 0.42, 0.29, 1), 0.8), "kitap_k": ((0.75, 0.22, 0.17, 1), 0.8),
    "kitap_m": ((0.18, 0.53, 0.76, 1), 0.8), "kitap_s": ((0.95, 0.77, 0.06, 1), 0.8), "bitki": ((0.24, 0.55, 0.25, 1), 0.9),
    "saksı": ((0.69, 0.50, 0.35, 1), 0.9), "paspas": ((0.33, 0.33, 0.33, 1), 1.0),
}
boxes: dict[str, list[tuple]] = {name: [] for name in MATERIALS}


def box(material, x, y, z, width, height, depth):
    """An axis-aligned box: centre and size in metres."""
    boxes[material].append((x, y, z, width, height, depth))


def desk(x, z, width=1.6, depth=0.8, monitor=True):
    box("masa", x, 0.735, z, width, 0.05, depth)
    for dx in (-width / 2 + 0.06, width / 2 - 0.06):
        for dz in (-depth / 2 + 0.06, depth / 2 - 0.06):
            box("metal", x + dx, 0.355, z + dz, 0.05, 0.71, 0.05)
    if monitor:
        box("ekran", x, 1.0, z - depth / 2 + 0.18, 0.62, 0.36, 0.04)
        box("metal", x, 0.84, z - depth / 2 + 0.2, 0.05, 0.16, 0.05)


def chair(x, z, facing_north=True):
    """Seat surface at 0.48 m; the back is behind the person."""
    back = 0.24 if facing_north else -0.24
    box("koltuk", x, 0.45, z, 0.5, 0.06, 0.5)
    box("koltuk", x, 0.78, z + back, 0.5, 0.56, 0.06)
    box("metal", x, 0.21, z, 0.06, 0.42, 0.06)
    box("metal", x, 0.03, z, 0.55, 0.04, 0.55)


def plant(x, z):
    box("saksı", x, 0.2, z, 0.4, 0.4, 0.4)
    box("bitki", x, 0.75, z, 0.6, 0.7, 0.6)


# ----- the room -----------------------------------------------------------------------------------
box("zemin", 0, -0.05, 0, 24, 0.1, 16)
box("halı_çalışma", -5.75, 0.004, -1.6, 10.5, 0.008, 9.4)
box("halı_bekleme", -4.6, 0.004, 6.2, 4.6, 0.008, 2.8)
box("parke", 8, 0.004, -5.5, 6, 0.008, 4)
box("paspas", 0, 0.006, 7.4, 2.4, 0.012, 1.0)
box("duvar", 0, 1.5, -8, 24, 3, 0.15)  # North and west walls are full height,
box("duvar", -12, 1.5, 0, 0.15, 3, 16)
box("duvar", 12, 0.5, 0, 0.15, 1, 16)  # south and east walls are low so the office stays visible.
box("duvar", -6.75, 0.5, 8, 10.5, 1, 0.15)
box("duvar", 6.75, 0.5, 8, 10.5, 1, 0.15)  # The entrance is the gap between x = -1.5 and 1.5.
# Work area: two rows of four desks; people face the north wall.
for row, (desk_z, chair_z) in enumerate(((-5.0, -4.2), (0.5, 1.3))):
    for x in (-9.5, -7.0, -4.5, -2.0):
        desk(x, desk_z)
        chair(x, chair_z)
# Manager's glass room in the north-east corner, door towards the south.
box("cam", 5, 1.4, -5.5, 0.06, 2.8, 4)
box("cam", 6.2, 1.4, -3.5, 2.4, 2.8, 0.06)
box("cam", 9.8, 1.4, -3.5, 2.4, 2.8, 0.06)
box("metal", 5, 2.82, -5.5, 0.1, 0.06, 4)
box("metal", 8, 2.82, -3.5, 6, 0.06, 0.1)
desk(8, -6.2, width=2.0, depth=0.9)
chair(8, -5.4)
plant(5.6, -7.4)
# Waiting area by the entrance and the research corner with a bookshelf.
box("kanepe", -4.6, 0.225, 7.0, 3.2, 0.45, 0.9)
box("kanepe", -4.6, 0.7, 7.45, 3.2, 0.5, 0.2)
box("masa", -4.6, 0.4, 6.0, 1.2, 0.05, 0.6)
box("metal", -4.6, 0.19, 6.0, 0.08, 0.38, 0.08)
box("raf", 9.9, 1.0, 7.55, 3.0, 2.0, 0.4)
for index, x in enumerate((8.8, 9.3, 9.8, 10.3, 10.8)):
    for height in (0.45, 1.05, 1.6):
        box(("kitap_k", "kitap_m", "kitap_s")[(index + int(height * 10)) % 3], x, height, 7.4, 0.35, 0.38, 0.22)
for x, z in ((-11.3, -7.3), (-11.3, 7.3), (11.3, 3.0), (3.0, 7.3), (-0.8, -7.3)):
    plant(x, z)

# ----- the layout contract ------------------------------------------------------------------------
anchors: list[tuple[str, tuple, float, dict]] = []


def anchor(name, x, y, z, yaw=None, **extras):
    anchors.append((name, (x, y, z), yaw, extras))


links: dict[str, list[str]] = {}


def link(first, *others):
    links.setdefault(first, []).extend(others)


anchor("RPA_ORIGIN", 0, 0, 0, rpa_layout_version=1)
anchor("RPA_CAMERA_TARGET", 1.0, 0, 0)
anchor("RPA_SPAWN_01", 0, 0, 7.0, NORTH)
for number, (x, z) in enumerate([(x, -4.2) for x in (-9.5, -7.0, -4.5, -2.0)]
                                + [(x, 1.3) for x in (-9.5, -7.0, -4.5, -2.0)], 1):
    work = f"RPA_WORK_{number:03d}"
    anchor(work, x, 0, z, NORTH)
    anchor(f"RPA_SEAT_{number:03d}", x, 0.48, z, NORTH)
    access = f"RPA_NAV_{number:03d}"
    anchor(access, x, 0, z + 1.0)
    link(work, access)
anchor("RPA_MANAGER_01", 8, 0, -5.4, NORTH)
anchor("RPA_SEAT_MANAGER", 8, 0.48, -5.4, NORTH)
for number, x in enumerate((-6.4, -5.2, -4.0, -2.8), 1):
    anchor(f"RPA_WAIT_{number:03d}", x, 0, 5.0, SOUTH)
anchor("RPA_MEET_001", 7.3, 0, -2.0, NORTH)
anchor("RPA_MEET_002", 8.7, 0, -2.0, NORTH)
anchor("RPA_RESEARCH_001", 9.2, 0, 6.4, SOUTH)
anchor("RPA_RESEARCH_002", 10.6, 0, 6.4, SOUTH)
# The corridors: rows of desks, the spine from the entrance and branches to the special areas.
spine = {"RPA_NAV_020": (0, 0, 6.2), "RPA_NAV_021": (0, 0, 4.0), "RPA_NAV_022": (0, 0, 2.3), "RPA_NAV_023": (0, 0, -3.2)}
branches = {"RPA_NAV_030": (-4.6, 0, 4.0), "RPA_NAV_040": (4.0, 0, -2.8), "RPA_NAV_041": (8.0, 0, -2.7),
            "RPA_NAV_042": (8.0, 0, -4.3), "RPA_NAV_050": (5.0, 0, 5.4), "RPA_NAV_051": (9.9, 0, 5.4)}
for name, position in {**spine, **branches}.items():
    anchor(name, *position)
link("RPA_NAV_001", "RPA_NAV_002")
link("RPA_NAV_002", "RPA_NAV_003")
link("RPA_NAV_003", "RPA_NAV_004")
link("RPA_NAV_004", "RPA_NAV_023")
link("RPA_NAV_005", "RPA_NAV_006")
link("RPA_NAV_006", "RPA_NAV_007")
link("RPA_NAV_007", "RPA_NAV_008")
link("RPA_NAV_008", "RPA_NAV_022")
link("RPA_SPAWN_01", "RPA_NAV_020")
link("RPA_NAV_020", "RPA_NAV_021")
link("RPA_NAV_021", "RPA_NAV_022", "RPA_NAV_030", "RPA_NAV_050")
link("RPA_NAV_022", "RPA_NAV_023")
link("RPA_NAV_023", "RPA_NAV_040")
link("RPA_NAV_040", "RPA_NAV_041")
link("RPA_NAV_041", "RPA_MEET_001", "RPA_MEET_002", "RPA_NAV_042")
link("RPA_NAV_042", "RPA_MANAGER_01")
link("RPA_NAV_030", "RPA_WAIT_001", "RPA_WAIT_002", "RPA_WAIT_003", "RPA_WAIT_004")
link("RPA_NAV_050", "RPA_NAV_051")
link("RPA_NAV_051", "RPA_RESEARCH_001", "RPA_RESEARCH_002")
for name, text, position in (("CALISMA", "Çalışma alanı", (-5.75, 0.05, -1.6)), ("YONETICI", "Yönetici odası", (8, 3.1, -5.5)),
                             ("BEKLEME", "Bekleme alanı", (-4.6, 0.05, 7.6)), ("ARASTIRMA", "Araştırma köşesi", (9.9, 2.4, 7.4))):
    anchor(f"RPA_LABEL_{name}", *position, rpa_label=text)


# ----- writing the GLB ----------------------------------------------------------------------------
FACES = (((1, 0, 0), (0, 1, 0), (0, 0, 1)), ((-1, 0, 0), (0, 1, 0), (0, 0, -1)), ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
         ((0, -1, 0), (0, 0, -1), (1, 0, 0)), ((0, 0, 1), (1, 0, 0), (0, 1, 0)), ((0, 0, -1), (-1, 0, 0), (0, 1, 0)))


def mesh_data(items):
    positions, normals, indices = [], [], []
    for x, y, z, width, height, depth in items:
        half = (width / 2, height / 2, depth / 2)
        for normal, first, second in FACES:
            base = len(positions)
            centre = [c + n * h for c, n, h in zip((x, y, z), normal, half)]
            for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                positions.append([centre[i] + a * first[i] * half[i] + b * second[i] * half[i] for i in range(3)])
                normals.append(list(normal))
            # Counter-clockwise seen from outside: (first x second) points along the normal.
            cross = [first[1] * second[2] - first[2] * second[1], first[2] * second[0] - first[0] * second[2],
                     first[0] * second[1] - first[1] * second[0]]
            order = (0, 1, 2, 0, 2, 3) if sum(c * n for c, n in zip(cross, normal)) > 0 else (0, 2, 1, 0, 3, 2)
            indices.extend(base + index for index in order)
    return positions, normals, indices


def quaternion(yaw):
    return [0.0, round(math.sin(yaw / 2), 6), 0.0, round(math.cos(yaw / 2), 6)]


def build() -> bytes:
    binary = bytearray()
    views, accessors, meshes, materials, nodes = [], [], [], [], []

    def add_view(data: bytes, target: int) -> int:
        while len(binary) % 4:
            binary.append(0)
        views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(data), "target": target})
        binary.extend(data)
        return len(views) - 1

    for name, ((r, g, b, a), roughness) in MATERIALS.items():
        if not boxes[name]:
            continue
        positions, normals, indices = mesh_data(boxes[name])
        material = {"name": name, "pbrMetallicRoughness": {"baseColorFactor": [r, g, b, a], "metallicFactor": 0.0,
                                                           "roughnessFactor": roughness}}
        if a < 1:
            material.update(alphaMode="BLEND", doubleSided=True)
        materials.append(material)
        flat = [value for point in positions for value in point]
        position_view = add_view(struct.pack(f"<{len(flat)}f", *flat), 34962)
        accessors.append({"bufferView": position_view, "componentType": 5126, "count": len(positions), "type": "VEC3",
                          "min": [round(min(p[i] for p in positions), 4) for i in range(3)],
                          "max": [round(max(p[i] for p in positions), 4) for i in range(3)]})
        flat = [value for normal in normals for value in normal]
        normal_view = add_view(struct.pack(f"<{len(flat)}f", *flat), 34962)
        accessors.append({"bufferView": normal_view, "componentType": 5126, "count": len(normals), "type": "VEC3"})
        index_view = add_view(struct.pack(f"<{len(indices)}I", *indices), 34963)
        accessors.append({"bufferView": index_view, "componentType": 5125, "count": len(indices), "type": "SCALAR"})
        meshes.append({"name": name, "primitives": [{"attributes": {"POSITION": len(accessors) - 3, "NORMAL": len(accessors) - 2},
                                                     "indices": len(accessors) - 1, "material": len(materials) - 1}]})
        nodes.append({"name": f"Ofis_{name}", "mesh": len(meshes) - 1})
    geometry = list(range(len(nodes)))
    layout = []
    for name, position, yaw, extras in anchors:
        node = {"name": name, "translation": [round(value, 4) for value in position]}
        if yaw is not None and yaw != 0:
            node["rotation"] = quaternion(yaw)
        extras = dict(extras)
        if name in links:
            extras["rpa_links"] = ", ".join(links[name])
        if extras:
            node["extras"] = extras
        nodes.append(node)
        layout.append(len(nodes) - 1)
    nodes.append({"name": "Ofis_modeli", "children": geometry})
    nodes.append({"name": "Yerlesim_noktalari", "children": layout})
    while len(binary) % 4:
        binary.append(0)
    document = {"asset": {"version": "2.0", "generator": "RpaOrkestrAI örnek ofis (RPA yerleşim 1)"},
                "scene": 0, "scenes": [{"name": "Ofis", "nodes": [len(nodes) - 2, len(nodes) - 1]}],
                "nodes": nodes, "meshes": meshes, "materials": materials, "accessors": accessors,
                "bufferViews": views, "buffers": [{"byteLength": len(binary)}]}
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    payload += b" " * (-len(payload) % 4)
    chunks = struct.pack("<II", len(payload), 0x4E4F534A) + payload + struct.pack("<II", len(binary), 0x004E4942) + bytes(binary)
    return b"glTF" + struct.pack("<II", 2, 12 + len(chunks)) + chunks


if __name__ == "__main__":
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_bytes(build())
    print(f"{TARGET.relative_to(Path.cwd()) if TARGET.is_relative_to(Path.cwd()) else TARGET}: {TARGET.stat().st_size} bayt")
