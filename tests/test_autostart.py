"""Bilgisayar açılınca Studio'yu başlat: the login item of the installed app on macOS and Windows."""

import platform
import plistlib
import sys
from uuid import uuid4

import pytest

from rpa_orkestrai import autostart


def test_running_from_source_offers_no_login_item(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    status = autostart.status()
    assert (status["supported"], status["enabled"]) == (False, False) and "kurulu" in status["reason"]
    with pytest.raises(RuntimeError, match="kurulu"):
        autostart.set_enabled(True)


def test_macos_agent_opens_the_installed_app_minimized_at_login(tmp_path, monkeypatch):
    app = tmp_path / "Applications" / "RpaOrkestrAI.app"
    executable = app / "Contents" / "MacOS" / "RpaOrkestrAI"
    executable.parent.mkdir(parents=True)
    executable.touch()
    assert autostart.app_bundle(str(executable)) == app.resolve()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(autostart.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(autostart.Path, "home", lambda: tmp_path)
    assert autostart.status() == {"supported": True, "enabled": False, "reason": None}
    assert autostart.set_enabled(True)["enabled"] is True
    agent = tmp_path / "Library" / "LaunchAgents" / "net.orkestrai.rpa.studio.plist"
    data = plistlib.loads(agent.read_bytes())
    # open -a starts it the way Finder does, so the app keeps its Accessibility and Screen Recording permissions.
    assert data["ProgramArguments"] == ["/usr/bin/open", "-a", str(app.resolve()), "--args", "--minimized"]
    assert (data["Label"], data["RunAtLoad"], data["LimitLoadToSessionType"]) == (
        "net.orkestrai.rpa.studio", True, "Aqua")
    assert autostart.set_enabled(False)["enabled"] is False and not agent.exists()
    assert autostart.set_enabled(False)["enabled"] is False


@pytest.mark.parametrize("executable", [
    "/Volumes/RpaOrkestrAI/RpaOrkestrAI.app/Contents/MacOS/RpaOrkestrAI",
    "/private/var/folders/x/T/AppTranslocation/ABC/d/RpaOrkestrAI.app/Contents/MacOS/RpaOrkestrAI",
])
def test_an_app_that_is_not_installed_is_not_registered(executable):
    # At the next login the disk image or the quarantine copy is gone.
    with pytest.raises(RuntimeError, match="Uygulamalar klasörüne"):
        autostart.app_bundle(executable)


def test_windows_command_starts_the_installed_exe_minimized():
    assert autostart.windows_command(r"C:\Users\Ayşe\AppData\Local\Programs\RpaOrkestrAI\RpaOrkestrAI.exe") == (
        '"C:\\Users\\Ayşe\\AppData\\Local\\Programs\\RpaOrkestrAI\\RpaOrkestrAI.exe" --minimized')


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows kayıt defteri yalnız Windows'ta var")
def test_windows_run_value_is_written_read_and_removed():
    name = f"RpaOrkestrAI Test {uuid4().hex[:8]}"
    command = autostart.windows_command(r"C:\Program Files\RpaOrkestrAI\RpaOrkestrAI.exe")
    try:
        autostart.write_run_value(command, name)
        assert autostart.read_run_value(name) == command
    finally:
        autostart.delete_run_value(name)
    assert autostart.read_run_value(name) is None
    autostart.delete_run_value(name)  # already gone: nothing to do


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows kayıt defteri yalnız Windows'ta var")
def test_windows_login_item_follows_the_setting(monkeypatch, tmp_path):
    executable = tmp_path / "RpaOrkestrAI.exe"
    executable.touch()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    previous = autostart.read_run_value()
    try:
        assert autostart.set_enabled(True)["enabled"] is True
        assert autostart.read_run_value() == f'"{executable}" --minimized'
        assert autostart.set_enabled(False)["enabled"] is False
        assert autostart.read_run_value() is None
    finally:
        if previous is not None:
            autostart.write_run_value(previous)


@pytest.mark.parametrize("system, program", [
    ("Darwin", "RpaOrkestrAI.app/Contents/MacOS/RpaOrkestrAI"),
    ("Windows", "RpaOrkestrAI/RpaOrkestrAI.exe"),
])
def test_package_check_finds_the_program_without_registering_it(monkeypatch, tmp_path, system, program):
    from rpa_orkestrai import package_check

    executable = tmp_path / program
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(autostart.platform, "system", lambda: system)
    monkeypatch.setattr(autostart.Path, "home", lambda: tmp_path / "home")
    package_check._check_login_item()
    assert not (tmp_path / "home").exists()
