"""Address native grid cells by row and column, never by guessed screen offsets.

Windows uses UIA Grid/Table and Value patterns; macOS uses AX table attributes.
An application must expose a writable cell. Unsupported/custom grids fail
closed. Native imports and COM initialization remain on the calling worker.
"""
from __future__ import annotations

import platform
from collections import deque

from .elements import MAC_DEPTH_LIMIT, MAC_ELEMENT_LIMIT, WINDOWS_ELEMENT_LIMIT, AxElements, UiaElements
from .table_columns import column_names, numbered_column, resolve_column
from .windows import WindowError

LIMIT = 10_000
UNSUPPORTED = ("Bu uygulama tablonun hücrelerine doğrudan yazmayı desteklemiyor. "
               "Tabloyu seç düğmesiyle tabloyu yeniden tanıtın; uygun yöntem otomatik seçilir.")


def column_index(names, wanted, *, canonical=False):
    wanted = wanted.strip()
    # Preserve native numeric selectors; named aliases share the clipboard rules.
    if wanted.isdecimal() and not canonical:
        index = numbered_column(wanted)
        if index is not None and index < len(names):
            return index
    try:
        titles = [name.strip() for name in names]
        return resolve_column(column_names(titles, len(titles)) if canonical else titles, wanted)
    except ValueError as exc:
        raise WindowError(str(exc)) from exc


def resolve_cell(backend, window, *, table, row_mode, row, column, match_column, match_value, check, point=None,
                 canonical=False):
    candidates = backend.tables(window, check)
    if point is not None:
        candidates = [item for item in candidates if (info := item.info()) is not None
                      and info.usable_in(window) and info.contains(*point)]
        if not candidates:
            raise WindowError("Seçilen noktada yazılabilir tablo bulunamadı. Ekranda seç ile tablonun içindeki "
                              "bir noktayı gösterin. Uygulamanın tablo hücrelerine erişim sunması gerekir.")
    if table:
        candidates = [item for item in candidates if table in {item.name, item.identifier}]
    if len(candidates) != 1:
        raise WindowError("Birden fazla tablo bulundu. Ekranda seç ile hedef tabloyu belirtin." if candidates else UNSUPPORTED)
    grid = candidates[0]
    rows, columns = grid.shape()
    if not 0 < rows <= LIMIT or not 0 < columns <= 1000:
        raise WindowError("Tablo boş veya desteklenen sınırın dışında (10.000 satır, 1.000 sütun).")
    names = grid.headers(columns)
    if len(names) != columns:
        raise WindowError("Tablonun sütun yapısı okunamadı.")
    col = column_index(names, column, canonical=canonical)
    if row_mode == "match":
        key_col = column_index(names, match_column, canonical=canonical)
        matches = []
        for index in range(rows):
            check()
            if grid.cell(index, key_col).read() == match_value:
                matches.append(index)
                if len(matches) > 1:
                    raise WindowError("Aranan değer birden fazla satırda var. Benzersiz bir değer kullanın.")
        if not matches:
            raise WindowError("Aranan değeri içeren satır bulunamadı.")
        index = matches[0]
    else:
        index = row - 1
        if not 0 <= index < rows:
            raise WindowError(f"Tabloda {rows} satır var; {row}. satır bulunamadı.")
    check()
    if grid.shape() != (rows, columns):
        raise WindowError("Tablonun satır veya sütun sayısı değişti; işlem durduruldu.")
    if row_mode == "match" and grid.cell(index, key_col).read() != match_value:
        raise WindowError("Tablo satırı değişti; işlem durduruldu.")
    return grid.cell(index, col), index, col


def native_backend():
    if platform.system() == "Windows":
        return UiaTables()
    if platform.system() == "Darwin":
        return AxTables()
    raise WindowError("Tabloya yazma macOS ve Windows üzerinde desteklenir.")


def _pattern(element, pattern_id, interface):
    from comtypes import COMError

    try:
        unknown = element.GetCurrentPattern(pattern_id)
        return unknown.QueryInterface(interface) if unknown else None
    except (OSError, COMError):
        return None


class UiaTables(UiaElements):
    def tables(self, window, check):
        automation, request, _ = self._context()
        from comtypes.gen import UIAutomationClient as uia

        root = automation.ElementFromHandle(window.window_id)
        # Ask for grids, including custom controls that expose the Grid pattern.
        condition = automation.CreatePropertyCondition(30030, True)  # IsGridPatternAvailable
        items = root.FindAllBuildCache(4, condition, request)
        if items.Length > WINDOWS_ELEMENT_LIMIT:
            raise WindowError("Pencerede çok fazla tablo var; işlem durduruldu.")
        result = []
        for index in range(items.Length):
            check()
            element = items.GetElement(index)
            info = self._info(element)
            if info and info.usable_in(window):
                grid = _pattern(element, 10006, uia.IUIAutomationGridPattern)
                if grid:
                    result.append(UiaGrid(self, element, grid, info))
        return result


