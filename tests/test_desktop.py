from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rpa_orkestrai.desktop import DesktopController, DialogDetector, DialogRule, DropdownIterator, Vision
from rpa_orkestrai.desktop.dropdown import DropdownScanLimitError
from rpa_orkestrai.desktop.vision import Match


def test_desktop_bounds_shortcut_and_cancel_do_not_touch_real_screen(monkeypatch):
    controller = DesktopController()
    backend = Mock()
    backend.size.return_value = (1280, 800)
    controller._backend = backend
    with pytest.raises(ValueError):
        controller.click(1280, 10)
    backend.click.assert_not_called()
    monkeypatch.setattr("rpa_orkestrai.desktop.controller.sys.platform", "darwin")
    controller.hotkey("mod", "a")
    backend.hotkey.assert_called_once_with("command", "a")
    assert backend.FAILSAFE is True
    controller.cancel_check = lambda: True
    with pytest.raises(InterruptedError):
        controller.click(10, 10)
    backend.click.assert_not_called()


def test_retina_screenshot_normalizes_before_crop():
    image = Mock()
    image.size = (2560, 1600)
    backend = Mock()
    backend.size.return_value = (1280, 800)
    backend.screenshot.return_value = image
    controller = DesktopController()
    controller._backend = backend
    controller.screenshot((10, 20, 100, 60))
    image.resize.assert_called_once_with((1280, 800))
    image.resize.return_value.crop.assert_called_once_with((10, 20, 110, 80))


def test_template_matches_offset_back_to_screen_coordinates(monkeypatch):
    controller = DesktopController()
    monkeypatch.setattr(controller, "screenshot", Mock(return_value="image"))
    monkeypatch.setattr(Vision, "match_template", Mock(return_value=Match(5, 8, 20, 10, 0.96)))
    result = controller.find_template("button.png", region=(100, 200, 300, 100))
    assert result.center == (115, 213)


def test_template_wait_is_bounded_without_real_sleep(monkeypatch):
    controller = DesktopController()
    monkeypatch.setattr(controller, "find_template", Mock(return_value=None))
    monkeypatch.setattr("rpa_orkestrai.desktop.controller.time.monotonic", Mock(side_effect=[0, 2]))
    with pytest.raises(TimeoutError):
        controller.wait_for_template("missing.png", timeout=1)


def test_dropdown_scans_overlapping_pages_then_stops_when_stable():
    pages = iter([[" Ankara ", "İzmir"], ["İzmir", "Bursa"], ["Bursa"], ["Bursa"], ["Bursa"]])
    scroll = Mock()
    result = DropdownIterator().scan(lambda: next(pages), scroll, max_scrolls=8, settle_seconds=0)
    assert result == ["Ankara", "İzmir", "Bursa"]
    assert scroll.call_count == 4


def test_dropdown_cap_is_visible_instead_of_silently_truncating():
    pages = iter([["A"], ["B"], ["C"]])
    with pytest.raises(DropdownScanLimitError) as failure:
        DropdownIterator().scan(lambda: next(pages), lambda: None, max_scrolls=2, settle_seconds=0)
    assert failure.value.values == ["A", "B", "C"]


def test_dropdown_selects_before_processing_and_propagates_failsafe():
    calls = []
    iterator = DropdownIterator()
    result = iterator.iterate(
        ["A", "A", "B"], lambda value: calls.append(("select", value)),
        lambda value: calls.append(("process", value)),
    )
    assert [item.value for item in result] == ["A", "B"]
    assert calls == [("select", "A"), ("process", "A"), ("select", "B"), ("process", "B")]
    failsafe = type("FailSafeException", (Exception,), {})
    with pytest.raises(failsafe):
        iterator.iterate(["A"], Mock(side_effect=failsafe()), Mock(), continue_on_error=True)


def test_dialog_uses_priority_and_dispatches_only_registered_handlers(monkeypatch):
    controller = SimpleNamespace(screenshot=Mock(return_value="image"))
    monkeypatch.setattr(Vision, "read_text", Mock(return_value="Onay bekleniyor. HATA: İşlem başarısız."))
    detector = DialogDetector(controller, [
        DialogRule("approval", "approve", contains=("onay",), priority=1),
        DialogRule("failure", "stop", contains=("hata",), priority=10),
    ])
    approve, stop = Mock(), Mock(return_value="stopped")
    assert detector.dispatch({"approve": approve, "stop": stop}) == "stopped"
    approve.assert_not_called()
    stop.assert_called_once()
    with pytest.raises(KeyError):
        detector.dispatch({"approve": approve})


def test_unknown_dialog_only_calls_explicit_default(monkeypatch):
    controller = SimpleNamespace(screenshot=Mock(return_value="image"))
    monkeypatch.setattr(Vision, "read_text", Mock(return_value="Tanımsız pencere"))
    detector = DialogDetector(controller, [DialogRule("approval", "approve", contains=("onay",))])
    handler = Mock()
    assert detector.dispatch({"approve": handler}) is None
    handler.assert_not_called()
    assert detector.dispatch({"approve": handler}, default=lambda: "paused") == "paused"


def test_template_algorithm_finds_synthetic_image_and_rejects_flat_templates():
    np = pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    random = np.random.default_rng(123)
    template = random.integers(0, 255, (10, 12), dtype=np.uint8)
    image = np.zeros((80, 100), dtype=np.uint8)
    image[25:35, 40:52] = template
    found = Vision.match_template(image, template, threshold=0.99)
    assert found is not None and found.center == (46, 30)
    with pytest.raises(ValueError, match="flat color"):
        Vision.match_template(image, np.zeros((10, 10), dtype=np.uint8))
