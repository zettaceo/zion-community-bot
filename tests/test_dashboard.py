from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from zion.admin_dashboard import _status_payload
from zion.db import ZionDB


class DashboardTests(unittest.TestCase):
    def test_status_payload_is_read_only_operational_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = ZionDB(root / "zion.db")
            db.initialize()

            payload = _status_payload(
                db,
                root_dir=root,
                wifi_interface="definitely-not-a-real-interface",
                started_monotonic=time.monotonic(),
            )

            self.assertEqual(payload["database"], "ok")
            self.assertIn("stats", payload)
            self.assertNotIn("telegram_token", payload)
            self.assertNotIn("mistral_api_key", payload)
            db.close()


if __name__ == "__main__":
    unittest.main()
