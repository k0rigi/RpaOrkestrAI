"""Address visible table text from fresh clipboard data and measured OCR boxes.

The saved rectangle bounds one table, including its headings. Both the initial
copy point and the write point are found anew inside it. Empty, clipped or
ambiguous cells are rejected; no column widths or row heights are estimated.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace

from .ocr import OcrUnavailable, read_words
from .windows import WindowError


class AmbiguousTable(WindowError):
    """A second OCR pass must never hide an already observed ambiguity."""


def normalized(text):
    return " ".join(str(text).replace("İ", "i").replace("I", "i").replace("ı", "i").casefold().split())


@dataclass(frozen=True)
class TableText:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    @classmethod
    def parse(cls, text):
        lines = str(text).replace("\r\n", "\n").replace("\r", "\n").strip("\n").split("\n")
        cells = tuple(tuple(cell.strip() for cell in line.split("\t")) for line in lines)
        if (len(cells) < 2 or len(cells) > 10_001 or not 2 <= len(cells[0]) <= 1000
                or sum(bool(c) for c in cells[0]) < 2 or any(len(row) != len(cells[0]) for row in cells)):
            raise WindowError("Tablo başlıkları ve satırları birlikte kopyalanamadı. Tabloyu okuma adımındaki gibi "
                              "bir veri hücresinden seçin; uygulamanın başlıklarla birlikte kopyalamayı desteklemesi gerekir.")
        return cls(cells[0], cells[1:])

    def column(self, value):
        wanted = normalized(value)
        matches = [i for i, title in enumerate(self.headers) if normalized(title) == wanted]
        if not matches and wanted.isdecimal() and 1 <= int(wanted) <= len(self.headers):
            matches = [int(wanted) - 1]
        if len(matches) != 1:
            raise WindowError("Sütun başlığı bulunamadı veya birden fazla sütunda aynı başlık var. "
                              "Başlığı kontrol edin ya da sütun numarasını kullanın.")
        return matches[0]

    def select(self, *, row_mode, row, column, match_column, match_value, **unused):
        col = self.column(column)
        if row_mode == "match":
            key = self.column(match_column)
            matches = [i for i, values in enumerate(self.rows) if values[key] == match_value]
            if len(matches) != 1:
                raise WindowError("Aranan değeri içeren tek bir satır bulunamadı; yazılmadı.")
            index = matches[0]
        else:
            index = row - 1
            if not 0 <= index < len(self.rows):
                raise WindowError(f"Tabloda {len(self.rows)} satır var; {row}. satır bulunamadı.")
        if not self.rows[index][col] or not self.headers[col]:
            raise WindowError("Başlığa göre yazmada sütun başlığı ve mevcut hücre metni görünür ve dolu olmalıdır. "
                              "Boş hücre için uygulamanın tablo yapısı yöntemini kullanın.")
        return index, col


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float
    words: int = 1

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height

    @property
    def center(self):
        return self.x + self.width / 2, self.y + self.height / 2


def same_line(a, b):
    return min(a.bottom, b.bottom) - max(a.y, b.y) >= min(a.height, b.height) * .5


def overlap_x(a, b):
    return min(a.right, b.right) - max(a.x, b.x)


class Phrases:
    """Exact phrases made of adjacent, aligned words; never fuzzy OCR text."""
    def __init__(self, words):
        if len(words) > 8000:
            raise WindowError("Ekranda çok fazla metin var; hedef tabloyu ayrı bir pencerede açın.")
        self.lines, self.cache = [], {}
        for word in sorted(words, key=lambda w: (w.y, w.x)):
            if word.confidence < .8 or not normalized(word.text):
                continue
            box = Box(word.x, word.y, word.width, word.height)
            matching = [line for line in self.lines if all(same_line(box, item[1]) for item in line)]
            if len(matching) == 1:
                matching[0].append((normalized(word.text), box))
            elif not matching:
                self.lines.append([(normalized(word.text), box)])
        for line in self.lines:
            line.sort(key=lambda item: item[1].x)

    def find(self, text):
        wanted = normalized(text)
        if not wanted:
            return []
        if wanted not in self.cache:
            result = []
            for line in self.lines:
                for start in range(len(line)):
                    assembled, boxes = "", []
                    for word, box in line[start:]:
                        if boxes and box.x - boxes[-1].right > 4 * max(box.height, boxes[-1].height):
                            break
                        assembled = (assembled + " " + word).strip()
                        if not wanted.startswith(assembled):
                            break
                        boxes.append(box)
                        if assembled == wanted:
                            x, y = min(b.x for b in boxes), min(b.y for b in boxes)
                            result.append(Box(x, y, max(b.right for b in boxes) - x,
                                              max(b.bottom for b in boxes) - y, len(boxes)))
                            break
            self.cache[wanted] = result
        return self.cache[wanted]


@dataclass(frozen=True)
class LocatedCell:
    header: Box
    text: Box
    witness_header: Box
    witness_text: Box

    @property
    def point(self):
        # The intersection is actual header/text evidence, not inferred cell bounds.
        return ((max(self.header.x, self.text.x) + min(self.header.right, self.text.right)) / 2,
                self.text.center[1])


def header_groups(phrases, table):
    entries = []
    for index, title in enumerate(table.headers):
        if not title or sum(normalized(h) == normalized(title) for h in table.headers) != 1:
            continue
        entries.extend((index, box) for box in phrases.find(title))
    bands = []
    for item in sorted(entries, key=lambda e: (e[1].y, e[1].x)):
        matches = [band for band in bands if all(same_line(item[1], entry[1]) for entry in band)]
        if len(matches) == 1:
            matches[0].append(item)
        elif not matches:
            bands.append([item])
    groups = []
    for band in bands:
        current = []
        for item in sorted(band, key=lambda e: e[1].x):
            if current and (item[0] <= current[-1][0] or overlap_x(item[1], current[-1][1]) > 0):
                if len(current) >= 2:
                    groups.append(current)
                current = []
            current.append(item)
        if len(current) >= 2:
            groups.append(current)
    return groups


def locate_cell(words, table, row, column, *, reference_point=None):
    phrases = Phrases(words)
    value = table.rows[row][column]
    heading = table.headers[column]
    if sum(normalized(h) == normalized(heading) for h in table.headers) != 1:
        raise WindowError("Ekrandaki sütun başlığı benzersiz değil; hücre güvenle bulunamadı.")
    # A second cell in the same row must distinguish this record in the full
    # clipboard table. Counting OCR lines would confuse scrolling with row index.
    witnesses = []
    for index, current in enumerate(table.rows[row]):
        title = table.headers[index]
        if index == column or not current or not title or sum(normalized(h) == normalized(title)
                                                             for h in table.headers) != 1:
            continue
        signature = (normalized(value), normalized(current))
        if sum((normalized(r[column]), normalized(r[index])) == signature for r in table.rows) == 1:
            witnesses.append(index)
    if not witnesses:
        raise WindowError("Satır, görünür diğer hücre değerleriyle ayırt edilemiyor; yazılmadı.")
    groups = header_groups(phrases, table)
    scopes = []
    for group in groups:
        if column not in {index for index, _ in group}:
            continue
        left, right = min(b.x for _, b in group), max(b.right for _, b in group)
        bottom = max(b.bottom for _, b in group)
        # The next header group in this horizontal band is another table. A
        # target from that table must never satisfy this table's row witness.
        end = min((min(b.y for _, b in other) for other in groups
                   if min(b.y for _, b in other) > bottom
                   and max(b.right for _, b in other) > left and min(b.x for _, b in other) < right),
                  default=float("inf"))
        if reference_point is None or (left <= reference_point[0] <= right
                                       and bottom <= reference_point[1] < end):
            scopes.append((dict(group), bottom, end))
    if reference_point is not None and len(scopes) != 1:
        error = AmbiguousTable if len(scopes) > 1 else WindowError
        raise error("Tablo içeriği ile sütun başlıkları aynı tabloda doğrulanamadı. "
                    "Tablo alanını çiz ile yalnız bir tablonun başlıklarını ve satırlarını seçin.")
    found = {}
    for headings, bottom, end in scopes:
        header = headings[column]

        def belongs(box, index, *, witness=False):
            own = headings[index]
            if overlap_x(own, box) < 2:
                return False
            if any(overlap_x(box, other) > 0 for i, other in headings.items() if i != index):
                return False
            # OCR can join text from adjacent cells into one phrase. A phrase
            # used as a row witness must fit the measured heading's span.
            return not witness or box.words == 1 or (own.x <= box.x and box.right <= own.right)

        for cell in phrases.find(value):
            if cell.y < bottom or cell.bottom >= end or not belongs(cell, column):
                continue
            for index in witnesses:
                for other_header in [headings[index]] if index in headings else []:
                    if (not same_line(header, other_header) or overlap_x(header, other_header) > 0
                            or (index - column) * (other_header.x - header.x) <= 0):
                        continue
                    for other_cell in phrases.find(table.rows[row][index]):
                        if (same_line(cell, other_cell) and belongs(other_cell, index, witness=True)
                                and overlap_x(cell, other_cell) <= 0
                                and (index - column) * (other_cell.x - cell.x) > 0):
                            location = LocatedCell(header, cell, other_header, other_cell)
                            found.setdefault((header, cell), location)
    if len(found) != 1:
        error = AmbiguousTable if len(found) > 1 else WindowError
        raise error("Sütun başlığı ve satırdaki mevcut değer ekranda tek bir hücreyle eşleştirilemedi. "
                    "Başlığı ve hücre metnini tam görünür yapın; kaydırılmış, kırpılmış veya belirsiz hücreye yazılmaz.")
    return next(iter(found.values()))


def same_location(before, after):
    # OCR floats can change by a pixel, especially when text becomes selected.
    # Require measured overlap of all four pieces of evidence and their centers
    # to remain inside each other's text boxes; permit no row/column jump.
    for old, new in zip((before.header, before.text, before.witness_header, before.witness_text),
                        (after.header, after.text, after.witness_header, after.witness_text)):
        if (not same_line(old, new) or overlap_x(old, new) < .5 * min(old.width, new.width)
                or abs(old.center[0] - new.center[0]) > min(old.width, new.width) / 2):
            return False
    return True


def measured_words(image, preparation, *, vocabulary, ocr_options):
    from PIL import Image, ImageOps

    size = (image.width * 2, image.height * 2)
    prepared = image.resize(size, Image.Resampling.BICUBIC if preparation == 0 else Image.Resampling.LANCZOS)
    if preparation == 1:
        prepared = ImageOps.grayscale(prepared).point(lambda v: 255 if v > 200 else 0).convert("RGB")
    elif preparation == 2:
        prepared = ImageOps.invert(prepared.convert("RGB"))
    words = read_words(prepared, vocabulary=vocabulary, **(ocr_options or {}))
    return [replace(w, x=w.x / 2, y=w.y / 2, width=w.width / 2, height=w.height / 2) for w in words]


def table_focus_point(image, column, *, ocr_options=None):
    """Find actual data text inside the one table rectangle; no saved point."""
    if str(column).strip().isdecimal():
        raise WindowError("Sütun başlığıyla yazmada sütun numarası yerine başlığını yazın.")
    for preparation in range(3):
        words = measured_words(image, preparation, vocabulary=(str(column),), ocr_options=ocr_options)
        phrases = Phrases(words)
        headers = phrases.find(column)
        if len(headers) > 1:
            raise AmbiguousTable("Seçilen alanda aynı sütun başlığı birden fazla yerde var. Yalnız bir tablo seçin.")
        if not headers:
            continue
        header = headers[0]
        header_words = [Box(w.x, w.y, w.width, w.height) for w in words if w.confidence >= .8
                        and same_line(header, Box(w.x, w.y, w.width, w.height))]
        data_words = [w for w in words if w.confidence >= .8 and any(c.isalnum() for c in w.text)
                      and w.y > header.bottom and any(overlap_x(Box(w.x, w.y, w.width, w.height), h) >= 2
                                                      for h in header_words)]
        candidates = [Box(w.x, w.y, w.width, w.height) for w in data_words if len(w.text.strip()) >= 2]
        for first in sorted(candidates, key=lambda b: (b.y, b.x)):
            row = [Box(w.x, w.y, w.width, w.height) for w in data_words
                   if same_line(first, Box(w.x, w.y, w.width, w.height))]
            if len(row) >= 2:
                # Use actual text rather than row selectors/checkboxes or the
                # potentially moved destination column's previous coordinate.
                return min((b for b in candidates if same_line(first, b)), key=lambda b: b.x).center
    raise WindowError("Seçilen tablo alanında sütun başlığı ve okunabilir veri satırı bulunamadı; tıklanmadı. "
                      "Tablo alanını başlıkları ve veri satırlarını kapsayacak şekilde çizin.")


def locate_image(image, table, row, column, *, reference_point, ocr_options=None):
    """Bounded OCR preparations; each must independently prove the whole cell."""
    for preparation in range(3):
        words = measured_words(image, preparation, vocabulary=(*table.headers, *table.rows[row]),
                               ocr_options=ocr_options)
        try:
            return locate_cell(words, table, row, column, reference_point=reference_point)
        except AmbiguousTable:
            raise
        except WindowError:
            if preparation == 2:
                raise


def screen_table_cell(service, target, desktop, *, region, selection, value=None, ocr_options=None,
                      edit_mode="double_click"):
    """Copy -> locate -> check editor -> paste once -> verify the full table."""
    import pyperclip

    previous = pyperclip.paste()
    attempted = False
    try:
        if edit_mode not in {"double_click", "single_click", "f2"}:
            raise WindowError("Hücre düzenleme yöntemi geçersiz.")
        if (not isinstance(region, (tuple, list)) or len(region) != 4
                or any(type(n) is not int for n in region) or min(region[:2]) < 0 or min(region[2:]) <= 0):
            raise WindowError("Geçerli bir tablo alanı çizin.")
        left, top, width, height = region
        current = service.current(target)
        if left + width > current.width or top + height > current.height:
            raise WindowError("Tablo alanı pencere sınırlarını aşıyor; alanı yeniden çizin.")
        window = service.focus(target)
        if left + width > window.width or top + height > window.height:
            raise WindowError("Pencere boyutu değişti; tablo alanını yeniden çizin.")

        def guard():
            service._guard(target, window)

        def pause():
            if service.cancel.wait(.15):
                service._check()
            guard()

        def copy_selection():
            marker = f"rpa-table-{time.monotonic_ns()}"
            pyperclip.copy(marker)
            guard()
            desktop.hotkey("mod", "c")
            deadline = time.monotonic() + 1.5
            while True:
                guard()
                copied = pyperclip.paste()
                if copied != marker:
                    return str(copied)
                if time.monotonic() >= deadline:
                    raise WindowError("Tablo veya hücre metni kopyalanamadı; yazılmadı.")
                pause()

        def copy_table(point):
            guard()
            desktop.click(*point, clicks=1, button="left")
            pause()
            guard()
            desktop.hotkey("mod", "a")
            guard()
            return TableText.parse(copy_selection())

        def locate(table, row, col):
            guard()
            captured_window, image = service._capture_window(target, desktop)
            if captured_window != window:
                raise WindowError("Pencere değişti; yazılmadı.")
            result = locate_image(image.crop((left, top, left + width, top + height)), table, row, col,
                                  reference_point=reference_point, ocr_options=ocr_options)
            guard()
            return result

        captured_window, image = service._capture_window(target, desktop)
        if captured_window != window:
            raise WindowError("Pencere değişti; yazılmadı.")
        reference_point = table_focus_point(image.crop((left, top, left + width, top + height)),
                                            selection["column"], ocr_options=ocr_options)
        table_point = service._point_in_window(window, left + reference_point[0], top + reference_point[1], desktop)
        guard()
        table = copy_table(table_point)
        row, col = table.select(**selection)
        location = locate(table, row, col)
        point = service._point_in_window(window, left + location.point[0], top + location.point[1], desktop)
        if value is None:
            return point
        # Check the clipboard snapshot and measured location immediately before
        # opening the editor, including records that moved within one window.
        if copy_table(point) != table or not same_location(location, locate(table, row, col)):
            raise WindowError("Tablonun içeriği veya hücrenin konumu değişti; yazılmadı.")
        guard()
        desktop.click(*point, clicks=2 if edit_mode == "double_click" else 1, button="left")
        pause()
        if edit_mode == "f2":
            desktop.press("f2")
            pause()
        desktop.hotkey("mod", "a")
        guard()
        editor_text = copy_selection()
        if editor_text != table.rows[row][col]:
            raise WindowError("Hücre düzenlemeye açılamadı veya mevcut metin doğrulanamadı; yeni değer yazılmadı. "
                              "Diğer seçenekler altındaki hücre düzenleme yöntemini kontrol edin.")
        # A sort/reflow between the double-click and paste must not redirect input.
        if not same_location(location, locate(table, row, col)):
            raise WindowError("Düzenlenen hücre veya satır değişti; yazılmadı.")
        guard()
        attempted = True
        desktop.paste(value)
        pause()
        desktop.press("tab")
        pause()
        expected_rows = [list(r) for r in table.rows]
        expected_rows[row][col] = value
        expected = TableText(table.headers, tuple(tuple(r) for r in expected_rows))
        # Pasting may resize columns; locate the new text again before copying.
        new_location = locate(expected, row, col)
        new_point = service._point_in_window(window, left + new_location.point[0], top + new_location.point[1], desktop)
        if copy_table(new_point) != expected:
            raise WindowError("Yazma sonrası tablo beklenen değerlerle eşleşmedi.")
        guard()
        return {"row": row + 1, "column": col + 1, "value": value}
    except InterruptedError:
        raise
    except Exception as exc:
        if attempted:
            raise WindowError("Hücreye yazma denendi ancak sonuç doğrulanamadı. Uygulamayı kontrol edin; "
                              "otomatik olarak yeniden yazılmadı.") from exc
        if isinstance(exc, (WindowError, OcrUnavailable)):
            raise WindowError(str(exc)) from exc
        raise WindowError("Tablo hücresi doğrulanamadı; yeni değer yazılmadı.") from exc
    finally:
        pyperclip.copy(previous)
