"""Wrap an already built macOS application in a drag-to-Applications disk image."""

from __future__ import annotations

import argparse
import platform
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    bundle, output = args.bundle.resolve(), args.output.resolve()
    if platform.system() != "Darwin":
        parser.error("Build the disk image on macOS.")
    if not (bundle / "Contents/MacOS/RpaOrkestrAI").is_file():
        parser.error("Expected a built RpaOrkestrAI.app bundle.")
    if output.exists():
        parser.error("Output already exists; choose a new filename.")
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(bundle)], check=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Stage outside synced folders; only the app and installation shortcut belong here.
    with tempfile.TemporaryDirectory(prefix="rpa-dmg-") as folder:
        stage = Path(folder) / "content"
        stage.mkdir()
        subprocess.run(["ditto", str(bundle), str(stage / "RpaOrkestrAI.app")], check=True)
        (stage / "Applications").symlink_to("/Applications", target_is_directory=True)
        subprocess.run(["hdiutil", "create", "-volname", "RpaOrkestrAI", "-srcfolder", str(stage),
                        "-fs", "HFS+", "-format", "UDZO", str(output)], check=True)
    subprocess.run(["hdiutil", "verify", str(output)], check=True)
    print("Disk image ready:", output)


if __name__ == "__main__":
    main()
