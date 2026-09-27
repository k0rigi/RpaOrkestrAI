"""Window discovery/input tests never send input to the real desktop."""

import ctypes
from ctypes import wintypes
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rpa_orkestrai.desktop.windows import MacWindows, Win32Windows, WindowError, WindowInfo, WindowService


@pytest.fixture
def window():
    return WindowInfo(0x100001234, 42, 'ERP', 'İade Faturası', 100, 80, 800, 600)


@pytest.fixture
def service(window):
    return WindowService(backend=SimpleNamespace(
        list_windows=Mock(return_value=[window]), activate=Mock(), is_active=Mock(return_value=True),
    ))


def test_find_window_exact_contains_and_missing(service, window):
    assert service.find('erp', 'İade Faturası')['window_id'] == window.window_id
    assert service.find('', 'Faturası', 'contains')['found'] is True
    assert service.find('Other', window.title, on_missing='continue') == {'found': False}
    with pytest.raises(WindowError, match='bulunamadı'):
        service.find('ERP', 'Missing')
    service.backend.activate.assert_not_called()


def test_ambiguity_never_selects_first_window(service, window):
    service.backend.list_windows.return_value.append(replace(window, window_id=13))
    with pytest.raises(WindowError, match='Birden fazla'):
        service.find('ERP', window.title, on_missing='continue')
    service.backend.activate.assert_not_called()


@pytest.mark.parametrize('title,match,timeout', [('', 'exact', 0), (' ', 'exact', 0),
                                               ('ERP', 'regex', 0), ('ERP', 'exact', -1),
                                               ('ERP', 'exact', float('nan')), ('ERP', 'exact', True)])
def test_invalid_selector_never_queries_native_api(service, title, match, timeout):
    with pytest.raises(WindowError):
        service.find('ERP', title, match, timeout)
    service.backend.list_windows.assert_not_called()


def test_window_wait_is_bounded_and_cancelled(service, monkeypatch):
    service.backend.list_windows.return_value = []
    monkeypatch.setattr('rpa_orkestrai.desktop.windows.time.monotonic', Mock(side_effect=[0, 2]))
    assert service.find('ERP', 'Title', timeout=1, on_missing='continue') == {'found': False}
    service.cancel.set()
    with pytest.raises(InterruptedError):
        service.list_windows()


def test_click_uses_fresh_window_position_and_checks_focus(service, window):
    desktop = Mock()
    service.backend.list_windows.return_value = [replace(window, x=300, y=200)]
    service.click(window.result(), 25, 40, desktop)
    desktop.click.assert_called_once_with(325, 240)
    assert service.backend.is_active.call_count >= 2


@pytest.mark.parametrize('x,y', [(-1, 2), (800, 0), (799.9, 0), (0, float('inf')), (True, 0)])
def test_out_of_bounds_click_never_activates_or_clicks(service, window, x, y):
    desktop = Mock()
    with pytest.raises(WindowError):
        service.click(window.result(), x, y, desktop)
    service.backend.activate.assert_not_called()
    desktop.click.assert_not_called()


def test_closed_or_renamed_window_does_not_receive_input(service, window):
    desktop = Mock()
    service.backend.list_windows.return_value = [replace(window, title='Different screen')]
    with pytest.raises(WindowError, match='kapanmış veya başlığı'):
        service.write(window.result(), 'invoice', desktop)
    desktop.write.assert_not_called()
    service.backend.activate.assert_not_called()


def test_lost_focus_and_missing_result_stop_input(service, window, monkeypatch):
    desktop = Mock()
    service.backend.is_active.return_value = False
    monkeypatch.setattr('rpa_orkestrai.desktop.windows.time.monotonic', Mock(side_effect=[0, 3]))
    with pytest.raises(WindowError, match='öne getirilemedi'):
        service.write(window.result(), 'invoice', desktop)
    with pytest.raises(WindowError, match='Önce'):
        service.click({'found': False}, 10, 10, desktop)
    desktop.write.assert_not_called()
    desktop.click.assert_not_called()


