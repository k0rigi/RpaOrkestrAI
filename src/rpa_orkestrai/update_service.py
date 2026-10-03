"""Desktop update lifecycle: download in the background, install before the next UI."""

from __future__ import annotations

import base64
import json
import logging
import math
import os
import sys
import threading
import time
from pathlib import Path

from . import __version__
from .config import atomic_json
from .locking import WorkspaceLock
from .update_config import CHANNEL, FEED_URL, PUBLIC_KEY
from .updates import UpdateClient, current_platform_key

logger = logging.getLogger("rpa.gui.updates")
STATE_LIMIT = 256 * 1024
INSTALL_MARKER_TTL = 15 * 60


def _process_alive(pid: int) -> bool:
    """Query a PID without sending a terminating signal or opening a console."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE only
        if not handle:
            return ctypes.get_last_error() == 5  # Access denied: conservatively treat as live.
        try:
            return kernel.WaitForSingleObject(handle, 0) != 0  # WAIT_OBJECT_0 means exited.
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def source_status() -> dict:
    return {"enabled": False, "status": "source", "version": __version__, "available_version": None,
            "message": "Otomatik güncellemeler kurulu masaüstü uygulamasında kullanılabilir."}


class DesktopUpdates:
    def __init__(self, workspace: Path, *, enabled: bool | None = None, client=None,
                 executable: Path | None = None, platform_key: str | None = None):
        self.enabled = bool(getattr(sys, "frozen", False)) if enabled is None else enabled
        self.cache = workspace / "updates"
        self.pending = self.cache / "pending.json"
        self.attempt = self.cache / "attempt.json"
        self.installing = self.cache / "installing.json"
        self.executable = executable or Path(sys.executable)
        self.platform_key = platform_key or current_platform_key()
        self.client = client
        self._guard = threading.RLock()
        self._stop = threading.Event()
        self._worker = None
        self._lease = None
        self._cache_busy = False
        self._state = source_status()
        if self.enabled:
            self._state.update(enabled=True, status="idle", message="Güncellemeler açılışta kontrol edilir.")

    def status(self) -> dict:
        with self._guard:
            return dict(self._state)

    def _set(self, status: str, message: str, version: str | None = None) -> None:
        with self._guard:
            self._state.update(status=status, message=message, available_version=version)

    def _acquire(self) -> bool:
        self._cache_busy = False
        if not self.enabled or not self.platform_key:
            return False
        if self._lease is not None:
            return True
        try:
            self.cache.mkdir(parents=True, mode=0o700, exist_ok=True)
            lease = WorkspaceLock(self.cache)
            try:
                lease.__enter__()
            except RuntimeError:
                self._cache_busy = True
                self._set("busy", "Studio zaten açık veya güncellemeye hazırlanıyor.")
                return False
            self._lease = lease
            if self.client is None:
                self.client = UpdateClient(FEED_URL, PUBLIC_KEY, cache_dir=self.cache, channel=CHANNEL)
            return True
        except Exception:
            self._release()
            self._set("unavailable", "Güncelleme kontrolü başka bir oturumda veya şu anda kullanılamıyor.")
            logger.info("Güncelleme oturumu başlatılamadı.", exc_info=True)
            return False

    def _release(self) -> None:
        with self._guard:
            if self._lease is not None:
                try:
                    self._lease.__exit__(None, None, None)
                except OSError:
                    logger.warning("Güncelleme kilidi kapatılamadı.", exc_info=True)
                self._lease = None

    def _read(self, path: Path) -> dict:
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > STATE_LIMIT:
                return {}
            with path.open("rb") as handle:
                raw = handle.read(STATE_LIMIT + 1)
            if len(raw) > STATE_LIMIT:
                return {}
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except (ValueError, OSError, RecursionError):
            return {}

    def _install_in_progress(self) -> bool:
        """Gate a second launch even while the original process owns the cache lock.

        A short-lived parent marker also covers the handoff interval and a failed
        helper-PID write. PID reuse may conservatively delay a launch, but cannot
        block it beyond the marker's bounded lifetime. New-version relaunch is
        allowed after replacement; the Mac helper clears its marker on rollback.
        """
        if not self.enabled:
            return False
        marker = self._read(self.installing)
        created, pid = marker.get("created_at"), marker.get("pid")
        version = marker.get("version")
        if (type(created) not in {int, float} or not math.isfinite(created)
                or type(pid) is not int or not 1 <= pid <= 2**31 - 1
                or not isinstance(version, str) or len(version) > 64
                or marker.get("phase") not in {"parent", "helper"}
                or marker.get("executable") != os.path.normcase(str(self.executable.resolve()))):
            return False
        age = time.time() - created
        if not -5 <= age <= INSTALL_MARKER_TTL or version == __version__:
            return False
        if marker["phase"] == "parent" or _process_alive(pid):
            self._set("installing", "Yeni sürüm kuruluyor; birkaç saniye içinde Studio kendiliğinden açılacak.",
                      version)
            return True
        return False

    def _note_installed(self) -> None:
        """Say which version was installed: the installation itself shows nothing any more."""
        marker = self._read(self.installing)
        if (marker.get("version") != __version__
                or marker.get("executable") != os.path.normcase(str(self.executable.resolve()))):
            return
        with self._guard:
            self._state["installed"] = __version__
        self.installing.unlink(missing_ok=True)

    def apply_pending(self, settings) -> bool:
        """True means installation is active; return before opening another UI."""
        if self._install_in_progress():
            return True
        self._note_installed()
        if not self._acquire():
            # The owner may be preparing installation before its marker is written.
            # A duplicate process must not race that owner into the native window.
            return self._cache_busy
        receipt = self._read(self.pending)
        if not receipt:
            return False
        handoff_started = False
        try:
            envelope = base64.b64decode(receipt.get("manifest", ""), validate=True)
            checked = self.client.authenticate_manifest(envelope, __version__, self.platform_key)
            if checked.status == "current":
                self.pending.unlink(missing_ok=True)
                self.attempt.unlink(missing_ok=True)
                return False
            if checked.status != "available" or checked.release is None:
                raise ValueError("Pending manifest no longer authorizes an update")
            release = checked.release
            name = receipt.get("asset")
            if not isinstance(name, str) or Path(name).name != name or "/" in name or "\\" in name:
                raise ValueError("Invalid cached asset name")
            asset = self.cache / name
            if asset.is_symlink() or not asset.is_file():
                raise ValueError("Cached asset missing")
            self.client.verify_download(release, asset)
            if self._read(self.attempt).get("version") == release.version:
                self._set("manual", "Önceki güncelleme tamamlanamadı. İndirme sayfasından yeniden kurabilirsiniz.",
                          release.version)
                return False
            # Never update application files while its workspace has another owner.
            try:
                lease = WorkspaceLock(settings.data_dir)
                lease.__enter__()
            except RuntimeError:
                self._set("ready", "Yeni sürüm hazır; açık Studio oturumları kapandıktan sonra kurulacak.",
                          release.version)
                return False
            try:
                from .update_install import cleanup, handoff, prepare_install

                plan = None
                # Preparation or handoff failures must not create an endless startup loop.
                atomic_json(self.attempt, {"version": release.version})
                try:
                    plan = prepare_install(asset, release.asset.type, release.version, self.executable, self.cache)
                    marker = {"version": release.version, "pid": os.getpid(), "created_at": time.time(),
                              "executable": os.path.normcase(str(self.executable.resolve())), "phase": "parent"}
                    atomic_json(self.installing, marker)
                    process = handoff(plan)
                    handoff_started = True
                    # From this point the current process MUST exit, even if persistence fails.
                    try:
                        atomic_json(self.installing, {**marker, "pid": process.pid, "phase": "helper"})
                    except OSError:
                        logger.warning("Kurulum başladı; yardımcı süreç kaydı yazılamadı.", exc_info=True)
                finally:
                    if not handoff_started:
                        try:
                            self.installing.unlink(missing_ok=True)
                        finally:
                            if plan is not None:
                                cleanup(plan)
                logger.info("%s sürümü için kurulum başlatıldı.", release.version)
                return True
            finally:
                try:
                    lease.__exit__(None, None, None)
                except OSError:
                    logger.warning("Çalışma alanı güncelleme kilidi kapatılamadı.", exc_info=True)
        except Exception:
            if handoff_started:
                logger.warning("Kurulum başladı; Studio kapanacak.", exc_info=True)
                return True
            logger.warning("Bekleyen güncelleme uygulanamadı; mevcut uygulama açılacak.", exc_info=True)
            self._set("manual", "Güncelleme otomatik kurulamadı. Mevcut sürümle çalışmaya devam edebilirsiniz.")
            return False

    def start(self) -> None:
        with self._guard:
            if self._stop.is_set() or (self._worker is not None and self._worker.is_alive()):
                return
            if not self._acquire():
                return
            self._worker = threading.Thread(target=self._check, name="rpa-updates", daemon=True)
            try:
                self._worker.start()
            except RuntimeError:
                self._worker = None
                self._release()
                self._set("unavailable", "Güncelleme kontrolü şu anda başlatılamadı. Mevcut sürüm kullanılabilir.")
                logger.warning("Güncelleme iş parçacığı başlatılamadı.", exc_info=True)

    def _check(self) -> None:
        previous = self.status()
        try:
            self._set("checking", "Yeni sürüm kontrol ediliyor…")
            result = self.client.check(__version__, self.platform_key)
            if self._stop.is_set():
                return
            if result.status != "available" or result.release is None:
                if result.status != "current" and previous["status"] in {"ready", "manual"}:
                    self._set(previous["status"], previous["message"], previous["available_version"])
                    return
                messages = {"current": "En güncel sürümü kullanıyorsunuz.",
                            "unavailable": "Güncelleme sunucusuna ulaşılamadı. Mevcut sürüm kullanılabilir.",
                            "unsupported": "Bu bilgisayar için uygun güncelleme paketi bulunmuyor.",
                            "invalid": "Güncelleme doğrulanamadı; mevcut sürüm korunuyor."}
                self._set(result.status, messages.get(result.status, "Güncelleme şu anda kullanılamıyor."))
                return
            release = result.release
            if self._read(self.attempt).get("version") == release.version:
                self._set("manual", "Yeni sürüm indirme sayfasından kurulabilir.", release.version)
                return
            self._set("downloading", "Yeni sürüm arka planda indiriliyor. Çalışmaya devam edebilirsiniz.",
                      release.version)
            asset = self.client.download(release, cancelled=self._stop.is_set)
            if self._stop.is_set():
                return
            atomic_json(self.pending, {"manifest": base64.b64encode(release.manifest_bytes).decode("ascii"),
                                       "asset": asset.name})
            self._set("ready", "Yeni sürüm hazır. Studio'yu kapatıp açın; kurulum ekranı açılmadan "
                               "kendiliğinden kurulur.", release.version)
        except Exception:
            if not self._stop.is_set():
                logger.warning("Güncelleme indirilemedi; mevcut sürüm korunuyor.", exc_info=True)
                if previous["status"] in {"ready", "manual"}:
                    self._set(previous["status"], previous["message"], previous["available_version"])
                else:
                    self._set("unavailable", "Güncelleme indirilemedi. Mevcut sürümle çalışmaya devam edebilirsiniz.")
        finally:
            if self._stop.is_set():
                self._release()

    def stop(self) -> None:
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=0.2)
        if self._worker is None or not self._worker.is_alive():
            self._release()
