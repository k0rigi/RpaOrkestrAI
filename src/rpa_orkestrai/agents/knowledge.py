"""Ajan bilgi kaynakları: firmanın belgelerinde yerel ve ücretsiz anahtar kelime araması.

Belgeler bu bilgisayarda okunur, parçalara bölünür ve BM25 ile aranır; arama için modele veya bir
bulut hizmetine istek gönderilmez. Modele yalnız bulunan kısa bölümler gider. Belge değişince (boyut
veya değişiklik zamanı) yeniden okunur. Kaynak metinleri veridir; içlerindeki talimatlar yetki vermez.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import re
import threading
import zipfile
from collections import Counter
from pathlib import Path

from ..config import atomic_json
from ..errors import WorkflowError

TEXT_TYPES = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm"}
SUPPORTED = TEXT_TYPES | {".pdf", ".docx", ".xlsx", ".xlsm"}
MAX_FILES = 500
MAX_FILE_BYTES = 30 * 1024 * 1024
MAX_TEXT = 2_000_000
MAX_CHUNKS = 20_000
MAX_DEPTH = 6
MAX_ROWS = 20_000
CHUNK = 900
OVERLAP = 150
RESULT_TEXT = 1200
CACHE_VERSION = 1
TURKISH = str.maketrans("çğıöşüâîû", "cgiosuaiu")
STOP = frozenset("""ve veya ile bir bu su o da de ki mi mu icin gibi daha en cok her ne ama ancak olarak olan
olup ise yani ya hem kadar sonra once bunu buna bunun sizin bizim the and or of to in for is are""".split())


def normalize_source(value: str) -> str:
    text = str(value or "").strip().strip('"')
    if not text:
        raise ValueError("Bilgi kaynağı yolu boş olamaz.")
    path = Path(text).expanduser()
    if not path.is_absolute():
        raise ValueError(f"Bilgi kaynağı tam yol olmalıdır: {text}")
    return str(path)


def terms(text: str) -> list[str]:
    """Casefolded, Turkish-insensitive words; long words also count by their first five letters."""
    lowered = text.replace("İ", "i").replace("I", "ı").casefold().translate(TURKISH)
    result = []
    for word in re.findall(r"[a-z0-9]+", lowered):
        if len(word) < 2 or word in STOP:
            continue
        result.append(word)
        if len(word) > 5 and not word.isdigit():
            result.append(word[:5] + "*")
    return result


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1254"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _docx(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        try:
            info = archive.getinfo("word/document.xml")
        except KeyError:
            raise WorkflowError("Word belgesinin metni bulunamadı.") from None
        if info.file_size > 50 * 1024 * 1024:
            raise WorkflowError("Word belgesi okunamayacak kadar büyük.")
        xml = archive.read(info).decode("utf-8", errors="replace")
    # No XML parser: paragraphs and text runs are enough, and nothing in the file is expanded or fetched.
    paragraphs = []
    for paragraph in re.split(r"</w:p>", xml):
        words = re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", paragraph)
        line = html.unescape("".join(words)).strip()
        if line:
            paragraphs.append(line)
    return "\n\n".join(paragraphs)


def _sheets(path: Path) -> list[tuple[str, str]]:
    import openpyxl

    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sections = []
    try:
        for sheet in book.worksheets:
            header, lines, start = None, [], 0
            for number, row in enumerate(sheet.iter_rows(values_only=True), 1):
                if number > MAX_ROWS:
                    break
                values = ["" if value is None else str(value).strip() for value in row]
                if not any(values):
                    continue
                if header is None:
                    header, start = values, number + 1
                    continue
                pairs = [f"{header[i] if i < len(header) and header[i] else f'Sütun {i + 1}'}: {value}"
                         for i, value in enumerate(values) if value]
                lines.append("; ".join(pairs))
            if header is not None and not lines:
                lines.append("; ".join(value for value in header if value))
            if lines:
                sections.append((f"{sheet.title} (satır {start}–)", "\n".join(lines)))
    finally:
        book.close()
    return sections


def _pdf(path: Path) -> list[tuple[str, str]]:
    from ..actions.documents import open_pdf

    sections = []
    with open_pdf(path) as document:
        for index, page in enumerate(document.pages):
            content = page.extract_text() or ""
            if content.strip():
                sections.append((f"s. {index + 1}", content))
    if not sections:
        raise WorkflowError("PDF'te okunabilir metin yok (taranmış belge olabilir; metin içeren bir kopya ekleyin).")
    return sections


def extract(path: Path) -> list[tuple[str, str]]:
    """The file's text as (location, text) sections."""
    suffix = path.suffix.casefold()
    if path.stat().st_size > MAX_FILE_BYTES:
        raise WorkflowError("Dosya 30 MB'tan büyük; bölerek ekleyin.")
    if suffix in TEXT_TYPES:
        content = _decode(path.read_bytes())
        if suffix in {".html", ".htm"}:
            from ..integrations.imap import html_text

            content = html_text(content)
        return [("", content)]
    if suffix == ".pdf":
        return _pdf(path)
    if suffix == ".docx":
        return [("", _docx(path))]
    if suffix in {".xlsx", ".xlsm"}:
        return _sheets(path)
    raise WorkflowError("Desteklenmeyen dosya türü.")


