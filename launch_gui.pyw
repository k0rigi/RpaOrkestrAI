"""Double-click/native bundle entry point: no terminal is required."""

import multiprocessing
import sys
from pathlib import Path


def main() -> int:
    multiprocessing.freeze_support()
    frozen = getattr(sys, "frozen", False)
    root = Path(__file__).resolve().parent
    if not frozen:
        sys.path.insert(0, str(root / "src"))
    from rpa_orkestrai.gui import main as run

    return run(workspace=None if frozen else root)


if __name__ == "__main__":
    raise SystemExit(main())
