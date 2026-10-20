"""Files, folders, CSV and Excel tables (AutoHotkey FileRead/FileAppend/Loop Files)."""

from __future__ import annotations

import csv
import fnmatch
import glob
import io
import math
import re
import shutil
import time
from datetime import date, datetime
from pathlib import Path

from ..errors import WorkflowError
from ..file_types import describe, extension_of, parse_extensions, problem
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


@handler("file.info")
def info(ctx, p):
    """Name, extension, size and content type of one file; optionally stops when it is not the expected kind."""
    file = path(p.get("path"))
    allowed = parse_extensions(p.get("extensions"))
    check = p.get("check_content", True) is not False
    on_problem = choice(p.get("on_problem", "stop"), "Uygun değilse", {"stop", "continue"})
    if file.is_file():
        data = describe(file)
        data["allowed"] = data["extension"] in allowed if allowed else None
        reason = problem(data, allowed, check)
        data.update(exists=True, ok=not reason, problem=reason)
    else:
        reason = f"Dosya bulunamadı: {file}" if not file.exists() else f"Bu bir klasör, dosya değil: {file}"
        data = {"path": str(file), "name": file.name, "stem": file.stem, "folder": str(file.parent),
                "extension": extension_of(file), "size": None, "modified": None, "type": None, "type_label": "",
                "content_matches": None, "allowed": None, "exists": False, "ok": False, "problem": reason}
    if reason and on_problem == "stop":
        raise WorkflowError(f"{reason} Akış durduruldu.")
    if reason:
        ctx.log(reason)
    return data


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


def _delimiter(content: str, suffix: str) -> str:
    """The separator used in the header line: ; (Turkish Excel), tab, | or ,."""
    if suffix == ".tsv":
        return "\t"
    header = next((line for line in content.splitlines() if line.strip()), "")
    counts = {candidate: header.count(candidate) for candidate in (";", "\t", "|", ",")}
    best = max(counts, key=counts.get)
    return best if counts[best] else ","


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
        matrix = [list(row) for row in csv.reader(io.StringIO(content, newline=""), delimiter=_delimiter(content, suffix))]
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
    formulas = p.get("formulas", False) is True
    suffix = file.suffix.lower()
    try:
        file.parent.mkdir(parents=True, exist_ok=True)
        if suffix in {".xlsx", ".xlsm"}:
            from openpyxl import Workbook

            sheet_name = text(p.get("sheet") or "Sayfa1", "Sayfa", limit=31).strip()
            if append and file.exists():
                key = _column(p.get("last_row_column"), "Son satırı belirleyen sütun", required=False)
                book = _load_book(file)
                sheet = book[sheet_name] if sheet_name in book.sheetnames else book.create_sheet(sheet_name)
                # Each header keeps its own column, even with empty header cells between them.
                positions = {}
                for cell in sheet[1]:
                    if cell.value not in (None, "") and str(cell.value) not in positions:
                        positions[str(cell.value)] = cell.column
                if not positions:
                    for column, name in enumerate(headers, start=1):
                        sheet.cell(row=1, column=column, value=name)
                        positions[name] = column
                next_column = max([*positions.values(), _last_column(sheet, 1)]) + 1
                for name in headers:
                    if name not in positions:
                        sheet.cell(row=1, column=next_column, value=name)
                        positions[name], next_column = next_column, next_column + 1
                row_number = max(_last_row(sheet, key), 1) + 1
            else:
                book = Workbook()
                sheet = book.active
                sheet.title = sheet_name
                positions = {name: column for column, name in enumerate(headers, start=1)}
                for name, column in positions.items():
                    sheet.cell(row=1, column=column, value=name)
                row_number = 2
            for offset, row in enumerate(records):
                for name in headers:
                    if name in row:
                        sheet.cell(row=row_number + offset, column=positions[name],
                                   value=_excel(row[name], formulas=formulas))
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


