"""Mouse, keyboard, window, screen, system, file, dialog and HTTP steps with fakes (no real input)."""

import json
import platform
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image, ImageDraw

from rpa_orkestrai.config import Settings
from rpa_orkestrai.desktop.windows import WindowInfo
from rpa_orkestrai.engine import Executor, WorkflowError
from rpa_orkestrai.models import Run, Step, Workflow
from rpa_orkestrai.storage import Store


@pytest.fixture
def runner(tmp_path):
    settings = Settings(tmp_path / "data", dotenv=False)
    settings.update({"template_dir": str(tmp_path / "templates")})
    store = Store(settings.data_dir)
    run = Run(workflow_id="0" * 32, workflow_name="Test", department="Genel")
    executor = Executor(settings, store, run, threading.Event(), lambda: store.save_run(run))
    executor._desktop = Mock()
    executor._desktop.modifier = "command" if platform.system() == "Darwin" else "ctrl"
    return executor


def go(runner, action, **params):
    runner.execute(Workflow(steps=[Step(action=action, params=params)]))
    return runner.variables


# ----- mouse and keyboard ----------------------------------------------------------------
def test_mouse_steps_use_primary_screen_coordinates(runner):
    desktop = runner._desktop
    go(runner, "input.mouse_click", x=120, y="45", button="right", clicks=2)
    desktop.click.assert_called_once_with(120.0, 45.0, clicks=2, button="right")
    go(runner, "input.mouse_move", x=5, y=6, duration=0)
    desktop.move.assert_called_once_with(5.0, 6.0, duration=0.0)
    go(runner, "input.drag", from_x=1, from_y=2, to_x=300, to_y=400, button="left", duration=0.3)
    desktop.drag.assert_called_once_with(1.0, 2.0, 300.0, 400.0, button="left", duration=0.3)
    go(runner, "input.scroll", amount=-3, direction="horizontal", x=10, y=20)
    desktop.hscroll.assert_called_once_with(-3, x=10, y=20)
    desktop.position.return_value = (7, 8)
    assert go(runner, "input.mouse_position", output="mouse")["mouse"] == {"x": 7, "y": 8}


@pytest.mark.parametrize("action,params", [
    ("input.mouse_click", {"x": -1, "y": 0}), ("input.mouse_click", {"x": 1, "y": 1, "button": "side"}),
    ("input.mouse_click", {"x": 1, "y": 1, "clicks": 4}), ("input.scroll", {"amount": 5, "x": 10}),
    ("input.drag", {"from_x": 1, "from_y": 1, "to_x": None, "to_y": 1}),
])
def test_invalid_mouse_parameters_never_move_the_mouse(runner, action, params):
    with pytest.raises(WorkflowError):
        go(runner, action, **params)
    assert not runner._desktop.method_calls


def test_off_screen_point_is_reported_in_turkish(runner):
    runner._desktop.click.side_effect = ValueError("outside")
    with pytest.raises(WorkflowError, match="ana ekranın dışında"):
        go(runner, "input.mouse_click", x=99999, y=5)


def test_typing_pastes_turkish_text_and_types_ascii(runner):
    go(runner, "input.type", text="Çağrı Öztürk", method="auto")
    runner._desktop.paste.assert_called_once_with("Çağrı Öztürk")
    go(runner, "input.type", text="INV-42", method="auto", interval=0)
    runner._desktop.write.assert_called_once_with("INV-42", interval=0.0)
    with pytest.raises(WorkflowError, match="Türkçe"):
        go(runner, "input.type", text="ş", method="type")


def test_hotkeys_and_key_presses(runner):
    go(runner, "input.hotkey", keys="Mod + Shift + S")
    runner._desktop.hotkey.assert_called_once_with("mod", "shift", "s")
    go(runner, "input.hotkey", keys="ctrl+alt+delete")
    go(runner, "input.press", key="tab", presses=3, interval=0)
    assert runner._desktop.press.call_count == 3
    with pytest.raises(WorkflowError, match="Tanınmayan tuş"):
        go(runner, "input.hotkey", keys="ctrl+uzay")
    with pytest.raises(WorkflowError, match="1–5"):
        go(runner, "input.hotkey", keys="a+b+c+d+e+f")


