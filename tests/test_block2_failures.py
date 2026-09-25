from __future__ import annotations

import os
import selectors
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from tests.helpers import make_settings
from zion.db import ZionDB
from zion.health import HealthService


def exercise_wal(db):
    reader = sqlite3.connect(db.path, isolation_level=None)
    try:
        db._conn.execute('PRAGMA wal_autocheckpoint=0')
        db.checkpoint_wal()
        reader.execute('BEGIN')
        before = reader.execute('SELECT COUNT(*) FROM user_events').fetchone()[0]
        initial_wal = db.file_sizes_bytes()['wal']
        writes = initial_wal // 4096 + 20
        for i in range(writes):
            db.record_user_event(chat_id=-9876, user_id=1, event_type='wal-rehearsal', now=i)
        during = reader.execute('SELECT COUNT(*) FROM user_events').fetchone()[0]
        wal_size = db.file_sizes_bytes()['wal']
        checkpoint_held = db.checkpoint_wal()
        assert during == before
        assert db._conn.execute('SELECT COUNT(*) FROM user_events').fetchone()[0] == before + writes
        assert wal_size > initial_wal
        reader.rollback()
        after = reader.execute('SELECT COUNT(*) FROM user_events').fetchone()[0]
        checkpoint_released = db.checkpoint_wal()
        assert after == before + writes
        assert db.verify_integrity(full=True)['ok']
        return dict(writer_count=writes, reader_before=before, reader_during=during, reader_after=after,
                    wal_before=initial_wal, wal_after=wal_size,
                    checkpoint_held=checkpoint_held, checkpoint_released=checkpoint_released)
    finally:
        reader.close()
        db._conn.execute('PRAGMA wal_autocheckpoint=1000')