def test_write_preserves_unicode_and_checks_cancellation(service, window):
    desktop = Mock()
    service.write(window.result(), 'İade-00042', desktop)
    desktop.write.assert_called_once_with('İade-00042')
    service.cancel.set()
    with pytest.raises(InterruptedError):
        service.write(window.result(), 'next', desktop)
    assert desktop.write.call_count == 1


def test_macos_permissions_layer_filter_and_front_dialog(window):
    backend = MacWindows.__new__(MacWindows)
    q = SimpleNamespace(**{name: name for name in (
        'kCGWindowName', 'kCGWindowBounds', 'kCGWindowLayer', 'kCGWindowNumber', 'kCGWindowOwnerPID', 'kCGWindowOwnerName',
    )})
    q.kCGWindowListOptionOnScreenOnly, q.kCGWindowListExcludeDesktopElements, q.kCGNullWindowID = 1, 16, 0
    q.CGPreflightScreenCaptureAccess = Mock(return_value=False)
    q.CGWindowListCopyWindowInfo = Mock()
    backend.quartz = q
    with pytest.raises(WindowError, match='Ekran Kaydı'):
        backend.list_windows()
    q.CGWindowListCopyWindowInfo.assert_not_called()
    q.CGPreflightScreenCaptureAccess.return_value = True
    record = {q.kCGWindowName: window.title, q.kCGWindowBounds: {'X': 100, 'Y': 80, 'Width': 800, 'Height': 600},
              q.kCGWindowLayer: 0, q.kCGWindowNumber: window.window_id, q.kCGWindowOwnerPID: 42,
              q.kCGWindowOwnerName: 'ERP'}
    q.CGWindowListCopyWindowInfo.return_value = [dict(record, kCGWindowLayer=1), record]
    assert backend.list_windows() == [window]
    backend.appkit = SimpleNamespace(NSWorkspace=Mock())
    backend.appkit.NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier.return_value = 42
    assert backend.is_active(window)
    # A dialog without a title is still a different foreground window.
    q.CGWindowListCopyWindowInfo.return_value.insert(0, dict(record, kCGWindowName='', kCGWindowNumber=12))
    assert not backend.is_active(window)


def test_macos_titles_are_script_arguments_not_executable_code(window, monkeypatch):
    run = Mock()
    monkeypatch.setattr('rpa_orkestrai.desktop.windows.subprocess.run', run)
    backend = MacWindows.__new__(MacWindows)
    title = 'ERP "test"; do shell script "anything"'
    backend.activate(replace(window, title=title))
    args = run.call_args.args[0]
    assert args[-1] == title
    assert title not in args[2]
    assert run.call_args.kwargs['timeout'] == 5


def test_win32_enumeration_keeps_64bit_handles_closes_process_and_skips_minimized(window):
    backend = Win32Windows.__new__(Win32Windows)
    backend.c, backend.w = ctypes, wintypes
    backend.callback = lambda callback: callback
    handle = window.window_id
    user, kernel = Mock(), Mock()
    backend.user, backend.kernel = user, kernel
    user.EnumWindows.side_effect = lambda callback, _: callback(handle, 0)
    user.IsWindowVisible.return_value = True
    user.IsIconic.return_value = False
    user.GetWindowTextLengthW.return_value = len(window.title)
    user.GetWindowTextW.side_effect = lambda _, buffer, length: setattr(buffer, 'value', window.title)
    user.GetWindowThreadProcessId.side_effect = lambda _, ptr: setattr(ptr._obj, 'value', 42)
    def rect(_, ptr):
        ptr._obj.left, ptr._obj.top, ptr._obj.right, ptr._obj.bottom = 100, 80, 900, 680
        return True
    user.GetWindowRect.side_effect = rect
    kernel.OpenProcess.return_value = 999
    def process_name(_, flags, buffer, size):
        buffer.value = r'C:\Program Files\ERP\erp.exe'
        return True
    kernel.QueryFullProcessImageNameW.side_effect = process_name
    assert backend.list_windows() == [replace(window, application='erp.exe')]
    kernel.CloseHandle.assert_called_once_with(999)
    backend.activate(window)
    user.SetForegroundWindow.assert_called_once_with(handle)
    user.GetForegroundWindow.return_value = handle
    assert backend.is_active(window)
    user.IsIconic.return_value = True
    assert backend.list_windows() == []