@handler("file.write_cell")
def write_cell(ctx, p):
    """One value or formula into a chosen column, on a given row or after the last filled row."""
    file = path(p.get("path"))
    if file.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise WorkflowError("Hücreye yazma yalnız .xlsx ve .xlsm dosyalarında yapılır.")
    sheet_name = text(p.get("sheet"), "Sayfa", required=False, limit=31).strip()
    column = _column(p.get("column"), "Sütun")
    row_mode = choice(p.get("row_mode", "number"), "Satır seçimi", {"number", "next", "last"})
    value_type = choice(p.get("value_type", "value"), "Değer türü", {"value", "number", "formula"})
    formula = value_type == "formula"
    value = p.get("value")
    if isinstance(value, (dict, list)):
        raise WorkflowError("Yazılacak değer bir metin veya sayı olmalıdır.")
    if formula:
        value = text(value, "Formül", limit=8000).strip()
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter

    try:
        if file.exists():
            book = _load_book(file)
            if sheet_name and sheet_name not in book.sheetnames:
                raise WorkflowError(f"“{sheet_name}” sayfası yok. Sayfalar: {', '.join(book.sheetnames)}")
            sheet = book[sheet_name] if sheet_name else book.active
        else:
            file.parent.mkdir(parents=True, exist_ok=True)
            book = Workbook()
            sheet = book.active
            sheet.title = sheet_name or "Sayfa1"
        if row_mode == "number":
            row = integer(p.get("row"), "Satır numarası", 1, 1_048_576)
        else:
            key = _column(p.get("last_row_column"), "Son satırı belirleyen sütun", required=False) or column
            last = _last_row(sheet, key)
            if row_mode == "last" and not last:
                raise WorkflowError(f"{get_column_letter(key)} sütununda dolu satır yok; yazma yapılmadı.")
            row = last + 1 if row_mode == "next" else last
            if row > 1_048_576:
                raise WorkflowError("Excel'in son satırına ulaşıldı; yazma yapılmadı.")
        if formula:
            # {satir} lets the formula refer to the row it lands on, e.g. =B{satir}*C{satir}.
            for token in ("{satir}", "{satır}"):
                value = value.replace(token, str(row))
            value = _formula(value if value.startswith("=") else "=" + value)
        elif value_type == "number":
            value = _number(value)
        else:
            value = _excel(value)
        sheet.cell(row=row, column=column, value=value)
        book.save(file)
    except PermissionError as exc:
        raise WorkflowError(f"Dosyaya yazılamadı: {file}. Dosya Excel'de açıksa kapatın.") from exc
    except OSError as exc:
        raise WorkflowError(f"Dosyaya yazılamadı: {file}.") from exc
    letter = get_column_letter(column)
    return {"cell": f"{letter}{row}", "row": row, "column": letter, "sheet": sheet.title, "path": str(file)}


# Excel files store formulas with English function names and comma separators.
TURKISH_FUNCTIONS = {
    "TOPLA": "SUM", "EĞER": "IF", "DÜŞEYARA": "VLOOKUP", "YATAYARA": "HLOOKUP", "ORTALAMA": "AVERAGE",
    "BAĞ_DEĞ_SAY": "COUNT", "BAĞ_DEĞ_DOLU_SAY": "COUNTA", "EĞERSAY": "COUNTIF", "ÇOKEĞERSAY": "COUNTIFS",
    "ETOPLA": "SUMIF", "ÇOKETOPLA": "SUMIFS", "BİRLEŞTİR": "CONCATENATE", "YUVARLA": "ROUND",
    "BUGÜN": "TODAY", "ŞİMDİ": "NOW", "MAK": "MAX", "EĞERHATA": "IFERROR", "METNEÇEVİR": "TEXT",
    "SOLDAN": "LEFT", "SAĞDAN": "RIGHT", "PARÇAAL": "MID", "UZUNLUK": "LEN", "KIRP": "TRIM", "İNDİS": "INDEX",
    "KAÇINCI": "MATCH", "ÇAPRAZARA": "XLOOKUP", "VE": "AND", "YADA": "OR", "DEĞİL": "NOT", "TARİH": "DATE",
    "YIL": "YEAR", "AY": "MONTH", "GÜN": "DAY", "ÇARPIM": "PRODUCT", "MUTLAK": "ABS", "SAYIYAÇEVİR": "VALUE",
}
# Newer functions are saved with Excel's _xlfn. prefix; without it Excel shows #NAME?.
NEWER_FUNCTIONS = {"XLOOKUP", "XMATCH", "IFS", "SWITCH", "TEXTJOIN", "CONCAT", "MAXIFS", "MINIFS", "IFNA", "DAYS"}


