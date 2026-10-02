"""Window discovery/input tests never send input to the real desktop."""

import ctypes
from ctypes import wintypes
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from rpa_orkestrai.desktop.vision import AmbiguousMatchError, Match, Vision
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
    with pytest.raises(WindowError, match='Pencere bulunamadığı için'):
        service.click({'found': False}, 10, 10, desktop)
    # A value that is not a window at all (an empty or mistyped Pencere field) says where to fix it.
    with pytest.raises(WindowError, match='Pencere alanındaki değer bir pencere değil'):
        service.click('', 10, 10, desktop)
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


def win32_backend_for(window):
    backend = Win32Windows.__new__(Win32Windows)
    backend.c, backend.w = ctypes, wintypes
    backend.callback = lambda callback: callback
    handle = window.window_id
    user, kernel = Mock(), Mock()
    backend.user, backend.kernel = user, kernel
    user.EnumWindows.side_effect = lambda callback, _: callback(handle, 0)
    user.IsWindowVisible.return_value = True
    user.IsIconic.return_value = False
    user.IsZoomed.return_value = False
    user.GetSystemMetrics.side_effect = {32: 4, 33: 4, 92: 4}.__getitem__
    user.GetWindowTextLengthW.return_value = len(window.title)
    user.GetWindowTextW.side_effect = lambda _, buffer, length: setattr(buffer, 'value', window.title)
    user.GetWindowThreadProcessId.side_effect = lambda _, ptr: setattr(ptr._obj, 'value', 42)
    def rect(_, ptr):
        ptr._obj.left, ptr._obj.top = window.x, window.y
        ptr._obj.right, ptr._obj.bottom = window.x + window.width, window.y + window.height
        return True
    user.GetWindowRect.side_effect = rect
    kernel.OpenProcess.return_value = 999
    def process_name(_, flags, buffer, size):
        buffer.value = r'C:\Program Files\ERP\erp.exe'
        return True
    kernel.QueryFullProcessImageNameW.side_effect = process_name
    user.GetForegroundWindow.return_value = handle
    return backend


def test_win32_enumeration_keeps_64bit_handles_closes_process_and_skips_minimized(window):
    backend = win32_backend_for(window)
    user, kernel = backend.user, backend.kernel
    assert backend.list_windows() == [replace(window, application='erp.exe')]
    kernel.CloseHandle.assert_called_once_with(999)
    backend.activate(window)
    user.SetForegroundWindow.assert_called_once_with(window.window_id)
    assert backend.is_active(window)
    user.IsIconic.return_value = True
    assert backend.list_windows() == []


@pytest.fixture
def desktop(window):
    controller = Mock()
    controller.size.return_value = (1440, 900)
    controller.screenshot.return_value = SimpleNamespace(size=(window.width, window.height))
    return controller


@pytest.fixture
def template(tmp_path):
    path = tmp_path / "FormID.png"
    path.write_bytes(b"mocked image decoder")
    return path


def test_target_coordinates_follow_current_window_and_click_options(service, window, desktop):
    service.backend.list_windows.return_value = [replace(window, x=250, y=150)]
    service.click_target(window.result(), desktop, x=25, y=40, clicks=2, button="right")
    desktop.click.assert_called_once_with(275, 190, clicks=2, button="right")
    desktop.screenshot.assert_not_called()


def test_target_coordinates_refresh_after_activation_moves_window(service, window, desktop):
    service.backend.activate.side_effect = lambda _: setattr(
        service.backend.list_windows, "return_value", [replace(window, x=400, y=200)],
    )
    service.click_target(window.result(), desktop, x=25, y=40)
    desktop.click.assert_called_once_with(425, 240, clicks=1, button="left")


def test_target_coordinates_reject_secondary_screen_without_input(service, window, desktop):
    service.backend.list_windows.return_value = [replace(window, x=-800)]
    with pytest.raises(WindowError, match="ana ekranın dışında"):
        service.click_target(window.result(), desktop, x=25, y=40)
    desktop.click.assert_not_called()
    service.backend.activate.assert_not_called()