class Block2FailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = ZionDB(self.root / 'zion.db')
        self.db.initialize()
        self.addCleanup(self.db.close)

    def test_default_busy_timeout_is_bounded_and_recovers(self):
        blocker = sqlite3.connect(self.db.path, isolation_level=None)
        try:
            blocker.execute('BEGIN IMMEDIATE')
            started = time.monotonic()
            with self.assertRaises(sqlite3.OperationalError) as caught:
                with self.db.transaction():
                    self.db.set_setting('partial', 'never')
                    self.db.record_user_event(chat_id=1, user_id=1, event_type='blocked')
            elapsed = time.monotonic() - started
            self.assertEqual(caught.exception.sqlite_errorcode, sqlite3.SQLITE_BUSY)
            self.assertGreaterEqual(elapsed, 4.8)
            self.assertLess(elapsed, 8)
            self.assertFalse(self.db._conn.in_transaction)
            self.assertIsNone(self.db.get_setting('partial'))
        finally:
            blocker.rollback()
            blocker.close()
        self.db.record_user_event(chat_id=1, user_id=1, event_type='recovered')
        self.assertEqual(self.db.count_user_events(chat_id=1, event_type='recovered', since=0), 1)
        self.assertTrue(self.db.verify_integrity(full=True)['ok'])

    def crash(self, commit):
        path = self.root / ('committed.db' if commit else 'uncommitted.db')
        code = '''
import signal, sys
from pathlib import Path
from zion.db import ZionDB
db = ZionDB(Path(sys.argv[1]))
db.initialize()
db._conn.execute('BEGIN IMMEDIATE')
db.set_setting('crash-proof', 'survives')
if sys.argv[2] == 'commit':
    db._conn.commit()
print('READY', flush=True)
signal.pause()
'''
        child = subprocess.Popen([sys.executable, '-c', code, str(path),
                                  'commit' if commit else 'rollback'],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 cwd=Path(__file__).resolve().parents[1])
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                self.assertTrue(selector.select(timeout=10), 'child readiness timeout')
            self.assertEqual(child.stdout.readline(), b'READY\n')
            child.kill()
            child.wait(timeout=5)
            self.assertEqual(child.returncode, -signal.SIGKILL)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            child.stdout.close()
            child.stderr.close()
        reopened = ZionDB(path)
        try:
            self.assertEqual(reopened.get_setting('crash-proof'), 'survives' if commit else None)
            self.assertTrue(reopened.verify_integrity(full=True)['ok'])
            self.assertEqual(reopened.integrity_check(), (True, 'ok'))
        finally:
            reopened.close()

    def test_crash_before_commit_rolls_back(self):
        self.crash(False)

    def test_crash_after_commit_survives(self):
        self.crash(True)

    def test_long_reader_writer_and_passive_checkpoint(self):
        result = exercise_wal(self.db)
        self.assertEqual(result['reader_after'], result['reader_before'] + result['writer_count'])

    def test_nonheader_corruption_fails_health_and_integrity(self):
        path = self.root / 'corrupted.db'
        self.db.backup_to(path)
        raw = sqlite3.connect(path)
        page = raw.execute("SELECT rootpage FROM sqlite_master WHERE name='users'").fetchone()[0]
        page_size = raw.execute('PRAGMA page_size').fetchone()[0]
        raw.close()
        self.assertGreater(page, 1)
        with path.open('r+b') as handle:
            handle.seek((page - 1) * page_size)
            handle.write(b'\xff')  # Invalid b-tree page type; SQLite header unchanged.
        broken = ZionDB(path, readonly=True)
        try:
            self.assertFalse(broken.integrity_check()[0])
            self.assertFalse(broken.full_integrity_check()[0])
            settings = replace(make_settings(self.root), db_path=path)
            health = HealthService(settings, broken)
            self.assertFalse(health.snapshot().db_ok)
            self.assertFalse(health.diagnostics()['sqlite_integrity_ok'])
        finally:
            broken.close()

    def test_runtime_database_wal_shm_are_private(self):
        self.db.set_setting('permissions', 'checked')
        for suffix in ('', '-wal', '-shm'):
            path = Path(str(self.db.path) + suffix)
            self.assertTrue(path.is_file())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o700)

    def test_backup_restore_matches_schema_counts_and_contents(self):
        self.db.set_setting('restore-test', 'value')
        self.db.record_user_event(chat_id=1, user_id=2, event_type='restore')
        path = self.root / 'restored.db'
        original = list(self.db._conn.iterdump())
        self.db.backup_to(path)
        independent = ZionDB(path, readonly=True)
        try:
            self.assertEqual(list(independent._conn.iterdump()), original)
            self.assertTrue(independent.verify_integrity(full=True)['ok'])
            self.assertEqual(independent.schema_version(), self.db.schema_version())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        finally:
            independent.close()

    def test_initialize_preserves_configured_busy_timeout(self):
        other = ZionDB(self.root / 'configured.db', busy_timeout_ms=75)
        try:
            other.initialize()
            self.assertEqual(other.runtime_pragmas()['busy_timeout_ms'], 75)
        finally:
            other.close()

    def test_failed_initialization_preserves_all_original_schema_and_data(self):
        path = self.root / 'legacy.db'
        raw = sqlite3.connect(path)
        raw.executescript("""
            CREATE TABLE scheduled_messages(id TEXT PRIMARY KEY, chat_id INTEGER,
              send_at REAL, text TEXT, status TEXT, created_by INTEGER,
              created_at REAL, sent_at REAL);
            CREATE TABLE recurring_messages(id TEXT PRIMARY KEY, chat_id INTEGER,
              interval_seconds INTEGER, next_send_at REAL, text TEXT, status TEXT,
              created_by INTEGER, created_at REAL, last_sent_at REAL);
            INSERT INTO scheduled_messages VALUES('original', 1, 1, 'preserve',
              'pending', 1, 1, NULL);
        """)
        original = list(raw.iterdump())
        raw.close()
        db = ZionDB(path)
        from unittest.mock import patch
        try:
            with patch.object(db, '_apply_schema_migrations_locked',
                              side_effect=RuntimeError('injected after DDL')):
                with self.assertRaises(RuntimeError):
                    db.initialize()
            self.assertEqual(list(db._conn.iterdump()), original)
            self.assertEqual(db._conn.execute('PRAGMA application_id').fetchone()[0], 0)
            self.assertFalse(db._conn.in_transaction)
            db.initialize()
            self.assertEqual(db.schema_version(), 2)
            self.assertEqual(db._conn.execute(
                "SELECT text FROM scheduled_messages WHERE id='original'"
            ).fetchone()[0], 'preserve')
        finally:
            db.close()

    def test_failed_state_read_cannot_reuse_healthy_cache(self):
        from unittest.mock import patch
        from zion.models import OperatingState
        health = HealthService(replace(make_settings(self.root), db_path=self.db.path), self.db)
        self.assertTrue(health.snapshot().db_ok)
        with patch.object(self.db, 'get_operating_state',
                          side_effect=sqlite3.DatabaseError('injected read failure')), \
             patch.object(self.db, 'verify_integrity', wraps=self.db.verify_integrity) as verify:
            snapshot = health.snapshot()
        self.assertFalse(snapshot.db_ok)
        self.assertEqual(snapshot.state, OperatingState.SAFE_MODE)
        verify.assert_called_once_with(full=False)
