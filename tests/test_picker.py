import os
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image, ImageDraw

from rpa_orkestrai.desktop.picker import (
    LivePicker,
    _SelectionBridge,
    native_available,
    register_native_host,
    unregister_native_host,
)
from rpa_orkestrai.desktop.windows import WindowError, WindowInfo


def fixture_picker(*, pointer=(145, 125), escape=None, selection=None):
    window = WindowInfo(12, 42, "ERP", "İade", 100, 80, 200, 150)
    image = Image.new("RGB", (window.width, window.height), "white")
    ImageDraw.Draw(image).text((15, 20), "FormID", fill="black")
    ImageDraw.Draw(image).rectangle((80, 20, 180, 40), outline="black")
    view = Mock()
    view.hud_bounds = (300, 500, 400, 100)
    view.select.return_value = selection or {
        "crop": {"x": 10, "y": 15, "width": 55, "height": 30},
        "point": {"x": 100, "y": 30},
    }
    windows = Mock()
    windows.find.return_value = window.result()
    windows.current.return_value = window
    windows.focus.return_value = window
    windows._screen_size.return_value = (1000, 800)
    windows._capture_window.return_value = (window, image)
    desktop = Mock()
    pointer_read = Mock(return_value=pointer)
    tick = [0.0]

    def clock():
        tick[0] += 0.1
        return tick[0]

    picker = LivePicker(view_factory=lambda: view, windows_factory=lambda **_: windows,
                        desktop_factory=lambda **_: desktop, pointer=pointer_read,
                        escape=escape or (lambda: False), clock=clock)
    return SimpleNamespace(picker=picker, view=view, windows=windows, desktop=desktop,
                           window=window, image=image, pointer=pointer_read)


def pick(fixture, mode="coordinates", *, delay=3, cancel=None, state=None):
    return fixture.picker.pick({"application": "ERP", "title": "İade", "match": "exact"},
                               mode, delay, cancel=cancel or threading.Event(), on_state=state)


def test_coordinate_deadline_reads_real_pointer_relative_to_erp_without_input():
    f = fixture_picker()
    states = []
    result = pick(f, state=states.append)
    assert (result["x"], result["y"]) == (45, 45)
    assert result["image"] is f.image
    assert result["window"] == f.window
    f.pointer.assert_called_once_with()
    assert [s["remaining"] for s in states if s["status"] == "countdown"] == [3, 2, 1, 0]
    assert f.view.countdown.call_args_list[-1].args == (1, "coordinates")
    f.view.hide_studio.assert_called_once()
    f.view.close_countdown.assert_called_once()
    f.view.close.assert_called_once()
    f.view.restore_studio.assert_called_once()
    f.view.select.assert_not_called()
    f.desktop.click.assert_not_called()
    f.desktop.write.assert_not_called()
    f.desktop.hotkey.assert_not_called()
    f.windows.click.assert_not_called()
    f.windows.write.assert_not_called()
    # Re-activating ERP after the countdown can dismiss its open menus.
    f.windows.focus.assert_called_once()
    f.windows.screenshot_window.assert_not_called()


@pytest.mark.parametrize("mode", ["image", "image_only"])
def test_overlay_keeps_crop_and_optional_target_in_ram_until_api_confirmation(mode):
    f = fixture_picker()
    states = []
    result = pick(f, mode, state=states.append)
    assert result["crop"] == {"x": 10, "y": 15, "width": 55, "height": 30}
    if mode == "image":
        assert result["point"] == {"x": 100, "y": 30}
    else:
        assert "point" not in result
    assert result["image"] is f.image
    assert states[-1]["status"] == "selecting"
    f.pointer.assert_not_called()
    f.view.restore_studio.assert_called_once()


@pytest.mark.parametrize("pointer", [(20, 20), (301, 230), (True, 125)])
def test_pointer_outside_erp_or_invalid_is_rejected_and_studio_returns(pointer):
    f = fixture_picker(pointer=pointer)
    with pytest.raises(WindowError):
        pick(f)
    f.windows._capture_window.assert_not_called()
    f.view.restore_studio.assert_called_once()


def test_countdown_hud_cannot_be_selected_as_an_erp_target():
    f = fixture_picker()
    f.view.hud_bounds = (100, 100, 100, 100)
    with pytest.raises(WindowError, match="geri sayım kutusunun"):
        pick(f)
    f.view.restore_studio.assert_called_once()


