"""Exercise Windows batch failure paths without network installs or desktop access."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows cmd.exe integration")
ROOT = Path(__file__).resolve().parents[1]


def launch(script: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", str(script), "--no-pause"],
        cwd=script.parent, capture_output=True, text=True, errors="replace", timeout=45,
    )


@pytest.fixture
def checkout(tmp_path):
    folder = tmp_path / "Studio test directory"
    folder.mkdir()
    for name in ("setup-windows.bat", "start.bat", "start-browser.bat"):
        shutil.copyfile(ROOT / name, folder / name)
    (folder / "pyproject.toml").write_text("# No package installation is performed in these tests.\n")
    return folder


@pytest.mark.parametrize("script", ["start.bat", "start-browser.bat"])
def test_missing_environment_explains_setup_and_returns_failure(checkout, script):
    result = launch(checkout / script)
    assert result.returncode == 1
    assert "setup-windows.bat" in result.stdout
    assert not (checkout / ".venv").exists()


def test_incomplete_environment_is_not_deleted_or_reported_as_installed(checkout):
    environment = checkout / ".venv"
    environment.mkdir()
    sentinel = environment / "keep.txt"
    sentinel.write_text("keep")
    result = launch(checkout / "setup-windows.bat")
    assert result.returncode == 1
    assert "yeniden adlandirip" in result.stdout
    assert "Kurulum tamamlandi." not in result.stdout
    assert sentinel.read_text() == "keep"


def test_failed_install_stops_and_preserves_workspace(checkout):
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(checkout / ".venv")], check=True)
    data = checkout / "data"
    data.mkdir()
    sentinel = data / "keep.json"
    sentinel.write_text('{}')
    result = launch(checkout / "setup-windows.bat")
    assert result.returncode == 1
    assert "Kurulum tamamlanamadi." in result.stdout
    assert "Kurulum tamamlandi." not in result.stdout
    assert sentinel.read_text() == '{}'


@pytest.mark.parametrize("script", ["start.bat", "start-browser.bat"])
def test_launcher_preserves_python_exit_code_in_a_path_with_spaces(checkout, script):
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(checkout / ".venv")], check=True)
    (checkout / "launch.py").write_text("raise SystemExit(7)\n")
    assert launch(checkout / script).returncode == 7
