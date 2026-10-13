"""Taskbar pinning and search name: the app id and the exe's version resource."""
import platform
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows shell app id")
def test_process_app_id_matches_the_installer_shortcuts():
    from rpa_orkestrai.gui import APP_USER_MODEL_ID, set_app_identity
    from rpa_orkestrai.package_check import app_identity

    assert set_app_identity() is True
    assert app_identity() == APP_USER_MODEL_ID
    installer = (ROOT / "packaging" / "windows-installer.iss").read_text(encoding="utf-8-sig")
    shortcuts = [line for line in installer.splitlines() if line.startswith("Name: \"{user")]
    assert shortcuts and all(f'AppUserModelID: "{APP_USER_MODEL_ID}"' in line for line in shortcuts)


def test_installer_shortcuts_and_app_share_one_id():
    from rpa_orkestrai.gui import APP_USER_MODEL_ID

    installer = (ROOT / "packaging" / "windows-installer.iss").read_text(encoding="utf-8-sig")
    assert re.findall(r'AppUserModelID: "([^"]+)"', installer) == [APP_USER_MODEL_ID] * 2


def test_version_resource_names_the_studio_and_carries_the_version(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import build_desktop
    finally:
        sys.path.pop(0)
    from rpa_orkestrai import __version__

    text = build_desktop.version_file(tmp_path).read_text(encoding="utf-8")
    assert "StringStruct('FileDescription', 'RpaOrkestrAI Studio')" in text
    assert f"StringStruct('ProductVersion', '{__version__}.0')" in text
    assert "StringTable('041F04B0'" in text and "VarStruct('Translation', [0x041F, 1200])" in text
