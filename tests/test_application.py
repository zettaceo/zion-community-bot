from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_settings
from zion.telegram_app import Runtime, build_application


class ApplicationBuildTests(unittest.TestCase):
    def test_application_builds_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = make_settings(Path(tmp))
            application = build_application(settings)

            runtime = application.bot_data.get("zion_runtime")
            self.assertIsInstance(runtime, Runtime)
            self.assertTrue(application.handlers)

            runtime.db.close()


if __name__ == "__main__":
    unittest.main()
