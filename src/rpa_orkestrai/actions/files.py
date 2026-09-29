"""Files, folders, CSV and Excel tables (AutoHotkey FileRead/FileAppend/Loop Files)."""

from __future__ import annotations

import csv
import fnmatch
import glob
import io
import shutil
import time
from datetime import date, datetime
from pathlib import Path

from ..errors import WorkflowError
from . import handler
from .common import choice, integer, jsonable, number, path, text

READ_LIMIT = 20 * 1024 * 1024
TABLE_ROWS = 100_000


def _read_bytes(file: Path) -> bytes:
    try:
        if file.stat().st_size > READ_LIMIT:
            raise WorkflowError("Dosya 20 MB'tan büyük; parça parça işleyin.")
        return file.read_bytes()
    except FileNotFoundError as exc:
        raise WorkflowError(f"Dosya bulunamadı: {file}") from exc
    except IsADirectoryError as exc:
        raise WorkflowError(f"Bu bir klasör, dosya değil: {file}") from exc
    except OSError as exc:
        raise WorkflowError(f"Dosya okunamadı: {file}") from exc


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


@handler("file.read_text")
def read_text(ctx, p):
    return _decode(_read_bytes(path(p.get("path"))))


@handler("file.write_text")
def write_text(ctx, p):
    file = path(p.get("path"))
    content = text(p.get("text"), "Yazılacak metin", required=False, limit=10_000_000)
    mode = choice(p.get("mode", "overwrite"), "Yazma biçimi", {"overwrite", "append"})
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        with file.open("a" if mode == "append" else "w", encoding="utf-8", newline="") as handle:
            if mode == "append" and p.get("new_line", True) is True and file.stat().st_size:
                handle.write("\n")
            handle.write(content)
    except OSError as exc:
        raise WorkflowError(f"Dosyaya yazılamadı: {file}. Klasörün yazma iznini ve dosyanın açık olup "
                            "olmadığını kontrol edin.") from exc
    return str(file)


@handler("file.exists")
def exists(ctx, p):
    file = path(p.get("path"))
    kind = choice(p.get("kind", "any"), "Tür", {"any", "file", "folder"})
    return file.is_file() if kind == "file" else file.is_dir() if kind == "folder" else file.exists()


@handler("file.list")
def list_files(ctx, p):
    folder = path(p.get("folder"), "Klasör")
    pattern = text(p.get("pattern") or "*", "Dosya deseni", limit=200)
    if not folder.is_dir():
        raise WorkflowError(f"Klasör bulunamadı: {folder}")
    candidates = folder.rglob("*") if p.get("recursive") is True else folder.iterdir()
    rows = []
    for item in candidates:
        ctx.check_cancelled()
        if not item.is_file() or not fnmatch.fnmatch(item.name.casefold(), pattern.casefold()):
            continue
        stat = item.stat()
        rows.append({"name": item.name, "path": str(item), "folder": str(item.parent),
                     "extension": item.suffix.lstrip(".").lower(), "size": stat.st_size,
                     "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")})
        if len(rows) >= 10_000:
            break
    order = choice(p.get("sort", "name"), "Sıralama", {"name", "newest", "oldest"})
    rows.sort(key=lambda row: row["name"].casefold() if order == "name" else row["modified"],
              reverse=order == "newest")
    return rows