def test_esc_and_http_cancellation_release_overlay_and_restore_studio():
    cancel = threading.Event()
    f = fixture_picker()
    f.view.countdown.side_effect = lambda *_: cancel.set()
    with pytest.raises(InterruptedError):
        pick(f, cancel=cancel)
    f.pointer.assert_not_called()
    f.view.restore_studio.assert_called_once()
    f = fixture_picker(escape=lambda: True)
    with pytest.raises(InterruptedError):
        pick(f)
    f.pointer.assert_not_called()
    f.view.restore_studio.assert_called_once()


def test_timeout_is_bounded_and_always_restores_studio():
    f = fixture_picker()
    ticks = iter([0, 1, 2, 122])
    f.picker.clock = lambda: next(ticks, 122)
    with pytest.raises(WindowError, match="süresi doldu"):
        pick(f)
    f.view.restore_studio.assert_called_once()


def test_focus_or_geometry_changes_never_save_a_target():
    f = fixture_picker()
    f.windows._guard.side_effect = WindowError("Pencere odağı değişti")
    with pytest.raises(WindowError, match="odağı"):
        pick(f)
    # Sample at the deadline first, then reject it if ERP lost focus. No image
    # or persisted target is produced from the rejected mouse position.
    f.pointer.assert_called_once()
    f.windows._capture_window.assert_not_called()
    f.view.restore_studio.assert_called_once()
    f = fixture_picker()
    changed = WindowInfo(12, 42, "ERP", "İade", 101, 80, 200, 150)
    f.windows._capture_window.return_value = (changed, f.image)
    with pytest.raises(WindowError, match="konumu değişti"):
        pick(f)
    f.view.restore_studio.assert_called_once()


def test_window_identity_is_checked_after_user_drags_crop():
    f = fixture_picker()
    f.windows.current.side_effect = [f.window, WindowInfo(99, 42, "ERP", "İade", 100, 80, 200, 150)]
    with pytest.raises(WindowError, match="penceresi değişti"):
        pick(f, "image")
    f.view.restore_studio.assert_called_once()


@pytest.mark.parametrize("crop", [
    {"x": -1, "y": 15, "width": 55, "height": 30},
    {"x": 10, "y": 15, "width": 5, "height": 30},
    {"x": 10.5, "y": 15, "width": 55, "height": 30},
    {"x": 10, "y": 15, "width": 55, "height": 3000},
    {"x": 150, "y": 100, "width": 20, "height": 20},  # flat white template
])
def test_invalid_or_flat_crop_is_rejected_with_no_persisted_image(crop):
    f = fixture_picker(selection={"crop": crop, "point": {"x": 100, "y": 30}})
    with pytest.raises(WindowError):
        pick(f, "image")
    f.view.restore_studio.assert_called_once()


@pytest.mark.parametrize("point", [{"x": 210, "y": 30}, {"x": True, "y": 30}, None])
def test_image_target_point_is_required_inside_erp(point):
    f = fixture_picker(selection={"crop": {"x": 10, "y": 15, "width": 55, "height": 30}, "point": point})
    with pytest.raises(WindowError):
        pick(f, "image")
    f.view.restore_studio.assert_called_once()


def test_negative_maximized_frame_origin_retains_raw_erp_coordinates():
    f = fixture_picker(pointer=(10, 30))
    f.window = WindowInfo(12, 42, "ERP", "İade", -8, -8, 1016, 808)
    f.image = Image.new("RGB", (1016, 808), "white")
    f.windows.find.return_value = f.window.result()
    f.windows.current.return_value = f.window
    f.windows.focus.return_value = f.window
    f.windows._capture_window.return_value = (f.window, f.image)
    result = pick(f)
    assert (result["x"], result["y"]) == (18, 38)


@pytest.mark.parametrize("delay", [0, 4, True, "3", 120])
def test_unsupported_delay_fails_before_hiding_studio(delay):
    f = fixture_picker()
    with pytest.raises(WindowError):
        pick(f, delay=delay)
    f.view.hide_studio.assert_not_called()


def test_native_registration_and_bridge_only_accept_first_explicit_result():
    first, second = Mock(), Mock()
    register_native_host(Mock(), first)
    assert native_available()
    unregister_native_host(second)
    assert native_available()
    unregister_native_host(first)
    assert not native_available()
    event = threading.Event()
    bridge = _SelectionBridge(event)
    bridge.finish({"crop": "first"})
    bridge.finish({"crop": "second"})
    assert bridge._payload == {"crop": "first"}
    assert not event.is_set()
    bridge = _SelectionBridge(event)
    bridge.cancel()
    bridge.finish({"crop": "late"})
    assert bridge._payload is None
    assert event.is_set()


