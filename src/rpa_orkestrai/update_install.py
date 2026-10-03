"""Hand an already authenticated update to the platform installer.

This module never downloads updates. Its caller must verify the manifest signature
and the asset digest before preparing an installation. User workspaces are outside
the application bundle/install directory and are never migrated or deleted here.
"""

from __future__ import annotations

import logging
import os
import platform
import plistlib
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from xml.parsers.expat import ExpatError

logger = logging.getLogger("rpa.gui.updates")
BUNDLE_ID = "com.rpaorkestrai.studio"
APP_NAME = "RpaOrkestrAI.app"


class UpdateInstallError(RuntimeError):
    """The update was not installed; the currently running app remains usable."""


class ManualUpdateRequired(UpdateInstallError):
    """The current installation cannot safely be replaced without user action."""


@dataclass(frozen=True)
class InstallPlan:
    platform: str
    command: tuple[str, ...]
    log_path: Path
    target: Path
    staging_dir: Path | None = None
    helper_path: Path | None = None


# Paths are positional arguments, never interpolated into shell source. Only the
# unique staging directory may be deleted. Failure to launch restores the old app.
_MAC_HELPER = """#!/bin/sh
set -eu
pid=$1
target=$2
staged=$3
backup=$4
stage_root=$5
version=$6
platform=$7
marker=$8
state=old
health_pid=
stop_health() {
    if [ -n "$health_pid" ]; then
        /bin/kill -TERM "$health_pid" 2>/dev/null || true
        /bin/sleep 1
        /bin/kill -KILL "$health_pid" 2>/dev/null || true
        wait "$health_pid" 2>/dev/null || true
        health_pid=
    fi
}
rollback() {
    result=$?
    trap - EXIT HUP INT TERM
    stop_health
    if [ "$state" = new ]; then
        if /bin/mv "$target" "$staged" && /bin/mv "$backup" "$target"; then
            /bin/rm -f "$marker"
            /usr/bin/open "$target" || true
        else
            echo "Restore the previous application from: $backup"
        fi
    elif [ "$state" = backup ]; then
        if /bin/mv "$backup" "$target"; then
            /bin/rm -f "$marker"
            /usr/bin/open "$target" || true
        fi
    else
        /bin/rm -f "$marker"
    fi
    exit "$result"
}
trap rollback EXIT HUP INT TERM
count=0
while /bin/kill -0 "$pid" 2>/dev/null; do
    if [ "$count" -ge 120 ]; then
        echo 'Update canceled: the previous application is still running.'
        exit 1
    fi
    /bin/sleep 1
    count=$((count + 1))
done
if [ ! -d "$target" ] || [ -L "$target" ] || [ ! -d "$staged" ] || [ -L "$staged" ] || [ -e "$backup" ]; then
    echo 'Update canceled: application paths changed.'
    exit 1
fi
if [ -L "$target/Contents" ] || [ -L "$target/Contents/Info.plist" ] ||
   [ "$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$target/Contents/Info.plist")" != 'com.rpaorkestrai.studio' ]; then
    echo 'Update canceled: installed application identity changed.'
    exit 1
fi
/bin/mv "$target" "$backup"
state=backup
/bin/mv "$staged" "$target"
state=new
report="$stage_root/package-check.json"
"$target/Contents/MacOS/RpaOrkestrAI" --self-test "$report" &
health_pid=$!
count=0
while /bin/kill -0 "$health_pid" 2>/dev/null; do
    if [ "$count" -ge 90 ]; then
        echo 'Update failed: the candidate health check timed out.'
        exit 1
    fi
    /bin/sleep 1
    count=$((count + 1))
done
if wait "$health_pid"; then
    health_pid=
else
    health_pid=
    echo 'Update failed: the candidate health check exited with an error.'
    exit 1
fi
if [ "$(/usr/bin/plutil -extract ok raw -expect bool -o - "$report")" != true ] ||
   [ "$(/usr/bin/plutil -extract frozen raw -expect bool -o - "$report")" != true ] ||
   [ "$(/usr/bin/plutil -extract version raw -expect string -o - "$report")" != "$version" ] ||
   [ "$(/usr/bin/plutil -extract platform raw -expect string -o - "$report")" != "$platform" ]; then
    echo 'Update failed: the candidate health report does not match the release.'
    exit 1
fi
/bin/rm -f "$marker"
/usr/bin/open "$target"
state=complete
trap - EXIT HUP INT TERM
/bin/rm -rf "$stage_root"
echo 'Update installed and application launch requested.'
"""


def _path(value: Path) -> Path:
    path = Path(value).expanduser()
    if any(character in str(path) for character in ("\x00", "\r", "\n")):
        raise UpdateInstallError("Güncelleme dosyasının yolu geçersiz.")
    return path


