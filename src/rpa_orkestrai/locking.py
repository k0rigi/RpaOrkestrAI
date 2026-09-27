"""An OS-managed lock prevents two processes from recovering/writing the same workspace."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class WorkspaceLock:
    def __init__(self, root: Path):
        self.path = root / ".studio.lock"
        self.handle: Any = None

    def __enter__(self) -> WorkspaceLock:
        self.handle = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            raise RuntimeError("Bu çalışma alanı başka bir Studio tarafından kullanılıyor. Önce onu kapatın.") from exc
        return self

    def __exit__(self, *_: Any) -> None:
        if self.handle is not None:
            try:
                if os.name == "nt":
                    import msvcrt

                    self.handle.seek(0)
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            finally:
                self.handle.close()
                self.handle = None
