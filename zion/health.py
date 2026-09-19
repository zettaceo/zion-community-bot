from __future__ import annotations

import shutil
import time
from pathlib import Path

from .config import Settings
from .db import ZionDB
from .models import HealthSnapshot, OperatingState


def _private_file(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        return (path.stat().st_mode & 0o077) == 0
    except OSError:
        return False


class HealthService:
    def __init__(self, settings: Settings, db: ZionDB):
        self.settings = settings
        self.db = db
        self._started_monotonic = time.monotonic()
        self._integrity_checked_at = float("-inf")
        self._integrity_cache: tuple[bool, str] = (True, "not_checked")

    def _integrity_status(self) -> tuple[bool, str]:
        now = time.monotonic()
        if now - self._integrity_checked_at >= 300:
            self._integrity_cache = self.db.integrity_check()
            self._integrity_checked_at = now
        return self._integrity_cache

    def snapshot(self) -> HealthSnapshot:
        try:
            disk = shutil.disk_usage(self.settings.root_dir)
            disk_free_mb = int(disk.free / 1024 / 1024)
        except OSError:
            disk_free_mb = -1

        wifi_path = Path("/sys/class/net") / self.settings.wifi_interface

        sensitive_paths = (
            self.settings.root_dir / ".env",
            self.settings.db_path,
            Path(str(self.settings.db_path) + "-wal"),
            Path(str(self.settings.db_path) + "-shm"),
            self.settings.log_path,
            self.settings.legacy_state_path,
        )
        sensitive_files_private = all(
            _private_file(path)
            for path in sensitive_paths
        )

        integrity_ok, integrity_result = self._integrity_status()
        db_size_mb = int(self.db.file_size_bytes() / 1024 / 1024)

        try:
            state = self.db.get_operating_state()
        except Exception:
            state = OperatingState.SAFE_MODE

        return HealthSnapshot(
            state=state,
            db_ok=self.db.ping() and integrity_ok,
            telegram_configured=bool(self.settings.telegram_token),
            ai_enabled=self.settings.ai_enabled,
            ai_configured=bool(self.settings.mistral_api_key),
            wifi_interface_present=wifi_path.exists(),
            disk_free_mb=disk_free_mb,
            uptime_seconds=int(
                time.monotonic() - self._started_monotonic
            ),
            details={
                "database": self.settings.db_path.name,
                "ai_provider": "mistral",
                "ai_model": self.settings.mistral_model,
                "sensitive_files_private": sensitive_files_private,
                "sqlite_integrity_ok": integrity_ok,
                "sqlite_integrity_result": integrity_result,
                "db_size_mb": db_size_mb,
                "disk_low": (
                    disk_free_mb >= 0
                    and disk_free_mb < self.settings.disk_warn_mb
                ),
                "disk_warn_mb": self.settings.disk_warn_mb,
            },
        )

    def diagnostics(self) -> dict[str, object]:
        snapshot = self.snapshot()
        latency = self.db.ai_latency_stats(time.time() - 86400)
        pragmas = self.db.runtime_pragmas()
        return {
            "state": snapshot.state.value,
            "db_ok": snapshot.db_ok,
            "sqlite_integrity_ok": bool(
                snapshot.details.get("sqlite_integrity_ok")
            ),
            "sqlite_integrity_result": str(
                snapshot.details.get("sqlite_integrity_result", "unknown")
            ),
            "db_size_mb": int(snapshot.details.get("db_size_mb", 0)),
            "disk_free_mb": snapshot.disk_free_mb,
            "disk_low": bool(snapshot.details.get("disk_low")),
            "sensitive_files_private": bool(
                snapshot.details.get("sensitive_files_private")
            ),
            "wifi_interface_present": snapshot.wifi_interface_present,
            "ai_latency_24h": latency,
            "schema_version": self.db.schema_version(),
            "sqlite_pragmas": pragmas,
        }

    @staticmethod
    def format_uptime(seconds: int) -> str:
        days, rem = divmod(max(0, seconds), 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        if days:
            return f"{days}d {hours:02d}h {minutes:02d}m"
        return f"{hours:02d}h {minutes:02d}m"
