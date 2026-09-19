from __future__ import annotations

import stat
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

    def test_symlinked_database_path_is_rejected(self) -> None:
        target = Path(self.temp.name) / "target.db"
        target.write_text("not a database", encoding="utf-8")
        link = Path(self.temp.name) / "linked.db"
        link.symlink_to(target)

        with self.assertRaises(RuntimeError):
            ZionDB(link)

    def test_database_permissions_are_private(self) -> None:
        mode = stat.S_IMODE(self.path.stat().st_mode)
        self.assertEqual(mode, 0o600)

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

    def test_active_strike_details(self) -> None:
        self.db.add_strike(
            chat_id=1,
            user_id=2,
            reason="flood",
            severity=Severity.MEDIUM,
            source="test",
            ttl_seconds=3600,
            now=100.0,
        )
        rows = self.db.list_active_strikes(
            1,
            2,
            now=101.0,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reason"], "flood")

    def test_incident_resolution_by_prefix(self) -> None:
        incident = self.db.create_incident(
            chat_id=1,
            user_id=2,
            category="test",
            severity=Severity.LOW,
            source="unittest",
        )
        found = self.db.get_incident(incident[:12])
        self.assertIsNotNone(found)
        self.assertEqual(found["id"], incident)
        self.assertTrue(
            self.db.set_incident_status(incident[:12], "resolved")
        )
        resolved = self.db.get_incident(incident)
        self.assertEqual(resolved["status"], "resolved")

    def test_user_event_retention_cleanup(self) -> None:
        self.db.record_user_event(
            1,
            2,
            "joined",
            now=100.0,
        )
        self.db.record_user_event(
            1,
            3,
            "joined",
            now=300.0,
        )

        removed = self.db.prune_user_events(200.0)
        self.assertEqual(removed, 1)
        self.assertEqual(
            self.db.count_user_events(
                chat_id=1,
                event_type="joined",
                since=0.0,
            ),
            1,
        )

    def test_knowledge_gap_retention_cleanup(self) -> None:
        self.db.record_knowledge_gap(
            question_hash="old-gap",
            sample_text="old question",
        )
        with self.db._lock:
            self.db._conn.execute(
                """
                UPDATE knowledge_gaps
                SET last_seen=?
                WHERE question_hash=?
                """,
                (100.0, "old-gap"),
            )
            self.db._conn.commit()

        removed = self.db.prune_knowledge_gaps(200.0)
        self.assertEqual(removed, 1)
        self.assertEqual(self.db.list_knowledge_gaps(), [])

    def test_resolved_user_report_retention_cleanup(self) -> None:
        report = self.db.create_incident(
            chat_id=1,
            user_id=2,
            category="user_report",
            severity=Severity.LOW,
            source="community",
            now=100.0,
        )
        self.assertTrue(
            self.db.set_incident_status(report, "resolved")
        )
        with self.db._lock:
            self.db._conn.execute(
                """
                UPDATE incidents
                SET updated_at=?
                WHERE id=?
                """,
                (100.0, report),
            )
            self.db._conn.commit()

        redacted = self.db.redact_resolved_user_reports(200.0)
        self.assertEqual(redacted, 1)
        incident = self.db.get_incident(report)
        self.assertIsNotNone(incident)
        self.assertEqual(incident["note"], "")
        self.assertEqual(
            incident["evidence_json"],
            '{"retention_redacted":true}',
        )

    def test_knowledge_gap_rollup(self) -> None:
        self.db.record_knowledge_gap(
            question_hash="abc123",
            sample_text="Como funciona isso?",
        )
        self.db.record_knowledge_gap(
            question_hash="abc123",
            sample_text="Como funciona isso?",
        )
        gaps = self.db.list_knowledge_gaps()
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["seen_count"], 2)
        self.assertTrue(
            self.db.set_knowledge_gap_status(
                "abc123",
                "resolved",
            )
        )
        self.assertEqual(self.db.list_knowledge_gaps(), [])

    def test_ai_token_usage(self) -> None:
        self.db.record_ai_event(
            chat_id=1,
            user_id=2,
            purpose="test",
            model="test-model",
            success=True,
            input_tokens=120,
            output_tokens=30,
        )
        self.assertEqual(
            self.db.ai_tokens_since(0),
            150,
        )

    def test_database_rejects_invalid_domain_disposition(self) -> None:
        with self.assertRaises(ValueError):
            self.db.set_domain(
                "example.com",
                "maybe",
                "test",
            )

    def test_database_rejects_invalid_incident_fields(self) -> None:
        with self.assertRaises(ValueError):
            self.db.create_incident(
                chat_id=1,
                user_id=2,
                category="test",
                severity="unknown",
                source="test",
            )

        with self.assertRaises(ValueError):
            self.db.create_incident(
                chat_id=1,
                user_id=2,
                category="test",
                severity=Severity.LOW,
                source="test",
                status="pending",
            )

    def test_incident_note_is_bounded(self) -> None:
        incident_id = self.db.create_incident(
            chat_id=1,
            user_id=2,
            category="test",
            severity=Severity.LOW,
            source="test",
            note="x" * 5000,
        )
        incident = self.db.get_incident(incident_id)
        self.assertIsNotNone(incident)
        self.assertEqual(len(incident["note"]), 2000)

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