def split(sections: list[tuple[str, str]]) -> list[dict]:
    chunks, total = [], 0
    for location, content in sections:
        content = content[:max(0, MAX_TEXT - total)]
        total += len(content)
        paragraphs = [" ".join(part.split()) for part in re.split(r"\n\s*\n|\r\n\r\n", content)]
        paragraphs = [part for part in paragraphs if part]
        current = ""
        for paragraph in paragraphs:
            while len(paragraph) > CHUNK:
                cut = paragraph.rfind(" ", 0, CHUNK)
                cut = cut if cut > CHUNK // 2 else CHUNK
                piece, paragraph = paragraph[:cut], paragraph[cut:].strip()
                if current:
                    chunks.append({"loc": location, "text": current})
                    current = current[-OVERLAP:]
                chunks.append({"loc": location, "text": (current + " " + piece).strip()})
                current = piece[-OVERLAP:]
            if current and len(current) + len(paragraph) + 1 > CHUNK:
                chunks.append({"loc": location, "text": current})
                current = current[-OVERLAP:] if len(current) > OVERLAP else ""
            current = f"{current} {paragraph}".strip()
        if current:
            chunks.append({"loc": location, "text": current})
        if total >= MAX_TEXT:
            break
    return [chunk for chunk in chunks if terms(chunk["text"])]


def files_of(source: Path) -> tuple[list[Path], int]:
    """Supported files of a file or folder (hidden, temporary and linked entries are skipped)."""
    if source.is_symlink():
        return [], 1
    if source.is_file():
        return ([source], 0) if source.suffix.casefold() in SUPPORTED else ([], 1)
    found, skipped = [], 0
    stack = [(source, 0)]
    while stack and len(found) < MAX_FILES:
        folder, depth = stack.pop()
        try:
            entries = sorted(folder.iterdir(), key=lambda item: item.name.casefold())
        except OSError:
            skipped += 1
            continue
        for entry in entries:
            if entry.name.startswith((".", "~$")) or entry.is_symlink():
                continue
            if entry.is_dir():
                if depth + 1 < MAX_DEPTH:
                    stack.append((entry, depth + 1))
            elif entry.suffix.casefold() in SUPPORTED:
                found.append(entry)
                if len(found) >= MAX_FILES:
                    break
            else:
                skipped += 1
    return found, skipped


