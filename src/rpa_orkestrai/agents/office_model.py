"""Kullanıcının kendi 3D ofis modeli (GLB): yalnız bu bilgisayarda ve ofise özel saklanır.

Model, RPA ofis yerleşim sözleşmesine (office_layout) uymalıdır: ajanlar modelin tanımladığı çalışma ve
bekleme noktalarına yerleşir, yalnız modelin yol ağı üzerinde yürür. Sözleşmeye uymayan model reddedilir.
Dosya sunucuya veya başka bir bilgisayara gönderilmez; her bilgisayar kendi modelini içe aktarır.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import threading
from pathlib import Path

from pydantic import Field

from ..models import Model, now
from .office_layout import assign, read_layout

MODEL_LIMIT = 100_000_000
JSON_LIMIT = 64_000_000
GLB_MAGIC = b"glTF"
GLB_VERSION = 2
JSON_CHUNK = 0x4E4F534A
NAME_LIMIT = 120
DEFAULT_NAME = "ofis-modeli.glb"
# A ready office that follows the layout contract, bundled with Studio.
SAMPLE = Path(__file__).resolve().parents[1] / "static" / "office-models" / "ornek-ofis.glb"
SAMPLE_NAME = "Örnek ofis (RPA yerleşim 1).glb"
MAX_OCCUPANTS = 1000
OCCUPANT = re.compile(r"^(?:[a-f0-9]{32}|human-[1-9][0-9]{0,9})$")
# The decoders below are not bundled. Draco breaks loading even as an optional extension.
ALWAYS_UNSUPPORTED = {"KHR_draco_mesh_compression": "Draco"}
REQUIRED_UNSUPPORTED = {"EXT_meshopt_compression": "meshopt", "KHR_texture_basisu": "KTX2/Basis"}


class OfficeModelError(ValueError):
    """A user-facing reason why a file cannot become the office model."""


class Placement(Model):
    """How the model is shown on this computer; its layout itself comes only from the model."""

    # Parts higher than this are cut away so a ceiling does not hide the office (0 = no cut).
    cut_height: float = Field(default=0.0, ge=0, le=100)


class Occupant(Model):
    id: str = Field(pattern=OCCUPANT.pattern)
    role: str = Field(default="department", pattern=r"^(?:manager|department|human)$")
    department: str = Field(default="", max_length=120)


class Occupants(Model):
    occupants: list[Occupant] = Field(max_length=MAX_OCCUPANTS)
    # False when the firm's people could not be loaded: their places are kept, not released.
    humans_complete: bool = True


def _broken() -> OfficeModelError:
    return OfficeModelError("GLB dosyası eksik veya bozuk. Modeli yeniden .glb (glTF 2.0) olarak dışa aktarın.")


def parse_glb(data: bytes) -> dict:
    """Checks the binary container and returns the scene description; the geometry is read by the 3D view."""
    if len(data) > MODEL_LIMIT:
        raise OfficeModelError("Model en fazla 100 MB olabilir. Dokuları küçültüp veya ayrıntıyı azaltıp yeniden dışa aktarın.")
    if len(data) < 20 or data[:4] != GLB_MAGIC:
        raise OfficeModelError("Dosya GLB biçiminde değil. Modeli tek dosya halinde .glb (glTF 2.0 ikili) olarak dışa aktarın.")
    version, length = struct.unpack_from("<II", data, 4)
    if version != GLB_VERSION or length != len(data):
        raise _broken()
    offset, chunks = 12, []
    while offset < length:
        if length - offset < 8:
            raise _broken()
        size, kind = struct.unpack_from("<II", data, offset)
        offset += 8
        if size > length - offset:
            raise _broken()
        chunks.append((kind, offset, size))
        offset += size
    if not chunks or chunks[0][0] != JSON_CHUNK or chunks[0][2] > JSON_LIMIT:
        raise _broken()
    _, start, size = chunks[0]
    try:
        document = json.loads(data[start:start + size].decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise _broken() from None
    asset = document.get("asset") if isinstance(document, dict) else None
    if not isinstance(asset, dict) or not str(asset.get("version", "")).startswith("2"):
        raise OfficeModelError("Yalnız glTF 2.0 modelleri açılabilir.")
    used, required = document.get("extensionsUsed", []), document.get("extensionsRequired", [])
    if not isinstance(used, list) or not isinstance(required, list):
        raise _broken()
    blocked = sorted({ALWAYS_UNSUPPORTED[name] for name in (*used, *required) if name in ALWAYS_UNSUPPORTED}
                     | {REQUIRED_UNSUPPORTED[name] for name in required if name in REQUIRED_UNSUPPORTED})
    if blocked:
        raise OfficeModelError(f"Model {', '.join(blocked)} sıkıştırması kullanıyor; Studio bunu açamaz. "
                               "Modeli sıkıştırmasız GLB olarak yeniden dışa aktarın.")
    for group in ("buffers", "images"):
        items = document.get(group, [])
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise _broken()
        # A path or address would make the view read other files; every part must be inside the GLB.
        if any("uri" in item for item in items):
            raise OfficeModelError("Model dış dosyalara (doku veya .bin) bağlı. Dokuları içine gömerek tek bir .glb dosyası olarak dışa aktarın.")
    meshes = document.get("meshes", [])
    if not isinstance(meshes, list) or not meshes:
        raise OfficeModelError("Modelde görüntülenecek bir şekil (mesh) yok.")
    return document


def contract_error(errors: list[str]) -> OfficeModelError:
    return OfficeModelError("Model RPA ofis yerleşim sözleşmesine uymuyor (Ayrıntılar: Ofis modeli yönergesi):\n"
                            + "\n".join("• " + item for item in errors))


def inspect_glb(data: bytes) -> dict:
    """The container and the layout contract; a model that does not follow the contract is refused."""
    document = parse_glb(data)
    layout = read_layout(document)
    if not layout["ok"]:
        raise contract_error(layout["errors"])
    return {"meshes": len(document["meshes"]), "layout": layout}


def clean_name(value: str) -> str:
    name = re.sub(r"[\x00-\x1f\x7f]", "", Path(str(value or "").replace("\\", "/")).name).strip()
    return name[:NAME_LIMIT] or DEFAULT_NAME


def _write(path: Path, data: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _placement(value) -> dict:
    # Earlier versions also stored a scale and offsets; the model now defines its own layout.
    known = {key: value[key] for key in Placement.model_fields if isinstance(value, dict) and key in value}
    return Placement(**known).model_dump()


class OfficeModels:
    def __init__(self, data_dir: Path | str):
        self.root = Path(data_dir).expanduser().absolute() / "office_models"
        self._lock = threading.Lock()

    @staticmethod
    def key(actor) -> str:
        # One model per office (or per firm without offices): another account on this computer never sees it.
        return f"ofis-{actor.office_id}" if actor.office_id else f"firma-{actor.company_id}"

    def _paths(self, actor) -> tuple[Path, Path]:
        key = self.key(actor)
        return self.root / f"{key}.glb", self.root / f"{key}.json"

    def _places_path(self, actor) -> Path:
        return self.root / f"{self.key(actor)}.places.json"

    def _stored(self, actor) -> dict | None:
        model, meta = self._paths(actor)
        try:
            record = json.loads(meta.read_text(encoding="utf-8"))
            if (not isinstance(record, dict) or not isinstance(record["name"], str)
                    or not re.fullmatch(r"[a-f0-9]{64}", record["sha256"])):
                return None
            if model.is_symlink() or not model.is_file() or model.stat().st_size != record["size"]:
                return None
            record["placement"] = _placement(record.get("placement"))
        except (OSError, ValueError, TypeError, KeyError):
            return None
        return record

    def _record(self, actor) -> dict | None:
        """The stored model when it follows the layout contract; a model of an earlier version is checked once."""
        record = self._stored(actor)
        if record is None:
            return None
        layout = record.get("layout")
        if not (isinstance(layout, dict) and layout.get("ok") is True):
            model, meta = self._paths(actor)
            try:
                layout = read_layout(parse_glb(model.read_bytes()))
            except (OSError, OfficeModelError):
                layout = {"ok": False, "errors": ["Model okunamadı."]}
            with self._lock:
                record["layout"] = layout
                try:
                    _write(meta, json.dumps(record, ensure_ascii=False).encode("utf-8"))
                except OSError:
                    pass
        return record

    def describe(self, actor) -> dict:
        record = self._record(actor)
        if record is None:
            return {"present": False, "placement": Placement().model_dump()}
        if not record["layout"].get("ok"):
            # Imported by an earlier version without the layout contract: kept off until replaced or removed.
            return {"present": False, "placement": Placement().model_dump(),
                    "rejected": {"name": record["name"], "errors": record["layout"].get("errors", [])[:12]}}
        return {"present": True, "id": record["sha256"][:16], "name": record["name"], "size": record["size"],
                "imported_at": record["imported_at"], "placement": record["placement"], "layout": record["layout"]}

    def file(self, actor) -> Path:
        record = self._record(actor)
        if record is None or not record["layout"].get("ok"):
            raise KeyError("model")
        return self._paths(actor)[0]

    def save(self, actor, data: bytes, name: str) -> dict:
        details = inspect_glb(data)
        model, meta = self._paths(actor)
        record = {"name": clean_name(name), "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                  "imported_at": now(), "placement": Placement().model_dump(), "layout": details["layout"]}
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            _write(model, data)
            _write(meta, json.dumps(record, ensure_ascii=False).encode("utf-8"))
        return self.describe(actor)

    def use_sample(self, actor) -> dict:
        try:
            data = SAMPLE.read_bytes()
        except OSError:
            raise OfficeModelError("Örnek ofis modeli bu kurulumda bulunamadı.") from None
        return self.save(actor, data, SAMPLE_NAME)

    def place(self, actor, placement: Placement) -> dict:
        with self._lock:
            record = self._stored(actor)
            if record is None or not (record.get("layout") or {}).get("ok"):
                raise KeyError("model")
            record["placement"] = placement.model_dump()
            _write(self._paths(actor)[1], json.dumps(record, ensure_ascii=False).encode("utf-8"))
        return self.describe(actor)

    def assignments(self, actor, body: Occupants) -> dict:
        """Persistent places of agents and people on the model's work and waiting points."""
        record = self._record(actor)
        if record is None or not record["layout"].get("ok"):
            raise KeyError("model")
        occupants = [item.model_dump() for item in body.occupants]
        if len({item["id"] for item in occupants}) != len(occupants):
            raise OfficeModelError("Aynı çalışan listede iki kez var.")
        path = self._places_path(actor)
        with self._lock:
            try:
                stored = json.loads(path.read_text(encoding="utf-8"))
                previous = stored.get("places") if isinstance(stored, dict) else {}
            except (OSError, ValueError):
                previous = {}
            result = assign(record["layout"], occupants, previous if isinstance(previous, dict) else {},
                            humans_complete=body.humans_complete)
            if result["places"] != previous:
                self.root.mkdir(parents=True, exist_ok=True)
                _write(path, json.dumps({"model": record["sha256"], "places": result["places"]},
                                        ensure_ascii=False).encode("utf-8"))
        return result

    def delete(self, actor) -> None:
        with self._lock:
            for path in (*self._paths(actor), self._places_path(actor)):
                path.unlink(missing_ok=True)