@handler("file.operation")
def operation(ctx, p):
    kind = choice(p.get("operation", "copy"), "İşlem", {"copy", "move", "delete", "create_folder"})
    source = path(p.get("source"), "Kaynak")
    try:
        if kind == "create_folder":
            source.mkdir(parents=True, exist_ok=True)
            return str(source)
        if not source.exists():
            raise WorkflowError(f"Kaynak bulunamadı: {source}")
        if kind == "delete":
            shutil.rmtree(source) if source.is_dir() else source.unlink()
            return str(source)
        destination = path(p.get("destination"), "Hedef")
        if destination.is_dir():
            destination = destination / source.name
        if destination.exists() and p.get("overwrite") is not True:
            raise WorkflowError(f"Hedefte aynı adlı dosya var: {destination}. Üzerine yazmayı açın veya başka ad verin.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if kind == "copy":
            if source.is_dir():
                shutil.copytree(source, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(source, destination)
        else:
            shutil.move(str(source), str(destination))
        return str(destination)
    except OSError as exc:
        raise WorkflowError(f"Dosya işlemi yapılamadı: {exc.strerror or exc}.") from exc


@handler("file.wait")
def wait(ctx, p):
    """Wait until a file (wildcards allowed) exists and its size stops changing, e.g. a download."""
    pattern = str(path(p.get("path")))
    timeout = number(p.get("timeout", 60), "Bekleme süresi", 0, 3600)
    deadline, last = time.monotonic() + timeout, None
    while True:
        ctx.check_cancelled()
        matches = sorted((Path(item) for item in glob.glob(pattern)), key=lambda item: item.stat().st_mtime
                         if item.exists() else 0)
        ready = [item for item in matches if item.is_file()
                 and not item.name.endswith((".crdownload", ".part", ".download", ".tmp"))]
        if ready:
            current = (str(ready[-1]), ready[-1].stat().st_size)
            if current == last:
                return current[0]
            last = current
        if time.monotonic() >= deadline:
            raise WorkflowError("Dosya bekleme süresi içinde oluşmadı veya indirmesi bitmedi.")
        ctx.wait(min(0.5, max(0.0, deadline - time.monotonic())))


def _cell(value):
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return jsonable(value)


def _headers(values, width):
    names, seen = [], set()
    for index in range(width):
        raw = values[index] if index < len(values) else None
        name = str(raw).strip() if raw not in (None, "") else f"sutun_{index + 1}"
        base, counter = name, 2
        while name in seen:
            name, counter = f"{base}_{counter}", counter + 1
        seen.add(name)
        names.append(name)
    return names


@handler("file.read_table")
def read_table(ctx, p):
    """Rows as objects keyed by the header row; empty trailing rows are skipped."""
    file = path(p.get("path"))
    header_row = integer(p.get("header_row", 1), "Başlık satırı", 0, 1000)
    limit = integer(p.get("max_rows", 10_000), "En fazla satır", 1, TABLE_ROWS)
    suffix = file.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        from openpyxl import load_workbook

        _read_bytes(file)  # size and existence checks
        try:
            book = load_workbook(file, read_only=True, data_only=True)
        except Exception as exc:
            raise WorkflowError("Excel dosyası açılamadı. Dosya Excel'de açıksa kapatıp tekrar deneyin.") from exc
        try:
            sheet_name = text(p.get("sheet"), "Sayfa", required=False, limit=100).strip()
            if sheet_name and sheet_name not in book.sheetnames:
                raise WorkflowError(f"“{sheet_name}” sayfası yok. Sayfalar: {', '.join(book.sheetnames)}")
            sheet = book[sheet_name] if sheet_name else book.active
            matrix = [list(row) for row in sheet.iter_rows(values_only=True)]
        finally:
            book.close()
    elif suffix in {".csv", ".txt", ".tsv"}:
        content = _decode(_read_bytes(file))
        try:
            dialect = csv.Sniffer().sniff(content[:5000], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        matrix = [list(row) for row in csv.reader(io.StringIO(content), dialect)]
    elif suffix == ".xls":
        raise WorkflowError("Eski .xls biçimi desteklenmez; dosyayı Excel'de .xlsx olarak kaydedin.")
    else:
        raise WorkflowError("Desteklenen tablo biçimleri: .xlsx, .xlsm, .csv, .tsv, .txt")
    if header_row:
        headers_source = matrix[header_row - 1] if len(matrix) >= header_row else []
        body = matrix[header_row:]
    else:
        headers_source, body = [], matrix
    width = max([len(headers_source), *(len(row) for row in body[:limit])], default=0)
    headers = _headers(headers_source, width)
    rows = []
    for number_in_sheet, values in enumerate(body, start=header_row + 1):
        if all(value in (None, "") for value in values):
            continue
        row = {name: _cell(values[index]) if index < len(values) else None for index, name in enumerate(headers)}
        row["row_number"] = number_in_sheet
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


@handler("file.write_table")
def write_table(ctx, p):
    rows = p.get("rows")
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list) or len(rows) > TABLE_ROWS:
        raise WorkflowError("Yazılacak veri en fazla 100.000 kayıtlık bir liste olmalıdır.")
    records = [row if isinstance(row, dict) else {"deger": row} for row in rows]
    headers = list(dict.fromkeys(key for row in records for key in row if key != "row_number"))
    file = path(p.get("path"))
    append = choice(p.get("mode", "overwrite"), "Yazma biçimi", {"overwrite", "append"}) == "append"
    suffix = file.suffix.lower()
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        if suffix in {".xlsx", ".xlsm"}:
            from openpyxl import Workbook, load_workbook

            sheet_name = text(p.get("sheet") or "Sayfa1", "Sayfa", limit=31).strip()
            if append and file.exists():
                book = load_workbook(file)
                sheet = book[sheet_name] if sheet_name in book.sheetnames else book.create_sheet(sheet_name)
                existing = [cell.value for cell in sheet[1]] if sheet.max_row >= 1 else []
                if not any(value not in (None, "") for value in existing):
                    sheet.append(headers)
                    existing = headers
                order = [str(name) for name in existing if name not in (None, "")]
                order += [name for name in headers if name not in order]
                if len(order) > len(existing):
                    for column, name in enumerate(order, start=1):
                        sheet.cell(row=1, column=column, value=name)
            else:
                book = Workbook()
                sheet = book.active
                sheet.title = sheet_name
                sheet.append(headers)
                order = headers
            for row in records:
                sheet.append([_excel(row.get(name)) for name in order])
            book.save(file)
        elif suffix in {".csv", ".txt", ".tsv"}:
            exists_before = file.exists() and file.stat().st_size > 0
            delimiter = "\t" if suffix == ".tsv" else text(p.get("delimiter") or ";", "Ayraç", limit=1)
            with file.open("a" if append else "w", encoding="utf-8-sig" if not (append and exists_before) else "utf-8",
                           newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=headers, delimiter=delimiter, extrasaction="ignore")
                if not (append and exists_before):
                    writer.writeheader()
                for row in records:
                    writer.writerow({name: _excel(row.get(name)) for name in headers})
        else:
            raise WorkflowError("Yazma için .xlsx, .csv veya .tsv uzantısı kullanın.")
    except PermissionError as exc:
        raise WorkflowError(f"Dosyaya yazılamadı: {file}. Dosya Excel'de açıksa kapatın.") from exc
    except OSError as exc:
        raise WorkflowError(f"Dosyaya yazılamadı: {file}.") from exc
    return str(file)


def _excel(value):
    if isinstance(value, (dict, list)):
        import json

        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) and not _numeric(value):
        return "'" + value  # never let data become a spreadsheet formula
    return value


def _numeric(value: str) -> bool:
    try:
        float(value.replace(",", "."))
        return True
    except ValueError:
        return False
