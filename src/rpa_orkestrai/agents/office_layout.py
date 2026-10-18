"""RPA ofis yerleşim sözleşmesi, sürüm 1: bir GLB'nin ajan yerleşimi için okunacak noktaları.

Rastgele bir model ajan yerleşimi için yeterli sayılmaz. Model, görünmez ve benzersiz adlı boş düğümlerle
ofis referansını, ajanların çalışacağı ve bekleyeceği noktaları ve yürünebilir yol ağını açıkça tanımlar.
Dekoratif nesne adlarından, zeminden veya mobilyadan yerleşim ya da yol tahmini yapılmaz.

Kurallar (ayrıntı: docs/ofis-modeli.md):
- Uzunluk birimi metre, yukarı ekseni +Y; ofisin zemini RPA_ORIGIN'e göre Y=0.
- Noktanın konumu karakterin ayak tabanıdır; düğümün yerel +Z ekseni karakterin bakacağı yöndür.
- Zorunlu: RPA_ORIGIN (rpa_layout_version = 1), RPA_SPAWN_01, en az bir RPA_WORK_###, en az bir RPA_WAIT_###
  ve RPA_NAV_### düğümleri ile rpa_links bağlantılarından oluşan yol ağı.
- İsteğe bağlı: RPA_LABEL_<alan>, RPA_CAMERA_TARGET, RPA_SEAT_### (aynı numaralı çalışma noktasının oturma
  referansı), RPA_SEAT_MANAGER, RPA_MANAGER_01, RPA_MEET_###, RPA_RESEARCH_###.
"""

from __future__ import annotations

import math
import re

LAYOUT_VERSION = 1
PREFIX = "RPA_"
KINDS = (
    ("origin", re.compile(r"RPA_ORIGIN")),
    ("camera", re.compile(r"RPA_CAMERA_TARGET")),
    ("spawn", re.compile(r"RPA_SPAWN_\d{2}")),
    ("work", re.compile(r"RPA_WORK_\d{3}")),
    ("wait", re.compile(r"RPA_WAIT_\d{3}")),
    ("nav", re.compile(r"RPA_NAV_\d{3}")),
    ("seat", re.compile(r"RPA_SEAT_(?:\d{3}|MANAGER)")),
    ("manager", re.compile(r"RPA_MANAGER_01")),
    ("meet", re.compile(r"RPA_MEET_\d{3}")),
    ("research", re.compile(r"RPA_RESEARCH_\d{3}")),
    ("label", re.compile(r"RPA_LABEL_[A-Za-z0-9_]{1,40}")),
)
# Points a character stands on; they and the RPA_NAV nodes form the walkable path network.
STANDING = ("spawn", "work", "wait", "manager", "meet", "research")
FLOOR_TOLERANCE = 0.05
LEVEL_TOLERANCE = 0.1
SEAT_HEIGHT = (0.3, 0.8)
SEAT_REACH = 1.0
MIN_SPACING = 0.6
MAX_EDGE = 40.0
EXTENT = (1.0, 500.0)
MAX_REPORTED = 12


def _identity():
    return [[1.0 if row == column else 0.0 for column in range(4)] for row in range(4)]


def _multiply(first, second):
    return [[sum(first[row][k] * second[k][column] for k in range(4)) for column in range(4)] for row in range(4)]


