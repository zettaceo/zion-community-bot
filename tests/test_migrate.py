from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from zion.db import ZionDB
from zion.migrate import migrate_legacy_guardian_state


class LegacyMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = ZionDB(self.root / "zion.db")
        self.db.initialize()
        self.state = self.root / "zion_state.json"

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_legacy_migration_is_idempotent(self) -> None:
        now = time.time()
        self.state.write_text(
            json.dumps(
                {
                    "message_history": {
                        "10:20": [[now, 1001]],
                    },
                    "flood_blocked_until": {
                        "10:20": now + 600,
                    },
                    "flood_strikes": {
                        "10:20": [2, now],
                    },
                }
            ),
            encoding="utf-8",
        )

        migrate_legacy_guardian_state(self.db, self.state)
        migrate_legacy_guardian_state(self.db, self.state)

        self.assertEqual(
            self.db.get_setting("legacy_guardian_state_imported_v1"),
            "1",
        )
        self.assertEqual(
            self.db.count_recent_messages(
                10,
                20,
                now - 60,
            ),
            1,
        )
        self.assertEqual(
            self.db.count_active_strikes(
                10,
                20,
                now + 1,
                reasons=("legacy_flood",),
            ),
            2,
        )
        self.assertGreater(
            self.db.containment_until(10, 20, now),
            now,
        )

    def test_legacy_strike_keeps_original_one_hour_expiry(self) -> None:
        now = time.time()
        last = now - 120
        self.state.write_text(
            json.dumps(
                {
                    "message_history": {},
                    "flood_blocked_until": {},
                    "flood_strikes": {
                        "10:20": [1, last],
                    },
                }
            ),
            encoding="utf-8",
        )

        migrate_legacy_guardian_state(self.db, self.state)

        rows = self.db.list_active_strikes(
            10,
            20,
            now=now,
            limit=10,
        )
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(
            float(rows[0]["expires_at"]),
            last + 3600,
            delta=1.0,
        )

    def test_expired_legacy_strikes_are_not_reintroduced(self) -> None:
        now = time.time()
        self.state.write_text(
            json.dumps(
                {
                    "message_history": {},
                    "flood_blocked_until": {},
                    "flood_strikes": {
                        "10:20": [3, now - 7200],
                    },
                }
            ),
            encoding="utf-8",
        )

        migrate_legacy_guardian_state(self.db, self.state)

        self.assertEqual(
            self.db.count_active_strikes(
                10,
                20,
                now=now,
                reasons=("legacy_flood",),
            ),
            0,
        )

    def test_malformed_legacy_state_applies_nothing(self) -> None:
        self.state.write_text(
            json.dumps(
                {
                    "message_history": {
                        "10:20": "not-a-list",
                    },
                    "flood_blocked_until": {},
                    "flood_strikes": {},
                }
            ),
            encoding="utf-8",
        )

        migrate_legacy_guardian_state(self.db, self.state)

        self.assertIsNone(
            self.db.get_setting("legacy_guardian_state_imported_v1")
        )
        self.assertEqual(
            self.db.count_recent_messages(10, 20, 0),
            0,
        )

    def test_atomic_import_rolls_back_on_mid_transaction_failure(self) -> None:
        marker = "test_atomic_marker"

        with self.assertRaises(Exception):
            self.db.import_legacy_guardian_state(
                marker=marker,
                recent_messages=[
                    (10, 20, 1001, 100.0),
                    (None, 20, 1002, 101.0),  # type: ignore[arg-type]
                ],
                containments=[],
                strikes=[],
                now=200.0,
            )

        self.assertIsNone(self.db.get_setting(marker))
        self.assertEqual(
            self.db.count_recent_messages(10, 20, 0),
            0,
        )


if __name__ == "__main__":
    unittest.main()
