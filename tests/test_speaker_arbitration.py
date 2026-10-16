from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from zion.agents import (
    DEFAULT_AGENT_REGISTRY,
    AgentId,
    ConversationIntent,
)
from zion.db import SUPPORTED_SCHEMA_VERSION, ZION_APPLICATION_ID, ZionDB
from zion.speaker import (
    InboundMessageIdentity,
    SpeakerArbiter,
    UpdateKind,
)


class SpeakerArbitrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "zion.db"
        self.db = ZionDB(self.path)
        self.db.initialize()
        self.addCleanup(self.db.close)
        self.arbiter = SpeakerArbiter(self.db)
        self.mimir = DEFAULT_AGENT_REGISTRY.get(AgentId.MIMIR)
        self.eir = DEFAULT_AGENT_REGISTRY.get(AgentId.EIR)

    def inbound(
        self,
        *,
        message_id: int = 40,
        update_id: int = 50,
        kind: UpdateKind = UpdateKind.MESSAGE,
    ) -> InboundMessageIdentity:
        return InboundMessageIdentity(
            source_identity=AgentId.ZION.value,
            chat_id=-100123,
            message_id=message_id,
            update_id=update_id,
            update_kind=kind,
        )

    def test_duplicate_update_has_one_speaker_claim(self) -> None:
        inbound = self.inbound()

        first = self.arbiter.claim(
            inbound,
            speaker=self.mimir,
            intent=ConversationIntent.TECHNICAL,
        )
        duplicate = self.arbiter.claim(
            inbound,
            speaker=self.mimir,
            intent=ConversationIntent.TECHNICAL,
        )

        self.assertIsNotNone(first)
        self.assertIsNone(duplicate)

    def test_edit_and_original_share_the_same_claim(self) -> None:
        original = self.inbound(message_id=70, update_id=80)
        edited = self.inbound(
            message_id=70,
            update_id=81,
            kind=UpdateKind.EDITED_MESSAGE,
        )

        first = self.arbiter.claim(
            original,
            speaker=self.mimir,
            intent=ConversationIntent.TECHNICAL,
        )
        second = self.arbiter.claim(
            edited,
            speaker=self.mimir,
            intent=ConversationIntent.TECHNICAL,
        )

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(original.claim_key(), edited.claim_key())

    def test_conflicting_agents_cannot_claim_same_message(self) -> None:
        inbound = self.inbound()
        first = self.arbiter.claim(
            inbound,
            speaker=self.mimir,
            intent=ConversationIntent.TECHNICAL,
        )
        conflicting = self.arbiter.claim(
            inbound,
            speaker=self.eir,
            intent=ConversationIntent.SUPPORT,
        )

        self.assertIsNotNone(first)
        self.assertIsNone(conflicting)
        row = self.db.get_speaker_claim(inbound.claim_key())
        self.assertEqual(row["selected_agent"], AgentId.MIMIR.value)

    def test_intent_outside_profile_authority_is_silenced(self) -> None:
        inbound = self.inbound()
        claim = self.arbiter.claim(
            inbound,
            speaker=self.eir,
            intent=ConversationIntent.TECHNICAL,
        )
        self.assertIsNone(claim)
        self.assertIsNone(self.db.get_speaker_claim(inbound.claim_key()))

    def test_concurrent_connections_acquire_exactly_one_claim(self) -> None:
        inbound = self.inbound(message_id=90, update_id=100)
        barrier = threading.Barrier(9)
        outcomes: list[bool] = []
        errors: list[BaseException] = []

        def worker() -> None:
            connection = ZionDB(self.path)
            try:
                arbiter = SpeakerArbiter(connection)
                barrier.wait()
                result = arbiter.claim(
                    inbound,
                    speaker=self.mimir,
                    intent=ConversationIntent.TECHNICAL,
                )
                outcomes.append(result is not None)
            except BaseException as exc:
                errors.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(outcomes.count(True), 1)
        self.assertEqual(outcomes.count(False), 7)

    def test_failed_safe_retry_is_atomic_and_same_speaker_only(self) -> None:
        inbound = self.inbound(message_id=110, update_id=120)
        first = self.arbiter.claim(
            inbound,
            speaker=self.mimir,
            intent=ConversationIntent.TECHNICAL,
        )
        self.assertIsNotNone(first)
        self.assertTrue(
            self.arbiter.failed_safe(
                first,
                error_type="telegram_rejected_before_send",
                now=20.0,
            )
        )

        wrong_speaker = self.arbiter.claim(
            inbound,
            speaker=self.eir,
            intent=ConversationIntent.SUPPORT,
            allow_failed_safe_retry=True,
            now=21.0,
        )
        retry = self.arbiter.claim(
            inbound,
            speaker=self.mimir,
            intent=ConversationIntent.TECHNICAL,
            allow_failed_safe_retry=True,
            now=22.0,
        )

        self.assertIsNone(wrong_speaker)
        self.assertIsNotNone(retry)
        self.assertEqual(retry.attempt_count, 2)

    def test_sent_and_uncertain_claims_never_retry(self) -> None:
        sent_inbound = self.inbound(message_id=130, update_id=140)
        sent_claim = self.arbiter.claim(
            sent_inbound,
            speaker=self.mimir,
            intent=ConversationIntent.TECHNICAL,
        )
        self.assertTrue(
            self.arbiter.sent(
                sent_claim,
                telegram_message_id=9001,
            )
        )
        self.assertIsNone(
            self.arbiter.claim(
                sent_inbound,
                speaker=self.mimir,
                intent=ConversationIntent.TECHNICAL,
                allow_failed_safe_retry=True,
            )
        )

        uncertain_inbound = self.inbound(message_id=131, update_id=141)
        uncertain_claim = self.arbiter.claim(
            uncertain_inbound,
            speaker=self.mimir,
            intent=ConversationIntent.TECHNICAL,
        )
        self.assertTrue(
            self.arbiter.uncertain(
                uncertain_claim,
                error_type="connection_lost_after_send",
            )
        )
        self.assertIsNone(
            self.arbiter.claim(
                uncertain_inbound,
                speaker=self.mimir,
                intent=ConversationIntent.TECHNICAL,
                allow_failed_safe_retry=True,
            )
        )

    def test_stale_claim_is_quarantined_without_replay(self) -> None:
        inbound = self.inbound(message_id=150, update_id=160)
        claim = self.arbiter.claim(
            inbound,
            speaker=self.mimir,
            intent=ConversationIntent.TECHNICAL,
            now=10.0,
        )
        self.assertIsNotNone(claim)

        count = self.db.quarantine_stale_speaker_claims(
            stale_after_seconds=30,
            now=100.0,
        )
        row = self.db.get_speaker_claim(inbound.claim_key())

        self.assertEqual(count, 1)
        self.assertEqual(row["status"], "uncertain")
        self.assertIsNone(
            self.arbiter.claim(
                inbound,
                speaker=self.mimir,
                intent=ConversationIntent.TECHNICAL,
                allow_failed_safe_retry=True,
            )
        )

    def test_callback_uses_update_identity(self) -> None:
        first = InboundMessageIdentity(
            source_identity=AgentId.ZION.value,
            chat_id=101,
            message_id=None,
            update_id=700,
            update_kind=UpdateKind.CALLBACK_QUERY,
        )
        replay = InboundMessageIdentity(
            source_identity=AgentId.ZION.value,
            chat_id=101,
            message_id=None,
            update_id=700,
            update_kind=UpdateKind.CALLBACK_QUERY,
        )
        self.assertEqual(first.claim_key(), replay.claim_key())

    def test_speaker_claims_store_no_message_text(self) -> None:
        columns = {
            row["name"]
            for row in self.db._conn.execute(
                "PRAGMA table_info(speaker_claims)"
            ).fetchall()
        }
        self.assertFalse(
            columns.intersection({"text", "message_text", "prompt", "body"})
        )