def _local(node):
    matrix = node.get("matrix")
    if matrix is not None:
        if not isinstance(matrix, list) or len(matrix) != 16 or not all(isinstance(value, (int, float)) for value in matrix):
            raise ValueError("matrix")
        # glTF stores matrices column by column.
        return [[float(matrix[column * 4 + row]) for column in range(4)] for row in range(4)]
    translation = node.get("translation", [0, 0, 0])
    rotation = node.get("rotation", [0, 0, 0, 1])
    scale = node.get("scale", [1, 1, 1])
    for value, size in ((translation, 3), (rotation, 4), (scale, 3)):
        if not isinstance(value, list) or len(value) != size or not all(isinstance(item, (int, float)) for item in value):
            raise ValueError("transform")
    x, y, z, w = (float(item) for item in rotation)
    length = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / length, y / length, z / length, w / length
    rotate = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
              [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
              [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    result = _identity()
    for row in range(3):
        for column in range(3):
            result[row][column] = rotate[row][column] * float(scale[column])
        result[row][3] = float(translation[row])
    return result


def _apply(matrix, point, w=1.0):
    vector = (*point, w)
    return [sum(matrix[row][k] * vector[k] for k in range(4)) for row in range(3)]


def _rigid_inverse(matrix):
    """Inverse of a rotation + translation (the office reference frame has no scale)."""
    rotate = [[matrix[column][row] for column in range(3)] for row in range(3)]
    offset = [-sum(rotate[row][k] * matrix[k][3] for k in range(3)) for row in range(3)]
    result = _identity()
    for row in range(3):
        result[row][:3] = rotate[row]
        result[row][3] = offset[row]
    return result


def _length(vector):
    return math.sqrt(sum(item * item for item in vector))


def _links(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [item for item in re.split(r"[\s,;]+", value.strip()) if item]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return [item.strip() for item in value if item.strip()]
    raise ValueError("links")


def _extent(document, worlds):
    """Size of the visible geometry from the accessor bounds, after every node transform."""
    accessors, meshes = document.get("accessors", []), document.get("meshes", [])
    low, high = [math.inf] * 3, [-math.inf] * 3
    for index, world in worlds.items():
        node = document["nodes"][index]
        if not isinstance(node.get("mesh"), int) or not 0 <= node["mesh"] < len(meshes):
            continue
        for primitive in meshes[node["mesh"]].get("primitives", []):
            position = (primitive.get("attributes") or {}).get("POSITION")
            if not isinstance(position, int) or not 0 <= position < len(accessors):
                continue
            accessor = accessors[position]
            minimum, maximum = accessor.get("min"), accessor.get("max")
            if not (isinstance(minimum, list) and isinstance(maximum, list) and len(minimum) == len(maximum) == 3):
                continue
            for x in (minimum[0], maximum[0]):
                for y in (minimum[1], maximum[1]):
                    for z in (minimum[2], maximum[2]):
                        corner = _apply(world, (float(x), float(y), float(z)))
                        low = [min(a, b) for a, b in zip(low, corner)]
                        high = [max(a, b) for a, b in zip(high, corner)]
    if not all(math.isfinite(value) for value in low + high):
        return None
    return max(b - a for a, b in zip(low, high))


def read_layout(document: dict) -> dict:
    """Validate the contract; returns {"ok", "errors", "warnings", ...positions in the office frame}."""
    errors: list[str] = []
    warnings: list[str] = []
    nodes = document.get("nodes", [])
    if not isinstance(nodes, list) or not all(isinstance(node, dict) for node in nodes):
        return {"ok": False, "errors": ["Modelin düğüm listesi okunamadı."], "warnings": []}
    scenes = document.get("scenes", [])
    scene_index = document.get("scene", 0)
    worlds: dict[int, list] = {}
    if isinstance(scenes, list) and scenes and isinstance(scene_index, int) and 0 <= scene_index < len(scenes):
        pending = [(index, _identity()) for index in (scenes[scene_index] or {}).get("nodes", [])
                   if isinstance(index, int) and 0 <= index < len(nodes)]
        while pending:
            index, parent = pending.pop()
            if index in worlds:
                return {"ok": False, "errors": ["Modelin düğüm ağacında döngü veya ortak alt düğüm var."], "warnings": []}
            try:
                worlds[index] = _multiply(parent, _local(nodes[index]))
            except ValueError:
                return {"ok": False, "errors": [f"{nodes[index].get('name') or 'Bir düğüm'} dönüşümü okunamadı."],
                        "warnings": []}
            pending.extend((child, worlds[index]) for child in nodes[index].get("children", [])
                           if isinstance(child, int) and 0 <= child < len(nodes))
    # Names: every RPA_ node must be a known, unique, empty node of the shown scene.
    found: dict[str, int] = {}
    for index, node in enumerate(nodes):
        name = node.get("name")
        if not isinstance(name, str) or not name.startswith(PREFIX):
            continue
        kind = next((kind for kind, pattern in KINDS if pattern.fullmatch(name)), None)
        if kind is None:
            errors.append(f"Tanınmayan yerleşim düğümü: {name}. Adın yazımını kontrol edin.")
            continue
        if name in found:
            errors.append(f"{name} adı birden fazla düğümde kullanılmış; her nokta benzersiz olmalı.")
            continue
        found[name] = index
        if "mesh" in node or "camera" in node or "skin" in node:
            errors.append(f"{name} görünmez boş bir düğüm olmalı; içinde şekil, kamera veya iskelet var.")
        if index not in worlds:
            errors.append(f"{name} gösterilen sahnenin içinde değil.")
    origin_index = found.get("RPA_ORIGIN")
    if origin_index is None:
        errors.append("RPA_ORIGIN düğümü yok; ofisin referans noktasını tanımlayın.")
    else:
        version = (nodes[origin_index].get("extras") or {}).get("rpa_layout_version")
        if isinstance(version, str) and version.strip().isdigit():
            version = int(version.strip())
        if type(version) is not int:
            errors.append("Yerleşim sözleşmesinin sürümü yok: RPA_ORIGIN düğümüne rpa_layout_version = 1 özelliğini ekleyin.")
        elif version != LAYOUT_VERSION:
            errors.append(f"Yerleşim sözleşmesi sürümü {version} bu Studio'da desteklenmiyor (desteklenen: {LAYOUT_VERSION}).")
    for name, label in (("RPA_SPAWN_01", "RPA_SPAWN_01 (yeni ajanların ilk görüneceği nokta)"),):
        if name not in found:
            errors.append(f"Zorunlu {label} yok.")
    for kind, label in (("work", "RPA_WORK_###"), ("wait", "RPA_WAIT_###"), ("nav", "RPA_NAV_### (yol ağı)")):
        if not any(next(k for k, pattern in KINDS if pattern.fullmatch(name)) == kind for name in found):
            errors.append(f"En az bir {label} noktası zorunlu.")
    if origin_index is None or origin_index not in worlds or errors:
        return {"ok": False, "errors": errors[:MAX_REPORTED], "warnings": warnings}

    origin = worlds[origin_index]
    axes = [[origin[row][column] for row in range(3)] for column in range(3)]
    if (any(abs(_length(axis) - 1) > 0.001 for axis in axes) or abs(axes[1][1] - 1) > 0.001):
        return {"ok": False, "errors": ["RPA_ORIGIN ölçeksiz ve dik olmalı: yerel +Y yukarıyı göstermeli, ölçek 1 olmalı."],
                "warnings": warnings}
    to_office = _multiply(_rigid_inverse(origin), _identity())
    extent = _extent(document, worlds)
    if extent is None:
        errors.append("Modelin boyutu okunamadı (şekillerin sınır bilgisi eksik).")
    elif not EXTENT[0] <= extent <= EXTENT[1]:
        errors.append(f"Modelin büyüklüğü {extent:.1f} birim; uzunluk birimi metre olmalı (ör. ofis 5–200 m).")

    points: dict[str, dict] = {}
    for name, index in found.items():
        kind = next(kind for kind, pattern in KINDS if pattern.fullmatch(name))
        matrix = _multiply(to_office, worlds[index])
        position = [round(value, 4) for value in _apply(matrix, (0.0, 0.0, 0.0))]
        forward = _apply(matrix, (0.0, 0.0, 1.0), w=0.0)
        size = _length(forward)
        entry = {"kind": kind, "position": position}
        if kind in STANDING or kind == "seat":
            flat = math.hypot(forward[0], forward[2])
            if size == 0 or abs(forward[1]) / size > LEVEL_TOLERANCE or flat == 0:
                errors.append(f"{name} yönü yatay değil: düğümün yerel +Z ekseni karakterin bakacağı yatay yönü göstermeli.")
            else:
                entry["yaw"] = round(math.atan2(forward[0], forward[2]), 5)
        if kind in STANDING or kind == "nav":
            if abs(position[1]) > FLOOR_TOLERANCE:
                errors.append(f"{name} zeminde değil (Y = {position[1]:.2f} m); ayak tabanı Y=0 olmalı.")
        if kind == "label":
            text = (nodes[index].get("extras") or {}).get("rpa_label")
            entry["text"] = (text.strip()[:40] if isinstance(text, str) and text.strip()
                             else name[len("RPA_LABEL_"):].replace("_", " "))
        points[name] = entry

    # Seats belong to the work (or manager) point with the same number.
    seats = {}
    for name, entry in points.items():
        if entry["kind"] != "seat":
            continue
        suffix = name[len("RPA_SEAT_"):]
        owner = "RPA_MANAGER_01" if suffix == "MANAGER" else "RPA_WORK_" + suffix
        if owner not in points:
            errors.append(f"{name} için {owner} yok; oturma referansı aynı numaralı çalışma noktasına aittir.")
            continue
        if not SEAT_HEIGHT[0] <= entry["position"][1] <= SEAT_HEIGHT[1]:
            errors.append(f"{name} oturma yüksekliği {entry['position'][1]:.2f} m; oturak yüzeyi 0,30–0,80 m olmalı.")
        reach = math.hypot(entry["position"][0] - points[owner]["position"][0],
                           entry["position"][2] - points[owner]["position"][2])
        if reach > SEAT_REACH:
            errors.append(f"{name}, {owner} noktasına {reach:.2f} m uzak; en fazla {SEAT_REACH:.1f} m olmalı.")
        if "yaw" in entry and "yaw" in points[owner]:
            turn = abs((entry["yaw"] - points[owner]["yaw"] + math.pi) % (2 * math.pi) - math.pi)
            if turn > math.radians(30):
                warnings.append(f"{name} ile {owner} farklı yönlere bakıyor; oturan karakter oturağın yönüne döner.")
        seats[owner] = name

    # Characters must never overlap: standing points keep a minimum distance.
    standing = sorted(name for name, entry in points.items() if entry["kind"] in STANDING)
    for position, first in enumerate(standing):
        for second in standing[position + 1:]:
            gap = math.hypot(points[first]["position"][0] - points[second]["position"][0],
                             points[first]["position"][2] - points[second]["position"][2])
            if gap < MIN_SPACING:
                errors.append(f"{first} ile {second} arasında {gap:.2f} m var; karakterler çakışır (en az {MIN_SPACING} m).")

    # The path network: only RPA_NAV and standing points, linked explicitly with rpa_links.
    graph_nodes = {name for name, entry in points.items() if entry["kind"] in STANDING or entry["kind"] == "nav"}
    edges = set()
    for name in sorted(graph_nodes):
        try:
            targets = _links((nodes[found[name]].get("extras") or {}).get("rpa_links"))
        except ValueError:
            errors.append(f"{name} rpa_links özelliği okunamadı; düğüm adlarını virgülle ayırarak yazın.")
            continue
        for target in targets:
            if target == name:
                errors.append(f"{name} kendisine bağlanamaz.")
            elif target not in graph_nodes:
                errors.append(f"{name} bilinmeyen veya yürünemeyen bir noktaya bağlanıyor: {target}.")
            else:
                gap = _length([a - b for a, b in zip(points[name]["position"], points[target]["position"])])
                if gap > MAX_EDGE:
                    errors.append(f"{name} – {target} yolu {gap:.1f} m; en fazla {MAX_EDGE:.0f} m olmalı, ara RPA_NAV ekleyin.")
                else:
                    edges.add(tuple(sorted((name, target))))
    neighbours = {name: set() for name in graph_nodes}
    for first, second in edges:
        neighbours[first].add(second)
        neighbours[second].add(first)
    for name in sorted(graph_nodes):
        if not neighbours[name]:
            errors.append(f"{name} yol ağına bağlı değil: rpa_links ile bir RPA_NAV noktasına bağlayın.")
    if "RPA_SPAWN_01" in graph_nodes:
        reached, pending = {"RPA_SPAWN_01"}, ["RPA_SPAWN_01"]
        while pending:
            for other in neighbours[pending.pop()]:
                if other not in reached:
                    reached.add(other)
                    pending.append(other)
        unreachable = sorted(graph_nodes - reached)
        if unreachable and all(neighbours[name] for name in unreachable):
            errors.append("Yol ağı kopuk; RPA_SPAWN_01'den ulaşılamayan noktalar: " + ", ".join(unreachable[:8])
                          + (" …" if len(unreachable) > 8 else ""))

    if errors:
        return {"ok": False, "errors": errors[:MAX_REPORTED] + ([f"… ve {len(errors) - MAX_REPORTED} hata daha."]
                                                                if len(errors) > MAX_REPORTED else []),
                "warnings": warnings[:MAX_REPORTED]}
    origin_world = [origin[row][column] for column in range(4) for row in range(4)]
    labels = [{"name": name, "text": entry["text"], "position": entry["position"]}
              for name, entry in sorted(points.items()) if entry["kind"] == "label"]
    return {"ok": True, "version": LAYOUT_VERSION, "errors": [], "warnings": warnings[:MAX_REPORTED],
            # Column-major, as glTF and three.js store matrices; the 3D view applies its inverse.
            "origin_matrix": [round(value, 6) for value in origin_world],
            "points": {name: entry for name, entry in sorted(points.items()) if entry["kind"] not in {"label", "origin"}},
            "seats": seats, "edges": sorted([list(edge) for edge in edges]), "labels": labels,
            "camera_target": points.get("RPA_CAMERA_TARGET", {}).get("position"),
            "capacity": {"work": sum(1 for entry in points.values() if entry["kind"] == "work"),
                         "wait": sum(1 for entry in points.values() if entry["kind"] == "wait")}}


# ----- placing people on the points --------------------------------------------------------------
def assign(layout: dict, occupants: list[dict], previous: dict[str, str], *, humans_complete: bool) -> dict:
    """Keep every valid earlier place; give newcomers the first free work point, else a free waiting point.

    Each work and waiting point holds one person. Who finds no free point stays in the logical list
    (overflow) and is never drawn on top of someone else or somewhere outside the model."""
    points = layout["points"]
    work = sorted(name for name, entry in points.items() if entry["kind"] == "work")
    wait = sorted(name for name, entry in points.items() if entry["kind"] == "wait")
    present = {item["id"]: item for item in occupants}
    places: dict[str, str] = {}
    taken: set[str] = set()
    # Earlier places stay while the point still exists with the same purpose. Someone missing from a list
    # that was not loaded completely (people of the firm) keeps the place for later.
    for occupant, point in previous.items():
        if not isinstance(point, str) or point not in points or point in taken:
            continue
        person = present.get(occupant)
        if person is None and (occupant.startswith("human-") and not humans_complete):
            places[occupant] = point
            taken.add(point)
            continue
        if person is None:
            continue  # Deleted: the point becomes free.
        kind = points[point]["kind"]
        if kind == "manager" and person.get("role") != "manager":
            continue
        if kind in {"work", "wait", "manager"}:
            places[occupant] = point
            taken.add(point)
    for person in occupants:
        identity = person["id"]
        # The manager agent belongs at the manager's point whenever the model defines one and it is free.
        if (person.get("role") == "manager" and places.get(identity) != "RPA_MANAGER_01"
                and "RPA_MANAGER_01" in points and "RPA_MANAGER_01" not in taken):
            taken.discard(places.get(identity))
            places[identity] = "RPA_MANAGER_01"
            taken.add("RPA_MANAGER_01")
            continue
        if identity in places:
            continue
        free = next((name for name in work + wait if name not in taken), None)
        if free is not None:
            places[identity] = free
            taken.add(free)
    # Someone waiting moves to a work point as soon as one is free, in the order of the list.
    for person in occupants:
        identity = person["id"]
        if places.get(identity) in wait:
            free = next((name for name in work if name not in taken), None)
            if free is None:
                break
            taken.discard(places[identity])
            places[identity] = free
            taken.add(free)
    overflow = [person["id"] for person in occupants if person["id"] not in places]
    return {"places": {identity: point for identity, point in places.items()
                       if identity in present or identity.startswith("human-")},
            "overflow": overflow, "full": bool(overflow)}
