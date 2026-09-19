from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from zion.db import ZionDB
from zion.models import OperatingState, Severity


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "zion.db"
        self.db = ZionDB(self.path)
        self.db.initialize()

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_default_state(self) -> None:
        self.assertEqual(
            self.db.get_operating_state(),
            OperatingState.NORMAL,
        )

    def test_state_round_trip(self) -> None:
        self.db.set_operating_state(OperatingState.LOCKDOWN)
        self.assertEqual(
            self.db.get_operating_state(),
            OperatingState.LOCKDOWN,
        )

    def test_strike_count(self) -> None:
        self.db.add_strike(
            chat_id=1,
            user_id=2,
            reason="flood",
            severity=Severity.MEDIUM,
            source="test",
            ttl_seconds=3600,
            now=100.0,
        )
        self.assertEqual(
            self.db.count_active_strikes(1, 2, now=101.0),
            1,
        )

    def test_incident_and_action(self) -> None:
        incident = self.db.create_incident(
            chat_id=1,
            user_id=2,
            category="test",
            severity=Severity.LOW,
            source="unittest",
        )
        action = self.db.record_action(
            incident_id=incident,
            chat_id=1,
            user_id=2,
            action_type="observe",
            actor_type="test",
            actor_id=None,
            reason="unittest",
            success=True,
        )
        self.assertTrue(incident)
        self.assertTrue(action)
        self.assertEqual(len(self.db.list_incidents()), 1)


if __name__ == "__main__":
    unittest.main()
