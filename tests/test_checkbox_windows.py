"""A real Win32 checkbox through UI Automation: read, toggle and verify, without mouse input."""
import os
import platform
import threading

import pytest

pytestmark = pytest.mark.skipif(platform.system() != "Windows", reason="Windows UI Automation")


def test_uia_reads_and_toggles_a_real_checkbox(monkeypatch):
    import ctypes
    from ctypes import wintypes

    from rpa_orkestrai.desktop import checkbox as module
    from rpa_orkestrai.desktop.checkbox import checkbox
    from rpa_orkestrai.desktop.elements import ElementService, UiaElements
    from rpa_orkestrai.desktop.windows import WindowInfo

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                       wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    ready, state = threading.Event(), {}

    def interface():
        form = user32.CreateWindowExW(0, "STATIC", "RpaOrkestrAI onay testi", 0x00CF0000 | 0x10000000,
                                      140, 140, 420, 200, None, None, None, None)
        # BS_AUTOCHECKBOX | WS_CHILD | WS_VISIBLE | WS_TABSTOP
        check = user32.CreateWindowExW(0, "BUTTON", "Onaylandı", 0x0003 | 0x40000000 | 0x10000000 | 0x00010000,
                                       30, 40, 200, 24, form, wintypes.HMENU(2001), None, None)
        state.update(form=form, check=check, thread=kernel32.GetCurrentThreadId())
        ready.set()
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        user32.DestroyWindow(form)

    thread = threading.Thread(target=interface, daemon=True)
    thread.start()
    assert ready.wait(10) and state["form"] and state["check"]
    rect = wintypes.RECT()
    user32.GetWindowRect(state["form"], ctypes.byref(rect))
    window = WindowInfo(int(state["form"]), os.getpid(), "python.exe", "RpaOrkestrAI onay testi",
                        rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
    checked = lambda: user32.SendMessageW(state["check"], 0x00F0, 0, 0) == 1  # BM_GETCHECK  # noqa: E731
    try:
        backend = UiaElements()
        boxes = [item for item in backend.elements(window, "CheckBox") if item.name == "Onaylandı"]
        assert len(boxes) == 1, backend.elements(window)
        info = boxes[0]
        assert backend.checkbox_state(window, info) is False and not checked()
        locator = {"platform": "Windows", "role": "CheckBox", "automation_id": info.automation_id,
                   "name": info.name, "class_name": info.class_name, "index": 0}
        cancel = threading.Event()
        service = type("Service", (), {})()
        service.elements = ElementService(backend, cancel=cancel)
        service.focus = lambda target: window
        service._guard = lambda target, w=None: window
        service.cancel, service._check = cancel, lambda: None
        monkeypatch.setattr(module, "VERIFY_SECONDS", 5)
        targeting = {"target_mode": "element", "element": locator, "timeout": 5}
        assert checkbox(service, {}, None, operation="check", targeting=targeting) is True and checked()
        # Already checked: nothing is toggled.
        assert checkbox(service, {}, None, operation="check", targeting=targeting) is True and checked()
        assert checkbox(service, {}, None, operation="uncheck", targeting=targeting) is False and not checked()
        assert checkbox(service, {}, None, operation="read", targeting=targeting) is False
    finally:
        user32.PostThreadMessageW(state["thread"], 0x0012, 0, 0)  # WM_QUIT
        thread.join(5)