def _private_cache(value: Path) -> Path:
    path = _path(value)
    if path.is_symlink():
        raise UpdateInstallError("Güncelleme klasörü bir bağlantı olamaz.")
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    path = path.resolve(strict=True)
    if not path.is_dir():
        raise UpdateInstallError("Güncelleme klasörü kullanılamıyor.")
    if os.name != "nt":
        if path.stat().st_uid != os.getuid():
            raise UpdateInstallError("Güncelleme klasörü bu kullanıcıya ait değil.")
        path.chmod(0o700)
    return path


def _run(arguments: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(arguments, check=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.exception("Platform güncelleme hazırlığı başarısız: %s", arguments[0])
        raise UpdateInstallError("Güncelleme paketi hazırlanamadı; mevcut uygulama korunuyor.") from exc


def _bundle_metadata(bundle: Path) -> dict:
    info = bundle / "Contents" / "Info.plist"
    executable = bundle / "Contents" / "MacOS" / "RpaOrkestrAI"
    if (bundle.is_symlink() or not bundle.is_dir() or (bundle / "Contents").is_symlink()
            or (bundle / "Contents" / "MacOS").is_symlink()
            or info.is_symlink() or executable.is_symlink()):
        raise UpdateInstallError("Uygulama paketinin yapısı doğrulanamadı.")
    try:
        if info.stat().st_size > 65536 or not executable.is_file():
            raise ValueError("Unexpected bundle structure")
        metadata = plistlib.loads(info.read_bytes())
        if not isinstance(metadata, dict) or metadata.get("CFBundleIdentifier") != BUNDLE_ID:
            raise ValueError("Unexpected bundle identity")
        return metadata
    except (OSError, ValueError, ExpatError, plistlib.InvalidFileException) as exc:
        raise UpdateInstallError("RpaOrkestrAI uygulama kimliği doğrulanamadı.") from exc


def _mac_target(executable: Path) -> Path:
    if (executable.name != "RpaOrkestrAI" or executable.parent.name != "MacOS"
            or executable.parent.parent.name != "Contents"
            or executable.parent.parent.parent.name != APP_NAME):
        raise ManualUpdateRequired("Otomatik güncelleme için kurulu RpaOrkestrAI.app uygulamasını açın.")
    bundle = executable.parent.parent.parent
    if bundle.is_relative_to(Path("/Volumes")):
        raise ManualUpdateRequired(
            "Uygulamayı önce disk imajından Uygulamalar klasörüne taşıyın, ardından oradan açın."
        )
    _bundle_metadata(bundle)
    if not os.access(bundle.parent, os.W_OK) or not os.access(bundle, os.W_OK):
        raise ManualUpdateRequired(
            "Uygulamalar klasörüne yazma izni yok. Yeni DMG dosyasını açıp uygulamayı elle değiştirin."
        )
    return bundle


def _remove_stage(stage: Path, target: Path) -> None:
    if stage.parent != target.parent or not stage.name.startswith(".rpa-update-") or stage.is_symlink():
        raise UpdateInstallError("Güncelleme geçici klasörünün yolu doğrulanamadı.")
    if stage.exists():
        shutil.rmtree(stage)


def _prepare_mac(asset: Path, version: str, executable: Path, cache: Path) -> InstallPlan:
    target = _mac_target(executable)
    machine = platform.machine().lower()
    if machine in ("arm64", "aarch64"):
        platform_key = "macos-arm64"
    elif machine in ("x86_64", "amd64"):
        platform_key = "macos-x64"
    else:
        raise ManualUpdateRequired("Bu Mac işlemcisi için uygun paketi elle indirip kurun.")
    if cache.is_relative_to(target):
        raise UpdateInstallError("Güncelleme klasörü uygulama paketinin dışında olmalıdır.")
    mount = Path(tempfile.mkdtemp(prefix="mount-", dir=cache))
    stage = None
    mounted = False
    helper = None
    try:
        result = _run([
            "/usr/bin/hdiutil", "attach", str(asset), "-readonly", "-nobrowse", "-noautoopen",
            "-mountpoint", str(mount), "-plist",
        ])
        mounted = True
        try:
            entities = plistlib.loads(result.stdout).get("system-entities", [])
            if not any(entity.get("mount-point") == str(mount) for entity in entities):
                raise ValueError("Unexpected mounted path")
        except (ValueError, AttributeError, TypeError, ExpatError, plistlib.InvalidFileException) as exc:
            raise UpdateInstallError("Güncelleme disk imajının konumu doğrulanamadı.") from exc
        source = mount / APP_NAME
        metadata = _bundle_metadata(source)
        if metadata.get("CFBundleShortVersionString") != version:
            raise UpdateInstallError("Güncelleme paketinin sürümü yayın bilgisiyle eşleşmiyor.")
        _run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(source)])
        stage = Path(tempfile.mkdtemp(prefix=".rpa-update-", dir=target.parent))
        staged = stage / APP_NAME
        _run(["/usr/bin/ditto", str(source), str(staged)])
        _bundle_metadata(staged)
        _run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(staged)])
        # ditto preserves quarantine and code-signing metadata; no security policy
        # is changed. Gatekeeper can still ask the user to approve this developer.
        descriptor, helper_name = tempfile.mkstemp(prefix="install-", suffix=".sh", dir=cache)
        helper = Path(helper_name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(_MAC_HELPER)
        plan = InstallPlan(
            platform="Darwin",
            command=("/bin/sh", str(helper), str(os.getpid()), str(target), str(staged),
                     str(stage / "previous.app"), str(stage), version, platform_key, str(cache / "installing.json")),
            log_path=cache / f"install-{version}.log",
            target=target,
            staging_dir=stage,
            helper_path=helper,
        )
    except Exception:
        if stage:
            _remove_stage(stage, target)
        if helper:
            helper.unlink(missing_ok=True)
        raise
    finally:
        if mounted or os.path.ismount(mount):
            try:
                _run(["/usr/bin/hdiutil", "detach", str(mount)], timeout=60)
            except UpdateInstallError:
                if stage:
                    _remove_stage(stage, target)
                if helper:
                    helper.unlink(missing_ok=True)
                raise
        try:
            mount.rmdir()
        except OSError:
            logger.warning("Güncelleme disk imajının geçici klasörü kaldı: %s", mount)
    return plan


def prepare_install(
    asset_path: Path, asset_type: str, version: str, current_executable: Path, cache_dir: Path,
) -> InstallPlan:
    """Validate local installation and stage an authenticated ``exe`` or ``dmg``.

    ``cache_dir`` must be the private directory containing the verified asset.
    Preparation never quits the running application or changes installed files.
    """
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?", version) or len(version) > 64:
        raise UpdateInstallError("Güncelleme sürümü geçersiz.")
    cache = _private_cache(cache_dir)
    asset = _path(asset_path)
    if asset.is_symlink() or not asset.is_file():
        raise UpdateInstallError("Doğrulanmış güncelleme dosyası bulunamadı.")
    asset = asset.resolve(strict=True)
    if not asset.is_relative_to(cache):
        raise UpdateInstallError("Güncelleme dosyası özel güncelleme klasöründe bulunmalıdır.")
    executable = _path(current_executable)
    if executable.is_symlink() or not executable.is_file():
        raise ManualUpdateRequired("Güncellemek için kurulu uygulamayı açın.")
    executable = executable.resolve(strict=True)
    system = platform.system()
    if system == "Darwin" and asset_type == "dmg" and asset.suffix.lower() == ".dmg":
        return _prepare_mac(asset, version, executable, cache)
    if system == "Windows" and asset_type == "exe" and asset.suffix.lower() == ".exe":
        target = executable.parent
        if executable.name.lower() != "rpaorkestrai.exe" or not (target / "unins000.exe").is_file():
            raise ManualUpdateRequired("Otomatik güncelleme için önce Windows kurulum EXE dosyasını çalıştırın.")
        if cache.is_relative_to(target):
            raise UpdateInstallError("Güncelleme klasörü kurulum klasörünün dışında olmalıdır.")
        if not os.access(target, os.W_OK):
            raise ManualUpdateRequired("Kurulum klasörüne yazılamıyor; güncel Windows kurulumunu elle çalıştırın.")
        log_path = cache / f"install-{version}.log"
        return InstallPlan(
            platform="Windows",
            # VERYSILENT: an update shows no setup window at all. The Studio closes, the files are
            # replaced and the Studio opens again by itself ([Run] … Check: IsUpdate).
            command=(str(asset), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/NOCLOSEAPPLICATIONS",
                     "/RPAUPDATE", f"/RPAPID={os.getpid()}", f"/DIR={target}", f"/LOG={log_path}"),
            log_path=log_path,
            target=target,
        )
    raise ManualUpdateRequired("Bu bilgisayar için uygun güncelleme paketini elle indirip kurun.")


def handoff(plan: InstallPlan) -> subprocess.Popen:
    """Start detached installation; caller must now close its app normally.

    Spawn failures raise before the caller quits. Both installers wait up to 120
    seconds for the current PID to exit; they never terminate it themselves.
    """
    if plan.platform != platform.system():
        raise UpdateInstallError("Güncelleme planı bu işletim sistemiyle eşleşmiyor.")
    options = {"stdin": subprocess.DEVNULL, "close_fds": True, "cwd": str(plan.log_path.parent)}
    if plan.platform == "Windows":
        options["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    try:
        # The Inno process owns its /LOG file. macOS writes the helper's output here.
        if plan.platform == "Windows":
            return subprocess.Popen(plan.command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
        with plan.log_path.open("ab") as log:
            return subprocess.Popen(plan.command, stdout=log, stderr=subprocess.STDOUT, **options)
    except OSError as exc:
        raise UpdateInstallError("Güncelleme başlatılamadı; uygulamayı kullanmaya devam edebilirsiniz.") from exc


def cleanup(plan: InstallPlan) -> None:
    """Discard prepared Mac files only when handoff has not succeeded."""
    if plan.staging_dir:
        _remove_stage(plan.staging_dir, plan.target)
    if plan.helper_path:
        plan.helper_path.unlink(missing_ok=True)
