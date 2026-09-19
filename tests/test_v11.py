from __future__ import annotations

import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from tests.helpers import make_settings
from zion.db import ZionDB
from zion.guardian import Guardian, normalize_policy_domain
from zion.knowledge import KnowledgeBase
from zion.models import OperatingState


class V11DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = make_settings(self.root)
        self.db = ZionDB(self.settings.db_path)
        self.db.initialize()

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_integrity_and_file_size(self) -> None:
        ok, result = self.db.integrity_check()
        self.assertTrue(ok)
        self.assertEqual(result.lower(), "ok")
        self.assertGreater(self.db.file_size_bytes(), 0)

    def test_recurring_message_lifecycle(self) -> None:
        schedule_id = self.db.schedule_recurring_message(
            chat_id=10,
            first_send_at=1000.0,
            interval_seconds=3600,
            text="Daily update",
            created_by=1,
        )
        self.assertEqual(
            self.db.due_recurring_messages(now=999.0),
            [],
        )
        due = self.db.due_recurring_messages(now=1000.0)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["id"], schedule_id)

        self.db.advance_recurring_message(
            schedule_id,
            success=True,
            now=1000.0,
        )
        self.assertEqual(
            self.db.due_recurring_messages(now=4599.0),
            [],
        )
        self.assertEqual(
            len(self.db.due_recurring_messages(now=4600.0)),
            1,
        )
        self.assertTrue(self.db.cancel_recurring_message(schedule_id))
        self.assertEqual(
            self.db.due_recurring_messages(now=999999.0),
            [],
        )

    def test_ama_lifecycle_and_retention(self) -> None:
        ama_id = self.db.create_ama(
            chat_id=10,
            title="Z-SWAP AMA",
            created_by=1,
        )
        active = self.db.active_ama(10)
        self.assertIsNotNone(active)
        self.assertEqual(active["id"], ama_id)

        question_id = self.db.add_ama_question(
            ama_id=ama_id,
            chat_id=10,
            user_id=22,
            question="Como funciona o ZION?",
        )
        questions = self.db.list_ama_questions(ama_id)
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["id"], question_id)

        closed = self.db.close_ama(10)
        self.assertIsNotNone(closed)
        self.assertIsNone(self.db.active_ama(10))

        removed = self.db.prune_ama_questions(time.time() + 1)
        self.assertEqual(removed, 1)


class V11GuardianTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        base = make_settings(self.root)
        self.settings = replace(
            base,
            allow_links=True,
            allowed_domains=frozenset({"example.com"}),
            chat_burst_max_messages=4,
            chat_burst_min_users=2,
            chat_burst_window_seconds=10,
        )
        self.db = ZionDB(self.settings.db_path)
        self.db.initialize()
        self.guardian = Guardian(self.settings, self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_unicode_domain_normalizes_to_idna(self) -> None:
        normalized = normalize_policy_domain(
            "https://例え.テスト/path"
        )
        self.assertIsNotNone(normalized)
        self.assertTrue(normalized.startswith("xn--"))
        self.assertIn(".xn--", normalized)

    def test_unicode_lookalike_does_not_match_ascii_allowlist(self) -> None:
        # First character is Cyrillic small ie, not ASCII e.
        decision = self.guardian.evaluate_links(
            "https://еxample.com/login"
        )
        self.assertTrue(decision.should_delete)
        self.assertTrue(
            any(domain.startswith("xn--") for domain in decision.domains)
        )

    def test_distributed_burst_only_elevates_state(self) -> None:
        now = 5000.0
        self.db.record_recent_message(10, 20, 1, now - 3)
        self.db.record_recent_message(10, 21, 2, now - 2)
        self.db.record_recent_message(10, 20, 3, now - 1)

        decision = self.guardian.evaluate_chat_burst(
            10,
            user_id=22,
            now=now,
        )
        self.assertTrue(decision.triggered)
        self.assertEqual(decision.message_count, 4)
        self.assertEqual(decision.unique_users, 3)
        self.assertEqual(
            self.db.get_operating_state(),
            OperatingState.ELEVATED,
        )
        self.assertEqual(
            self.db.count_active_strikes(10, 22, now),
            0,
        )


class V11KnowledgeTests(unittest.TestCase):
    def test_section_level_source_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "official.md").write_text(
                "# Security\nNever share a seed phrase.\n\n"
                "# Support\nUse official support channels.\n",
                encoding="utf-8",
            )
            kb = KnowledgeBase(root)
            labels = kb.source_labels("seed phrase security")
            self.assertEqual(
                labels,
                ["official.md — Security"],
            )


if __name__ == "__main__":
    unittest.main()