class UiaGrid:
    def __init__(self, backend, element, grid, info):
        self.backend, self.element, self.grid = backend, element, grid
        self.name, self.identifier = info.name, info.automation_id

    def info(self):
        _, request, _ = self.backend._context()
        return self.backend._info(self.element.BuildUpdatedCache(request))

    def shape(self):
        return int(self.grid.CurrentRowCount), int(self.grid.CurrentColumnCount)

    def headers(self, count):
        from comtypes.gen import UIAutomationClient as uia

        table = _pattern(self.element, 10012, uia.IUIAutomationTablePattern)
        if table:
            headers = table.GetCurrentColumnHeaders()
            if headers and headers.Length == count:
                return [str(headers.GetElement(i).CurrentName or "") for i in range(count)]
        return [""] * count

    def cell(self, row, column):
        return UiaCell(self.backend, self.grid.GetItem(row, column))


class UiaCell:
    def __init__(self, backend, element):
        self.backend, self.element = backend, element

    def info(self):
        _, request, _ = self.backend._context()
        return self.backend._info(self.element.BuildUpdatedCache(request))

    def value_pattern(self):
        from comtypes.gen import UIAutomationClient as uia

        value = _pattern(self.element, 10002, uia.IUIAutomationValuePattern)
        if value is None:
            raise WindowError(UNSUPPORTED)
        return value

    def read(self):
        return str(self.value_pattern().CurrentValue)

    def write_available(self):
        from comtypes.gen import UIAutomationClient as uia

        return _pattern(self.element, 10002, uia.IUIAutomationValuePattern) is not None

    def write(self, value, guard):
        pattern = self.value_pattern()
        if pattern.CurrentIsReadOnly or not self.element.CurrentIsEnabled:
            raise WindowError("Tablo hücresi salt okunur veya devre dışı; yazılmadı.")
        guard()
        pattern.SetValue(value)


class AxTables(AxElements):
    def tables(self, window, check):
        root = self._window_element(self._application(window), window)
        queue, result, visited = deque([(root, 0)]), [], 0
        while queue:
            check()
            element, depth = queue.popleft()
            visited += 1
            if visited > MAC_ELEMENT_LIMIT or depth > MAC_DEPTH_LIMIT:
                raise WindowError("Pencerenin tablo yapısı çok büyük; işlem durduruldu.")
            role = self._text(element, "AXRole")
            if role == "AXTable":
                info = self._info(element)
                if info and info.usable_in(window):
                    result.append(AxGrid(self, element, info))
                # Rows cannot contain another peer table; don't scan every cell.
                continue
            queue.extend((child, depth + 1) for child in self._attribute(element, "AXChildren") or [])
        return result


class AxGrid:
    def __init__(self, backend, element, info):
        self.backend, self.element = backend, element
        self.name, self.identifier = info.name, info.automation_id

    def info(self):
        return self.backend._info(self.element)

    def shape(self):
        return (len(self.backend._attribute(self.element, "AXRows") or []),
                len(self.backend._attribute(self.element, "AXColumns") or []))

    def headers(self, count):
        headers = self.backend._attribute(self.element, "AXColumnHeaderUIElements") or []
        if len(headers) != count:
            return [""] * count
        return [self.backend._text(item, "AXTitle") or self.backend._text(item, "AXValue") for item in headers]

    def cell(self, row, column):
        error, cell = self.backend.ax.AXUIElementCopyParameterizedAttributeValue(
            self.element, "AXCellForColumnAndRow", [column, row], None)
        if error or cell is None:
            raise WindowError(UNSUPPORTED)
        return AxCell(self.backend, cell)


class AxCell:
    def __init__(self, backend, element):
        self.backend, self.element = backend, element

    def info(self):
        return self.backend._info(self.element)

    def value_element(self):
        if self.backend._attribute(self.element, "AXValue") is not None:
            return self.element
        children = [item for item in self.backend._attribute(self.element, "AXChildren") or []
                    if self.backend._text(item, "AXRole") in {"AXTextField", "AXTextArea", "AXStaticText"}]
        if len(children) != 1:
            raise WindowError(UNSUPPORTED)
        return children[0]

    def read(self):
        value = self.backend._attribute(self.value_element(), "AXValue")
        if value is None:
            raise WindowError(UNSUPPORTED)
        return str(value)

    def write_available(self):
        try:
            element = self.value_element()
        except WindowError:
            return False
        error, _ = self.backend.ax.AXUIElementIsAttributeSettable(element, "AXValue", None)
        return error == 0

    def write(self, value, guard):
        element = self.value_element()
        error, settable = self.backend.ax.AXUIElementIsAttributeSettable(element, "AXValue", None)
        if error or not settable or self.backend._attribute(element, "AXEnabled") is False:
            raise WindowError("Tablo hücresi salt okunur veya devre dışı; yazılmadı.")
        guard()
        if self.backend.ax.AXUIElementSetAttributeValue(element, "AXValue", value):
            raise WindowError("Uygulama hücreye yazma işlemini reddetti.")
