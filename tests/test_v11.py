from __future__ import annotations

import sqlite3
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path

from tests.helpers import make_settings, write_test_knowledge_manifest
from zion.db import SUPPORTED_SCHEMA_VERSION, ZionDB
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
        self.assertEqual(
            self.db.schema_version(),
            SUPPORTED_SCHEMA_VERSION,
        )

    def test_idempotency_key_is_atomic_until_expiry(self) -> None:
        self.assertTrue(
            self.db.claim_idempotency_key(
                "telegram_command:123",
                ttl_seconds=60,
                now=1000.0,
            )
        )
        self.assertFalse(
            self.db.claim_idempotency_key(
                "telegram_command:123",
                ttl_seconds=60,
                now=1059.0,
            )
        )
        self.assertTrue(
            self.db.claim_idempotency_key(
                "telegram_command:123",
                ttl_seconds=60,
                now=1060.0,
            )
        )
        self.assertEqual(
            self.db.prune_idempotency_keys(before=1121.0),
            1,
        )

    def test_idempotency_key_is_atomic_across_connections(self) -> None:
        other = ZionDB(self.settings.db_path)
        other.initialize()

        barrier = threading.Barrier(2)
        results: list[bool] = []
        errors: list[BaseException] = []

        def claim(db: ZionDB) -> None:
            try:
                barrier.wait(timeout=2)
                results.append(
                    db.claim_idempotency_key(
                        "telegram_command:atomic",
                        ttl_seconds=3600,
                        now=1000.0,
                    )
                )
            except BaseException as exc:
                errors.append(exc)

        first_thread = threading.Thread(
            target=claim,
            args=(self.db,),
        )
        second_thread = threading.Thread(
            target=claim,
            args=(other,),
        )
        try:
            first_thread.start()
            second_thread.start()
            first_thread.join(timeout=3)
            second_thread.join(timeout=3)

            self.assertFalse(first_thread.is_alive())
            self.assertFalse(second_thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(sorted(results), [False, True])
        finally:
            other.close()

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

        self.assertTrue(
            self.db.claim_recurring_message(
                schedule_id,
                now=1000.0,
            )
        )
        self.assertEqual(
            self.db.due_recurring_messages(now=1000.0),
            [],
        )

        state = self.db.advance_recurring_message(
            schedule_id,
            success=True,
            max_failures=3,
            retry_seconds=60,
            now=1000.0,
        )
        self.assertEqual(state, "active")
        self.assertEqual(
            self.db.due_recurring_messages(now=4599.0),
            [],
        )
        self.assertEqual(
            len(self.db.due_recurring_messages(now=4600.0)),
            1,
        )
        self.assertEqual(
            self.db.community_stats()["active_recurring"],
            1,
        )
        self.assertFalse(
            self.db.cancel_recurring_message(
                schedule_id[:8],
                chat_id=999,
            )
        )
        self.assertTrue(
            self.db.cancel_recurring_message(
                schedule_id[:8],
                chat_id=10,
            )
        )
        self.assertEqual(
            self.db.community_stats()["active_recurring"],
            0,
        )
        self.assertEqual(
            self.db.due_recurring_messages(now=999999.0),
            [],
        )

    def test_atomic_scheduled_claim_allows_only_one_worker(self) -> None:
        schedule_id = self.db.schedule_message(
            chat_id=10,
            send_at=1000.0,
            text="exactly one claimant",
            created_by=1,
        )
        other = ZionDB(self.settings.db_path)
        other.initialize()

        barrier = threading.Barrier(2)
        results: list[int | None] = []
        errors: list[BaseException] = []

        def claim(db: ZionDB) -> None:
            try:
                barrier.wait(timeout=2)
                results.append(
                    db.claim_scheduled_message(
                        schedule_id,
                        now=1000.0,
                    )
                )
            except BaseException as exc:
                errors.append(exc)

        first_thread = threading.Thread(
            target=claim,
            args=(self.db,),
        )
        second_thread = threading.Thread(
            target=claim,
            args=(other,),
        )
        try:
            first_thread.start()
            second_thread.start()
            first_thread.join(timeout=3)
            second_thread.join(timeout=3)
            self.assertFalse(first_thread.is_alive())
            self.assertFalse(second_thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(len(results), 2)
            self.assertEqual(
                sum(result is not None for result in results),
                1,
            )
        finally:
            other.close()

    def test_atomic_recurring_claim_allows_only_one_worker(self) -> None:
        schedule_id = self.db.schedule_recurring_message(
            chat_id=10,
            first_send_at=1000.0,
            interval_seconds=3600,
            text="exactly one recurring claimant",
            created_by=1,
        )
        other = ZionDB(self.settings.db_path)
        other.initialize()

        barrier = threading.Barrier(2)
        results: list[bool] = []
        errors: list[BaseException] = []

        def claim(db: ZionDB) -> None:
            try:
                barrier.wait(timeout=2)
                results.append(
                    db.claim_recurring_message(
                        schedule_id,
                        now=1000.0,
                    )
                )
            except BaseException as exc:
                errors.append(exc)

        first_thread = threading.Thread(
            target=claim,
            args=(self.db,),
        )
        second_thread = threading.Thread(
            target=claim,
            args=(other,),
        )
        try:
            first_thread.start()
            second_thread.start()
            first_thread.join(timeout=3)
            second_thread.join(timeout=3)
            self.assertFalse(first_thread.is_alive())
            self.assertFalse(second_thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(sorted(results), [False, True])
        finally:
            other.close()

    def test_stale_claims_are_quarantined_not_replayed(self) -> None:
        scheduled_id = self.db.schedule_message(
            chat_id=10,
            send_at=1000.0,
            text="unknown outcome",
            created_by=1,
        )
        recurring_id = self.db.schedule_recurring_message(
            chat_id=10,
            first_send_at=1000.0,
            interval_seconds=3600,
            text="unknown recurring outcome",
            created_by=1,
        )

        self.assertEqual(
            self.db.claim_scheduled_message(
                scheduled_id,
                now=1000.0,
            ),
            1,
        )
        self.assertTrue(
            self.db.claim_recurring_message(
                recurring_id,
                now=1000.0,
            )
        )

        not_stale = self.db.quarantine_stale_delivery_claims(
            now=1299.0,
            stale_after_seconds=300,
        )
        self.assertEqual(
            not_stale,
            {
                "scheduled_uncertain": 0,
                "recurring_paused": 0,
            },
        )

        quarantined = self.db.quarantine_stale_delivery_claims(
            now=1301.0,
            stale_after_seconds=300,
        )
        self.assertEqual(
            quarantined,
            {
                "scheduled_uncertain": 1,
                "recurring_paused": 1,
            },
        )

        scheduled = self.db.list_scheduled_messages(limit=1)[0]
        recurring = self.db.list_recurring_messages(limit=1)[0]
        self.assertEqual(scheduled["status"], "uncertain")
        self.assertEqual(
            scheduled["last_error_type"],
            "stale_claim_after_crash",
        )
        self.assertIsNone(scheduled["claimed_at"])
        self.assertEqual(recurring["status"], "paused")
        self.assertEqual(
            recurring["last_error_type"],
            "stale_claim_after_crash",
        )
        self.assertIsNone(recurring["claimed_at"])

        self.assertEqual(
            self.db.due_scheduled_messages(now=9999.0),
            [],
        )
        self.assertEqual(
            self.db.due_recurring_messages(now=9999.0),
            [],
        )

        self.assertTrue(
            self.db.retry_scheduled_message(
                scheduled_id[:8],
                now=1400.0,
            )
        )
        self.assertTrue(
            self.db.resume_recurring_message(
                recurring_id[:8],
                now=1400.0,
            )
        )
        self.assertEqual(
            self.db.due_recurring_messages(now=1400.0),
            [],
        )
        self.assertEqual(
            len(self.db.due_recurring_messages(now=4600.0)),
            1,
        )

    def test_scheduled_delivery_retries_then_manual_recovery(self) -> None:
        schedule_id = self.db.schedule_message(
            chat_id=10,
            send_at=1000.0,
            text="One shot",
            created_by=1,
        )

        attempt = self.db.claim_scheduled_message(
            schedule_id,
            now=1000.0,
        )
        self.assertEqual(attempt, 1)
        self.assertEqual(
            self.db.due_scheduled_messages(now=1000.0),
            [],
        )

        state = self.db.mark_scheduled_message(
            schedule_id,
            success=False,
            max_attempts=2,
            retry_seconds=60,
            error_type="NetworkError",
            now=1000.0,
        )
        self.assertEqual(state, "pending")
        self.assertEqual(
            self.db.due_scheduled_messages(now=1059.0),
            [],
        )
        self.assertEqual(
            len(self.db.due_scheduled_messages(now=1060.0)),
            1,
        )

        attempt = self.db.claim_scheduled_message(
            schedule_id,
            now=1060.0,
        )
        self.assertEqual(attempt, 2)

        state = self.db.mark_scheduled_message(
            schedule_id,
            success=False,
            max_attempts=2,
            retry_seconds=60,
            error_type="NetworkError",
            now=1060.0,
        )
        self.assertEqual(state, "failed")
        self.assertEqual(
            self.db.due_scheduled_messages(now=9999.0),
            [],
        )

        jobs = self.db.list_scheduled_messages()
        self.assertEqual(jobs[0]["attempts"], 2)
        self.assertEqual(jobs[0]["last_error_type"], "NetworkError")

        self.assertTrue(
            self.db.retry_scheduled_message(
                schedule_id[:8],
                now=1100.0,
            )
        )
        due = self.db.due_scheduled_messages(now=1100.0)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["attempts"], 0)

        attempt = self.db.claim_scheduled_message(
            schedule_id,
            now=1100.0,
        )
        self.assertEqual(attempt, 1)

        state = self.db.mark_scheduled_message(
            schedule_id,
            success=True,
            max_attempts=2,
            retry_seconds=60,
            now=1100.0,
        )
        self.assertEqual(state, "sent")

    def test_scheduled_cancellation_is_chat_scoped(self) -> None:
        schedule_id = self.db.schedule_message(
            chat_id=10,
            send_at=2000.0,
            text="cancel me",
            created_by=1,
        )
        self.assertFalse(
            self.db.cancel_scheduled_message(
                schedule_id[:8],
                chat_id=999,
            )
        )
        self.assertTrue(
            self.db.cancel_scheduled_message(
                schedule_id[:8],
                chat_id=10,
            )
        )
        self.assertEqual(
            self.db.due_scheduled_messages(now=9999.0),
            [],
        )

    def test_recurring_delivery_pauses_and_can_resume(self) -> None:
        schedule_id = self.db.schedule_recurring_message(
            chat_id=10,
            first_send_at=1000.0,
            interval_seconds=3600,
            text="Recurring",
            created_by=1,
        )

        self.assertTrue(
            self.db.claim_recurring_message(
                schedule_id,
                now=1000.0,
            )
        )
        state = self.db.advance_recurring_message(
            schedule_id,
            success=False,
            max_failures=2,
            retry_seconds=30,
            error_type="TimedOut",
            now=1000.0,
        )
        self.assertEqual(state, "active")
        self.assertEqual(
            len(self.db.due_recurring_messages(now=1029.0)),
            0,
        )
        self.assertEqual(
            len(self.db.due_recurring_messages(now=1030.0)),
            1,
        )

        self.assertTrue(
            self.db.claim_recurring_message(
                schedule_id,
                now=1030.0,
            )
        )
        state = self.db.advance_recurring_message(
            schedule_id,
            success=False,
            max_failures=2,
            retry_seconds=30,
            error_type="TimedOut",
            now=1030.0,
        )
        self.assertEqual(state, "paused")
        self.assertEqual(
            len(self.db.due_recurring_messages(now=9999.0)),
            0,
        )

        self.assertTrue(
            self.db.resume_recurring_message(
                schedule_id[:8],
                now=1100.0,
            )
        )
        due = self.db.due_recurring_messages(now=1100.0)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["consecutive_failures"], 0)

    def test_legacy_scheduler_schema_is_migrated_in_place(self) -> None:
        self.db.close()

        legacy_path = self.root / "legacy-scheduler.db"
        conn = sqlite3.connect(legacy_path)
        try:
            conn.executescript(
                """
                CREATE TABLE scheduled_messages (
                    id TEXT PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    send_at REAL NOT NULL,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_by INTEGER,
                    created_at REAL NOT NULL,
                    sent_at REAL
                );
                CREATE TABLE recurring_messages (
                    id TEXT PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    interval_seconds INTEGER NOT NULL,
                    next_send_at REAL NOT NULL,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_by INTEGER,
                    created_at REAL NOT NULL,
                    last_sent_at REAL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

        migrated = ZionDB(legacy_path)
        try:
            migrated.initialize()
            self.assertEqual(
                migrated.schema_version(),
                SUPPORTED_SCHEMA_VERSION,
            )
            scheduled_columns = migrated._table_columns_locked(
                "scheduled_messages"
            )
            recurring_columns = migrated._table_columns_locked(
                "recurring_messages"
            )
            self.assertTrue(
                {
                    "attempts",
                    "next_attempt_at",
                    "last_error_type",
                    "claimed_at",
                }.issubset(scheduled_columns)
            )
            self.assertTrue(
                {
                    "consecutive_failures",
                    "last_error_type",
                    "claimed_at",
                }.issubset(recurring_columns)
            )
        finally:
            migrated.close()

        self.db = ZionDB(self.settings.db_path)
        self.db.initialize()

    def test_ama_lifecycle_and_retention(self) -> None:
        ama_id = self.db.create_ama(
            chat_id=10,
            title="Z-SWAP AMA",
            created_by=1,
        )
        active = self.db.active_ama(10)
        self.assertIsNotNone(active)
        self.assertEqual(active["id"], ama_id)
        self.assertEqual(self.db.community_stats()["open_amas"], 1)
        with self.assertRaises(ValueError):
            self.db.create_ama(
                chat_id=10,
                title="Second AMA",
                created_by=1,
            )

        question_id = self.db.add_ama_question(
            ama_id=ama_id,
            chat_id=10,
            user_id=22,
            question="Como funciona o ZION?",
        )
        questions = self.db.list_ama_questions(ama_id)
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["id"], question_id)
        self.assertEqual(
            self.db.community_stats()["pending_ama_questions"],
            1,
        )

        closed = self.db.close_ama(10)
        self.assertIsNotNone(closed)
        self.assertIsNone(self.db.active_ama(10))
        self.assertEqual(self.db.community_stats()["open_amas"], 0)
        self.assertEqual(
            self.db.community_stats()["pending_ama_questions"],
            0,
        )

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
            write_test_knowledge_manifest(root)
            kb = KnowledgeBase(root)
            labels = kb.source_labels("seed phrase security")
            self.assertEqual(
                labels,
                ["official.md — Security"],
            )


if __name__ == "__main__":
    unittest.main()
