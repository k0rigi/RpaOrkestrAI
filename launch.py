"""Source checkout launcher: independent of editable-install .pth files."""

import sys
from pathlib import Path


def main() -> None:
    print("RpaOrkestrAI açılıyor… İlk açılışta bileşenlerin yüklenmesi biraz sürebilir.", flush=True)
    root = Path(__file__).resolve().parent
    sys.path.insert(0, str(root / "src"))
    from rpa_orkestrai.cli import main as run

    run()


if __name__ == "__main__":
    main()
