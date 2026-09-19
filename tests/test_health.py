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