# ----- windows -----------------------------------------------------------------------------
@pytest.fixture
def window():
    return WindowInfo(77, 42, "ERP", "İade Faturası", 100, 80, 800, 600)


def test_window_management_steps(runner, window):
    windows = Mock()
    windows.activate.return_value = window.result()
    windows.move_resize.return_value = window.result()
    runner._windows = windows
    target = window.result()
    go(runner, "window.activate", window=target)
    windows.activate.assert_called_once_with(target)
    go(runner, "window.state", window=target, state="maximize")
    windows.set_state.assert_called_once_with(target, "maximize")
    go(runner, "window.move", window=target, x=0, y=0, width=1280, height=800, output="erp_window")
    windows.move_resize.assert_called_once_with(target, 0, 0, 1280, 800)
    go(runner, "window.close", window=target)
    go(runner, "window.wait_close", window=target, timeout=5)
    windows.wait_closed.assert_called_once_with(target, 5.0)
    with pytest.raises(WorkflowError, match="Pencereyi tanı"):
        go(runner, "window.activate", window={"found": False})


def test_read_field_passes_the_structural_target(runner, window):
    windows = Mock()
    windows.read_field.return_value = "INV-7"
    runner._windows = windows
    element = {"platform": platform.system(), "role": "Edit", "automation_id": "txtFormId", "name": "", "index": 0}
    result = go(runner, "window.read_field", window=window.result(), target_mode="element", element=element,
                timeout=3, output="value")
    assert result["value"] == "INV-7"
    assert windows.read_field.call_args.kwargs == {"target_mode": "element", "element": element, "timeout": 3}


def test_window_backend_operations_are_platform_specific(window):
    from rpa_orkestrai.desktop.windows import WindowError, WindowService

    backend = SimpleNamespace(list_windows=Mock(return_value=[window]), activate=Mock(), is_active=Mock(return_value=True),
                              set_state=Mock(), move_resize=Mock(), close=Mock())
    service = WindowService(backend=backend)
    service.set_state(window.result(), "minimize")
    backend.set_state.assert_called_once()
    service.move_resize(window.result(), 10, 20, 900, 700)
    backend.move_resize.assert_called_once_with(window, 10, 20, 900, 700)
    with pytest.raises(WindowError):
        service.move_resize(window.result(), 10, 20, 50, 700)
    service.close(window.result())
    backend.close.assert_called_once_with(window)
    backend.list_windows.return_value = []
    service.wait_closed(window.result(), 1)
    with pytest.raises(WindowError, match="başka bir işletim"):
        service.set_state({**window.result(), "platform": "Other"}, "restore")


