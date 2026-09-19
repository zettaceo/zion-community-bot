from __future__ import annotations

import hashlib
import os
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from zion.db import (
    SUPPORTED_SCHEMA_VERSION,
    ZION_APPLICATION_ID,
    ZionDB,
)


class PersistenceHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db_path = self.root / "zion.db"
        self.db = ZionDB(self.db_path)
        self.db.initialize()

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_full_integrity_and_foreign_keys_are_clean(self) -> None:
        verification = self.db.verify_integrity(full=True)
        self.assertTrue(verification["ok"])
        self.assertTrue(verification["database_ok"])
        self.assertTrue(verification["foreign_keys_ok"])
        self.assertEqual(
            verification["database_messages"],
            ["ok"],
        )
        self.assertEqual(
            verification["foreign_key_violations"],
            [],
        )

    def test_backup_captures_committed_wal_state_and_is_private(self) -> None:
        self.db.record_user_event(
            chat_id=10,
            user_id=20,
            event_type="backup-test",
            metadata={"value": "committed"},
            now=1000.0,
        )

        wal = Path(str(self.db_path) + "-wal")
        self.assertTrue(wal.is_file())
        self.assertGreater(wal.stat().st_size, 0)

        backup = self.root / "backups" / "zion.db"
        metadata = self.db.backup_to(backup)

        self.assertTrue(backup.is_file())
        self.assertEqual(
            stat.S_IMODE(backup.stat().st_mode),
            0o600,
        )
        self.assertEqual(
            metadata["schema_version"],
            SUPPORTED_SCHEMA_VERSION,
        )
        self.assertEqual(
            metadata["size_bytes"],
            backup.stat().st_size,
        )

        digest = hashlib.sha256(backup.read_bytes()).hexdigest()
        self.assertEqual(metadata["sha256"], digest)

        restored = ZionDB(backup, readonly=True)
        try:
            self.assertTrue(restored.verify_integrity(full=True)["ok"])
            self.assertEqual(
                restored.count_user_events(
                    chat_id=10,
                    event_type="backup-test",
                    since=0,
                ),
                1,
            )
        finally:
            restored.close()

    def test_backup_supports_pre_migration_database(self) -> None:
        legacy = self.root / "pre-migration.db"
        conn = sqlite3.connect(legacy)
        try:
            conn.execute(
                """
                CREATE TABLE legacy_data(
                    id INTEGER PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO legacy_data(value) VALUES ('preserved')"
            )
            conn.commit()
        finally:
            conn.close()

        source = ZionDB(legacy, readonly=True)
        backup = self.root / "pre-migration-backup.db"
        try:
            metadata = source.backup_to(backup)
        finally:
            source.close()

        self.assertEqual(metadata["schema_version"], 0)
        raw = sqlite3.connect(backup)
        try:
            value = raw.execute(
                "SELECT value FROM legacy_data"
            ).fetchone()[0]
        finally:
            raw.close()
        self.assertEqual(value, "preserved")

    def test_backup_refuses_existing_destination(self) -> None:
        backup = self.root / "backup.db"
        backup.write_bytes(b"do-not-overwrite")

        with self.assertRaises(FileExistsError):
            self.db.backup_to(backup)

        self.assertEqual(
            backup.read_bytes(),
            b"do-not-overwrite",
        )

    def test_backup_refuses_symlink_destination(self) -> None:
        target = self.root / "target.db"
        target.write_bytes(b"target")
        link = self.root / "backup.db"
        link.symlink_to(target)

        with self.assertRaises(RuntimeError):
            self.db.backup_to(link)

        self.assertEqual(target.read_bytes(), b"target")

    def test_corrupt_database_is_detected_and_not_backed_up(self) -> None:
        corrupt = self.root / "corrupt.db"
        corrupt.write_bytes(
            b"this is intentionally not a sqlite database" * 16
        )
        backup = self.root / "corrupt-backup.db"

        broken = ZionDB(corrupt, readonly=True)
        try:
            verification = broken.verify_integrity(full=True)
            self.assertFalse(verification["ok"])
            with self.assertRaises(RuntimeError):
                broken.backup_to(backup)
            self.assertFalse(backup.exists())
        finally:
            broken.close()

    def test_foreign_key_corruption_is_detected(self) -> None:
        self.db.close()

        raw = sqlite3.connect(self.db_path)
        try:
            raw.execute("PRAGMA foreign_keys=OFF")
            raw.execute(
                """
                INSERT INTO ama_questions(
                    id, ama_id, chat_id, user_id,
                    question, status, created_at
                )
                VALUES (
                    'broken-question', 'missing-session',
                    1, 2, 'orphan', 'pending', 1
                )
                """
            )
            raw.commit()
        finally:
            raw.close()

        self.db = ZionDB(self.db_path)
        self.db.initialize()
        verification = self.db.verify_integrity(full=True)

        self.assertFalse(verification["ok"])
        self.assertTrue(verification["database_ok"])
        self.assertFalse(verification["foreign_keys_ok"])
        self.assertGreater(
            len(verification["foreign_key_violations"]),
            0,
        )

    def test_new_database_gets_zion_application_id(self) -> None:
        pragmas = self.db.runtime_pragmas()
        self.assertEqual(
            pragmas["application_id"],
            ZION_APPLICATION_ID,
        )

    def test_unidentified_sqlite_database_is_rejected_untouched(self) -> None:
        foreign = self.root / "foreign.db"
        conn = sqlite3.connect(foreign)
        try:
            conn.execute(
                """
                CREATE TABLE customer_records(
                    id INTEGER PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "INSERT INTO customer_records(value) VALUES ('keep-me')"
            )
            conn.commit()
        finally:
            conn.close()

        other = ZionDB(foreign)
        try:
            with self.assertRaises(RuntimeError):
                other.initialize()

            tables = {
                str(row["name"])
                for row in other._conn.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type='table'
                      AND name NOT LIKE 'sqlite_%'
                    """
                ).fetchall()
            }
            self.assertEqual(tables, {"customer_records"})
            value = other._conn.execute(
                "SELECT value FROM customer_records"
            ).fetchone()[0]
            self.assertEqual(value, "keep-me")
            self.assertEqual(
                other._conn.execute(
                    "PRAGMA application_id"
                ).fetchone()[0],
                0,
            )
        finally:
            other.close()

    def test_legacy_zion_database_adopts_application_id(self) -> None:
        self.db.close()

        legacy = self.root / "legacy-identity.db"
        conn = sqlite3.connect(legacy)
        try:
            conn.executescript(
                """
                CREATE TABLE scheduled_messages(
                    id TEXT PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    send_at REAL NOT NULL,
                    text TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_by INTEGER,
                    created_at REAL NOT NULL,
                    sent_at REAL
                );
                CREATE TABLE recurring_messages(
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

        adopted = ZionDB(legacy)
        try:
            adopted.initialize()
            self.assertEqual(
                adopted.runtime_pragmas()["application_id"],
                ZION_APPLICATION_ID,
            )
        finally:
            adopted.close()

        self.db = ZionDB(self.db_path)
        self.db.initialize()

    def test_future_schema_is_rejected_before_mutation(self) -> None:
        future_path = self.root / "future.db"
        conn = sqlite3.connect(future_path)
        try:
            conn.execute(
                f"PRAGMA application_id={ZION_APPLICATION_ID}"
            )
            conn.execute(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO schema_migrations(version, name, applied_at)
                VALUES (?, 'future', 1)
                """,
                (SUPPORTED_SCHEMA_VERSION + 1,),
            )
            conn.commit()
        finally:
            conn.close()

        future = ZionDB(future_path)
        try:
            with self.assertRaises(RuntimeError):
                future.initialize()

            row = future._conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM sqlite_master
                WHERE type='table' AND name='users'
                """
            ).fetchone()
            self.assertEqual(int(row["count"]), 0)
        finally:
            future.close()

    def test_interrupted_migration_rolls_back_column_and_marker(self) -> None:
        self.db.close()

        legacy_path = self.root / "migration-failure.db"
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
        original = migrated._ensure_column_locked
        calls = 0

        def fail_second_column(
            table: str,
            column: str,
            definition: str,
        ) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("forced migration failure")
            original(table, column, definition)

        migrated._ensure_column_locked = fail_second_column
        try:
            with self.assertRaises(RuntimeError):
                migrated.initialize()

            columns = migrated._table_columns_locked(
                "scheduled_messages"
            )
            self.assertNotIn("attempts", columns)

            row = migrated._conn.execute(
                """
                SELECT COALESCE(MAX(version), 0) AS version
                FROM schema_migrations
                """
            ).fetchone()
            self.assertEqual(int(row["version"]), 0)
        finally:
            migrated.close()

        self.db = ZionDB(self.db_path)
        self.db.initialize()

    def test_commit_failure_rolls_back_and_connection_recovers(self) -> None:
        self.db._conn.executescript(
            """
            CREATE TABLE commit_parent(
                id INTEGER PRIMARY KEY
            );
            CREATE TABLE commit_child(
                id INTEGER PRIMARY KEY,
                parent_id INTEGER NOT NULL,
                FOREIGN KEY(parent_id)
                    REFERENCES commit_parent(id)
                    DEFERRABLE INITIALLY DEFERRED
            );
            """
        )

        with self.assertRaises(sqlite3.IntegrityError):
            with self.db._lock:
                with self.db._transaction_locked(immediate=True):
                    self.db._conn.execute(
                        """
                        INSERT INTO commit_child(id, parent_id)
                        VALUES (1, 999)
                        """
                    )

        self.assertFalse(self.db._conn.in_transaction)
        count = self.db._conn.execute(
            "SELECT COUNT(*) FROM commit_child"
        ).fetchone()[0]
        self.assertEqual(count, 0)

        with self.db._lock:
            with self.db._transaction_locked(immediate=True):
                self.db._conn.execute(
                    "INSERT INTO commit_parent(id) VALUES (999)"
                )
                self.db._conn.execute(
                    """
                    INSERT INTO commit_child(id, parent_id)
                    VALUES (2, 999)
                    """
                )

        count = self.db._conn.execute(
            "SELECT COUNT(*) FROM commit_child"
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_wal_recovers_committed_data_after_sigkill(self) -> None:
        self.db.close()

        repo = Path(__file__).resolve().parent.parent
        code = r'''
import sys
import time
from pathlib import Path
from zion.db import ZionDB

path = Path(sys.argv[1])
db = ZionDB(path)
db.initialize()
db.record_user_event(
    chat_id=7,
    user_id=8,
    event_type="committed-before-crash",
    now=1000.0,
)
db._conn.execute("BEGIN IMMEDIATE")
db._conn.execute(
    """
    INSERT INTO user_events(
        id, chat_id, user_id, event_type,
        created_at, metadata_json
    )
    VALUES (
        'uncommitted-crash-row',
        7, 8, 'uncommitted-before-crash',
        1001.0, '{}'
    )
    """
)
print("READY", flush=True)
time.sleep(30)
'''
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo)

        child = subprocess.Popen(
            [sys.executable, "-c", code, str(self.db_path)],
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        try:
            ready = child.stdout.readline().strip()
            self.assertEqual(ready, "READY")
            os.kill(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)

        self.db = ZionDB(self.db_path)
        self.db.initialize()

        verification = self.db.verify_integrity(full=True)
        self.assertTrue(verification["ok"])
        self.assertEqual(
            self.db.count_user_events(
                chat_id=7,
                event_type="committed-before-crash",
                since=0,
            ),
            1,
        )
        self.assertEqual(
            self.db.count_user_events(
                chat_id=7,
                event_type="uncommitted-before-crash",
                since=0,
            ),
            0,
        )

    def test_busy_writer_times_out_then_recovers_cleanly(self) -> None:
        other = ZionDB(
            self.db_path,
            busy_timeout_ms=50,
        )
        try:
            self.db._conn.execute("BEGIN IMMEDIATE")
            started = time.monotonic()

            with self.assertRaises(sqlite3.OperationalError):
                other.record_user_event(
                    chat_id=1,
                    user_id=2,
                    event_type="blocked",
                )

            elapsed = time.monotonic() - started
            self.assertGreaterEqual(elapsed, 0.03)
            self.assertLess(elapsed, 1.0)

            self.db._conn.rollback()

            other.record_user_event(
                chat_id=1,
                user_id=2,
                event_type="recovered",
            )
            self.assertEqual(
                other.count_user_events(
                    chat_id=1,
                    event_type="recovered",
                    since=0,
                ),
                1,
            )
        finally:
            if self.db._conn.in_transaction:
                self.db._conn.rollback()
            other.close()

    def test_simulated_disk_full_does_not_poison_connection(self) -> None:
        page_count = int(
            self.db._conn.execute("PRAGMA page_count").fetchone()[0]
        )
        self.db._conn.execute(
            f"PRAGMA max_page_count={page_count}"
        )

        with self.assertRaises(sqlite3.OperationalError):
            self.db.schedule_message(
                chat_id=1,
                send_at=1000.0,
                text="x" * (2 * 1024 * 1024),
                created_by=1,
            )

        self.assertFalse(self.db._conn.in_transaction)

        self.db._conn.execute("PRAGMA max_page_count=2147483646")
        schedule_id = self.db.schedule_message(
            chat_id=1,
            send_at=1000.0,
            text="connection recovered",
            created_by=1,
        )
        self.assertTrue(schedule_id)

    def test_concurrent_ama_open_allows_one_session(self) -> None:
        other = ZionDB(self.db_path)
        other.initialize()

        barrier = threading.Barrier(2)
        created: list[str] = []
        errors: list[BaseException] = []

        def open_ama(db: ZionDB, title: str) -> None:
            try:
                barrier.wait(timeout=2)
                created.append(
                    db.create_ama(
                        chat_id=100,
                        title=title,
                        created_by=1,
                    )
                )
            except BaseException as exc:
                errors.append(exc)

        first = threading.Thread(
            target=open_ama,
            args=(self.db, "first"),
        )
        second = threading.Thread(
            target=open_ama,
            args=(other, "second"),
        )
        try:
            first.start()
            second.start()
            first.join(timeout=3)
            second.join(timeout=3)

            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual(len(created), 1)
            self.assertEqual(len(errors), 1)
            self.assertIsInstance(errors[0], ValueError)
            self.assertEqual(
                self.db.community_stats()["open_amas"],
                1,
            )
        finally:
            other.close()

    def test_close_ama_rolls_back_if_question_update_fails(self) -> None:
        ama_id = self.db.create_ama(
            chat_id=200,
            title="rollback test",
            created_by=1,
        )
        self.db.add_ama_question(
            ama_id=ama_id,
            chat_id=200,
            user_id=2,
            question="question",
        )

        self.db._conn.execute(
            """
            CREATE TRIGGER force_ama_question_failure
            BEFORE UPDATE ON ama_questions
            BEGIN
                SELECT RAISE(ABORT, 'forced close failure');
            END
            """
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.db.close_ama(200)

        active = self.db.active_ama(200)
        self.assertIsNotNone(active)
        self.assertEqual(active["id"], ama_id)

        questions = self.db.list_ama_questions(ama_id)
        self.assertEqual(questions[0]["status"], "pending")

    def test_failed_fk_write_does_not_poison_connection(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.add_ama_question(
                ama_id="missing",
                chat_id=1,
                user_id=2,
                question="must fail",
            )

        self.assertFalse(self.db._conn.in_transaction)
        self.db.record_user_event(
            chat_id=1,
            user_id=2,
            event_type="after-fk-failure",
        )
        self.assertEqual(
            self.db.count_user_events(
                chat_id=1,
                event_type="after-fk-failure",
                since=0,
            ),
            1,
        )

    def test_retention_prunes_ephemeral_data_not_uncertain_jobs(self) -> None:
        old = 1000.0
        cutoff = 2000.0

        self.db.record_ai_event(
            chat_id=1,
            user_id=2,
            purpose="old-ai",
            model="test",
            success=True,
        )
        self.db._conn.execute(
            "UPDATE ai_events SET created_at=? WHERE purpose='old-ai'",
            (old,),
        )

        sent_id = self.db.schedule_message(
            chat_id=1,
            send_at=old,
            text="sent",
            created_by=1,
        )
        self.assertEqual(
            self.db.claim_scheduled_message(sent_id, now=old),
            1,
        )
        self.assertEqual(
            self.db.mark_scheduled_message(
                sent_id,
                success=True,
                max_attempts=1,
                retry_seconds=60,
                now=old,
            ),
            "sent",
        )

        uncertain_id = self.db.schedule_message(
            chat_id=1,
            send_at=old,
            text="uncertain",
            created_by=1,
        )
        self.assertEqual(
            self.db.claim_scheduled_message(
                uncertain_id,
                now=old,
            ),
            1,
        )
        self.db.quarantine_stale_delivery_claims(
            now=cutoff,
            stale_after_seconds=1,
        )

        self.db.set_containment(
            chat_id=1,
            user_id=2,
            blocked_until=old,
            reason="expired",
            now=old - 10,
        )

        self.assertEqual(self.db.prune_ai_events(cutoff), 1)
        self.assertEqual(
            self.db.prune_completed_scheduled_messages(cutoff),
            1,
        )
        self.assertEqual(
            self.db.prune_expired_containments(cutoff),
            1,
        )

        scheduled = self.db.list_scheduled_messages(limit=10)
        self.assertEqual(len(scheduled), 1)
        self.assertEqual(scheduled[0]["id"], uncertain_id)
        self.assertEqual(scheduled[0]["status"], "uncertain")

    def test_closed_ama_session_prunes_only_after_questions(self) -> None:
        ama_id = self.db.create_ama(
            chat_id=10,
            title="retention",
            created_by=1,
        )
        self.db.add_ama_question(
            ama_id=ama_id,
            chat_id=10,
            user_id=2,
            question="temporary",
        )
        self.db.close_ama(10)
        self.db._conn.execute(
            "UPDATE ama_sessions SET closed_at=1000 WHERE id=?",
            (ama_id,),
        )

        self.assertEqual(
            self.db.prune_closed_ama_sessions(2000.0),
            0,
        )
        self.assertEqual(
            self.db.prune_ama_questions(2000.0),
            1,
        )
        self.assertEqual(
            self.db.prune_closed_ama_sessions(2000.0),
            1,
        )

    def test_scheduler_status_counters_are_distinct(self) -> None:
        first = self.db.schedule_message(
            chat_id=1,
            send_at=1000.0,
            text="uncertain",
            created_by=1,
        )
        second = self.db.schedule_message(
            chat_id=1,
            send_at=1000.0,
            text="sending",
            created_by=1,
        )

        self.assertEqual(
            self.db.claim_scheduled_message(first, now=1000.0),
            1,
        )
        self.db.quarantine_stale_delivery_claims(
            now=2000.0,
            stale_after_seconds=300,
        )
        self.assertEqual(
            self.db.claim_scheduled_message(second, now=1000.0),
            1,
        )

        stats = self.db.community_stats()
        self.assertEqual(stats["uncertain_scheduled"], 1)
        self.assertEqual(stats["sending_scheduled"], 1)


if __name__ == "__main__":
    unittest.main()
