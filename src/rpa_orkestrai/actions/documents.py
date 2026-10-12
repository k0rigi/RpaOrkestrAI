"""Archives and PDF documents: Zip aç / oluştur and PDF'ten oku."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path, PurePosixPath

from ..errors import WorkflowError
from . import handler
from .common import choice, path

# A small archive can expand enormously (zip bomb); a real business archive stays far below these.
ZIP_MAX_FILES = 20_000
ZIP_MAX_BYTES = 4 * 1024 ** 3
UTF8_FLAG = 0x800


def entry_name(info: zipfile.ZipInfo) -> str:
    """Windows Explorer stores Turkish names in the OEM code page (cp857) without the UTF-8 flag."""
    if info.flag_bits & UTF8_FLAG:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp857")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def safe_member(name: str) -> PurePosixPath | None:
    """The relative path an entry may take, or None for one that would leave the folder."""
    parts = PurePosixPath(name.replace("\\", "/")).parts
    if not parts or name.startswith(("/", "\\")) or any(part in {"..", ""} for part in parts) \
            or ":" in parts[0]:
        return None
    return PurePosixPath(*parts)


def extract(source: Path, destination: Path, overwrite: bool) -> list[str]:
    if not source.is_file():
        raise WorkflowError(f"Zip dosyası bulunamadı: {source}")
    try:
        archive = zipfile.ZipFile(source)
    except (zipfile.BadZipFile, OSError) as exc:
        raise WorkflowError(f"Zip dosyası açılamadı veya bozuk: {source.name}") from exc
    with archive:
        members = archive.infolist()
        if len(members) > ZIP_MAX_FILES:
            raise WorkflowError(f"Zip en fazla {ZIP_MAX_FILES:,} dosya içerebilir; açılmadı.".replace(",", "."))
        if sum(info.file_size for info in members) > ZIP_MAX_BYTES:
            raise WorkflowError("Zip'in açılmış boyutu 4 GB'ı aşıyor; açılmadı.")
        plan = []
        root = destination.resolve()
        for info in members:
            relative = safe_member(entry_name(info))
            if relative is None:
                raise WorkflowError(f"Zip, klasör dışına yazmaya çalışan bir yol içeriyor ({entry_name(info)}); "
                                    "hiçbir dosya açılmadı.")
            target = (root / Path(*relative.parts)).resolve()
            if root != target and root not in target.parents:
                raise WorkflowError("Zip, klasör dışına yazmaya çalışan bir yol içeriyor; hiçbir dosya açılmadı.")
            if info.is_dir():
                continue
            if target.exists() and not overwrite:
                raise WorkflowError(f"Hedefte aynı adlı dosya var: {target}. Üzerine yazmayı açın veya boş bir "
                                    "klasör seçin; hiçbir dosya açılmadı.")
            plan.append((info, target))
        # Every entry is checked before the first file is written.
        written = []
        try:
            for info, target in plan:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as reader, open(target, "wb") as writer:
                    while chunk := reader.read(1024 * 1024):
                        writer.write(chunk)
                written.append(str(target))
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            raise WorkflowError(f"Zip açılırken hata oluştu ({len(written)} dosya açılmıştı): "
                                f"{getattr(exc, 'strerror', None) or exc}") from exc
        return written


def create(sources: list[Path], destination: Path, overwrite: bool) -> list[str]:
    if destination.suffix.lower() != ".zip":
        raise WorkflowError("Oluşturulacak dosyanın uzantısı .zip olmalıdır.")
    if destination.exists() and not overwrite:
        raise WorkflowError(f"Hedefte aynı adlı dosya var: {destination}. Üzerine yazmayı açın veya başka ad verin.")
    files: list[tuple[Path, str]] = []
    for source in sources:
        if not source.exists():
            raise WorkflowError(f"Eklenecek dosya veya klasör bulunamadı: {source}")
        if source.is_dir():
            for folder, _, names in os.walk(source):
                for name in sorted(names):
                    item = Path(folder) / name
                    files.append((item, str(PurePosixPath(source.name, *item.relative_to(source).parts))))
        else:
            files.append((source, source.name))
        if len(files) > ZIP_MAX_FILES:
            raise WorkflowError(f"Zip'e en fazla {ZIP_MAX_FILES:,} dosya eklenebilir.".replace(",", "."))
    target = destination.resolve()
    if target in {item.resolve() for item, _ in files} or any(
            source.is_dir() and source.resolve() in target.parents for source in sources):
        # Inside an added folder, the next run would pack the previous zip into the new one.
        raise WorkflowError("Zip dosyası, eklenen dosyaların veya klasörlerin arasında olamaz; başka bir yere kaydedin.")
    names = [name for _, name in files]
    if len(set(names)) != len(names):
        raise WorkflowError("Aynı adlı iki dosya zip'in aynı yerine eklenecekti; kaynakları kontrol edin.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    try:
        # Names are stored as UTF-8 (flag set by zipfile): Windows and macOS show Turkish letters.
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item, name in files:
                archive.write(item, name)
        os.replace(temporary, destination)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise WorkflowError(f"Zip oluşturulamadı: {exc.strerror or exc}.") from exc
    return names


@handler("file.zip")
def zip_files(ctx, p):
    operation = choice(p.get("operation", "extract"), "İşlem", {"extract", "create"})
    overwrite = p.get("overwrite") is True
    if operation == "extract":
        folder = path(p.get("folder"), "Açılacak klasör")
        files = extract(path(p.get("source"), "Zip dosyası"), folder, overwrite)
        ctx.log(f"Zip açıldı: {len(files)} dosya → {folder}")
        return {"files": files, "count": len(files), "folder": str(folder)}
    destination = path(p.get("destination"), "Oluşturulacak zip dosyası")
    sources = p.get("items")
    items = sources if isinstance(sources, list) else str(sources or "").splitlines()
    items = [item for item in items if str(item).strip()]
    if not items:
        raise WorkflowError("Zip'e eklenecek dosya veya klasörü yazın (her satıra bir tane).")
    if len(items) > 1000:
        raise WorkflowError("Zip'e en fazla 1.000 kaynak satırı eklenebilir.")
    names = create([path(item, "Eklenecek dosya") for item in items], destination, overwrite)
    ctx.log(f"Zip oluşturuldu: {len(names)} dosya → {destination}")
    return {"files": names, "count": len(names), "path": str(destination)}



# ----- PDF'ten oku ---------------------------------------------------------------------------
PDF_MAX_BYTES = 200 * 1024 * 1024
PDF_MAX_PAGES = 1000


def page_numbers(value, count: int) -> list[int]:
    """Zero-based pages from "1-3, 5"; empty means every page."""
    raw = str(value or "").replace(" ", "")
    if not raw:
        return list(range(count))
    chosen: list[int] = []
    for part in raw.split(","):
        bounds = part.split("-")
        if len(bounds) > 2 or not all(item.isdigit() for item in bounds):
            raise WorkflowError("Sayfalar 1-3, 5 biçiminde yazılmalıdır.")
        first, last = int(bounds[0]), int(bounds[-1])
        if not 1 <= first <= last or last > count:
            raise WorkflowError(f"PDF'te {count} sayfa var; {part} sayfası okunamaz.")
        chosen.extend(index for index in range(first - 1, last) if index not in chosen)
    return chosen


def open_pdf(source: Path):
    import pdfplumber
    from pdfminer.pdfdocument import PDFPasswordIncorrect

    if not source.is_file():
        raise WorkflowError(f"PDF dosyası bulunamadı: {source}")
    if source.stat().st_size > PDF_MAX_BYTES:
        raise WorkflowError("PDF dosyası 200 MB'tan büyük; okunmadı.")
    try:
        document = pdfplumber.open(source)
        len(document.pages)
    except PDFPasswordIncorrect as exc:
        raise WorkflowError("PDF şifreli; şifresiz bir kopyasını kullanın.") from exc
    except Exception as exc:
        raise WorkflowError(f"PDF açılamadı veya bozuk: {source.name}") from exc
    if len(document.pages) > PDF_MAX_PAGES:
        document.close()
        raise WorkflowError(f"PDF en fazla {PDF_MAX_PAGES} sayfa olabilir; okunacak sayfaları yazın.")
    return document


def page_image(source: Path, index: int):
    """A scanned page as an image for OCR (about 200 dpi)."""
    import pypdfium2

    document = pypdfium2.PdfDocument(str(source))
    try:
        return document[index].render(scale=200 / 72).to_pil().convert("RGB")
    finally:
        document.close()


def pdf_text(ctx, source: Path, pages: str, ocr: bool) -> str:
    from .screen import ocr as read_image

    texts, scanned = [], []
    with open_pdf(source) as document:
        for index in page_numbers(pages, len(document.pages)):
            ctx.check_cancelled()
            content = document.pages[index].extract_text() or ""
            if not content.strip() and ocr:
                content = read_image(ctx, page_image(source, index))
                scanned.append(index + 1)
            texts.append(content.strip())
    if scanned:
        ctx.log(f"Metni olmayan sayfalar OCR ile okundu: {', '.join(map(str, scanned))}.")
    return "\n\n".join(texts)


def pdf_table(ctx, source: Path, pages: str, number: int, header: bool) -> list[dict]:
    from ..desktop.table_columns import column_names

    found = []
    with open_pdf(source) as document:
        for index in page_numbers(pages, len(document.pages)):
            ctx.check_cancelled()
            found.extend(document.pages[index].extract_tables())
            if len(found) >= number:
                break
    if len(found) < number:
        raise WorkflowError(f"Seçilen sayfalarda {len(found)} tablo bulundu; {number}. tablo yok. Tablolar çizgileriyle "
                            "tanınır; taranmış PDF'te tablo okunamaz, metin modunu kullanın.")
    rows = [[" ".join(str(cell or "").split()) for cell in row] for row in found[number - 1] if row]
    width = max((len(row) for row in rows), default=0)
    rows = [row + [""] * (width - len(row)) for row in rows]
    titles, data = (rows[0], rows[1:]) if header and rows else ([], rows)
    names = column_names(titles, width)
    return [dict(zip(names, row)) for row in data]


@handler("file.read_pdf")
def read_pdf(ctx, p):
    from .common import integer

    source = path(p.get("path"), "PDF dosyası")
    if source.suffix.lower() != ".pdf":
        raise WorkflowError("Dosyanın uzantısı .pdf olmalıdır.")
    if choice(p.get("mode", "text"), "Ne okunsun", {"text", "table"}) == "text":
        return pdf_text(ctx, source, p.get("pages", ""), p.get("ocr", True) is not False)
    return pdf_table(ctx, source, p.get("pages", ""), integer(p.get("table", 1), "Tablo sırası", 1, 1000),
                     p.get("header", True) is not False)
