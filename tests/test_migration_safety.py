from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from zion.db import ZionDB
from zion.migrate import (
    MAX_LEGACY_STATE_BYTES,
    migrate_legacy_guardian_state,
)


class LegacyMigrationSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = ZionDB(self.root / "zion.db")
        self.db.initialize()

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_symlinked_legacy_state_is_rejected_without_marker(self) -> None:
        target = self.root / "real.json"
        target.write_text("{}", encoding="utf-8")
        link = self.root / "zion_state.json"
        link.symlink_to(target)

        migrate_legacy_guardian_state(self.db, link)

        self.assertIsNone(
            self.db.get_setting("legacy_guardian_state_imported_v1")
        )

    def test_oversized_legacy_state_is_rejected_without_marker(self) -> None:
        path = self.root / "zion_state.json"
        with path.open("wb") as handle:
            handle.truncate(MAX_LEGACY_STATE_BYTES + 1)

        migrate_legacy_guardian_state(self.db, path)

        self.assertIsNone(
            self.db.get_setting("legacy_guardian_state_imported_v1")
        )

    def test_valid_legacy_state_imports_once(self) -> None:
        path = self.root / "zion_state.json"
        payload = {
            "message_history": {
                "10:20": [],
            },
            "flood_blocked_until": {},
            "flood_strikes": {},
        }
        path.write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

        migrate_legacy_guardian_state(self.db, path)
        self.assertEqual(
            self.db.get_setting("legacy_guardian_state_imported_v1"),
            "1",
        )

        before = self.db.stats()
        migrate_legacy_guardian_state(self.db, path)
        after = self.db.stats()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