# ----- screen ------------------------------------------------------------------------------
def screen_with_button():
    image = Image.new("RGB", (400, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((150, 100, 230, 130), fill="navy")
    draw.text((160, 108), "KAYDET", fill="white")
    return image


def save_template(runner, image):
    folder = runner.store.root.parent / "templates"
    folder.mkdir(exist_ok=True)
    image.crop((150, 100, 231, 131)).save(folder / "kaydet.png")
    return "kaydet.png"


def test_find_and_click_image_on_screen(runner):
    screen = screen_with_button()
    runner._desktop.screenshot.return_value = screen
    template = save_template(runner, screen)
    found = go(runner, "screen.find_image", template=template, timeout=0, output="image")["image"]
    assert found["found"] is True and (found["x"], found["y"]) == (150, 100)
    go(runner, "screen.click_image", template=template, timeout=0, offset_x=10, clicks=2)
    runner._desktop.click.assert_called_once_with(found["center_x"] + 10, found["center_y"], clicks=2, button="left")
    runner._desktop.screenshot.return_value = Image.new("RGB", (400, 300), "white")
    missing = go(runner, "screen.find_image", template=template, timeout=0, on_missing="continue", output="image")
    assert missing["image"] == {"found": False}
    with pytest.raises(WorkflowError, match="bulunamadı"):
        go(runner, "screen.click_image", template=template, timeout=0)


def test_screen_region_can_follow_a_window(runner, window):
    screen = screen_with_button()
    windows = Mock()
    windows.screenshot_window.return_value = (window, screen)
    runner._windows = windows
    template = save_template(runner, screen)
    found = go(runner, "screen.find_image", template=template, timeout=0, relative_to="window",
               window=window.result(), region=[100, 50, 250, 200], output="image")["image"]
    # Window origin (100, 80) + region origin (100, 50) + match inside region (50, 50).
    assert (found["x"], found["y"]) == (250, 180)


def test_ocr_steps_use_the_system_engine(runner, monkeypatch):
    runner._desktop.screenshot.return_value = Image.new("RGB", (200, 100), "white")
    monkeypatch.setattr("rpa_orkestrai.desktop.ocr.read_text", lambda image, **kwargs: "Kayıt  BAŞARIYLA\ntamamlandı")
    assert go(runner, "screen.read_text", region=[0, 0, 200, 100], output="t")["t"].startswith("Kayıt")
    assert go(runner, "screen.wait_text", text="kayıt başarıyla", timeout=0, output="ok")["ok"] is True
    assert go(runner, "screen.wait_text", text="Hata", timeout=0, on_missing="continue", output="ok")["ok"] is False
    with pytest.raises(WorkflowError, match="görünmedi"):
        go(runner, "screen.wait_text", text="Hata", timeout=0, on_missing="stop", output="ok")


def test_pixel_and_screenshot_artifact(runner, tmp_path):
    runner._desktop.pixel.return_value = (255, 128, 0)
    assert go(runner, "screen.pixel", x=1, y=2, output="color")["color"] == "#FF8000"
    runner._desktop.screenshot.return_value = Image.new("RGB", (50, 40), "red")
    saved = go(runner, "screen.screenshot", filename="hata", folder=str(tmp_path / "shots"), output="p")["p"]
    assert saved.endswith("hata.png") and Image.open(saved).size == (50, 40)
    assert runner.run.artifacts[-1].name == "hata.png"


def test_native_ocr_reads_turkish_text_on_macos():
    if platform.system() != "Darwin":
        pytest.skip("macOS Vision OCR")
    pytest.importorskip("Vision")
    from PIL import ImageFont

    from rpa_orkestrai.desktop.ocr import read_text

    candidates = ["/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf"]
    font_path = next((path for path in candidates if __import__("os").path.exists(path)), None)
    if font_path is None:
        pytest.skip("Arial font")
    image = Image.new("RGB", (900, 120), "white")
    ImageDraw.Draw(image).text((20, 30), "Şirket: Çağdaş Lojistik Ödeme", fill="black",
                               font=ImageFont.truetype(font_path, 40))
    assert "Çağdaş Lojistik" in read_text(image, engine="system")


def test_native_ocr_reads_text_on_windows():
    if platform.system() != "Windows":
        pytest.skip("Windows.Media.Ocr")
    from PIL import ImageFont

    from rpa_orkestrai.desktop.ocr import read_text

    image = Image.new("RGB", (900, 120), "white")
    ImageDraw.Draw(image).text((20, 30), "Invoice INV 2026 approved", fill="black",
                               font=ImageFont.truetype("arial.ttf", 40))
    assert "INV" in read_text(image, engine="system").upper()


# ----- system -----------------------------------------------------------------------------
def test_command_captures_output_and_errors(runner):
    result = go(runner, "system.command", command="echo merhaba", output="command")["command"]
    assert result["code"] == 0 and "merhaba" in result["output"]
    with pytest.raises(WorkflowError, match="hata koduyla"):
        go(runner, "system.command", command="exit 3", output="command")
    failed = go(runner, "system.command", command="exit 3", fail_on_error=False, output="command")["command"]
    assert failed["code"] == 3


def test_open_uses_the_platform_launcher(runner, monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: calls.append(command) or
                        SimpleNamespace(returncode=0))
    monkeypatch.setattr(subprocess, "Popen", lambda command, **kwargs: calls.append(command))
    import os

    monkeypatch.setattr(os, "startfile", lambda target: calls.append(["startfile", target]), raising=False)
    go(runner, "system.open", target="https://orkestrai.net", wait=0)
    if platform.system() == "Darwin":
        assert calls[-1] == ["/usr/bin/open", "https://orkestrai.net"]
        go(runner, "system.open", target="TextEdit", arguments="--new", wait=0)
        assert calls[-1] == ["/usr/bin/open", "-a", "TextEdit", "--args", "--new"]
    elif platform.system() == "Windows":
        assert calls[-1] == ["startfile", "https://orkestrai.net"]


def test_close_app_rejects_paths_and_quotes(runner):
    with pytest.raises(WorkflowError, match="yol veya tırnak"):
        go(runner, "system.close_app", application='x" & rm')


def test_clipboard_steps(runner, monkeypatch):
    import pyperclip

    store = {"value": ""}
    monkeypatch.setattr(pyperclip, "copy", lambda value: store.update(value=value))
    monkeypatch.setattr(pyperclip, "paste", lambda: store["value"])
    go(runner, "clipboard.set", value="Şube 42")
    assert go(runner, "clipboard.get", output="clip")["clip"] == "Şube 42"


# ----- dialogs ------------------------------------------------------------------------------
def test_message_and_input_boxes(runner, monkeypatch):
    if platform.system() == "Darwin":
        answers = iter([SimpleNamespace(returncode=0, stdout="Evet\n", stderr=""),
                        SimpleNamespace(returncode=0, stdout="ok:INV-9\n", stderr=""),
                        SimpleNamespace(returncode=1, stdout="", stderr="execution error: User canceled. (-128)")])
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: next(answers))
    elif platform.system() == "Windows":
        import ctypes

        monkeypatch.setattr(ctypes.windll.user32, "MessageBoxW", lambda *args: 6)
        answers = iter([SimpleNamespace(returncode=0, stdout="ok:INV-9".encode(), stderr=b""),
                        SimpleNamespace(returncode=0, stdout=b"cancel", stderr=b"")])
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: next(answers))
    else:
        pytest.skip("native dialogs")
    assert go(runner, "ui.message", text="Devam?", buttons="yes_no", output="answer")["answer"] == "yes"
    assert go(runner, "ui.input", prompt="Fatura no?", output="value")["value"] == "INV-9"
    with pytest.raises(WorkflowError, match="iptal"):
        go(runner, "ui.input", prompt="Fatura no?", output="value")