def test_windows_hud_is_sized_and_positioned_in_physical_pixels(monkeypatch):
    from rpa_orkestrai.desktop.picker import NativePickerView

    hud = Mock()
    hud.events.loaded.wait.return_value = True
    webview = Mock()
    webview.screens = [SimpleNamespace(x=0, y=0)]
    webview.create_window.return_value = hud
    view = NativePickerView((webview, Mock()))
    geometry = Mock()
    monkeypatch.setattr('rpa_orkestrai.desktop.picker.platform.system', lambda: 'Windows')
    monkeypatch.setattr('rpa_orkestrai.desktop.picker._window_scale', lambda _: 1.5)
    monkeypatch.setattr('rpa_orkestrai.desktop.picker._windows_geometry', geometry)
    view.open_countdown(1920, 1080, threading.Event(), lambda: None)
    assert view.hud_bounds == (615, 865, 690, 165)
    geometry.assert_called_once_with(hud, 615, 865, 690, 165)
    view.move_countdown()
    assert view.hud_bounds == (615, 30, 690, 165)
    geometry.assert_called_with(hud, 615, 30, 690, 165)
    view.close_countdown()
    hud.destroy.assert_called_once()


def test_restore_only_shows_studio_preserving_windows_maximized_state():
    from rpa_orkestrai.desktop.picker import NativePickerView

    studio = Mock()
    view = NativePickerView((Mock(), studio))
    view.restore_studio()
    studio.show.assert_called_once()
    studio.restore.assert_not_called()


@pytest.mark.skipif(os.environ.get("RPA_UI_TESTS") != "1", reason="Opt-in Chromium overlay checks")
@pytest.mark.parametrize("mode, viewport", [
    ("image", {"width": 1280, "height": 800}),
    ("image_only", {"width": 853, "height": 533}),
])
def test_native_overlay_drag_point_flat_region_and_escape(mode, viewport):
    from rpa_orkestrai.desktop.picker import _png_data, overlay_html

    playwright = pytest.importorskip("playwright.sync_api")
    window = WindowInfo(12, 42, "ERP", "Fixture", 100, 80, 1000, 650)
    picture = Image.new("RGB", (1000, 650), "white")
    drawing = ImageDraw.Draw(picture)
    drawing.text((100, 250), "FormID", fill="black")
    drawing.rectangle((250, 245, 550, 275), outline="black")
    with playwright.sync_playwright() as runner:
        browser = runner.chromium.launch()
        page = browser.new_page(viewport=viewport)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.set_content(overlay_html(window, _png_data(picture), mode, (1280, 800)))
        page.evaluate("""window.results=[];window.cancelled=false;window.pywebview={api:{
            finish:async payload=>window.results.push(payload),cancel:()=>window.cancelled=true}};
            window.dispatchEvent(new Event('pywebviewready'));""")
        page.wait_for_function("picture.complete && picture.naturalWidth > 0")
        sx, sy = viewport["width"] / 1280, viewport["height"] / 800

        def drag(x1, y1, x2, y2):
            page.mouse.move(x1 * sx, y1 * sy)
            page.mouse.down()
            page.mouse.move(x2 * sx, y2 * sy, steps=5)
            page.mouse.up()

        drag(700, 400, 730, 440)
        assert "düz renk" in page.locator("#error").inner_text()
        assert page.locator("#confirm").is_disabled()
        drag(195, 325, 260, 352)
        if mode == "image":
            assert page.locator("#confirm").is_disabled()
            page.mouse.click(400 * sx, 340 * sy)
            assert page.locator("#confirm").is_enabled()
            # Refine the target without re-cropping the stable label.
            page.mouse.click(420 * sx, 340 * sy)
        assert page.locator("#confirm").is_enabled()
        page.locator("#confirm").click()
        payload = page.evaluate("window.results")
        assert len(payload) == 1
        assert payload[0]["crop"]["x"] in (94, 95)  # CSS viewport rounding at 150% scale
        if mode == "image":
            assert payload[0]["point"] == {"x": 320, "y": 260}
        else:
            assert "point" not in payload[0]
        page.keyboard.press("Escape")
        assert page.evaluate("window.cancelled")
        assert not errors
        browser.close()
