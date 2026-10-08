"""Window management beyond input: focus, size, close, wait and read field values."""

from __future__ import annotations

from typing import Any

from ..desktop.windows import WindowError, found_window
from ..errors import WorkflowError
from . import handler
from .common import choice, fold, integer, number, region, text

# A grid copies one row per line with the cells separated by tabs.
TABLE_LIMIT = 10_000


def _window(p):
    try:
        return found_window(p.get("window"))
    except WindowError as exc:
        raise WorkflowError(str(exc)) from exc


@handler("window.activate")
def activate(ctx, p):
    return ctx.windows().activate(_window(p))


@handler("window.state")
def state(ctx, p):
    ctx.windows().set_state(_window(p), choice(p.get("state"), "Pencere işlemi", {"maximize", "minimize", "restore"}))
    ctx.wait(0.3)


@handler("window.move")
def move(ctx, p):
    values = [integer(p.get(key), label, -10_000, 20_000) for key, label in
              (("x", "X"), ("y", "Y"), ("width", "Genişlik"), ("height", "Yükseklik"))]
    return ctx.windows().move_resize(_window(p), *values)


@handler("window.close")
def close(ctx, p):
    ctx.windows().close(_window(p))


@handler("window.wait_close")
def wait_close(ctx, p):
    ctx.windows().wait_closed(_window(p), number(p.get("timeout", 30), "Bekleme süresi", 0, 3600))


@handler("window.read_field")
def read_field(ctx, p):
    try:
        return ctx.windows().read_field(_window(p), ctx.desktop(), **ctx.window_target(p))
    except WindowError:
        raise
    except ImportError as exc:
        raise WorkflowError("Pano erişimi için masaüstü otomasyon paketleri gerekir.") from exc


def table_of(value: Any, *, header: bool) -> tuple[list[str], list[list[str]]]:
    """Column names and rows from the text a grid copies out."""
    lines = [line for line in str(value).replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    if len(lines) > TABLE_LIMIT:
        raise WorkflowError(f"Tablodan en fazla {TABLE_LIMIT:,} satır okunabilir.".replace(",", "."))
    cells = [[cell.strip() for cell in line.split("\t")] for line in lines]
    if not cells:
        return [], []
    width = max(len(row) for row in cells)
    titles = cells[0] if header else []
    names: list[str] = []
    for index in range(width):
        name = titles[index] if index < len(titles) and titles[index] else f"sutun_{index + 1}"
        base, counter = name, 2
        while name in names:  # two columns with the same heading stay apart
            name, counter = f"{base} ({counter})", counter + 1
        names.append(name)
    body = cells[1:] if header else cells
    return names, [[row[index] if index < len(row) else "" for index in range(width)] for row in body]


def table_column(names: list[str], column: Any) -> int:
    wanted = text(column, "Sütun").strip()
    for index, name in enumerate(names):
        if fold(name) == fold(wanted):
            return index
    if wanted.isdigit() and 1 <= int(wanted) <= len(names):
        return int(wanted) - 1
    raise WorkflowError(f"Tabloda “{wanted}” sütunu yok. Okunan sütunlar: " + ", ".join(names) + ". "
                        "Başlığı tablodaki gibi yazın veya sütun numarasını (1, 2, …) kullanın.")


@handler("window.read_table")
def read_table(ctx, p):
    """One cell of an ERP grid, or how many rows it holds."""
    header = p.get("header", True) is not False
    names, rows = table_of(read_field(ctx, p), header=header)
    if choice(p.get("mode", "value"), "Ne okunacak", {"value", "count"}) == "count":
        return len(rows)
    if not rows:
        raise WorkflowError("Tabloda okunacak satır yok." + (
            " Tablo yalnız bir satır verdiyse “İlk satır sütun başlıklarıdır” seçeneğini kapatın." if header and names
            else " Arama sonuç vermemiş olabilir; Satır sayısı ile kontrol edin."))
    wanted = integer(p.get("row", 1), "Satır", 1, TABLE_LIMIT)
    if wanted > len(rows):
        raise WorkflowError(f"Tabloda {len(rows)} satır var; {wanted}. satır okunamadı.")
    return rows[wanted - 1][table_column(names, p.get("column"))]


def table_selection(p):
    mode = choice(p.get("row_mode", "index"), "Satır seçimi", {"index", "match"})
    return {
        "table": text(p.get("table", ""), "Tablo adı veya kimliği", required=False, limit=300).strip(),
        "row_mode": mode,
        "row": integer(p.get("row", 1), "Satır", 1, TABLE_LIMIT) if mode == "index" else 1,
        "column": text(p.get("column"), "Yazılacak sütun", limit=300),
        "match_column": text(p.get("match_column"), "Aranacak sütun", limit=300) if mode == "match" else "",
        "match_value": text(p.get("match_value"), "Aranacak değer", limit=10_000) if mode == "match" else "",
    }


def table_target(ctx, p):
    # Missing means the 0.9.6 automatic/name-based selector, not a missing image.
    mode = choice(p.get("target_mode", "auto"), "Tabloyu bulma yöntemi",
                  {"auto", "coordinates", "image", "element"})
    return {} if mode == "auto" else {"targeting": ctx.window_target(p)}


def table_operation(ctx, p, *, value=None):
    method = choice(p.get("write_method", "native"), "Hücreye yazma yöntemi", {"native", "screen"})
    selection = table_selection(p)
    if method == "screen":
        area = region(p.get("region"))
        if area is None:
            raise WorkflowError("Tablo alanını çiz ile yalnız bir tablonun başlıklarını ve veri satırlarını seçin.")
        if value is not None and value != value.strip():
            raise WorkflowError("Tabloya yazılacak değerin başında veya sonunda boşluk olmamalıdır.")
        edit_mode = choice(p.get("edit_mode", "double_click"), "Hücreyi düzenlemeye aç",
                           {"double_click", "single_click", "f2"})
        return ctx.windows().screen_table_cell(
            _window(p), ctx.desktop(), value=value, selection=selection, region=area, edit_mode=edit_mode,
            ocr_options={"language": ctx.config.get("ocr_language") or "tur+eng",
                         "tesseract_cmd": ctx.config.get("tesseract_cmd") or None,
                         "timeout": ctx.settings.action_timeout})
    return ctx.windows().table_cell(_window(p), ctx.desktop(), value=value, **selection, **table_target(ctx, p))


@handler("window.write_table")
def write_table(ctx, p):
    value = text(p.get("value"), "Yazılacak değer", limit=10_000)
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise WorkflowError("Tablo hücresine yazılacak değer satır sonu, Tab veya kontrol karakteri içeremez.")
    return table_operation(ctx, p, value=value)
