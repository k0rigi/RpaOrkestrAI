"""Run the frozen office check with a process deadline, then verify its report."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rpa_orkestrai import __version__  # noqa: E402
from rpa_orkestrai.native_office_check import CHECKS  # noqa: E402


def check(executable: Path, report: Path) -> None:
    executable, report = executable.resolve(strict=True), report.absolute()
    if report.exists():
        raise ValueError("Ofis kontrolü için yeni bir rapor yolu seçin.")
    report.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.run([str(executable), "--self-test-office", str(report)], timeout=120, check=False)
    value = json.loads(report.read_text(encoding="utf-8"))
    expected = {"Windows": ("edgechromium", "Microsoft.Web.WebView2.WinForms.WebView2", "windows-x64"),
                "Darwin": ("wkwebview", "WebKit.WKWebView", "macos-arm64" if platform.machine() == "arm64" else "macos-x64")}
    renderer, native_type, system = expected[platform.system()]
    if (process.returncode != 0 or value.get("ok") is not True or value.get("frozen") is not True
            or value.get("version") != __version__ or value.get("platform") != system
            or value.get("renderer") != renderer or value.get("native_type") != native_type
            or set(value.get("checks", {})) != CHECKS or not all(item is True for item in value["checks"].values())
            or value.get("webgl_available") is not True or type(value.get("draw_calls")) is not int
            or value["draw_calls"] <= 0 or value.get("errors") != []):
        raise ValueError("Paket gerçek yerel ofis kontrolünden geçemedi; tanılama raporunu inceleyin.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Paket içindeki ofisi gerçek WKWebView/WebView2 ile doğrula")
    parser.add_argument("executable", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        check(args.executable, args.report)
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        parser.exit(1, "Yerel ofis paket kontrolü başarısız oldu; raporu ve grafik oturumunu kontrol edin.\n")
    print("Paket içindeki yerel ofis ve 3D çizim doğrulandı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
