from __future__ import annotations

import shutil
import time
from pathlib import Path

from .config import Settings
from .db import ZionDB
from .models import HealthSnapshot


class HealthService:
    def __init__(self, settings: Settings, db: ZionDB):
        self.settings = settings
        self.db = db
        self._started_monotonic = time.monotonic()

    def snapshot(self) -> HealthSnapshot:
        try:
            disk = shutil.disk_usage(self.settings.root_dir)
            disk_free_mb = int(disk.free / 1024 / 1024)
        except OSError:
            disk_free_mb = -1

        wifi_path = Path("/sys/class/net") / self.settings.wifi_interface

        return HealthSnapshot(
            state=self.db.get_operating_state(),
            db_ok=self.db.ping(),
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
            },
        )

    @staticmethod
    def format_uptime(seconds: int) -> str:
        days, rem = divmod(max(0, seconds), 86400)
        hours, rem = divmod(rem, 3600)
        minutes, _ = divmod(rem, 60)
        if days:
            return f"{days}d {hours:02d}h {minutes:02d}m"
        return f"{hours:02d}h {minutes:02d}m"