class SpeakerMigrationTests(unittest.TestCase):
    def test_schema_two_database_migrates_to_four_without_data_loss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy.db"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                PRAGMA application_id=1514753870;
                CREATE TABLE settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at REAL NOT NULL
                );
                INSERT INTO schema_migrations VALUES
                    (1, 'scheduler_delivery_reliability', 1.0),
                    (2, 'scheduler_claim_tracking', 2.0);
                INSERT INTO settings VALUES ('sentinel', 'preserved', 1.0);
                """
            )
            connection.commit()
            connection.close()

            db = ZionDB(path)
            try:
                db.initialize()
                self.assertEqual(db.schema_version(), SUPPORTED_SCHEMA_VERSION)
                self.assertEqual(SUPPORTED_SCHEMA_VERSION, 4)
                self.assertEqual(db.get_setting("sentinel"), "preserved")
                pragmas = db.runtime_pragmas()
                self.assertEqual(pragmas["application_id"], ZION_APPLICATION_ID)
                self.assertIsNotNone(
                    db._conn.execute(
                        "SELECT 1 FROM sqlite_master "
                        "WHERE type='table' AND name='speaker_claims'"
                    ).fetchone()
                )
                self.assertIsNotNone(
                    db._conn.execute(
                        "SELECT 1 FROM sqlite_master "
                        "WHERE type='table' AND name='routing_events'"
                    ).fetchone()
                )
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
