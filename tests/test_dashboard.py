from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from zion.admin_dashboard import (
    _allowed_dashboard_host,
    _status_payload,
)
from zion.db import ZionDB


class DashboardTests(unittest.TestCase):
    def test_dashboard_host_header_blocks_dns_rebinding(self) -> None:
        self.assertTrue(_allowed_dashboard_host("localhost:8765", 8765))
        self.assertTrue(_allowed_dashboard_host("127.0.0.1:8765", 8765))
        self.assertTrue(_allowed_dashboard_host("[::1]:8765", 8765))
        self.assertFalse(
            _allowed_dashboard_host("attacker.example:8765", 8765)
        )
        self.assertFalse(
            _allowed_dashboard_host("127.0.0.1.attacker.example", 8765)
        )

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

            readonly = ZionDB(root / "zion.db", readonly=True)
            try:
                self.assertTrue(readonly.ping())
                self.assertEqual(readonly.get_operating_state().value, "NORMAL")
                with self.assertRaises(RuntimeError):
                    readonly.initialize()
            finally:
                readonly.close()


if __name__ == "__main__":
    unittest.main()
