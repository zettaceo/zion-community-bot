#!/usr/bin/env python3
"""Read-only source backup and migration/WAL/restore rehearsal in private /tmp.

Print only metadata and counts. Never initialize or chmod the source.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zion.db import ZionDB
from tests.test_block2_failures import exercise_wal


def counts(conn):
    return {name: conn.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
            for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()}


def checks(conn):
    result = {name: [tuple(row) for row in conn.execute('PRAGMA ' + name)]
              for name in ('quick_check', 'integrity_check')}
    if any(rows != [('ok',)] for rows in result.values()):
        raise RuntimeError('STOP: SQLite integrity failure')
    return result


def snapshot(conn, columns):
    # Used exclusively on disposable copies; values never leave memory.
    return {table: [tuple(row) for row in conn.execute(
        'SELECT ' + ','.join('"' + col.replace('"', '""') + '"' for col in names)
        + ' FROM "' + table.replace('"', '""') + '" ORDER BY rowid')]
        for table, names in columns.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix='zion-block2-' + datetime.datetime.now(
        datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-'))
    root.chmod(0o700)
    path = root / 'zion.db'
    source = sqlite3.connect(args.source.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        source.execute('BEGIN')
        report = {'directory': str(root), 'source_checks': checks(source),
                  'source_counts': counts(source)}
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        copy = sqlite3.connect(path)
        try:
            source.backup(copy)
            report['copy_checks'] = checks(copy)
            report['copy_counts'] = counts(copy)
        finally:
            copy.close()
        assert report['source_counts'] == report['copy_counts']
    finally:
        source.rollback()
        source.close()
    report.update(copy_size=path.stat().st_size,
                  copy_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                  directory_mode=oct(root.stat().st_mode & 0o777),
                  copy_mode=oct(path.stat().st_mode & 0o777))
    db = ZionDB(path)
    try:
        columns = {table: [row[1] for row in db._conn.execute(
            'PRAGMA table_info("' + table.replace('"', '""') + '")')]
            for table in report['copy_counts']}
        before = snapshot(db._conn, columns)
        report['schema_before'] = db.schema_version()
        db.initialize()
        report['original_values_preserved'] = before == snapshot(db._conn, columns)
        assert report['original_values_preserved']
        report['schema_after'] = db.schema_version()
        report['migration_rows'] = [dict(row) for row in db._conn.execute(
            'SELECT version,name,applied_at FROM schema_migrations ORDER BY version')]
        report['counts_after'] = counts(db._conn)
        report['pragmas'] = db.runtime_pragmas()
        report['migration_checks'] = checks(db._conn)
        first = list(db._conn.iterdump())
        db.initialize()
        report['second_initialize_identical'] = first == list(db._conn.iterdump())
        assert report['second_initialize_identical']
        backup = root / 'migrated-backup.db'
        report['restore_backup'] = db.backup_to(backup)
    finally:
        db.close()
    restored = ZionDB(backup, readonly=True)
    try:
        report['restore_checks'] = checks(restored._conn)
        report['restore_counts'] = counts(restored._conn)
        report['restore_identical'] = first == list(restored._conn.iterdump())
        assert report['restore_identical']
        report['restore_mode'] = oct(backup.stat().st_mode & 0o777)
    finally:
        restored.close()
    db = ZionDB(path)
    try:
        db.initialize()
        blocker = sqlite3.connect(path, isolation_level=None)
        try:
            blocker.execute('BEGIN IMMEDIATE')
            started = time.monotonic()
            try:
                with db.transaction():
                    db.set_setting('block2-must-not-commit', '1')
            except sqlite3.OperationalError as exc:
                report['busy'] = dict(elapsed_seconds=time.monotonic()-started,
                                      error=exc.sqlite_errorname,
                                      in_transaction=db._conn.in_transaction)
            else:
                raise AssertionError('Expected SQLITE_BUSY')
        finally:
            blocker.rollback()
            blocker.close()
        assert report['busy']['error'] == 'SQLITE_BUSY'
        assert 4.8 <= report['busy']['elapsed_seconds'] < 8
        assert db.get_setting('block2-must-not-commit') is None
        report['wal'] = exercise_wal(db)
        report['post_failure_checks'] = checks(db._conn)
    finally:
        db.close()
    report['tested_head'] = __import__('subprocess').check_output(
        ['/usr/bin/git', 'rev-parse', 'HEAD'], cwd=Path(__file__).resolve().parents[1], text=True).strip()
    evidence = root / 'evidence.json'
    fd = os.open(evidence, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
