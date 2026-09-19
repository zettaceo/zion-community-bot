from __future__ import annotations

import fcntl
import os
from pathlib import Path


class ProcessLock:
    """Single-process guard shared across ZION worktrees for one OS user."""

    def __init__(self, path: Path):
        self.path = path.expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass

        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        self._fd = os.open(
            self.path,
            flags,
            0o600,
        )
        try:
            os.fchmod(self._fd, 0o600)
        except OSError:
            pass

        try:
            fcntl.flock(
                self._fd,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError as exc:
            os.close(self._fd)
            self._fd = -1
            raise RuntimeError(
                "Outra instância do ZION já possui o runtime lock."
            ) from exc

        payload = f"pid={os.getpid()}\n"
        try:
            os.ftruncate(self._fd, 0)
            os.write(self._fd, payload.encode("ascii"))
            os.fsync(self._fd)
        except Exception:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = -1
            raise

    @property
    def acquired(self) -> bool:
        return self._fd >= 0

    def close(self) -> None:
        if self._fd < 0:
            return
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = -1

    def __enter__(self) -> "ProcessLock":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
