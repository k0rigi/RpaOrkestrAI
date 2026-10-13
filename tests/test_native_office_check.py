"""The isolated package diagnostic never needs an account, vault, or external service."""

import http.client
import io
import json
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rpa_orkestrai import __version__, gui
from rpa_orkestrai import native_office_check as native
from scripts import check_native_office as runner


def browser_report():
    return {"checks": dict.fromkeys(native.CHECKS, True), "webgl_available": True, "draw_calls": 120, "errors": []}


@pytest.fixture
def fixture_server():
    fixture = native.OfficeFixture()
    server = native.fixture_server(fixture)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield fixture, server
    finally:
        server.shutdown()
        server.server_close()
        worker.join(3)


def request(server, method, path, body=None, headers=None):
    client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
    try:
        client.request(method, path, body, headers or {})
        response = client.getresponse()
        return response.status, dict(response.headers), response.read()
    finally:
        client.close()


def test_fixture_loads_actual_local_importmap_with_strict_csp_and_no_studio_app(fixture_server):
    fixture, server = fixture_server
    status, headers, data = request(server, "GET", "/")
    assert status == 200
    assert 'src="/app.js"' not in data.decode()
    assert 'src="/office.js"' in data.decode()
    assert "unsafe-eval" not in headers["Content-Security-Policy"]
    assert "unsafe-inline" not in headers["Content-Security-Policy"]
    assert headers["Content-Security-Policy"] == fixture.csp
    assert fixture.token in data.decode()
    for path, expected in [("/office.js", b"mountOffice"), ("/native-office-check.js", b"drawElements"),
                           ("/vendor/three/three.module.js", b"REVISION = '160'")]:
        assert expected in request(server, "GET", path)[2]
    assert request(server, "GET", "/api/agents/office")[0] == 404
    assert request(server, "GET", "/", headers={"Host": "attacker.test"})[0] == 403


@pytest.mark.parametrize("path", ["/../gui.py", "/%2e%2e/gui.py", "/..%5cgui.py", "/vendor/../office.js", "/index.html"])
def test_fixture_never_serves_workspace_or_non_static_files(path):
    assert native.OfficeFixture().asset(path) is None


def test_fixture_rejects_symlink_resources(tmp_path):
    (tmp_path / "index.html").write_text((native.STATIC / "index.html").read_text())
    target = tmp_path / "outside.js"
    target.write_text("private")
    link = tmp_path / "linked.js"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("Bu Windows hesabında sembolik bağlantı izni yok.")
    assert native.OfficeFixture(tmp_path).asset("/linked.js") is None


def test_report_needs_nonce_origin_and_is_single_use(fixture_server):
    fixture, server = fixture_server
    value = json.dumps(browser_report())
    headers = {"Content-Type": "application/json", "Origin": fixture.origin, "X-Office-Check": fixture.token}
    for change in [{"Origin": "https://attacker.test"}, {"X-Office-Check": "wrong"}, {"Host": "attacker.test"}]:
        assert request(server, "POST", "/__office_report", value, headers | change)[0] == 403
        assert not fixture.done.is_set()
    assert request(server, "POST", "/api/agents", value, headers)[0] == 403
    assert request(server, "POST", "/__office_report", value, headers)[0] == 204
    assert fixture.done.is_set() and fixture.browser_report == browser_report()
    assert request(server, "POST", "/__office_report", value, headers)[0] == 409


def test_report_rejects_large_and_malformed_bodies(fixture_server):
    fixture, server = fixture_server
    headers = {"Content-Type": "application/json", "Origin": fixture.origin, "X-Office-Check": fixture.token}
    assert request(server, "POST", "/__office_report", "x" * (native.BODY_LIMIT + 1), headers)[0] == 413
    assert request(server, "POST", "/__office_report", "{", headers)[0] == 400
    assert request(server, "POST", "/__office_report", '{"ok":true}', headers)[0] == 400
    assert not fixture.done.is_set()


@pytest.mark.parametrize("change", [{"draw_calls": True}, {"draw_calls": -1}, {"webgl_available": "yes"},
                                     {"errors": ["x" * 201]}, {"checks": {"three_rendered": True}}, {"other": 1}])
def test_browser_report_uses_bounded_strict_fields(change):
    with pytest.raises(ValueError):
        native.validate_browser_report(browser_report() | change)


