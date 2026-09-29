"""Real accessibility trees: a Win32 edit control on Windows, never sending input."""

import os
import platform
import threading

import pytest

from rpa_orkestrai.desktop.elements import ElementService, UiaElements
from rpa_orkestrai.desktop.windows import WindowInfo

pytestmark = pytest.mark.skipif(platform.system() != "Windows", reason="Windows UI Automation")

EDIT_ID = 1001


@pytest.fixture
def win32_form():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                       wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.SetProcessDPIAware()
    ready, state = threading.Event(), {}

    def interface():
        # Win32 controls answer UI Automation through their own thread's message loop.
        overlapped_visible = 0x00CF0000 | 0x10000000
        child_visible_border = 0x40000000 | 0x10000000 | 0x00800000
        form = user32.CreateWindowExW(0, "STATIC", "RpaOrkestrAI UIA test", overlapped_visible,
                                      120, 120, 420, 220, None, None, None, None)
        edit = user32.CreateWindowExW(0x200, "EDIT", "", child_visible_border, 30, 50, 220, 26, form,
                                      wintypes.HMENU(EDIT_ID), None, None)
        state.update(form=form, edit=edit, thread=kernel32.GetCurrentThreadId())
        ready.set()
        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        user32.DestroyWindow(form)

    thread = threading.Thread(target=interface, daemon=True)
    thread.start()
    assert ready.wait(10) and state["form"] and state["edit"]
    rect, edit_rect = wintypes.RECT(), wintypes.RECT()
    user32.GetWindowRect(state["form"], ctypes.byref(rect))
    user32.GetWindowRect(state["edit"], ctypes.byref(edit_rect))
    window = WindowInfo(int(state["form"]), os.getpid(), "python.exe", "RpaOrkestrAI UIA test",
                        rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
    try:
        yield window, (edit_rect.left, edit_rect.top, edit_rect.right - edit_rect.left,
                       edit_rect.bottom - edit_rect.top)
    finally:
        user32.PostThreadMessageW(state["thread"], 0x0012, 0, 0)  # WM_QUIT
        thread.join(10)


def test_ui_automation_reads_edit_identity_and_bounds(win32_form):
    window, (x, y, width, height) = win32_form
    backend = UiaElements()
    edits = [item for item in backend.elements(window) if item.role == "Edit"]
    assert [item.automation_id for item in edits] == [str(EDIT_ID)]
    assert edits[0].bounds == (x, y, width, height)

    hit = backend.element_at(window, x + 5, y + 5)
    assert hit is not None and hit.role == "Edit"
    described = ElementService(backend).describe_at(window, x + 5, y + 5)
    assert described["available"] is True
    assert described["locator"]["automation_id"] == str(EDIT_ID)

    found = ElementService(backend).find(window, described["locator"], timeout=2)
    assert found.center == (x + width // 2, y + height // 2)


def test_ui_automation_works_from_worker_threads(win32_form):
    window, _ = win32_form
    backend, results = UiaElements(), []

    def worker():
        results.append(len(backend.elements(window)))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert len(results) == 2 and all(count >= 1 for count in results)


def test_ui_automation_reads_the_current_field_value(win32_form):
    import ctypes
    from ctypes import wintypes

    window, _ = win32_form
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowExW.restype = wintypes.HWND
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR]
    edit = user32.FindWindowExW(window.window_id, None, "EDIT", None)
    user32.SendMessageW(edit, 0x000C, 0, "INV-2026-9")  # WM_SETTEXT
    locator = {"platform": "Windows", "role": "Edit", "automation_id": str(EDIT_ID), "name": "", "index": 0}
    assert ElementService(UiaElements()).find(window, locator, timeout=2).value == "INV-2026-9"


def test_win32_window_move_state_and_close(win32_form):
    import ctypes

    from rpa_orkestrai.desktop.windows import Win32Windows, WindowService

    window, _ = win32_form
    service = WindowService(backend=Win32Windows())
    target = service.find("", window.title)
    moved = service.move_resize(target, 50, 60, 500, 300)
    assert (moved["x"], moved["y"], moved["width"], moved["height"]) == (50, 60, 500, 300)
    user32 = ctypes.WinDLL("user32")
    service.set_state(target, "minimize")
    assert user32.IsIconic(window.window_id)
    service.set_state(target, "restore")
    assert not user32.IsIconic(window.window_id)
    service.close(target)
    service.wait_closed(target, 5)