class KnowledgeBase:
    """Extracted text per file is cached under the Studio data folder and reused until the file changes."""

    def __init__(self, cache_dir: Path, *, protected: list[Path] | tuple = ()):
        self.cache_dir = Path(cache_dir)
        self.protected = [Path(item).expanduser().resolve() for item in protected]
        self._lock = threading.RLock()
        self._memory: dict[str, tuple[tuple[int, int], dict]] = {}

    def check_source(self, source: str) -> Path:
        path = Path(source).expanduser()
        resolved = path.resolve()
        for root in self.protected:
            if resolved == root or root in resolved.parents or resolved in root.parents:
                raise WorkflowError("Bilgi kaynağı Studio'nun veri veya program klasörü olamaz: "
                                    f"{source}. Belgeleri ayrı bir klasöre koyun.")
        return path

    def _entry(self, path: Path) -> dict:
        stat = path.stat()
        signature = (stat.st_size, stat.st_mtime_ns)
        key = str(path)
        with self._lock:
            cached = self._memory.get(key)
            if cached and cached[0] == signature:
                return cached[1]
        cache = self.cache_dir / (hashlib.sha256(key.encode("utf-8")).hexdigest() + ".json")
        entry = None
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if data.get("version") == CACHE_VERSION and data.get("path") == key and tuple(data.get("signature", ())) == signature:
                entry = data
        except (OSError, ValueError):
            pass
        if entry is None:
            try:
                chunks, error = split(extract(path)), None
            except WorkflowError as exc:
                chunks, error = [], str(exc)
            except Exception:
                chunks, error = [], "Dosya okunamadı (bozuk, şifreli veya başka bir programda açık olabilir)."
            entry = {"version": CACHE_VERSION, "path": key, "signature": list(signature), "chunks": chunks, "error": error}
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                atomic_json(cache, entry)
            except OSError:
                pass
        entry["counts"] = [Counter(terms(chunk["text"])) for chunk in entry["chunks"]]
        with self._lock:
            self._memory[key] = (signature, entry)
            if len(self._memory) > 2000:
                self._memory.pop(next(iter(self._memory)))
        return entry

    def _documents(self, sources: list[str]):
        for source in sources:
            path = self.check_source(source)
            if not path.exists():
                continue
            files, _ = files_of(path)
            for file in files:
                try:
                    yield file, self._entry(file)
                except OSError:
                    continue

    def status(self, sources: list[str]) -> list[dict]:
        result = []
        for source in sources:
            item = {"path": source, "exists": False, "kind": "", "files": 0, "chunks": 0, "skipped": 0, "errors": []}
            try:
                path = self.check_source(source)
            except WorkflowError as exc:
                item["errors"].append({"name": source, "error": str(exc)})
                result.append(item)
                continue
            if path.exists():
                item.update(exists=True, kind="folder" if path.is_dir() else "file")
                files, item["skipped"] = files_of(path)
                for file in files:
                    try:
                        entry = self._entry(file)
                    except OSError:
                        item["errors"].append({"name": file.name, "error": "Dosya okunamadı."})
                        continue
                    item["files"] += 1
                    item["chunks"] += len(entry["chunks"])
                    if entry["error"] and len(item["errors"]) < 5:
                        item["errors"].append({"name": file.name, "error": entry["error"]})
            result.append(item)
        return result

    def search(self, sources: list[str], query: str, limit: int = 4) -> list[dict]:
        wanted = list(dict.fromkeys(terms(query)))
        if not wanted:
            raise WorkflowError("Aranacak anlamlı bir kelime yazın.")
        pool = []
        for file, entry in self._documents(sources):
            for chunk, counts in zip(entry["chunks"], entry["counts"]):
                pool.append((file, chunk, counts))
                if len(pool) >= MAX_CHUNKS:
                    break
            if len(pool) >= MAX_CHUNKS:
                break
        if not pool:
            return []
        lengths = [sum(counts.values()) for _, _, counts in pool]
        average = sum(lengths) / len(lengths) or 1
        frequency = {term: sum(1 for _, _, counts in pool if term in counts) for term in wanted}
        scored = []
        for (file, chunk, counts), length in zip(pool, lengths):
            score = 0.0
            for term in wanted:
                found = counts.get(term, 0)
                if not found:
                    continue
                idf = math.log(1 + (len(pool) - frequency[term] + 0.5) / (frequency[term] + 0.5))
                # Stems weigh half: an exact word match ranks above a shared five-letter beginning.
                weight = 0.5 if term.endswith("*") else 1.0
                score += weight * idf * found * 2.2 / (found + 1.2 * (0.25 + 0.75 * length / average))
            if score > 0:
                scored.append((score, file, chunk))
        scored.sort(key=lambda item: -item[0])
        return [{"source": file.name, "location": chunk["loc"], "text": chunk["text"][:RESULT_TEXT],
                 "score": round(score, 3)} for score, file, chunk in scored[:limit]]
