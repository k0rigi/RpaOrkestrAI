"""Reference images travel inside an exported flow, so its image steps work on another computer.

The steps keep naming an image by its path below the template folder (``capture-….png``). An
export adds the images it finds there; an import writes them back. An import never overwrites a
file: the same image is reused, a different image with the same name is saved under a new name
and the steps are pointed at it.
"""

from __future__ import annotations

import base64
import binascii
from pathlib import Path, PurePosixPath

from .models import Step

IMAGE_LIMIT = 4 * 1024 * 1024
SIGNATURES = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")  # PNG, JPEG
SUFFIXES = {".png", ".jpg", ".jpeg"}


class TemplateError(ValueError):
    pass


def referenced(steps: list[Step]) -> list[str]:
    """The image names the steps use, in flow order, each once."""
    names: list[str] = []

    def walk(items: list[Step]) -> None:
        for step in items:
            value = step.params.get("template")
            if isinstance(value, str) and value.strip() and value not in names:
                names.append(value)
            walk(step.children)
            walk(step.otherwise)

    walk(steps)
    return names


def relative_name(name: str) -> PurePosixPath | None:
    """The name as a path below the template folder; None for anything that could point elsewhere."""
    if not isinstance(name, str) or not 0 < len(name) <= 255 or any(c in name for c in "\\:\x00"):
        return None
    path = PurePosixPath(name)
    if path.is_absolute() or any(part.startswith(".") or not part.strip() for part in path.parts):
        return None
    return path if path.suffix.lower() in SUFFIXES else None


def inside(root: Path, relative: PurePosixPath) -> Path | None:
    path = (root / relative).resolve()
    return path if path.is_relative_to(root) else None


def pack(steps: list[Step], root: Path) -> dict[str, str]:
    """The images the steps use that exist in the template folder, base64 encoded by name."""
    images: dict[str, str] = {}
    for name in referenced(steps):
        relative = relative_name(name)
        path = inside(root, relative) if relative else None
        if path is None or not path.is_file() or path.stat().st_size > IMAGE_LIMIT:
            continue
        data = path.read_bytes()
        if data.startswith(SIGNATURES):
            images[name] = base64.b64encode(data).decode("ascii")
    return images


def decode(images: dict[str, str], root: Path) -> list[tuple[str, Path, bytes]]:
    """Checks every image before anything is written; an import saves all of them or none."""
    decoded = []
    for name, encoded in images.items():
        relative = relative_name(name)
        target = inside(root, relative) if relative else None
        if target is None:
            raise TemplateError(f"Akış dosyasındaki referans görselin adı geçersiz: {name}")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError, TypeError) as exc:
            raise TemplateError(f"Akış dosyasındaki referans görsel okunamadı: {name}") from exc
        if len(data) > IMAGE_LIMIT or not data.startswith(SIGNATURES):
            raise TemplateError(f"Referans görsel 4 MB'tan küçük bir PNG veya JPEG olmalıdır: {name}")
        decoded.append((name, target, data))
    return decoded


def unpack(images: dict[str, str], root: Path) -> dict[str, str]:
    """Saves the images below root; returns old name → new name for the images saved under a new name."""
    renames: dict[str, str] = {}
    for name, target, data in decode(images, root):
        stem, suffix, number = target.stem, target.suffix, 1
        while target.exists():
            if target.is_file() and target.read_bytes() == data:
                break
            number += 1
            target = target.with_name(f"{stem}-{number}{suffix}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as handle:  # never replaces a file that appeared meanwhile
                handle.write(data)
        saved = target.relative_to(root).as_posix()
        if saved != name:
            renames[name] = saved
    return renames


def rename(steps: list[Step], renames: dict[str, str]) -> None:
    for step in steps:
        value = step.params.get("template")
        if isinstance(value, str) and value in renames:
            step.params["template"] = renames[value]
        rename(step.children, renames)
        rename(step.otherwise, renames)