def test_gui_diagnostic_bypasses_real_workspace_and_updater(monkeypatch, tmp_path):
    check = Mock(return_value=0)
    monkeypatch.setattr(native, "run_native_check", check)
    monkeypatch.setattr(gui, "default_workspace", Mock(side_effect=AssertionError("workspace")))
    report = tmp_path / "report.json"
    assert gui.main(argv=["--self-test-office", str(report)]) == 0
    check.assert_called_once_with(report.resolve())
    assert list(tmp_path.iterdir()) == []


def test_native_identity_checks_real_control_type_and_rejects_browser_fallback():
    control = SimpleNamespace(GetType=lambda: SimpleNamespace(FullName="Microsoft.Web.WebView2.WinForms.WebView2"),
                              CoreWebView2=object())
    window = SimpleNamespace(native=SimpleNamespace(webview=control))
    assert native.native_identity(window, "edgechromium", "Windows")["renderer"] == "edgechromium"
    with pytest.raises(RuntimeError):
        native.native_identity(window, "mshtml", "Windows")
    control.GetType = lambda: SimpleNamespace(FullName="System.Windows.Forms.WebBrowser")
    with pytest.raises(RuntimeError):
        native.native_identity(window, "edgechromium", "Windows")


def test_native_identity_requires_wkwebview_instance(monkeypatch):
    class WKWebView:
        pass
    monkeypatch.setitem(sys.modules, "WebKit", SimpleNamespace(WKWebView=WKWebView))
    window = SimpleNamespace(native=SimpleNamespace(contentView=lambda: WKWebView()))
    assert native.native_identity(window, "wkwebview", "Darwin")["native_type"] == "WebKit.WKWebView"
    window.native.contentView = lambda: object()
    with pytest.raises(RuntimeError):
        native.native_identity(window, "wkwebview", "Darwin")


@pytest.mark.parametrize("system,engine", [("Windows", "edgechromium"), ("Darwin", "cocoa")])
def test_native_window_uses_visible_real_engine_without_js_bridge(monkeypatch, tmp_path, system, engine):
    fixture = native.OfficeFixture()
    fixture.accept(browser_report())
    window = SimpleNamespace(destroy=Mock())
    webview = SimpleNamespace(create_window=Mock(return_value=window), renderer="checked",
                              start=Mock(side_effect=lambda function, **kwargs: function()))
    monkeypatch.setitem(sys.modules, "webview", webview)
    monkeypatch.setattr(native.platform, "system", lambda: system)
    monkeypatch.setattr(native, "native_identity", lambda *args: {"renderer": "checked"})
    native.open_native_fixture(fixture, tmp_path, 0.01)
    options = webview.create_window.call_args.kwargs
    assert options["hidden"] is False and options["minimized"] is False
    assert options["text_select"] is True
    assert "js_api" not in options
    assert webview.start.call_args.kwargs == {"gui": engine, "private_mode": True,
                                               "storage_path": str(tmp_path / "browser"), "debug": False}
    window.destroy.assert_called_once()


def test_native_timeout_closes_window_and_does_not_claim_engine_success(monkeypatch, tmp_path):
    fixture = native.OfficeFixture()
    window = SimpleNamespace(destroy=Mock())
    webview = SimpleNamespace(create_window=Mock(return_value=window), renderer="wkwebview",
                              start=Mock(side_effect=lambda function, **kwargs: function()))
    monkeypatch.setitem(sys.modules, "webview", webview)
    monkeypatch.setattr(native.platform, "system", lambda: "Darwin")
    native.open_native_fixture(fixture, tmp_path, 0.001)
    assert "süre sınırında" in fixture.error
    assert fixture.native == {}
    window.destroy.assert_called_once()


@pytest.mark.parametrize("fallback_only", [False, True])
def test_report_cannot_claim_native_3d_success_for_svg_only(monkeypatch, tmp_path, fallback_only):
    def run(fixture, folder, timeout):
        assert folder.is_dir() and str(folder).startswith(str(Path(folder).parent / "rpa-native-office-"))
        value = browser_report()
        if fallback_only:
            value["checks"]["three_rendered"] = False
            value["webgl_available"] = False
            value["draw_calls"] = 0
        fixture.accept(value)
        fixture.native = {"renderer": "wkwebview", "native_type": "WebKit.WKWebView"}
    monkeypatch.setattr(native, "open_native_fixture", run)
    report = tmp_path / "check.json"
    assert native.run_native_check(report) == (1 if fallback_only else 0)
    result = json.loads(report.read_text())
    assert result["ok"] is (not fallback_only)
    assert result["checks"]["svg_fallback"] is True
    assert result["version"] == __version__