def test_image_target_is_window_scoped_and_offset_is_from_center(service, window, desktop, template, monkeypatch):
    matcher = Mock(return_value=Match(40, 60, 20, 10, 0.99))
    monkeypatch.setattr(Vision, "match_template", matcher)
    service.click_target(window.result(), desktop, target_mode="image", template=template,
                         offset_x=30, offset_y=-5, confidence=0.95)
    desktop.screenshot.assert_called_once_with((100, 80, 800, 600))
    matcher.assert_called_once_with(desktop.screenshot.return_value, template, threshold=0.95, require_unique=True)
    desktop.click.assert_called_once_with(180, 140, clicks=1, button="left")


def test_image_offset_must_stay_inside_window(service, window, desktop, template, monkeypatch):
    monkeypatch.setattr(Vision, "match_template", Mock(return_value=Match(780, 100, 20, 10, 0.99)))
    with pytest.raises(WindowError, match="pencere sınırlarının dışında"):
        service.click_target(window.result(), desktop, target_mode="image", template=template, offset_x=20)
    desktop.click.assert_not_called()


def test_window_moved_during_image_search_never_receives_stale_click(service, window, desktop, template, monkeypatch):
    def match(*args, **kwargs):
        service.backend.list_windows.return_value = [replace(window, x=300)]
        return Match(40, 60, 20, 10, 0.99)
    monkeypatch.setattr(Vision, "match_template", match)
    with pytest.raises(WindowError, match="konumu veya boyutu değişti"):
        service.click_target(window.result(), desktop, target_mode="image", template=template)
    desktop.click.assert_not_called()


def test_capture_checks_focus_and_normalized_size(service, window, desktop):
    observed, image = service.screenshot_window(window.result(), desktop)
    assert observed == window and image.size == (800, 600)
    desktop.screenshot.return_value = SimpleNamespace(size=(1600, 1200))
    with pytest.raises(WindowError, match="ölçeği değişti"):
        service.screenshot_window(window.result(), desktop)


def test_retina_capture_image_matching_and_click_share_logical_coordinates(service, window, tmp_path):
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    image_module = pytest.importorskip("PIL.Image")
    from rpa_orkestrai.desktop.controller import DesktopController

    pixels = np.zeros((900, 1440), dtype=np.uint8)
    reference = np.random.default_rng(17).integers(0, 255, (20, 24), dtype=np.uint8)
    pixels[130:150, 140:164] = reference
    logical_image = image_module.fromarray(pixels)
    physical_image = logical_image.resize((2880, 1800), image_module.Resampling.NEAREST)
    backend = Mock()
    backend.size.return_value = (1440, 900)
    backend.screenshot.return_value = physical_image
    desktop = DesktopController()
    desktop._backend = backend
    path = tmp_path / "reference.png"
    image_module.fromarray(reference).save(path)

    service.click_target(window.result(), desktop, target_mode="image", template=path, confidence=0.9)

    backend.click.assert_called_once_with(x=152, y=140, clicks=1, interval=0.1, button="left")


def test_capture_rejects_partially_hidden_window_before_screenshot(service, window, desktop):
    service.backend.list_windows.return_value = [replace(window, x=-20)]
    with pytest.raises(WindowError, match="tamamını ana ekranın"):
        service.screenshot_window(window.result(), desktop)
    desktop.screenshot.assert_not_called()


