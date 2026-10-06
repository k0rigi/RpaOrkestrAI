"""Find fields through the OS accessibility tree: Windows UI Automation, macOS AX.

A structural locator (identifier or accessible name, plus role) is independent of
the window's size, position and the display scale: the click point is taken from
the field's current bounds at run time. Applications that draw their own controls,
Java without the Access Bridge, and remote desktop/Citrix images expose no such
tree; image or X/Y targets remain available there. Nothing here sends input, and
native imports are lazy.
"""

from __future__ import annotations

import platform
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .windows import WindowError, WindowInfo

LOCATOR_TEXT_KEYS = ("role", "automation_id", "name", "class_name")
LOCATOR_KEYS = frozenset({"platform", "index", *LOCATOR_TEXT_KEYS})
MAX_LOCATOR_TEXT = 300
MAX_INDEX = 999
WINDOWS_ELEMENT_LIMIT = 20_000
MAC_ELEMENT_LIMIT = 5_000
MAC_DEPTH_LIMIT = 60
POLL_SECONDS = 0.25

ROLE_LABELS = {
    "Edit": "Metin kutusu", "AXTextField": "Metin kutusu", "AXTextArea": "Metin alanı",
    "Document": "Metin alanı", "ComboBox": "Açılır liste", "AXComboBox": "Açılır liste",
    "AXPopUpButton": "Açılır liste", "Button": "Düğme", "AXButton": "Düğme",
    "SplitButton": "Düğme", "CheckBox": "Onay kutusu", "AXCheckBox": "Onay kutusu",
    "RadioButton": "Seçenek düğmesi", "AXRadioButton": "Seçenek düğmesi",
    "Text": "Etiket", "AXStaticText": "Etiket", "Hyperlink": "Bağlantı", "AXLink": "Bağlantı",
    "List": "Liste", "AXList": "Liste", "ListItem": "Liste öğesi", "TabItem": "Sekme",
    "AXTab": "Sekme", "MenuItem": "Menü öğesi", "AXMenuItem": "Menü öğesi",
    "DataItem": "Tablo hücresi", "AXCell": "Tablo hücresi", "Spinner": "Sayı kutusu",
    "AXIncrementor": "Sayı kutusu", "Calendar": "Tarih seçici", "AXDateField": "Tarih alanı",
}

# UI Automation ids from UIAutomationClient.h.
UIA_CONTROL_TYPES = {
    50000: "Button", 50001: "Calendar", 50002: "CheckBox", 50003: "ComboBox", 50004: "Edit",
    50005: "Hyperlink", 50006: "Image", 50007: "ListItem", 50008: "List", 50009: "Menu",
    50010: "MenuBar", 50011: "MenuItem", 50012: "ProgressBar", 50013: "RadioButton",
    50014: "ScrollBar", 50015: "Slider", 50016: "Spinner", 50017: "StatusBar", 50018: "Tab",
    50019: "TabItem", 50020: "Text", 50021: "ToolBar", 50022: "ToolTip", 50023: "Tree",
    50024: "TreeItem", 50025: "Custom", 50026: "Group", 50027: "Thumb", 50028: "DataGrid",
    50029: "DataItem", 50030: "Document", 50031: "SplitButton", 50032: "Window",
    50033: "Pane", 50034: "Header", 50035: "HeaderItem", 50036: "Table", 50037: "TitleBar",
    50038: "Separator",
}
UIA_BOUNDS, UIA_PROCESS, UIA_CONTROL_TYPE, UIA_NAME = 30001, 30002, 30003, 30005
UIA_AUTOMATION_ID, UIA_CLASS_NAME, UIA_OFFSCREEN, UIA_VALUE = 30011, 30012, 30022, 30045
UIA_TREE_SCOPE_DESCENDANTS = 4


@dataclass(frozen=True)
class ElementInfo:
    role: str
    automation_id: str
    name: str
    class_name: str
    x: int
    y: int
    width: int
    height: int
    value: str = ""
    offscreen: bool = False

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.width, self.height

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height

    def usable_in(self, window: WindowInfo) -> bool:
        """Visible and inside the window; offscreen fields (e.g. other tabs) are never clicked."""
        x, y = self.center
        return (self.width > 0 and self.height > 0 and not self.offscreen
                and window.x <= x < window.x + window.width and window.y <= y < window.y + window.height)


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role or "Alan")


def stable_identity(info: ElementInfo) -> tuple[str, str]:
    """Identifier and name, excluding a name that only repeats the field's changing value."""
    name = info.name.strip()
    if name and info.value.strip() and name == info.value.strip():
        name = ""
    return info.automation_id.strip(), name