def test_native_start_failure_writes_safe_report_and_closes_server(monkeypatch, tmp_path):
    monkeypatch.setattr(native, "open_native_fixture", Mock(side_effect=RuntimeError("private-do-not-log")))
    report = tmp_path / "check.json"
    assert native.run_native_check(report) == 1
    assert "private-do-not-log" not in report.read_text()
    assert json.loads(report.read_text())["ok"] is False


def test_browser_success_without_verified_native_engine_is_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(native, "open_native_fixture", lambda fixture, *_: fixture.accept(browser_report()))
    report = tmp_path / "check.json"
    assert native.run_native_check(report) == 1
    assert json.loads(report.read_text())["renderer"] is None


@pytest.mark.parametrize("change", [{}, {"frozen": False}, {"renderer": "chromium"}, {"version": "0.0.1"},
                                     {"checks": {"three_rendered": True}}, {"draw_calls": 0}])
def test_ci_wrapper_requires_complete_frozen_matching_native_report(monkeypatch, tmp_path, change):
    executable = tmp_path / "app.exe"
    executable.touch()
    report = tmp_path / "report.json"
    value = browser_report() | {"ok": True, "frozen": True, "version": __version__, "platform": "windows-x64",
                                "renderer": "edgechromium", "native_type": "Microsoft.Web.WebView2.WinForms.WebView2"}
    value.update(change)
    def launch(command, **kwargs):
        assert command == [str(executable), "--self-test-office", str(report)]
        assert kwargs == {"timeout": 120, "check": False}
        report.write_text(json.dumps(value))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(runner.platform, "system", lambda: "Windows")
    monkeypatch.setattr(runner.subprocess, "run", launch)
    if change:
        with pytest.raises(ValueError):
            runner.check(executable, report)
    else:
        runner.check(executable, report)


@pytest.mark.parametrize("failed", [False, True])
def test_ci_wrapper_prints_turkish_with_windows_ansi_redirected_streams(monkeypatch, failed):
    output, errors = io.BytesIO(), io.BytesIO()
    stdout = io.TextIOWrapper(output, encoding="cp1252", errors="strict", write_through=True)
    stderr = io.TextIOWrapper(errors, encoding="cp1252", errors="strict", write_through=True)
    monkeypatch.setattr(runner.sys, "stdout", stdout)
    monkeypatch.setattr(runner.sys, "stderr", stderr)
    monkeypatch.setattr(runner.sys, "argv", ["check_native_office.py", "app.exe", "report.json"])
    check = Mock(side_effect=ValueError("private-error") if failed else None)
    monkeypatch.setattr(runner, "check", check)
    if failed:
        with pytest.raises(SystemExit) as caught:
            runner.main()
        assert caught.value.code == 1
        assert "başarısız oldu" in errors.getvalue().decode("utf-8")
        assert "private-error" not in errors.getvalue().decode("utf-8")
        assert output.getvalue() == b""
    else:
        assert runner.main() == 0
        assert output.getvalue().decode("utf-8").splitlines() == ["Paket içindeki yerel ofis ve 3D çizim doğrulandı."]
        assert errors.getvalue() == b""
    check.assert_called_once_with(Path("app.exe"), Path("report.json"))


@pytest.mark.skipif(os.environ.get("RPA_UI_TESTS") != "1", reason="İsteğe bağlı ağsız tanılama sayfası testi")
def test_actual_diagnostic_js_completes_with_real_local_office(fixture_server):
    fixture, _server = fixture_server
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        browser = runtime.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1280, "height": 960})
        outside = []
        def route_request(route):
            if not route.request.url.startswith(fixture.origin + "/"):
                outside.append(route.request.url)
                route.abort()
            else:
                route.continue_()
        page.route("**/*", route_request)
        page.goto(fixture.origin, wait_until="load")
        page.locator("html[data-native-office-check='done']").wait_for(timeout=25000)
        assert fixture.done.is_set()
        browser.close()
    assert outside == []
    assert fixture.browser_report["errors"] == []
    assert all(fixture.browser_report["checks"].values()), fixture.browser_report
    assert fixture.browser_report["draw_calls"] > 0
