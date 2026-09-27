"""Build on the target OS; never bundles workspace data or credentials."""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def app_version() -> str:
    import tomllib

    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def finalize_mac_bundle(bundle: Path) -> None:
    import plistlib

    path = bundle / "Contents" / "Info.plist"
    with path.open("rb") as handle:
        info = plistlib.load(handle)
    info.update(NSAppleEventsUsageDescription="Tanıttığınız ERP penceresini öne getirmek için kullanılır.",
                NSHighResolutionCapable=True, CFBundleShortVersionString=app_version(),
                CFBundleVersion=app_version())
    with path.open("wb") as handle:
        plistlib.dump(info, handle)
    # Clean Finder/iCloud metadata only on our newly generated bundle before signing.
    subprocess.run(["/usr/bin/xattr", "-cr", str(bundle)], check=True)
    subprocess.run(["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(bundle)], check=True)


def make_icon(folder: Path) -> Path:
    from PIL import Image, ImageDraw

    folder.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (1024, 1024))
    draw = ImageDraw.Draw(image)
    # The Studio's existing mint/dark O mark, rendered at app-icon sizes.
    draw.rounded_rectangle((48, 48, 976, 976), radius=230, fill="#ACD6B5")
    draw.ellipse((245, 280, 710, 800), fill="#173237")
    draw.ellipse((375, 420, 580, 660), fill="#ACD6B5")
    draw.ellipse((705, 220, 835, 350), fill="#173237")
    icon = folder / ("studio.icns" if platform.system() == "Darwin" else "studio.ico")
    image.save(icon)
    return icon


def main() -> None:
    parser = argparse.ArgumentParser(description="RpaOrkestrAI masaüstü paketi oluştur")
    parser.add_argument("--without-odbc", action="store_true",
                        help="SQL Server adaptörü olmadan oluştur (unixODBC bulunmayan macOS test ortamları).")
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist",
                        help="Paket çıktı klasörü; macOS'ta iCloud dışındaki bir klasör seçilebilir.")
    args = parser.parse_args()
    destination = args.dist_dir.expanduser().resolve()
    system = platform.system()
    if system not in {"Windows", "Darwin"}:
        raise SystemExit("Masaüstü paketini Windows veya macOS üzerinde oluşturun.")
    icon = make_icon(ROOT / "build" / "app-icon")
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
               "--name", "RpaOrkestrAI", "--icon", str(icon),
               "--specpath", str(ROOT / "build"), "--distpath", str(destination),
               "--workpath", str(ROOT / "build" / "pyinstaller"), "--paths", str(ROOT / "src"),
               "--add-data", f"{ROOT / 'src' / 'rpa_orkestrai' / 'static'}:rpa_orkestrai/static",
               "--collect-data", "webview", "--collect-data", "certifi",
               "--collect-submodules", "uvicorn", "--collect-submodules", "rpa_orkestrai",
               "--hidden-import", "sqlalchemy.dialects.postgresql.psycopg",
               "--hidden-import", "sqlalchemy.dialects.mssql.pyodbc",
               "--exclude-module", "PyQt5", "--exclude-module", "PyQt6",
               "--exclude-module", "PySide2", "--exclude-module", "PySide6"]
    if args.without_odbc:
        command += ["--exclude-module", "pyodbc"]
    if system == "Darwin":
        command += ["--osx-bundle-identifier", "com.rpaorkestrai.studio",
                    "--hidden-import", "webview.platforms.cocoa"]
    else:
        command += ["--hidden-import", "webview.platforms.winforms", "--hidden-import", "webview.platforms.edgechromium"]
    command += [str(ROOT / "launch_gui.pyw")]
    subprocess.run(command, cwd=ROOT, check=True)
    if system == "Darwin":
        # Re-sign after editing Info.plist; distribution signing/notarization is separate.
        finalize_mac_bundle(destination / "RpaOrkestrAI.app")
    print("Package ready:", destination)


if __name__ == "__main__":
    main()