def validate_locator(locator: Any, system: str | None = None) -> dict:
    invalid = "Alan kimliği geçersiz. Hedefi Ekranda seç ile yeniden belirleyin."
    if not isinstance(locator, dict) or set(locator) - LOCATOR_KEYS:
        raise WindowError(invalid)
    result: dict[str, Any] = {}
    for key in LOCATOR_TEXT_KEYS:
        value = locator.get(key, "")
        if not isinstance(value, str) or len(value) > MAX_LOCATOR_TEXT:
            raise WindowError(invalid)
        result[key] = value
    index = locator.get("index", 0)
    if type(index) is not int or not 0 <= index <= MAX_INDEX:
        raise WindowError(invalid)
    result["index"] = index
    if not result["automation_id"] and not result["name"]:
        raise WindowError("Alanın kimliği veya adı yok. Konum veya görsel yöntemini kullanın.")
    current = system or platform.system()
    if locator.get("platform") != current:
        raise WindowError("Alan başka bir işletim sisteminde seçilmiş. Bu bilgisayarda Ekranda seç ile yeniden seçin.")
    result["platform"] = current
    return result


def matches(info: ElementInfo, locator: dict) -> bool:
    if locator["role"] and info.role != locator["role"]:
        return False
    automation_id, name = stable_identity(info)
    if locator["automation_id"]:
        return automation_id == locator["automation_id"]
    return bool(locator["name"]) and name == locator["name"]


def describe_locator(locator: dict) -> str:
    parts = [role_label(locator.get("role", ""))]
    if locator.get("automation_id"):
        parts.append(f"kimlik {locator['automation_id']}")
    if locator.get("name"):
        parts.append(f"“{locator['name']}”")
    return " · ".join(parts)


class ElementService:
    def __init__(self, backend: Any = None, *, cancel: threading.Event | None = None,
                 clock: Callable[[], float] = time.monotonic, system: str | None = None):
        self._backend = backend
        self.cancel = cancel or threading.Event()
        self.clock = clock
        self.system = system or platform.system()

    @property
    def backend(self) -> Any:
        if self._backend is None:
            if self.system == "Windows":
                self._backend = UiaElements()
            elif self.system == "Darwin":
                self._backend = AxElements()
            else:
                raise WindowError("Alan kimliği macOS ve Windows üzerinde desteklenir.")
        return self._backend

    def _matching(self, window: WindowInfo, locator: dict) -> list[ElementInfo]:
        return [info for info in self.backend.elements(window, locator["role"] or None)
                if info.usable_in(window) and matches(info, locator)]

    def describe_at(self, window: WindowInfo, x: int, y: int) -> dict:
        """Locator for the field at a screen point, or the reason none is usable."""
        try:
            info = self.backend.element_at(window, x, y)
            if info is None or not info.usable_in(window):
                return {"available": False, "reason": "Bu noktada uygulama yapısından bir alan okunamadı. "
                                                      "Konum veya görsel yöntemini kullanın."}
            automation_id, name = stable_identity(info)
            if not automation_id and not name:
                return {"available": False, "summary": role_label(info.role),
                        "reason": f"{role_label(info.role)} bulundu ancak uygulama bu alana kimlik veya ad "
                                  "vermiyor. Konum veya görsel yöntemini kullanın."}
            locator = {"platform": self.system, "role": info.role[:MAX_LOCATOR_TEXT],
                       "automation_id": automation_id[:MAX_LOCATOR_TEXT], "name": name[:MAX_LOCATOR_TEXT],
                       "class_name": info.class_name[:MAX_LOCATOR_TEXT], "index": 0}
            found = self._matching(window, locator)
            index = next((i for i, item in enumerate(found) if item.bounds == info.bounds), None)
            if index is None or index > MAX_INDEX:
                return {"available": False, "summary": describe_locator(locator),
                        "reason": "Alan bulundu ancak pencere içinde yeniden doğrulanamadı. "
                                  "Konum veya görsel yöntemini kullanın."}
            locator["index"] = index
            summary = describe_locator(locator)
            if len(found) > 1:
                summary += f" · aynı kimlikteki {len(found)} alanın {index + 1}. sırası"
            return {"available": True, "locator": locator, "summary": summary, "unique": len(found) == 1}
        except WindowError as exc:
            return {"available": False, "reason": str(exc)}

    def find(self, window: WindowInfo, locator: Any, *, timeout: float) -> ElementInfo:
        locator = validate_locator(locator, self.system)
        deadline = self.clock() + timeout
        while True:
            if self.cancel.is_set():
                raise InterruptedError("Alan araması iptal edildi.")
            found = self._matching(window, locator)
            if len(found) > locator["index"]:
                return found[locator["index"]]
            remaining = deadline - self.clock()
            if remaining <= 0:
                raise WindowError(f"Alan bulunamadı ({describe_locator(locator)}). Doğru ekranın açık ve alanın "
                                  "görünür olduğunu kontrol edin; gerekirse hedefi yeniden seçin.")
            self.cancel.wait(min(POLL_SECONDS, remaining))


