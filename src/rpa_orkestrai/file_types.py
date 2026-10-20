"""Dosya uzantısı ve içerik türü: izin verilen uzantılar listesi ve dosyanın içinin uzantısıyla uyuşması.

İçerik, dosyanın ilk baytlarından tanınır (PDF, Office, zip, resim, HTML, düz metin…). Tanınamayan veya uzantısı
listede olmayan türlerde "uyuşmuyor" denmez; yalnız açıkça farklı olan içerik (ör. .xlsx adıyla inen bir web
sayfası) uyuşmazlık sayılır.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .errors import WorkflowError

HEAD_BYTES = 4096
EXTENSION = re.compile(r"^[a-z0-9]{1,15}$")
SEPARATORS = re.compile(r"[\s,;|]+")
MAX_EXTENSIONS = 50

# Detected type -> label shown to the user.
LABELS = {
    "pdf": "PDF", "zip": "Office (yeni biçim) veya zip arşivi", "ole": "Office (eski biçim: .xls/.doc)",
    "png": "PNG resmi", "jpeg": "JPEG resmi", "gif": "GIF resmi", "bmp": "BMP resmi", "tiff": "TIFF resmi",
    "webp": "WEBP resmi", "gzip": "gzip arşivi", "rar": "RAR arşivi", "7z": "7z arşivi",
    "html": "web sayfası (HTML)", "xml": "XML", "text": "düz metin", "empty": "boş dosya",
    "binary": "tanınmayan ikili içerik", "unknown": "tanınmadı",
}
# Extension -> the detected types its content may have.
EXPECTED = {
    **dict.fromkeys(("xlsx", "xlsm", "xltx", "xltm", "docx", "docm", "dotx", "pptx", "pptm", "ppsx", "zip",
                     "odt", "ods", "odp", "epub", "jar", "apk", "nupkg", "vsix", "kmz"), {"zip"}),
    **dict.fromkeys(("xls", "xlt", "doc", "dot", "ppt", "pps", "msg", "vsd", "mpp"), {"ole"}),
    "pdf": {"pdf"}, "png": {"png"}, "jpg": {"jpeg"}, "jpeg": {"jpeg"}, "jfif": {"jpeg"}, "gif": {"gif"},
    "bmp": {"bmp"}, "tif": {"tiff"}, "tiff": {"tiff"}, "webp": {"webp"}, "gz": {"gzip"}, "tgz": {"gzip"},
    "rar": {"rar"}, "7z": {"7z"},
    **dict.fromkeys(("txt", "csv", "tsv", "json", "log", "prn", "sql", "md", "ini", "yaml", "yml", "dat"),
                    {"text", "empty"}),
    "xml": {"xml", "text", "empty"}, "html": {"html", "xml", "text"}, "htm": {"html", "xml", "text"},
}
SIGNATURES = (
    (b"%PDF-", "pdf"), (b"PK\x03\x04", "zip"), (b"PK\x05\x06", "zip"), (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "ole"),
    (b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpeg"), (b"GIF87a", "gif"), (b"GIF89a", "gif"),
    (b"II*\x00", "tiff"), (b"MM\x00*", "tiff"), (b"\x1f\x8b", "gzip"), (b"Rar!\x1a\x07", "rar"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
)


def parse_extensions(value, label: str = "İzin verilen uzantılar") -> list[str]:
    """'xlsx, .XLS; csv' -> ['xlsx', 'xls', 'csv']; empty -> []."""
    items = value if isinstance(value, list) else SEPARATORS.split(str(value or ""))
    extensions = []
    for item in items:
        item = str(item).strip().lstrip("*").lstrip(".").casefold()
        if not item:
            continue
        if not EXTENSION.match(item):
            raise WorkflowError(f"{label}: “{item}” geçerli bir uzantı değil. Örnek: xlsx, csv, pdf")
        if item not in extensions:
            extensions.append(item)
    if len(extensions) > MAX_EXTENSIONS:
        raise WorkflowError(f"{label} en fazla {MAX_EXTENSIONS} uzantı olabilir.")
    return extensions


def extension_of(file: Path) -> str:
    return file.suffix.lstrip(".").casefold()


def detect(file: Path) -> str:
    """The content type read from the file's first bytes."""
    with file.open("rb") as handle:
        head = handle.read(HEAD_BYTES)
    if not head:
        return "empty"
    for signature, kind in SIGNATURES:
        if head.startswith(signature):
            return kind
    if head.startswith(b"BM") and len(head) > 14:
        return "bmp"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    for bom, encoding in ((b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")):
        if head.startswith(bom):
            return _text_kind(head[len(bom):].decode(encoding, errors="ignore"))
    if b"\x00" in head:
        return "binary"
    try:
        text = head.decode("utf-8")
    except UnicodeDecodeError as exc:
        # A cut multi-byte character at the end of the sample is still text.
        if exc.start < len(head) - 3:
            text = head.decode("cp1254", errors="replace")
        else:
            text = head[:exc.start].decode("utf-8")
    return _text_kind(text)


def _text_kind(text: str) -> str:
    start = text.lstrip().casefold()
    if start.startswith(("<!doctype html", "<html", "<head", "<body")):
        return "html"
    if start.startswith("<?xml"):
        return "html" if "<html" in start[:600] else "xml"
    return "text"


def content_matches(extension: str, kind: str) -> bool | None:
    """True/False when the extension's content is known; None when it cannot be judged."""
    expected = EXPECTED.get(extension)
    if expected is None or kind == "unknown":
        return None
    return kind in expected


def describe(file: Path) -> dict:
    """Name, extension, size and the content type of an existing file."""
    stat = file.stat()
    kind = detect(file)
    extension = extension_of(file)
    return {"path": str(file), "name": file.name, "stem": file.stem, "folder": str(file.parent),
            "extension": extension, "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"), "type": kind,
            "type_label": LABELS[kind], "content_matches": content_matches(extension, kind)}


def problem(info: dict, allowed: list[str], check_content: bool) -> str:
    """Why the file does not fit, in Turkish; empty when it fits."""
    if allowed and info["extension"] not in allowed:
        shown = f".{info['extension']}" if info["extension"] else "uzantısız"
        return f"“{info['name']}” {shown} dosyası; izin verilenler: {', '.join('.' + item for item in allowed)}."
    if check_content and info["content_matches"] is False:
        return (f"“{info['name']}” .{info['extension']} uzantılı ama içeriği {info['type_label']}. Dosya beklenen "
                "türde değil (ör. site hata sayfası indirmiş olabilir).")
    return ""
