import io
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from rpa_orkestrai import gui
from rpa_orkestrai.instance import StartupError


@pytest.mark.parametrize('system,expected', [
    ('Windows', 'windows/RpaOrkestrAI/workspace'),
    ('Darwin', 'home/Library/Application Support/RpaOrkestrAI/workspace'),
])
def test_installed_app_workspace_is_outside_install_directory(monkeypatch, tmp_path, system, expected):
    monkeypatch.setattr(gui.platform, 'system', lambda: system)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path / 'home')
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'windows'))
    assert gui.default_workspace() == tmp_path / expected


def test_gui_handles_missing_console_and_uses_explicit_checkout_workspace(monkeypatch, tmp_path):
    from rpa_orkestrai import native

    previous_cwd = Path.cwd()
    observed = []
    def serve(settings, *, auto_port):
        assert auto_port is True
        observed.append(settings.data_dir)
        assert Path.cwd() == tmp_path
        assert isinstance(sys.stderr, io.TextIOBase)
        assert sys.stderr.isatty() is False
        print('No console required')
    monkeypatch.delenv('RPA_DATA_DIR', raising=False)
    monkeypatch.setattr(native, 'serve_native', serve)
    monkeypatch.setattr(sys, 'stdout', None)
    monkeypatch.setattr(sys, 'stderr', None)
    assert gui.main(workspace=tmp_path, argv=[]) == 0
    assert observed == [tmp_path / 'data']
    assert sys.stdout is None and sys.stderr is None
    assert Path.cwd() == previous_cwd
    assert 'No console required' in (tmp_path / 'logs/studio.log').read_text()
    assert (tmp_path / 'assets/templates').is_dir()


def test_gui_startup_error_is_visible_and_logged(monkeypatch, tmp_path):
    from rpa_orkestrai import native

    monkeypatch.setattr(native, 'serve_native', Mock(side_effect=StartupError('Bu port kullanimda.')))
    alert = Mock()
    monkeypatch.setattr(gui, 'show_error', alert)
    assert gui.main(workspace=tmp_path, argv=[]) == 1
    assert 'Bu port kullanimda.' in alert.call_args.args[0]
    assert str(tmp_path / 'logs/studio.log') in alert.call_args.args[0]
    assert 'StartupError' in (tmp_path / 'logs/studio.log').read_text()


def test_gui_failure_before_logging_still_displays_error(monkeypatch, tmp_path):
    blocker = tmp_path / 'not-a-directory'
    blocker.write_text('keep')
    alert = Mock()
    monkeypatch.setattr(gui, 'show_error', alert)
    assert gui.main(workspace=blocker, argv=[]) == 1
    alert.assert_called_once()
    assert blocker.read_text() == 'keep'


def test_gui_keeps_existing_workflows_and_settings(monkeypatch, tmp_path):
    from rpa_orkestrai import native

    data = tmp_path / 'data'
    data.mkdir()
    settings = data / 'settings.json'
    settings.write_text('{"ocr_language": "tur"}')
    workflow = data / 'untouched.json'
    workflow.write_text('{"name": "My flow"}')
    monkeypatch.delenv('RPA_DATA_DIR', raising=False)
    serve = Mock()
    monkeypatch.setattr(native, 'serve_native', serve)
    assert gui.main(workspace=tmp_path, argv=[]) == 0
    assert serve.call_args.args[0].get('ocr_language') == 'tur'
    assert settings.read_text() == '{"ocr_language": "tur"}'
    assert workflow.read_text() == '{"name": "My flow"}'


def test_source_shortcut_quotes_paths_and_does_not_interpolate_powershell(monkeypatch, tmp_path):
    import importlib.util

    script = Path(__file__).resolve().parents[1] / 'scripts/create_windows_shortcut.py'
    spec = importlib.util.spec_from_file_location('shortcut_builder', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "ERP's Studio $folder"
    (root / '.venv/Scripts').mkdir(parents=True)
    (root / '.venv/Scripts/pythonw.exe').touch()
    (root / 'launch_gui.pyw').touch()
    monkeypatch.setattr(module, '__file__', str(root / 'scripts/create_windows_shortcut.py'))
    monkeypatch.setattr(module, 'os', SimpleNamespace(name='nt', environ=dict(os.environ)))
    run = Mock()
    monkeypatch.setattr(module.subprocess, 'run', run)
    module.main()
    arguments = run.call_args.args[0]
    assert str(root) not in arguments[-1]
    assert run.call_args.kwargs['env']['RPA_SHORTCUT_ROOT'] == str(root)
    assert run.call_args.kwargs['env']['RPA_SHORTCUT_PYTHON'].endswith('pythonw.exe')


def test_update_handoff_exits_before_opening_workspace(monkeypatch, tmp_path):
    from rpa_orkestrai import native, update_service

    updater = Mock()
    updater.apply_pending.return_value = True
    monkeypatch.setattr(update_service, 'DesktopUpdates', Mock(return_value=updater))
    serve = Mock()
    monkeypatch.setattr(native, 'serve_native', serve)
    previous_cwd = Path.cwd()
    assert gui.main(workspace=tmp_path, argv=[]) == 0
    serve.assert_not_called()
    updater.start.assert_not_called()
    updater.stop.assert_called_once()
    assert Path.cwd() == previous_cwd