def import_comtypes():
    """Import comtypes without clashing with a thread already joined to COM.

    comtypes initializes COM for the importing thread. The workflow thread may
    already be in the multithreaded apartment (e.g. after Windows OCR), so try
    that first, which UI Automation also recommends, and fall back to STA.
    """
    import sys

    if "comtypes" in sys.modules:
        return sys.modules["comtypes"]
    previous = getattr(sys, "coinit_flags", None)
    try:
        for flags in (0, 2):  # COINIT_MULTITHREADED, COINIT_APARTMENTTHREADED
            sys.coinit_flags = flags
            try:
                import comtypes
                import comtypes.client  # noqa: F401

                return comtypes
            except OSError:
                for name in [module for module in sys.modules if module == "comtypes" or module.startswith("comtypes.")]:
                    del sys.modules[name]
        raise WindowError("Windows COM başlatılamadı. Uygulamayı yeniden açıp tekrar deneyin.")
    finally:
        if previous is None:
            del sys.coinit_flags
        else:
            sys.coinit_flags = previous


class UiaElements:
    """Windows UI Automation through comtypes; one COM context per calling thread."""

    def __init__(self):
        try:
            import_comtypes()
        except ImportError as exc:
            raise WindowError("Alan kimliği için Windows otomasyon paketlerini kurun: .[automation]") from exc
        self._local = threading.local()

    def _context(self) -> Any:
        context = getattr(self._local, "context", None)
        if context is not None:
            return context
        import_comtypes()
        import comtypes
        import comtypes.client

        try:
            # UI Automation clients should use the multithreaded apartment.
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except OSError:
            pass  # This thread already joined an apartment.
        try:
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen import UIAutomationClient as uia

            automation = comtypes.client.CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)
            request = automation.CreateCacheRequest()
            for property_id in (UIA_BOUNDS, UIA_PROCESS, UIA_CONTROL_TYPE, UIA_NAME, UIA_AUTOMATION_ID,
                                UIA_CLASS_NAME, UIA_OFFSCREEN, UIA_VALUE):
                request.AddProperty(property_id)
            context = (automation, request, automation.CreateTrueCondition())
        except (OSError, ImportError, AttributeError) as exc:
            raise WindowError("Windows UI Automation başlatılamadı. Uygulamayı yeniden açıp tekrar deneyin.") from exc
        self._local.context = context
        return context

    @staticmethod
    def _text(value: Any) -> str:
        return value if isinstance(value, str) else ""

    def _info(self, element: Any) -> ElementInfo | None:
        try:
            rect = element.CachedBoundingRectangle
            value = element.GetCachedPropertyValue(UIA_VALUE)
            return ElementInfo(
                role=UIA_CONTROL_TYPES.get(int(element.CachedControlType), "Custom"),
                automation_id=self._text(element.CachedAutomationId), name=self._text(element.CachedName),
                class_name=self._text(element.CachedClassName),
                x=int(rect.left), y=int(rect.top), width=int(rect.right - rect.left),
                height=int(rect.bottom - rect.top), value=self._text(value),
                offscreen=bool(element.CachedIsOffscreen),
            )
        except (OSError, ValueError, TypeError, AttributeError):
            return None

    def elements(self, window: WindowInfo, role: str | None = None) -> list[ElementInfo]:
        automation, request, everything = self._context()
        try:
            root = automation.ElementFromHandle(window.window_id)
            # One cross-process call returns every descendant with the cached properties.
            found = root.FindAllBuildCache(UIA_TREE_SCOPE_DESCENDANTS, everything, request)
            count = min(found.Length, WINDOWS_ELEMENT_LIMIT) if found is not None else 0
            items = (self._info(found.GetElement(index)) for index in range(count))
            return [item for item in items if item is not None and (role is None or item.role == role)]
        except OSError as exc:
            raise WindowError("uygulama penceresinin alanları okunamadı. Pencere kapanmış veya yanıt vermiyor olabilir.") from exc

    def element_at(self, window: WindowInfo, x: int, y: int) -> ElementInfo | None:
        # Hit-test the window's own tree: another window above the point (Studio,
        # the picker HUD) can never be mistaken for the uygulama field.
        candidates = [(item.width * item.height, -index, item)
                      for index, item in enumerate(self.elements(window))
                      if item.width > 0 and item.height > 0 and not item.offscreen and item.contains(x, y)]
        return min(candidates, key=lambda entry: entry[:2])[2] if candidates else None


