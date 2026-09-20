from __future__ import annotations

import shutil
import stat
import time
from pathlib import Path

from .config import Settings
from .db import SUPPORTED_SCHEMA_VERSION, ZION_APPLICATION_ID, ZionDB
from .models import HealthSnapshot, OperatingState


def _private_file(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False

    return (
        stat.S_ISREG(info.st_mode)
        and info.st_nlink == 1
        and (info.st_mode & 0o077) == 0
    )


class HealthService:
    def __init__(self, settings: Settings, db: ZionDB):
        self.settings = settings
        self.db = db
        self._started_monotonic = time.monotonic()
        self._integrity_checked_at = float("-inf")
        self._integrity_cache_seconds = max(
            1,
            min(
                300,
                int(settings.health_check_interval_seconds),
            ),
        )
        self._integrity_cache: dict[str, object] = {
            "ok": True,
            "database_ok": True,
            "database_messages": ["not_checked"],
            "foreign_keys_ok": True,
            "foreign_key_violations": [],
        }

    def _integrity_status(self) -> dict[str, object]:
        now = time.monotonic()
        if (
            now - self._integrity_checked_at
            >= self._integrity_cache_seconds
        ):
            try:
                self._integrity_cache = self.db.verify_integrity(
                    full=False
                )
            except Exception as exc:
                error_type = type(exc).__name__
                self._integrity_cache = {
                    "ok": False,
                    "database_ok": False,
                    "database_messages": [
                        f"integrity_probe_unavailable:{error_type}"
                    ],
                    "foreign_keys_ok": False,
                    "foreign_key_violations": [
                        f"integrity_probe_unavailable:{error_type}"
                    ],
                }
            self._integrity_checked_at = now
        return self._integrity_cache

    def snapshot(self) -> HealthSnapshot:
        disk_usage_ok = True
        try:
            disk = shutil.disk_usage(self.settings.root_dir)
            disk_free_mb = int(disk.free / 1024 / 1024)
        except OSError:
            disk_usage_ok = False
            disk_free_mb = -1

        wifi_path = Path("/sys/class/net") / self.settings.wifi_interface

        sensitive_paths = (
            self.settings.root_dir / ".env",
            self.settings.db_path,
            Path(str(self.settings.db_path) + "-wal"),
            Path(str(self.settings.db_path) + "-shm"),
            self.settings.log_path,
            self.settings.runtime_lock_path,
            self.settings.legacy_state_path,
        )
        sensitive_files_private = all(
            _private_file(path)
            for path in sensitive_paths
        )
        rotated_logs_private = all(
            _private_file(path)
            for path in self.settings.log_path.parent.glob(
                self.settings.log_path.name + "*"
            )
        )
        sensitive_files_private = (
            sensitive_files_private and rotated_logs_private
        )

        state_read_ok = True
        try:
            state = self.db.get_operating_state()
        except Exception:
            state = OperatingState.SAFE_MODE
            state_read_ok = False
            # A failed real read invalidates a previously healthy cache.
            self._integrity_checked_at = float("-inf")

        integrity = self._integrity_status()
        integrity_ok = bool(integrity["ok"])
        database_messages = list(
            integrity.get("database_messages", ["unknown"])
        )
        integrity_result = (
            str(database_messages[0])
            if database_messages
            else "unknown"
        )
        foreign_keys_ok = bool(
            integrity.get("foreign_keys_ok", False)
        )
        foreign_key_violations = list(
            integrity.get("foreign_key_violations", [])
        )
        db_file_present = self.settings.db_path.exists()
        db_sizes = self.db.file_sizes_bytes()
        db_size_mb = int(db_sizes["total"] / 1024 / 1024)
        db_file_mb = int(db_sizes["database"] / 1024 / 1024)
        wal_size_mb = int(db_sizes["wal"] / 1024 / 1024)
        shm_size_mb = int(db_sizes["shm"] / 1024 / 1024)

        return HealthSnapshot(
            state=state,
            db_ok=(
                state_read_ok
                and db_file_present
                and self.db.ping()
                and integrity_ok
            ),
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
                "sqlite_foreign_keys_ok": foreign_keys_ok,
                "sqlite_foreign_key_violations": (
                    foreign_key_violations[:20]
                ),
                "db_file_present": db_file_present,
                "db_size_mb": db_size_mb,
                "db_file_mb": db_file_mb,
                "wal_size_mb": wal_size_mb,
                "shm_size_mb": shm_size_mb,
                "db_large": (
                    db_file_mb >= self.settings.db_warn_mb
                ),
                "wal_large": (
                    wal_size_mb >= self.settings.wal_warn_mb
                ),
                "db_warn_mb": self.settings.db_warn_mb,
                "wal_warn_mb": self.settings.wal_warn_mb,
                "disk_usage_ok": disk_usage_ok,
                "disk_low": (
                    disk_usage_ok
                    and disk_free_mb < self.settings.disk_warn_mb
                ),
                "disk_warn_mb": self.settings.disk_warn_mb,
                "configuration_issues": (
                    self.settings.configuration_issues()
                ),
                "operator_count": len(
                    self.settings.admin_user_ids
                ),
            },
        )

    def diagnostics(self) -> dict[str, object]:
        snapshot = self.snapshot()

        ai_latency_read_ok = True
        try:
            latency = self.db.ai_latency_stats(time.time() - 86400)
        except Exception:
            ai_latency_read_ok = False
            latency = {"count": 0, "avg_ms": 0, "p95_ms": 0}

        pragma_read_ok = True
        try:
            pragmas = self.db.runtime_pragmas()
        except Exception:
            pragma_read_ok = False
            pragmas = {
                "journal_mode": "unknown",
                "foreign_keys": 0,
                "busy_timeout_ms": 0,
                "synchronous": -1,
                "wal_autocheckpoint": -1,
                "journal_size_limit": -1,
                "trusted_schema": -1,
                "application_id": 0,
            }

        pragma_issues: list[str] = []
        if pragma_read_ok:
            if pragmas["journal_mode"] != "wal":
                pragma_issues.append("journal_mode")
            if int(pragmas["foreign_keys"]) != 1:
                pragma_issues.append("foreign_keys")
            if int(pragmas["synchronous"]) != 2:
                pragma_issues.append("synchronous")
            if int(pragmas["trusted_schema"]) != 0:
                pragma_issues.append("trusted_schema")
            if int(pragmas["application_id"]) != ZION_APPLICATION_ID:
                pragma_issues.append("application_id")
            if int(pragmas["busy_timeout_ms"]) < 5000:
                pragma_issues.append("busy_timeout")
            if int(pragmas["wal_autocheckpoint"]) != 1000:
                pragma_issues.append("wal_autocheckpoint")
            if int(pragmas["journal_size_limit"]) != 16777216:
                pragma_issues.append("journal_size_limit")

        schema_version_read_ok = True
        try:
            schema_version = self.db.schema_version()
        except Exception:
            schema_version_read_ok = False
            schema_version = -1
        schema_version_ok = (
            schema_version_read_ok
            and schema_version == SUPPORTED_SCHEMA_VERSION
        )

        return {
            "state": snapshot.state.value,
            "db_ok": snapshot.db_ok,
            "sqlite_integrity_ok": bool(
                snapshot.details.get("sqlite_integrity_ok")
            ),
            "sqlite_integrity_result": str(
                snapshot.details.get("sqlite_integrity_result", "unknown")
            ),
            "sqlite_foreign_keys_ok": bool(
                snapshot.details.get("sqlite_foreign_keys_ok")
            ),
            "sqlite_foreign_key_violations": list(
                snapshot.details.get(
                    "sqlite_foreign_key_violations",
                    [],
                )
            ),
            "db_file_present": bool(
                snapshot.details.get("db_file_present")
            ),
            "db_size_mb": int(snapshot.details.get("db_size_mb", 0)),
            "db_file_mb": int(snapshot.details.get("db_file_mb", 0)),
            "wal_size_mb": int(snapshot.details.get("wal_size_mb", 0)),
            "shm_size_mb": int(snapshot.details.get("shm_size_mb", 0)),
            "db_large": bool(snapshot.details.get("db_large")),
            "wal_large": bool(snapshot.details.get("wal_large")),
            "db_warn_mb": int(snapshot.details.get("db_warn_mb", 0)),
            "wal_warn_mb": int(snapshot.details.get("wal_warn_mb", 0)),
            "disk_free_mb": snapshot.disk_free_mb,
            "disk_usage_ok": bool(
                snapshot.details.get("disk_usage_ok")
            ),
            "disk_low": bool(snapshot.details.get("disk_low")),
            "sensitive_files_private": bool(
                snapshot.details.get("sensitive_files_private")
            ),
            "wifi_interface_present": snapshot.wifi_interface_present,
            "ai_latency_24h": latency,
            "ai_latency_read_ok": ai_latency_read_ok,
            "schema_version": schema_version,
            "schema_version_supported": SUPPORTED_SCHEMA_VERSION,
            "schema_version_read_ok": schema_version_read_ok,
            "schema_version_ok": schema_version_ok,
            "sqlite_pragmas": pragmas,
            "sqlite_pragmas_ok": (
                pragma_read_ok and not pragma_issues
            ),
            "sqlite_pragma_read_ok": pragma_read_ok,
            "sqlite_pragma_issues": pragma_issues,
            "configuration_issues": list(
                snapshot.details.get("configuration_issues", ())
            ),
            "operator_count": int(
                snapshot.details.get("operator_count", 0)
            ),
        }

    @staticmethod
    def format_uptime(seconds: int) -> str:
        days, rem = divmod(max(0, seconds), 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        if days:
            return f"{days}d {hours:02d}h {minutes:02d}m"
        return f"{hours:02d}h {minutes:02d}m"
