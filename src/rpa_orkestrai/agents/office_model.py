"""Kullanıcının kendi 3D ofis modeli (GLB): yalnız bu bilgisayarda ve ofise özel saklanır.

Model yalnız görünümdür: ajanlar, masalar ve durumlar ofisin kendi düzeninde kalır. Dosya
sunucuya veya başka bir bilgisayara gönderilmez; her bilgisayar kendi modelini içe aktarır.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import threading
from pathlib import Path
from typing import Literal

from pydantic import Field

from ..models import Model, now

MODEL_LIMIT = 100_000_000
JSON_LIMIT = 64_000_000
GLB_MAGIC = b"glTF"
GLB_VERSION = 2
JSON_CHUNK = 0x4E4F534A
NAME_LIMIT = 120
DEFAULT_NAME = "ofis-modeli.glb"
# The decoders below are not bundled. Draco breaks loading even as an optional extension.
ALWAYS_UNSUPPORTED = {"KHR_draco_mesh_compression": "Draco"}
REQUIRED_UNSUPPORTED = {"EXT_meshopt_compression": "meshopt", "KHR_texture_basisu": "KTX2/Basis"}


class OfficeModelError(ValueError):
    """A user-facing reason why a file cannot become the office model."""


class Placement(Model):
    """Where the model sits in the office; lengths are metres, as glTF defines them."""

    scale: float = Field(default=1.0, ge=0.01, le=100)
    rotation: Literal[0, 90, 180, 270] = 0
    offset_x: float = Field(default=0.0, ge=-500, le=500)
    offset_y: float = Field(default=0.0, ge=-50, le=50)
    offset_z: float = Field(default=0.0, ge=-500, le=500)
    # Parts higher than this are cut away so a ceiling does not hide the office (0 = no cut).
    cut_height: float = Field(default=0.0, ge=0, le=100)
    # The model brings its own floor and walls; the generated ones would overlap them.
    hide_room: bool = True


def _broken() -> OfficeModelError:
    return OfficeModelError("GLB dosyası eksik veya bozuk. Modeli yeniden .glb (glTF 2.0) olarak dışa aktarın.")


def inspect_glb(data: bytes) -> dict:
    """Checks the binary container and the scene description; the geometry is read by the 3D view."""
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
    return {"meshes": len(meshes)}


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

    def _record(self, actor) -> dict | None:
        model, meta = self._paths(actor)
        try:
            record = json.loads(meta.read_text(encoding="utf-8"))
            placement = Placement(**record["placement"]).model_dump()
            if not isinstance(record["name"], str) or not re.fullmatch(r"[a-f0-9]{64}", record["sha256"]):
                return None
            if model.is_symlink() or not model.is_file() or model.stat().st_size != record["size"]:
                return None
        except (OSError, ValueError, TypeError, KeyError):
            return None
        return {**record, "placement": placement}

    def describe(self, actor) -> dict:
        record = self._record(actor)
        if record is None:
            return {"present": False, "placement": Placement().model_dump()}
        return {"present": True, "id": record["sha256"][:16], "name": record["name"], "size": record["size"],
                "imported_at": record["imported_at"], "placement": record["placement"]}

    def file(self, actor) -> Path:
        if self._record(actor) is None:
            raise KeyError("model")
        return self._paths(actor)[0]

    def save(self, actor, data: bytes, name: str) -> dict:
        inspect_glb(data)
        model, meta = self._paths(actor)
        record = {"name": clean_name(name), "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                  "imported_at": now(), "placement": Placement().model_dump()}
        with self._lock:
            self.root.mkdir(parents=True, exist_ok=True)
            # The new model starts from the default placement; the old one's offsets would not fit it.
            _write(model, data)
            _write(meta, json.dumps(record, ensure_ascii=False).encode("utf-8"))
        return self.describe(actor)

    def place(self, actor, placement: Placement) -> dict:
        with self._lock:
            record = self._record(actor)
            if record is None:
                raise KeyError("model")
            record["placement"] = placement.model_dump()
            _write(self._paths(actor)[1], json.dumps(record, ensure_ascii=False).encode("utf-8"))
        return self.describe(actor)

    def delete(self, actor) -> None:
        with self._lock:
            for path in self._paths(actor):
                path.unlink(missing_ok=True)