class AxElements:
    """macOS Accessibility (AXUIElement) through pyobjc; needs the Accessibility permission."""

    def __init__(self):
        try:
            import ApplicationServices
        except ImportError as exc:
            raise WindowError("Alan kimliği için macOS otomasyon paketlerini kurun: .[automation]") from exc
        self.ax = ApplicationServices

    def _application(self, window: WindowInfo) -> Any:
        if not self.ax.AXIsProcessTrusted():
            raise WindowError("Alan kimliğini okumak için Sistem Ayarları → Gizlilik ve Güvenlik → Erişilebilirlik "
                              "bölümünden RpaOrkestrAI'ye izin verin.")
        application = self.ax.AXUIElementCreateApplication(window.pid)
        # A hung uygulama must not freeze the picker or a run for the 6-second default.
        self.ax.AXUIElementSetMessagingTimeout(application, 1.0)
        return application

    def _attribute(self, element: Any, name: str) -> Any:
        try:
            error, value = self.ax.AXUIElementCopyAttributeValue(element, name, None)
        except (TypeError, ValueError):
            return None
        return value if error == 0 else None

    def _text(self, element: Any, name: str) -> str:
        value = self._attribute(element, name)
        return str(value) if isinstance(value, str) else ""

    def _bounds(self, element: Any) -> tuple[int, int, int, int] | None:
        position, size = self._attribute(element, "AXPosition"), self._attribute(element, "AXSize")
        if position is None or size is None:
            return None
        point_ok, point = self.ax.AXValueGetValue(position, self.ax.kAXValueCGPointType, None)
        size_ok, extent = self.ax.AXValueGetValue(size, self.ax.kAXValueCGSizeType, None)
        if not point_ok or not size_ok:
            return None
        return round(point.x), round(point.y), round(extent.width), round(extent.height)

    def _info(self, element: Any, role: str | None = None) -> ElementInfo | None:
        bounds = self._bounds(element)
        if bounds is None:
            return None
        name = self._text(element, "AXTitle") or self._text(element, "AXDescription")
        if not name:
            label = self._attribute(element, "AXTitleUIElement")
            if label is not None:
                name = self._text(label, "AXValue") or self._text(label, "AXTitle")
        return ElementInfo(
            role=role if role is not None else self._text(element, "AXRole"),
            automation_id=self._text(element, "AXIdentifier"), name=name,
            class_name=self._text(element, "AXSubrole"), x=bounds[0], y=bounds[1],
            width=bounds[2], height=bounds[3], value=self._text(element, "AXValue"),
        )

    def _window_element(self, application: Any, window: WindowInfo) -> Any:
        candidates = [item for item in self._attribute(application, "AXWindows") or []
                      if self._text(item, "AXTitle") == window.title]
        if len(candidates) > 1:
            candidates = [item for item in candidates if (self._bounds(item) or (None, None))[:2] == (window.x, window.y)]
        if len(candidates) != 1:
            raise WindowError("uygulama penceresi erişilebilirlik ağacında bulunamadı. Pencereyi yeniden tanıtın.")
        return candidates[0]

    def elements(self, window: WindowInfo, role: str | None = None) -> list[ElementInfo]:
        application = self._application(window)
        queue = deque([(self._window_element(application, window), 0)])
        found, visited = [], 0
        # Breadth-first with limits: large grids must not stall a run.
        while queue and visited < MAC_ELEMENT_LIMIT:
            element, depth = queue.popleft()
            visited += 1
            element_role = self._text(element, "AXRole")
            if role is None or element_role == role:
                info = self._info(element, element_role)
                if info is not None:
                    found.append(info)
            if depth < MAC_DEPTH_LIMIT:
                queue.extend((child, depth + 1) for child in self._attribute(element, "AXChildren") or [])
        return found

    def element_at(self, window: WindowInfo, x: int, y: int) -> ElementInfo | None:
        application = self._application(window)
        # Hit-testing through the application element ignores other apps' windows.
        error, element = self.ax.AXUIElementCopyElementAtPosition(application, float(x), float(y), None)
        if error != 0 or element is None:
            return None
        return self._info(element)