# ----- files ------------------------------------------------------------------------------
def test_text_files_and_folders(runner, tmp_path):
    log = tmp_path / "klasör" / "günlük.txt"
    go(runner, "file.write_text", path=str(log), text="ilk satır", mode="append")
    go(runner, "file.write_text", path=str(log), text="ikinci", mode="append")
    assert go(runner, "file.read_text", path=str(log), output="t")["t"] == "ilk satır\nikinci"
    assert go(runner, "file.exists", path=str(log), kind="file", output="e")["e"] is True
    assert go(runner, "file.exists", path=str(log), kind="folder", output="e")["e"] is False
    (tmp_path / "klasör" / "fatura_2.pdf").write_text("x")
    listed = go(runner, "file.list", folder=str(tmp_path / "klasör"), pattern="*.PDF", output="files")["files"]
    assert [item["name"] for item in listed] == ["fatura_2.pdf"]
    copied = go(runner, "file.operation", operation="copy", source=str(log), destination=str(tmp_path / "yedek"))
    assert (tmp_path / "yedek").is_file() and copied
    with pytest.raises(WorkflowError, match="aynı adlı"):
        go(runner, "file.operation", operation="copy", source=str(log), destination=str(tmp_path / "yedek"))
    go(runner, "file.operation", operation="move", source=str(tmp_path / "yedek"), destination=str(tmp_path / "taşındı.txt"))
    go(runner, "file.operation", operation="delete", source=str(tmp_path / "taşındı.txt"))
    assert not (tmp_path / "taşındı.txt").exists()
    with pytest.raises(WorkflowError, match="bulunamadı"):
        go(runner, "file.read_text", path=str(tmp_path / "yok.txt"), output="t")


def test_wait_for_download(runner, tmp_path):
    (tmp_path / "rapor_1.xlsx.crdownload").write_text("partial")
    (tmp_path / "rapor_1.xlsx").write_text("done")
    assert go(runner, "file.wait", path=str(tmp_path / "rapor_*.xlsx"), timeout=2, output="f")["f"].endswith("rapor_1.xlsx")
    with pytest.raises(WorkflowError, match="oluşmadı"):
        go(runner, "file.wait", path=str(tmp_path / "yok*.xlsx"), timeout=0, output="f")