@pytest.mark.parametrize("border", [8, 12])
def test_maximized_win32_capture_preserves_image_and_legacy_click_origin(window, border, tmp_path):
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    image_module = pytest.importorskip("PIL.Image")
    maximized = replace(window, application="erp.exe", x=-border, y=-border,
                        width=1920 + 2 * border, height=1080 + 2 * border)
    backend = win32_backend_for(maximized)
    backend.user.IsZoomed.return_value = True
    backend.user.GetSystemMetrics.side_effect = {32: border // 2, 33: border // 2,
                                               92: border // 2}.__getitem__
    service = WindowService(backend=backend)
    pixels = np.zeros((1080, 1920), dtype=np.uint8)
    reference = np.random.default_rng(83).integers(0, 255, (20, 24), dtype=np.uint8)
    pixels[130:150, 140:164] = reference
    desktop = Mock()
    desktop.size.return_value = (1920, 1080)
    desktop.screenshot.return_value = image_module.fromarray(pixels)

    observed, capture = service.screenshot_window(maximized.result(), desktop)
    assert observed == maximized
    assert capture.size == (maximized.width, maximized.height)
    desktop.screenshot.assert_called_once_with((0, 0, 1920, 1080))
    assert np.array_equal(np.array(capture)[border:border + 1080, border:border + 1920], pixels)
    assert capture.getpixel((0, 0)) == 0
    # A template selected from the padded picker resolves to its visible screen point.
    template = tmp_path / "form.png"
    capture.crop((140 + border, 130 + border, 164 + border, 150 + border)).save(template)
    service.click_target(maximized.result(), desktop, target_mode="image", template=template)
    desktop.click.assert_called_once_with(152, 140, clicks=1, button="left")
    desktop.reset_mock()
    service.click_target(maximized.result(), desktop, x=152 + border, y=140 + border)
    desktop.click.assert_called_once_with(152, 140, clicks=1, button="left")
    desktop.reset_mock()
    service.click(maximized.result(), 152 + border, 140 + border, desktop)
    desktop.click.assert_called_once_with(152, 140)


@pytest.mark.parametrize("maximized,x,y,width,height", [
    (False, -8, -8, 1936, 1096),  # A normal partially offscreen window is still rejected.
    (True, -9, -8, 1937, 1096),  # Even one pixel beyond the actual frame is rejected.
    (True, -8, -9, 1936, 1097),
    (True, -8, -8, 1937, 1096),
    (True, -8, -8, 1936, 1097),
    (True, -1928, -8, 1936, 1096),  # A maximized secondary display is not captured.
])
def test_win32_clipping_never_accepts_hidden_content(window, maximized, x, y, width, height):
    hidden = replace(window, x=x, y=y, width=width, height=height)
    backend = win32_backend_for(hidden)
    backend.user.IsZoomed.return_value = maximized
    service = WindowService(backend=backend)
    desktop = Mock()
    desktop.size.return_value = (1920, 1080)
    target = service.find("erp.exe", window.title)
    with pytest.raises(WindowError, match="tamamını ana ekranın"):
        service.screenshot_window(target, desktop)
    desktop.screenshot.assert_not_called()
    desktop.click.assert_not_called()


def test_focus_lost_during_capture_never_receives_input(service, window, desktop, template):
    def screenshot(region):
        service.backend.is_active.return_value = False
        return SimpleNamespace(size=(800, 600))
    desktop.screenshot.side_effect = screenshot
    with pytest.raises(WindowError, match="odağı değişti"):
        service.click_target(window.result(), desktop, target_mode="image", template=template)
    desktop.click.assert_not_called()


def test_fill_clears_selected_field_before_writing_and_append_does_not_clear(service, window, desktop):
    service.fill_target(window.result(), "İade-00042", desktop, x=40, y=60)
    input_calls = [entry for entry in desktop.mock_calls if entry[0] in {"click", "hotkey", "press", "write"}]
    assert input_calls == [call.click(140, 140, clicks=1, button="left"), call.hotkey("mod", "a"),
                           call.press("backspace"), call.write("İade-00042")]
    desktop.reset_mock()
    service.fill_target(window.result(), "-ek", desktop, x=40, y=60, clear=False)
    desktop.hotkey.assert_not_called()
    desktop.press.assert_not_called()
    desktop.write.assert_called_once_with("-ek")


def test_fill_focus_change_after_click_stops_before_clear_or_write(service, window, desktop):
    desktop.click.side_effect = lambda *args, **kwargs: setattr(service.backend.is_active, "return_value", False)
    with pytest.raises(WindowError, match="odağı değişti"):
        service.fill_target(window.result(), "42", desktop, x=40, y=60)
    desktop.hotkey.assert_not_called()
    desktop.press.assert_not_called()
    desktop.write.assert_not_called()


@pytest.mark.parametrize("modifier", ["none", "mod", "shift", "alt", "ctrl"])
def test_press_key_targets_only_identified_window(service, window, desktop, modifier):
    service.press_key(window.result(), "enter", modifier, desktop)
    if modifier == "none":
        desktop.press.assert_called_once_with("enter")
        desktop.hotkey.assert_not_called()
    else:
        desktop.hotkey.assert_called_once_with(modifier, "enter")
        desktop.press.assert_not_called()


def test_unknown_key_or_modifier_is_rejected_before_focus(service, window, desktop):
    for key, modifier in (("not-a-key", "none"), ("enter", "meta"), (["enter"], "none")):
        with pytest.raises(WindowError, match="desteklenmiyor"):
            service.press_key(window.result(), key, modifier, desktop)
    service.backend.activate.assert_not_called()
    desktop.press.assert_not_called()
    desktop.hotkey.assert_not_called()


def test_image_wait_activates_once_and_observes_appearance(service, window, desktop, template, monkeypatch):
    monkeypatch.setattr(Vision, "match_template", Mock(side_effect=[None, Match(20, 30, 10, 10, 0.97)]))
    monkeypatch.setattr(service.cancel, "wait", Mock(return_value=False))
    result = service.wait_image(window.result(), template, desktop, timeout=1)
    assert result.center == (125, 115)
    service.backend.activate.assert_called_once()
    assert desktop.screenshot.call_count == 2
    desktop.click.assert_not_called()
    desktop.write.assert_not_called()


def test_image_wait_can_observe_disappearance(service, window, desktop, template, monkeypatch):
    monkeypatch.setattr(Vision, "match_template", Mock(side_effect=[Match(20, 30, 10, 10, 0.97), None]))
    monkeypatch.setattr(service.cancel, "wait", Mock(return_value=False))
    assert service.wait_image(window.result(), template, desktop, visible=False, timeout=1) is None
    service.backend.activate.assert_called_once()
    desktop.click.assert_not_called()


def test_missing_or_ambiguous_image_never_clicks(service, window, desktop, template, monkeypatch):
    monkeypatch.setattr(Vision, "match_template", Mock(return_value=None))
    with pytest.raises(TimeoutError, match="bekleme süresi"):
        service.click_target(window.result(), desktop, target_mode="image", template=template, timeout=0)
    monkeypatch.setattr(Vision, "match_template", Mock(side_effect=AmbiguousMatchError()))
    with pytest.raises(WindowError, match="birden fazla"):
        service.click_target(window.result(), desktop, target_mode="image", template=template)
    desktop.click.assert_not_called()


def test_cancel_during_image_matching_prevents_click(service, window, desktop, template, monkeypatch):
    def match(*args, **kwargs):
        service.cancel.set()
        return Match(20, 30, 10, 10, 0.99)
    monkeypatch.setattr(Vision, "match_template", match)
    with pytest.raises(InterruptedError):
        service.click_target(window.result(), desktop, target_mode="image", template=template)
    desktop.click.assert_not_called()


def test_missing_template_and_empty_fill_never_activate(service, window, desktop, tmp_path):
    with pytest.raises(WindowError, match="görsel dosyası bulunamadı"):
        service.click_target(window.result(), desktop, target_mode="image", template=tmp_path / "missing.png")
    with pytest.raises(WindowError, match="boş olmamalıdır"):
        service.fill_target(window.result(), "", desktop, x=10, y=10)
    service.backend.activate.assert_not_called()
    desktop.click.assert_not_called()


@pytest.mark.parametrize("character", ["\t", "\n", "\r", "\x00", "\x1b", "\x1f", "\x7f"])
def test_fill_rejects_control_characters_before_focus_or_input(service, window, desktop, character):
    with pytest.raises(WindowError, match="Pencerede tuşa bas"):
        service.fill_target(window.result(), "FAT-001" + character, desktop, x=40, y=60)
    service.backend.activate.assert_not_called()
    desktop.click.assert_not_called()
    desktop.hotkey.assert_not_called()
    desktop.press.assert_not_called()
    desktop.write.assert_not_called()


def test_fill_text_limit_is_checked_before_focus(service, window, desktop):
    with pytest.raises(WindowError, match="10.000"):
        service.fill_target(window.result(), "A" * 10_001, desktop, x=40, y=60)
    service.backend.activate.assert_not_called()
    desktop.click.assert_not_called()
    desktop.write.assert_not_called()
    service.fill_target(window.result(), "A" * 10_000, desktop, x=40, y=60, clear=False)
    desktop.write.assert_called_once_with("A" * 10_000)
