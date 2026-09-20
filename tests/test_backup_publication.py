from __future__ import annotations

from contextlib import closing
import multiprocessing
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from zion.db import ZionDB


def publish_worker(source, destination, barrier, results):
    db = ZionDB(Path(source), readonly=True)
    real_link = os.link

    def synchronized_link(src, dst):
        barrier.wait(timeout=10)
        return real_link(src, dst)

    try:
        with patch('zion.db.os.link', side_effect=synchronized_link):
            db.backup_to(Path(destination))
        results.put('won')
    except FileExistsError:
        results.put('exists')
    except Exception as exc:
        results.put(type(exc).__name__)
    finally:
        db.close()


class BackupPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = ZionDB(self.root / 'source.db')
        self.db.initialize()
        self.addCleanup(self.db.close)

    def test_concurrent_destination_is_preserved_and_temp_cleaned(self):
        destination = self.root / 'backup.db'
        sentinel = b'concurrent backup must survive'
        verify = self.db.verify_integrity

        def publish_during_verification(*, full=False):
            result = verify(full=full)
            destination.write_bytes(sentinel)
            return result

        with patch.object(self.db, 'verify_integrity',
                          side_effect=publish_during_verification):
            with self.assertRaises(FileExistsError):
                self.db.backup_to(destination)
        self.assertEqual(destination.read_bytes(), sentinel)
        self.assertEqual(list(self.root.glob('*.tmp-*')), [])
        self.assertTrue(self.db.verify_integrity(full=True)['ok'])

    def test_two_processes_publish_exactly_one_complete_backup(self):
        context = multiprocessing.get_context('spawn')
        barrier = context.Barrier(2)
        results = context.Queue()
        destination = self.root / 'backup.db'
        children = [context.Process(target=publish_worker, args=(
            str(self.db.path), str(destination), barrier, results
        )) for _ in range(2)]
        try:
            for child in children:
                child.start()
            for child in children:
                child.join(timeout=15)
                self.assertFalse(child.is_alive())
                self.assertEqual(child.exitcode, 0)
            self.assertCountEqual([results.get(timeout=2) for _ in children],
                                  ['won', 'exists'])
        finally:
            for child in children:
                if child.is_alive():
                    child.kill()
                    child.join(timeout=5)
            results.close()
            results.join_thread()
        with closing(sqlite3.connect(destination)) as restored:
            self.assertEqual(restored.execute('PRAGMA integrity_check').fetchall(),
                             [('ok',)])
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
        self.assertEqual(list(self.root.glob('*.tmp-*')), [])
        self.assertTrue(self.db.verify_integrity(full=True)['ok'])

    def test_publication_sees_only_private_complete_file(self):
        destination = self.root / 'private' / 'backup.db'
        real_link = os.link

        def inspect_then_publish(src, dst):
            self.assertFalse(Path(dst).exists())
            self.assertEqual(stat.S_IMODE(Path(src).stat().st_mode), 0o600)
            with closing(sqlite3.connect(src)) as conn:
                self.assertEqual(conn.execute('PRAGMA quick_check').fetchall(),
                                 [('ok',)])
            real_link(src, dst)

        with patch('zion.db.os.link', side_effect=inspect_then_publish):
            self.db.backup_to(destination)
        self.assertEqual(stat.S_IMODE(destination.parent.stat().st_mode), 0o700)
        self.assertEqual(list(destination.parent.glob('*.tmp-*')), [])

    def test_directory_fsync_failure_is_explicit_and_cleans_temp(self):
        destination = self.root / 'backup.db'
        real_fsync = os.fsync

        def fail_directory(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError('injected directory fsync failure')
            real_fsync(fd)

        with patch('zion.db.os.fsync', side_effect=fail_directory):
            with self.assertRaises(OSError):
                self.db.backup_to(destination)
        self.assertEqual(list(self.root.glob('*.tmp-*')), [])
        # Publication happened: preserve the complete final file, never delete it.
        restored = ZionDB(destination, readonly=True)
        try:
            self.assertTrue(restored.verify_integrity(full=True)['ok'])
        finally:
            restored.close()

    def test_deploy_preserves_env_metadata_without_copying_secret(self):
        script = (Path(__file__).resolve().parents[1] /
                  'scripts/apply-zion-v1.sh').read_text()
        self.assertIn('sha256sum "$ROOT/.env"', script)
        self.assertIn('stat -c', script)
        self.assertIn('A .env NÃO foi duplicada', script)
        self.assertNotRegex(script, r'(?:cp|install|copy2)\s+[^\n]*["/]\.env')
        self.assertLess(script.index('metadata = db.backup_to(target)'),
                        script.index('systemctl stop zion.service'))
