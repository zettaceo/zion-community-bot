from __future__ import annotations

import ast
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.helpers import make_settings
from zion.db import ZionDB
from zion.guardian import Guardian
from zion.models import OperatingState
from zion.telegram_app import expire_temporary_state, lockdown_command


class AtomicityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = make_settings(self.root)
        self.db = ZionDB(self.settings.db_path)
        self.db.initialize()
        self.addCleanup(self.db.close)

    def fail_inserts(self, table):
        self.db._conn.execute(
            f"CREATE TEMP TRIGGER fail_{table} BEFORE INSERT ON {table} "
            "BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )

    def test_incident_and_action_rollback_as_one_unit(self):
        self.fail_inserts('actions')
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.transaction():
                incident = self.db.create_incident(
                    chat_id=1, user_id=2, category='test',
                    severity='medium', source='test')
                self.db.record_action(
                    incident_id=incident, chat_id=1, user_id=2,
                    action_type='test', actor_type='test', actor_id=None,
                    reason='test', success=True)
        self.assertEqual(self.db._conn.execute('SELECT COUNT(*) FROM incidents').fetchone()[0], 0)
        self.assertFalse(self.db._conn.in_transaction)

    def test_lockdown_expiration_failure_rolls_back_state(self):
        import asyncio
        self.db.set_setting('operating_state_expires_at', '123')
        self.db._conn.execute("""CREATE TEMP TRIGGER fail_expiration
            BEFORE INSERT ON settings WHEN NEW.key='operating_state_expires_at'
            BEGIN SELECT RAISE(ABORT, 'injected'); END""")
        update = SimpleNamespace(effective_message=object(), effective_user=SimpleNamespace(id=1),
                                 effective_chat=SimpleNamespace(id=1))
        with patch('zion.telegram_app.require_operator', return_value=True), \
             patch('zion.telegram_app.runtime', return_value=SimpleNamespace(db=self.db)):
            with self.assertRaises(sqlite3.IntegrityError):
                asyncio.run(lockdown_command(update, None))
        self.assertEqual(self.db.get_operating_state(), OperatingState.NORMAL)
        self.assertEqual(self.db.get_setting('operating_state_expires_at'), '123')

    def test_expiration_audit_failure_rolls_back_state_and_deadline(self):
        self.db.set_operating_state(OperatingState.ELEVATED)
        self.db.set_setting('operating_state_expires_at', '1')
        self.fail_inserts('actions')
        with self.assertRaises(sqlite3.IntegrityError):
            expire_temporary_state(SimpleNamespace(db=self.db))
        self.assertEqual(self.db.get_operating_state(), OperatingState.ELEVATED)
        self.assertEqual(self.db.get_setting('operating_state_expires_at'), '1')

    def test_flood_containment_failure_preserves_messages_and_strikes(self):
        guardian = Guardian(self.settings, self.db)
        for i in range(2):
            guardian.record_message(chat_id=1, user_id=2, message_id=i, now=100)
        self.fail_inserts('containments')
        with self.assertRaises(sqlite3.IntegrityError):
            guardian.record_message(chat_id=1, user_id=2, message_id=2, now=100)
        self.assertEqual(self.db.count_active_strikes(1, 2, 100), 0)
        self.assertEqual(self.db.count_recent_messages(1, 2, 0), 2)
        self.assertEqual(self.db.containment_until(1, 2, 100), 0)

    def test_scheduler_transition_audit_failure_keeps_claim(self):
        job = self.db.schedule_message(chat_id=1, send_at=1, text='test', created_by=1)
        self.db.claim_scheduled_message(job, now=2)
        self.fail_inserts('actions')
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.transaction():
                self.db.mark_scheduled_message(job, success=True, max_attempts=2, retry_seconds=10)
                self.db.record_action(incident_id=None, chat_id=1, user_id=None,
                    action_type='delivery', actor_type='test', actor_id=None, reason='test', success=True)
        self.assertEqual(self.db.list_scheduled_messages()[0]['status'], 'sending')

    def test_ama_create_and_audit_failure_roll_back(self):
        self.fail_inserts('actions')
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.transaction():
                self.db.create_ama(chat_id=1, title='test', created_by=1)
                self.db.record_action(incident_id=None, chat_id=1, user_id=None,
                    action_type='ama', actor_type='test', actor_id=None, reason='test', success=True)
        self.assertIsNone(self.db.active_ama(1))

    def test_idempotency_claim_rolls_back_with_logical_operation(self):
        with self.assertRaises(RuntimeError):
            with self.db.transaction():
                self.assertTrue(self.db.claim_idempotency_key('key', ttl_seconds=60, now=1))
                raise RuntimeError('injected')
        self.assertTrue(self.db.claim_idempotency_key('key', ttl_seconds=60, now=1))

    def test_nested_transaction_full_preserves_original_error(self):
        pages = self.db._conn.execute('PRAGMA page_count').fetchone()[0]
        self.db._conn.execute(f'PRAGMA max_page_count={pages}')
        with self.assertRaises(sqlite3.OperationalError) as caught:
            with self.db.transaction():
                self.db.set_setting('must_rollback', 'value')
                with self.db.transaction():
                    self.db.schedule_message(chat_id=1, send_at=1, text='x'*(2*1024*1024), created_by=1)
        self.assertEqual(caught.exception.sqlite_errorcode, sqlite3.SQLITE_FULL)
        self.assertIsNone(self.db.get_setting('must_rollback'))
        self.assertFalse(self.db._conn.in_transaction)
        self.assertTrue(self.db.verify_integrity(full=True)['ok'])

    def test_interrupt_rolls_back(self):
        with self.assertRaises(KeyboardInterrupt):
            with self.db.transaction():
                self.db.set_setting('interrupted', '1')
                raise KeyboardInterrupt
        self.assertIsNone(self.db.get_setting('interrupted'))

    def test_concurrent_scheduler_transition_returns_persisted_state(self):
        job = self.db.schedule_message(chat_id=1, send_at=1, text='test', created_by=1)
        self.db.claim_scheduled_message(job, now=2)
        other = ZionDB(self.settings.db_path)
        barrier = threading.Barrier(2)
        results, errors = [], []
        def transition(db, success):
            try:
                barrier.wait(timeout=3)
                results.append(db.mark_scheduled_message(job, success=success,
                    max_attempts=1, retry_seconds=10, now=3))
            except BaseException as exc:
                errors.append(exc)
        children = [threading.Thread(target=transition, args=(db, success))
                    for db, success in [(self.db, True), (other, False)]]
        try:
            for child in children: child.start()
            for child in children:
                child.join(timeout=5)
                self.assertFalse(child.is_alive())
            self.assertEqual(errors, [])
            state = self.db.list_scheduled_messages()[0]['status']
            self.assertEqual(results, [state, state])
        finally:
            other.close()

    def test_no_transaction_scope_spans_network_await(self):
        # Async tasks share an RLock's thread: suspending here would break isolation.
        source = Path(__file__).resolve().parents[1] / 'zion/telegram_app.py'
        for node in ast.walk(ast.parse(source.read_text())):
            if isinstance(node, ast.With) and any(
                isinstance(item.context_expr, ast.Call) and
                isinstance(item.context_expr.func, ast.Attribute) and
                item.context_expr.func.attr == 'transaction' for item in node.items
            ):
                self.assertFalse(any(isinstance(child, ast.Await) for child in ast.walk(node)))

    def test_schema_marker_failure_rolls_back_migration_columns(self):
        path = self.root / 'legacy.db'
        raw = sqlite3.connect(path)
        raw.executescript('''
            CREATE TABLE scheduled_messages(id TEXT PRIMARY KEY, chat_id INTEGER,
              send_at REAL, text TEXT, status TEXT, created_by INTEGER,
              created_at REAL, sent_at REAL);
            CREATE TABLE recurring_messages(id TEXT PRIMARY KEY, chat_id INTEGER,
              interval_seconds INTEGER, next_send_at REAL, text TEXT, status TEXT,
              created_by INTEGER, created_at REAL, last_sent_at REAL);
            CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY,
              name TEXT NOT NULL, applied_at REAL NOT NULL);
            CREATE TRIGGER fail_marker BEFORE INSERT ON schema_migrations
              BEGIN SELECT RAISE(ABORT, 'injected marker failure'); END;
        ''')
        raw.close()
        db = ZionDB(path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                db.initialize()
            self.assertNotIn('attempts', db._table_columns_locked('scheduled_messages'))
            self.assertEqual(db.schema_version(), 0)
            self.assertFalse(db._conn.in_transaction)
            db._conn.execute('DROP TRIGGER fail_marker')
            db.initialize()
            self.assertEqual(db.schema_version(), 2)
            before = list(db._conn.iterdump())
            db.initialize()
            self.assertEqual(list(db._conn.iterdump()), before)
        finally:
            db.close()

    def test_future_schema_does_not_adopt_application_id(self):
        self.db._conn.execute('PRAGMA application_id=0')
        self.db._conn.execute("INSERT INTO schema_migrations VALUES (99, 'future', 1)")
        with self.assertRaises(RuntimeError):
            self.db.initialize()
        self.assertEqual(self.db._conn.execute('PRAGMA application_id').fetchone()[0], 0)

    def test_initialize_and_backup_reject_uncommitted_transaction(self):
        with self.db.transaction():
            self.db.set_setting('pending', '1')
            with self.assertRaises(RuntimeError):
                self.db.initialize()
            with self.assertRaises(RuntimeError):
                self.db.backup_to(self.root / 'uncommitted.db')
            self.assertTrue(self.db._conn.in_transaction)
        self.assertEqual(self.db.get_setting('pending'), '1')