def test_excel_and_csv_round_trip(runner, tmp_path):
    rows = [{"Fatura": "INV-1", "Tutar": 1250.5, "Not": "=HACK()"}, {"Fatura": "INV-2", "Tutar": 10, "Not": ""}]
    book = tmp_path / "çıktı" / "faturalar.xlsx"
    go(runner, "file.write_table", rows=rows, path=str(book), sheet="Liste")
    go(runner, "file.write_table", rows=[{"Fatura": "INV-3", "Tutar": 7, "Yeni": "x"}], path=str(book),
       sheet="Liste", mode="append")
    read = go(runner, "file.read_table", path=str(book), sheet="Liste", output="rows")["rows"]
    assert [row["Fatura"] for row in read] == ["INV-1", "INV-2", "INV-3"]
    assert read[0]["Tutar"] == 1250.5 and read[0]["Not"] == "'=HACK()"
    assert read[2]["Yeni"] == "x" and read[0]["row_number"] == 2
    with pytest.raises(WorkflowError, match="sayfası yok"):
        go(runner, "file.read_table", path=str(book), sheet="Yok", output="rows")

    csv_file = tmp_path / "liste.csv"
    csv_file.write_text("No;Ürün;Adet\n1;Çay;3\n\n2;Şeker;5\n", encoding="utf-8")
    parsed = go(runner, "file.read_table", path=str(csv_file), output="rows")["rows"]
    assert parsed == [{"No": "1", "Ürün": "Çay", "Adet": "3", "row_number": 2},
                      {"No": "2", "Ürün": "Şeker", "Adet": "5", "row_number": 4}]
    go(runner, "file.write_table", rows=parsed, path=str(tmp_path / "kopya.csv"))
    assert "Ürün" in (tmp_path / "kopya.csv").read_text(encoding="utf-8-sig")


# ----- HTTP ------------------------------------------------------------------------------
@pytest.fixture
def api_server():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self.respond(404 if self.path == "/missing" else 200, {"path": self.path})

        def do_POST(self):
            length = int(self.headers["Content-Length"])
            self.respond(201, {"received": json.loads(self.rfile.read(length)), "auth": self.headers["Authorization"]})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_http_requests(runner, api_server):
    response = go(runner, "http.request", method="POST", url=api_server + "/siparis",
                  headers={"Authorization": "Bearer x"}, body={"no": "INV-1"}, output="response")["response"]
    assert response == {"status": 201, "ok": True, "body": {"received": {"no": "INV-1"}, "auth": "Bearer x"}}
    with pytest.raises(WorkflowError, match="404"):
        go(runner, "http.request", url=api_server + "/missing", output="response")
    assert go(runner, "http.request", url=api_server + "/missing", fail_on_error=False,
              output="response")["response"]["status"] == 404
    with pytest.raises(WorkflowError, match="http"):
        go(runner, "http.request", url="ftp://x", output="response")


def test_system_variables_point_to_real_user_folders():
    from pathlib import Path

    from rpa_orkestrai.actions.environment import system_variables

    values = system_variables()
    assert values["isletim_sistemi"] in {"macOS", "Windows", "Linux"}
    assert Path(values["ev"]).is_dir()
    if platform.system() in {"Windows", "Darwin"}:
        assert Path(values["masaustu"]).is_dir() and Path(values["belgeler"]).is_dir()


def test_native_ocr_works_from_a_workflow_thread_on_windows():
    if platform.system() != "Windows":
        pytest.skip("Windows.Media.Ocr")
    from PIL import ImageFont

    from rpa_orkestrai.desktop.ocr import read_text

    image = Image.new("RGB", (900, 120), "white")
    ImageDraw.Draw(image).text((20, 30), "Invoice INV 2026 approved", fill="black",
                               font=ImageFont.truetype("arial.ttf", 40))
    results = []
    worker = threading.Thread(target=lambda: results.append(read_text(image, engine="system")))
    worker.start()
    worker.join(60)
    assert results and "INV" in results[0].upper()


def test_command_output_decodes_turkish_text(runner):
    command = "echo Çağrı Şule" if platform.system() == "Windows" else "printf 'Çağrı Şule'"
    assert "Çağrı Şule" in go(runner, "system.command", command=command, output="c")["c"]["output"]
