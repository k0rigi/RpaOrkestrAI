"""The native title bar takes the sidebar color on a real window of each platform."""

import platform
import sys

import pytest

from rpa_orkestrai.native import TITLE_BAR, macos_title_bar, style_title_bar, windows_title_bar


def test_unavailable_native_window_keeps_system_title_bar():
    class Window:
        native = None

    style_title_bar(Window())  # Must not raise before pywebview sets .native.


@pytest.mark.skipif(platform.system() != "Windows", reason="Win32 DWM title bar")
def test_windows_caption_takes_sidebar_color():
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    # WS_OVERLAPPEDWINDOW: a real top-level frame with a caption, never shown.
    hwnd = user32.CreateWindowExW(0, "STATIC", "RpaOrkestrAI başlık testi", 0x00CF0000,
                                  0, 0, 400, 300, None, None, None, None)
    assert hwnd
    try:
        result = windows_title_bar(int(hwnd))
        if sys.getwindowsversion().build >= 22000:
            assert result == 0
            color = wintypes.DWORD()
            ctypes.windll.dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), wintypes.DWORD(35),
                                                       ctypes.byref(color), ctypes.sizeof(color))
            red, green, blue = TITLE_BAR
            assert color.value in {0, red | green << 8 | blue << 16}
    finally:
        user32.DestroyWindow(wintypes.HWND(hwnd))


@pytest.mark.skipif(platform.system() != "Darwin", reason="AppKit title bar")
def test_macos_title_bar_is_dark_and_transparent(monkeypatch):
    from AppKit import NSApplication, NSBackingStoreBuffered, NSMakeRect, NSWindow
    from PyObjCTools import AppHelper

    NSApplication.sharedApplication()
    monkeypatch.setattr(AppHelper, "callAfter", lambda function: function())
    window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, 400, 300), 1 | 2 | 8, NSBackingStoreBuffered, True)
    window.setReleasedWhenClosed_(False)
    try:
        macos_title_bar(window)
        assert window.titlebarAppearsTransparent()
        assert window.appearance().name() == "NSAppearanceNameDarkAqua"
        color = window.backgroundColor()
        assert round(color.redComponent() * 255) == TITLE_BAR[0]
        assert round(color.blueComponent() * 255) == TITLE_BAR[2]
    finally:
        window.close()
