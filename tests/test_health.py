from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_settings
from zion.db import ZionDB
from zion.health import HealthService


class HealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = make_settings(self.root)
        self.db = ZionDB(self.settings.db_path)
        self.db.initialize()
        self.health = HealthService(self.settings, self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_private_sensitive_files_are_healthy(self) -> None:
        env_path = self.root / ".env"
        env_path.write_text("TEST=1\n", encoding="utf-8")
        os.chmod(env_path, 0o600)

        snapshot = self.health.snapshot()
        self.assertTrue(
            snapshot.details["sensitive_files_private"]
        )

    def test_diagnostics_include_sqlite_integrity(self) -> None:
        diagnostics = self.health.diagnostics()
        self.assertTrue(diagnostics["db_ok"])
        self.assertTrue(diagnostics["sqlite_integrity_ok"])
        self.assertEqual(
            diagnostics["sqlite_integrity_result"].lower(),
            "ok",
        )
        self.assertGreaterEqual(diagnostics["db_size_mb"], 0)
        self.assertEqual(
            diagnostics["ai_latency_24h"],
            {"count": 0, "avg_ms": 0, "p95_ms": 0},
        )

    def test_world_readable_env_is_reported(self) -> None:
        env_path = self.root / ".env"
        env_path.write_text("TEST=1\n", encoding="utf-8")
        os.chmod(env_path, 0o644)

        snapshot = self.health.snapshot()
        self.assertFalse(
            snapshot.details["sensitive_files_private"]
        )


if __name__ == "__main__":
    unittest.main()