def _formula(value: str) -> str:
    """Check a formula before it reaches the file; a broken one makes Excel repair and drop it."""
    from openpyxl.formula import Tokenizer
    from openpyxl.formula.tokenizer import TokenizerError

    if len(value) > 8192:
        raise WorkflowError("Formül en fazla 8.192 karakter olabilir.")
    try:
        tokens = Tokenizer(value).items
    except (TokenizerError, IndexError, ValueError) as exc:
        raise WorkflowError("Formül çözümlenemedi: tırnak veya parantezleri kontrol edin.") from exc
    depth = arrays = 0
    parts, prefixed = ["="], False
    for token in tokens:
        if token.type == "ARRAY" and token.subtype in {"OPEN", "CLOSE"}:
            arrays += 1 if token.subtype == "OPEN" else -1
        if token.type in {"FUNC", "PAREN"} and token.subtype in {"OPEN", "CLOSE"}:
            depth += 1 if token.subtype == "OPEN" else -1
            if depth < 0:
                raise WorkflowError("Formülde kapanan parantez açılandan fazla.")
        if token.type == "SEP" and token.value == ";" and not arrays:
            raise WorkflowError("Formülde bağımsız değişkenleri ; yerine virgülle ayırın (ör. =IF(A2>0,\"Var\",\"Yok\")). "
                                "Excel dosyası formülü İngilizce biçimde saklar.")
        text_value = token.value
        if token.type == "FUNC" and token.subtype == "OPEN":
            name = text_value[:-1].upper()
            if name in TURKISH_FUNCTIONS:
                raise WorkflowError(f"Formülde {text_value[:-1]} yerine İngilizce adı {TURKISH_FUNCTIONS[name]} "
                                    "kullanılmalıdır. Excel dosyası formülü İngilizce biçimde saklar; Türkçe Excel "
                                    "açarken kendi dilinde gösterir.")
            if name in NEWER_FUNCTIONS:
                text_value, prefixed = "_xlfn." + text_value, True
        parts.append(text_value)
    if depth:
        raise WorkflowError("Formülde açılan parantez kapanmamış.")
    if len(tokens) == 0:
        raise WorkflowError("Formül boş olamaz.")
    return "".join(parts) if prefixed else value


def _number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    raw = text(value, "Sayı", limit=100).strip().replace(" ", "")
    if "," not in raw and re.fullmatch(r"-?\d{1,3}(\.\d{3})+", raw):
        raise WorkflowError(f"“{value}” belirsiz: binlik ayıracı mı ondalık mı anlaşılamıyor. Binlik ayıracı "
                            "kullanmayın veya ondalığı virgülle yazın (ör. 1250 ya da 1,25).")
    if "," in raw:
        # Turkish form: 1.234,56; a comma marks the decimals.
        raw = raw.replace(".", "").replace(",", ".")
    try:
        result = float(raw)
    except ValueError as exc:
        raise WorkflowError(f"“{value}” sayı olarak okunamadı (ör. 1250, 1250,50 veya 1.250,50).") from exc
    if not math.isfinite(result):
        raise WorkflowError("Sayı sonlu olmalıdır.")
    return int(result) if result.is_integer() and "." not in raw else result


def _load_book(file: Path):
    from openpyxl import load_workbook

    _read_bytes(file)  # size and existence checks
    try:
        # Macros of an .xlsm file are kept when it is saved again.
        return load_workbook(file, keep_vba=file.suffix.lower() == ".xlsm")
    except Exception as exc:
        raise WorkflowError("Excel dosyası açılamadı. Dosya bozuk veya parola korumalı olabilir.") from exc


def _column(value, label: str, *, required: bool = True) -> int | None:
    """A column letter (A, C, AB) as its 1-based number."""
    from openpyxl.utils import column_index_from_string

    raw = text(value, label, required=required, limit=10).strip().upper()
    if not raw:
        return None
    try:
        if not raw.isalpha() or not raw.isascii():
            raise ValueError(raw)
        index = column_index_from_string(raw)
    except ValueError as exc:
        raise WorkflowError(f"{label} bir sütun harfi olmalıdır (ör. A, C, AB).") from exc
    if index > 16_384:
        raise WorkflowError(f"{label} Excel'in son sütunu XFD'yi aşamaz.")
    return index


def _filled(value) -> bool:
    return value is not None and not (isinstance(value, str) and not value.strip())


def _last_row(sheet, column: int | None) -> int:
    """The last row holding a value, in one column or in any; formatted empty cells do not count."""
    if column is None:
        return max((cell.row for row in sheet.iter_rows() for cell in row if _filled(cell.value)), default=0)
    for row in range(sheet.max_row, 0, -1):
        if _filled(sheet.cell(row=row, column=column).value):
            return row
    return 0


def _last_column(sheet, row: int) -> int:
    return max((cell.column for cell in sheet[row] if _filled(cell.value)), default=0)


def _excel(value, *, formulas: bool = False):
    if isinstance(value, (dict, list)):
        import json

        return json.dumps(value, ensure_ascii=False)
    if formulas and isinstance(value, str) and value.startswith("=") and len(value) > 1:
        return value
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) and not _numeric(value):
        return "'" + value  # never let data become a spreadsheet formula
    return value


def _numeric(value: str) -> bool:
    try:
        float(value.replace(",", "."))
        return True
    except ValueError:
        return False
