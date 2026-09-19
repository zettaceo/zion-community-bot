from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .models import OperatingState, Severity


SUPPORTED_SCHEMA_VERSION = 2
DEFAULT_BUSY_TIMEOUT_MS = 5000

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
PRAGMA wal_autocheckpoint=1000;
PRAGMA journal_size_limit=16777216;

CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT,
    first_name TEXT,
    language_code TEXT,
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS user_events (
    id TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    created_at REAL NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_user_events_user
ON user_events(chat_id, user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_events_type_window
ON user_events(chat_id, event_type, created_at DESC);

CREATE TABLE IF NOT EXISTS strikes (
    id TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    severity TEXT NOT NULL,
    source TEXT NOT NULL,
    occurred_at REAL NOT NULL,
    expires_at REAL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_strikes_active
ON strikes(chat_id, user_id, expires_at, occurred_at DESC);

CREATE TABLE IF NOT EXISTS containments (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    blocked_until REAL NOT NULL,
    reason TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS recent_messages (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (chat_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_recent_messages_user
ON recent_messages(chat_id, user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_recent_messages_created
ON recent_messages(created_at);

CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    chat_id INTEGER,
    user_id INTEGER,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    note TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_incidents_created
ON incidents(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_incidents_retention
ON incidents(category, status, updated_at);

CREATE TABLE IF NOT EXISTS actions (
    id TEXT PRIMARY KEY,
    incident_id TEXT,
    chat_id INTEGER,
    user_id INTEGER,
    action_type TEXT NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id TEXT,
    reason TEXT NOT NULL,
    success INTEGER NOT NULL,
    created_at REAL NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_actions_created
ON actions(created_at DESC);

CREATE TABLE IF NOT EXISTS domains (
    domain TEXT PRIMARY KEY,
    disposition TEXT NOT NULL,
    source TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    key TEXT PRIMARY KEY,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_idempotency_expires
ON idempotency_keys(expires_at);

CREATE TABLE IF NOT EXISTS ai_events (
    id TEXT PRIMARY KEY,
    chat_id INTEGER,
    user_id INTEGER,
    purpose TEXT NOT NULL,
    model TEXT NOT NULL,
    success INTEGER NOT NULL,
    category TEXT,
    risk REAL,
    requires_human INTEGER,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    input_hash TEXT,
    created_at REAL NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_ai_events_created
ON ai_events(created_at DESC);

CREATE TABLE IF NOT EXISTS knowledge_gaps (
    question_hash TEXT PRIMARY KEY,
    sample_text TEXT NOT NULL,
    seen_count INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'open',
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_knowledge_gaps_open
ON knowledge_gaps(status, seen_count DESC, last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_knowledge_gaps_last_seen
ON knowledge_gaps(last_seen);

CREATE TABLE IF NOT EXISTS scheduled_messages (
    id TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    send_at REAL NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_by INTEGER,
    created_at REAL NOT NULL,
    sent_at REAL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL,
    last_error_type TEXT,
    claimed_at REAL
);

CREATE INDEX IF NOT EXISTS idx_scheduled_pending
ON scheduled_messages(status, send_at);


CREATE TABLE IF NOT EXISTS recurring_messages (
    id TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    interval_seconds INTEGER NOT NULL,
    next_send_at REAL NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_by INTEGER,
    created_at REAL NOT NULL,
    last_sent_at REAL,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_error_type TEXT,
    claimed_at REAL
);

CREATE INDEX IF NOT EXISTS idx_recurring_due
ON recurring_messages(status, next_send_at);

CREATE TABLE IF NOT EXISTS ama_sessions (
    id TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_by INTEGER,
    created_at REAL NOT NULL,
    closed_at REAL
);

CREATE INDEX IF NOT EXISTS idx_ama_sessions_chat
ON ama_sessions(chat_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS ama_questions (
    id TEXT PRIMARY KEY,
    ama_id TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    question TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL,
    FOREIGN KEY (ama_id) REFERENCES ama_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_ama_questions_session
ON ama_questions(ama_id, status, created_at ASC);
"""


def _json(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"))


class ZionDB:
    def __init__(
        self,
        path: Path,
        *,
        readonly: bool = False,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    ):
        self.path = path
        self.readonly = readonly
        self.busy_timeout_ms = max(0, int(busy_timeout_ms))

        if self.path.is_symlink():
            raise RuntimeError("ZION database path must not be a symlink.")
        if not readonly:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

        timeout_seconds = self.busy_timeout_ms / 1000
        if readonly:
            database = self.path.resolve().as_uri() + "?mode=ro"
            self._conn = sqlite3.connect(
                database,
                uri=True,
                timeout=timeout_seconds,
                check_same_thread=False,
                isolation_level=None,
            )
        else:
            self._conn = sqlite3.connect(
                str(path),
                timeout=timeout_seconds,
                check_same_thread=False,
                isolation_level=None,
            )

        self._conn.row_factory = sqlite3.Row
        self._conn.execute(
            f"PRAGMA busy_timeout={self.busy_timeout_ms}"
        )
        if not readonly:
            self._secure_runtime_permissions()

    def _secure_runtime_permissions(self) -> None:
        for candidate in (
            self.path,
            Path(str(self.path) + "-wal"),
            Path(str(self.path) + "-shm"),
        ):
            if not candidate.exists():
                continue
            try:
                os.chmod(candidate, 0o600)
            except OSError:
                # Permission hardening is best-effort here; startup/health
                # remains responsible for surfacing filesystem failures.
                pass

    def initialize(self) -> None:
        if self.readonly:
            raise RuntimeError(
                "Cannot initialize schema through a read-only ZionDB."
            )
        with self._lock:
            existing_version = self._existing_schema_version_locked()
            if existing_version > SUPPORTED_SCHEMA_VERSION:
                raise RuntimeError(
                    "Database schema is newer than this ZION build: "
                    f"db=v{existing_version} "
                    f"supported=v{SUPPORTED_SCHEMA_VERSION}"
                )

            self._conn.executescript(SCHEMA)
            self._apply_schema_migrations_locked()

        if self.get_setting("operating_state") is None:
            self.set_setting("operating_state", OperatingState.NORMAL.value)
        self._secure_runtime_permissions()

    def _existing_schema_version_locked(self) -> int:
        row = self._conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table' AND name='schema_migrations'
            """
        ).fetchone()
        if not row:
            return 0

        version = self._conn.execute(
            "SELECT COALESCE(MAX(version), 0) AS version "
            "FROM schema_migrations"
        ).fetchone()
        return int(version["version"]) if version else 0

    @contextmanager
    def _transaction_locked(
        self,
        *,
        immediate: bool = False,
    ) -> Iterator[None]:
        if self.readonly:
            raise RuntimeError(
                "Cannot start a write transaction on a read-only ZionDB."
            )
        if self._conn.in_transaction:
            savepoint = "sp_" + uuid.uuid4().hex
            self._conn.execute(f"SAVEPOINT {savepoint}")
            try:
                yield
            except Exception:
                self._conn.execute(
                    f"ROLLBACK TO SAVEPOINT {savepoint}"
                )
                self._conn.execute(f"RELEASE SAVEPOINT {savepoint}")
                raise
            else:
                self._conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            return

        self._conn.execute(
            "BEGIN IMMEDIATE" if immediate else "BEGIN"
        )
        try:
            yield
        except Exception:
            self._conn.rollback()
            raise
        else:
            self._conn.commit()

    def _table_columns_locked(self, table: str) -> set[str]:
        rows = self._conn.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
        return {str(row["name"]) for row in rows}

    def _ensure_column_locked(
        self,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        if column in self._table_columns_locked(table):
            return
        self._conn.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )

    def _apply_schema_migrations_locked(self) -> None:
        migrations: tuple[
            tuple[int, str, tuple[tuple[str, str, str], ...]],
            ...
        ] = (
            (
                1,
                "scheduler_delivery_reliability",
                (
                    (
                        "scheduled_messages",
                        "attempts",
                        "INTEGER NOT NULL DEFAULT 0",
                    ),
                    (
                        "scheduled_messages",
                        "next_attempt_at",
                        "REAL",
                    ),
                    (
                        "scheduled_messages",
                        "last_error_type",
                        "TEXT",
                    ),
                    (
                        "recurring_messages",
                        "consecutive_failures",
                        "INTEGER NOT NULL DEFAULT 0",
                    ),
                    (
                        "recurring_messages",
                        "last_error_type",
                        "TEXT",
                    ),
                ),
            ),
            (
                2,
                "scheduler_claim_tracking",
                (
                    (
                        "scheduled_messages",
                        "claimed_at",
                        "REAL",
                    ),
                    (
                        "recurring_messages",
                        "claimed_at",
                        "REAL",
                    ),
                ),
            ),
        )

        applied_rows = self._conn.execute(
            "SELECT version FROM schema_migrations"
        ).fetchall()
        applied = {int(row["version"]) for row in applied_rows}

        for version, name, columns in migrations:
            if version in applied:
                continue
            with self._transaction_locked(immediate=True):
                for table, column, definition in columns:
                    self._ensure_column_locked(
                        table,
                        column,
                        definition,
                    )
                self._conn.execute(
                    """
                    INSERT INTO schema_migrations(
                        version, name, applied_at
                    )
                    VALUES (?, ?, ?)
                    """,
                    (version, name, time.time()),
                )

        with self._transaction_locked(immediate=True):
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_scheduled_retry
                ON scheduled_messages(status, next_attempt_at)
                """
            )

        final_version = self._existing_schema_version_locked()
        if final_version != SUPPORTED_SCHEMA_VERSION:
            raise RuntimeError(
                "Unexpected schema version after migrations: "
                f"db=v{final_version} "
                f"supported=v{SUPPORTED_SCHEMA_VERSION}"
            )

    def schema_version(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(version), 0) AS version "
                "FROM schema_migrations"
            ).fetchone()
        return int(row["version"]) if row else 0

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def ping(self) -> bool:
        try:
            with self._lock:
                row = self._conn.execute("SELECT 1 AS ok").fetchone()
            return bool(row and row["ok"] == 1)
        except sqlite3.Error:
            return False

    def integrity_check(self) -> tuple[bool, str]:
        try:
            with self._lock:
                row = self._conn.execute("PRAGMA quick_check").fetchone()
            result = str(row[0]) if row else "no_result"
            return result.lower() == "ok", result
        except sqlite3.Error as exc:
            return False, type(exc).__name__

    def full_integrity_check(
        self,
    ) -> tuple[bool, list[str]]:
        try:
            with self._lock:
                rows = self._conn.execute(
                    "PRAGMA integrity_check"
                ).fetchall()
            messages = [str(row[0]) for row in rows] or ["no_result"]
            return (
                len(messages) == 1
                and messages[0].lower() == "ok",
                messages,
            )
        except sqlite3.Error as exc:
            return False, [type(exc).__name__]

    def foreign_key_check(
        self,
    ) -> tuple[bool, list[str]]:
        try:
            with self._lock:
                rows = self._conn.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()
            violations = [
                ":".join(str(value) for value in row)
                for row in rows
            ]
            return not violations, violations
        except sqlite3.Error as exc:
            return False, [type(exc).__name__]

    def verify_integrity(
        self,
        *,
        full: bool = False,
    ) -> dict[str, Any]:
        if full:
            database_ok, database_messages = (
                self.full_integrity_check()
            )
        else:
            quick_ok, quick_result = self.integrity_check()
            database_ok = quick_ok
            database_messages = [quick_result]

        foreign_keys_ok, violations = self.foreign_key_check()
        return {
            "ok": database_ok and foreign_keys_ok,
            "database_ok": database_ok,
            "database_messages": database_messages,
            "foreign_keys_ok": foreign_keys_ok,
            "foreign_key_violations": violations,
        }

    def backup_to(self, destination: Path) -> dict[str, Any]:
        destination = destination.expanduser()
        if destination.is_symlink():
            raise RuntimeError(
                "SQLite backup destination must not be a symlink."
            )
        if destination.exists():
            raise FileExistsError(
                f"SQLite backup already exists: {destination}"
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_name(
            destination.name + ".tmp-" + uuid.uuid4().hex
        )
        dst: sqlite3.Connection | None = None

        try:
            with self._lock:
                source_integrity = self.verify_integrity(full=True)
                if not source_integrity["ok"]:
                    raise RuntimeError(
                        "Source SQLite integrity verification failed."
                    )

                dst = sqlite3.connect(
                    str(tmp),
                    timeout=max(1.0, self.busy_timeout_ms / 1000),
                    isolation_level=None,
                )
                self._conn.backup(dst)

            row = dst.execute(
                "PRAGMA integrity_check"
            ).fetchall()
            database_messages = [str(item[0]) for item in row]
            if not (
                len(database_messages) == 1
                and database_messages[0].lower() == "ok"
            ):
                raise RuntimeError(
                    "Backup SQLite integrity_check failed."
                )

            fk_rows = dst.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            if fk_rows:
                raise RuntimeError(
                    "Backup SQLite foreign_key_check failed."
                )

            dst.close()
            dst = None

            os.chmod(tmp, 0o600)
            with tmp.open("rb") as handle:
                os.fsync(handle.fileno())

            digest = hashlib.sha256()
            with tmp.open("rb") as handle:
                for chunk in iter(
                    lambda: handle.read(1024 * 1024),
                    b"",
                ):
                    digest.update(chunk)

            os.replace(tmp, destination)
            os.chmod(destination, 0o600)

            try:
                directory_fd = os.open(
                    destination.parent,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0),
                )
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass

            return {
                "path": str(destination),
                "sha256": digest.hexdigest(),
                "size_bytes": destination.stat().st_size,
                "schema_version": self.schema_version(),
            }
        except Exception:
            if dst is not None:
                dst.close()
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            raise

    def runtime_pragmas(self) -> dict[str, int | str]:
        with self._lock:
            journal_row = self._conn.execute(
                "PRAGMA journal_mode"
            ).fetchone()
            foreign_row = self._conn.execute(
                "PRAGMA foreign_keys"
            ).fetchone()
            timeout_row = self._conn.execute(
                "PRAGMA busy_timeout"
            ).fetchone()
            synchronous_row = self._conn.execute(
                "PRAGMA synchronous"
            ).fetchone()
            checkpoint_row = self._conn.execute(
                "PRAGMA wal_autocheckpoint"
            ).fetchone()
            journal_limit_row = self._conn.execute(
                "PRAGMA journal_size_limit"
            ).fetchone()

        return {
            "journal_mode": (
                str(journal_row[0]).lower()
                if journal_row
                else "unknown"
            ),
            "foreign_keys": (
                int(foreign_row[0])
                if foreign_row
                else 0
            ),
            "busy_timeout_ms": (
                int(timeout_row[0])
                if timeout_row
                else 0
            ),
            "synchronous": (
                int(synchronous_row[0])
                if synchronous_row
                else -1
            ),
            "wal_autocheckpoint": (
                int(checkpoint_row[0])
                if checkpoint_row
                else -1
            ),
            "journal_size_limit": (
                int(journal_limit_row[0])
                if journal_limit_row
                else -1
            ),
        }

    def checkpoint_wal(self) -> dict[str, int]:
        with self._lock:
            row = self._conn.execute(
                "PRAGMA wal_checkpoint(PASSIVE)"
            ).fetchone()
        if not row:
            return {
                "busy": -1,
                "log_frames": -1,
                "checkpointed_frames": -1,
            }
        return {
            "busy": int(row[0]),
            "log_frames": int(row[1]),
            "checkpointed_frames": int(row[2]),
        }

    def file_size_bytes(self) -> int:
        total = 0
        for candidate in (
            self.path,
            Path(str(self.path) + "-wal"),
            Path(str(self.path) + "-shm"),
        ):
            try:
                total += candidate.stat().st_size
            except OSError:
                pass
        return total

    def import_legacy_guardian_state(
        self,
        *,
        marker: str,
        recent_messages: list[tuple[int, int, int, float]],
        containments: list[tuple[int, int, float, str, float]],
        strikes: list[
            tuple[int, int, int, float, int]
        ],
        now: float,
    ) -> None:
        """Atomically import the legacy JSON guardian state.

        The marker is committed in the same transaction as the data so a
        process failure cannot leave a partially imported state that is then
        duplicated on the next startup.
        """
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")

                for chat_id, user_id, message_id, created_at in recent_messages:
                    self._conn.execute(
                        """
                        INSERT INTO recent_messages(
                            chat_id, user_id, message_id, created_at
                        )
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(chat_id, message_id) DO NOTHING
                        """,
                        (
                            chat_id,
                            user_id,
                            message_id,
                            created_at,
                        ),
                    )

                for (
                    chat_id,
                    user_id,
                    blocked_until,
                    reason,
                    updated_at,
                ) in containments:
                    self._conn.execute(
                        """
                        INSERT INTO containments(
                            chat_id, user_id, blocked_until,
                            reason, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(chat_id, user_id) DO UPDATE SET
                            blocked_until=MAX(
                                containments.blocked_until,
                                excluded.blocked_until
                            ),
                            reason=excluded.reason,
                            updated_at=excluded.updated_at
                        """,
                        (
                            chat_id,
                            user_id,
                            blocked_until,
                            reason,
                            updated_at,
                        ),
                    )

                for (
                    chat_id,
                    user_id,
                    count,
                    last_strike,
                    ttl_seconds,
                ) in strikes:
                    expires_at = last_strike + ttl_seconds
                    for index in range(max(0, count)):
                        strike_id = uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            (
                                "zion:legacy_flood:"
                                f"{chat_id}:{user_id}:"
                                f"{last_strike:.6f}:{index + 1}"
                            ),
                        ).hex
                        self._conn.execute(
                            """
                            INSERT INTO strikes(
                                id, chat_id, user_id, reason,
                                severity, source, occurred_at,
                                expires_at, metadata_json
                            )
                            VALUES (?, ?, ?, 'legacy_flood', ?, ?, ?, ?, ?)
                            ON CONFLICT(id) DO NOTHING
                            """,
                            (
                                strike_id,
                                chat_id,
                                user_id,
                                Severity.MEDIUM.value,
                                "legacy_import",
                                last_strike,
                                expires_at,
                                _json(
                                    {
                                        "legacy_index": index + 1,
                                        "legacy_count": count,
                                    }
                                ),
                            ),
                        )

                self._conn.execute(
                    """
                    INSERT INTO settings(key, value, updated_at)
                    VALUES (?, '1', ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value='1',
                        updated_at=excluded.updated_at
                    """,
                    (marker, now),
                )
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def upsert_user(
        self,
        *,
        chat_id: int,
        user_id: int,
        username: str | None,
        first_name: str | None,
        language_code: str | None,
        increment_messages: bool = False,
        now: float | None = None,
    ) -> None:
        ts = time.time() if now is None else now
        increment = 1 if increment_messages else 0
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO users (
                    chat_id, user_id, username, first_name,
                    language_code, first_seen, last_seen, message_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    username=excluded.username,
                    first_name=excluded.first_name,
                    language_code=excluded.language_code,
                    last_seen=excluded.last_seen,
                    message_count=users.message_count + ?
                """,
                (
                    chat_id,
                    user_id,
                    username,
                    first_name,
                    language_code,
                    ts,
                    ts,
                    increment,
                    increment,
                ),
            )
            self._conn.commit()

    def record_user_event(
        self,
        chat_id: int,
        user_id: int,
        event_type: str,
        metadata: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> str:
        event_id = uuid.uuid4().hex
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO user_events
                (id, chat_id, user_id, event_type, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    chat_id,
                    user_id,
                    event_type,
                    now or time.time(),
                    _json(metadata),
                ),
            )
            self._conn.commit()
        return event_id

    def count_user_events(
        self,
        *,
        chat_id: int,
        event_type: str,
        since: float,
    ) -> int:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM user_events
                WHERE chat_id=? AND event_type=? AND created_at >= ?
                """,
                (chat_id, event_type, since),
            ).fetchone()
        return int(row["count"]) if row else 0

    def prune_user_events(self, before: float) -> int:
        with self._lock:
            cursor = self._conn.execute(
                """
                DELETE FROM user_events
                WHERE created_at < ?
                """,
                (before,),
            )
            self._conn.commit()
        return int(cursor.rowcount)

    def add_strike(
        self,
        *,
        chat_id: int,
        user_id: int,
        reason: str,
        severity: Severity | str,
        source: str,
        ttl_seconds: int | None,
        metadata: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> str:
        ts = time.time() if now is None else now
        strike_id = uuid.uuid4().hex
        severity_value = severity.value if isinstance(severity, Severity) else str(severity)
        expires_at = ts + ttl_seconds if ttl_seconds else None
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO strikes (
                    id, chat_id, user_id, reason, severity, source,
                    occurred_at, expires_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    strike_id,
                    chat_id,
                    user_id,
                    reason,
                    severity_value,
                    source,
                    ts,
                    expires_at,
                    _json(metadata),
                ),
            )
            self._conn.commit()
        return strike_id

    def count_active_strikes(
        self,
        chat_id: int,
        user_id: int,
        now: float | None = None,
        reasons: tuple[str, ...] | None = None,
    ) -> int:
        ts = time.time() if now is None else now
        params: list[Any] = [chat_id, user_id, ts]
        reason_clause = ""

        if reasons:
            placeholders = ",".join("?" for _ in reasons)
            reason_clause = f" AND reason IN ({placeholders})"
            params.extend(reasons)

        with self._lock:
            row = self._conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM strikes
                WHERE chat_id=?
                  AND user_id=?
                  AND (expires_at IS NULL OR expires_at >= ?)
                """
                + reason_clause,
                tuple(params),
            ).fetchone()
        return int(row["count"]) if row else 0

    def list_active_strikes(
        self,
        chat_id: int,
        user_id: int,
        *,
        limit: int = 20,
        now: float | None = None,
    ) -> list[dict[str, Any]]:
        ts = time.time() if now is None else now
        safe_limit = max(1, min(int(limit), 50))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, reason, severity, source,
                       occurred_at, expires_at, metadata_json
                FROM strikes
                WHERE chat_id=?
                  AND user_id=?
                  AND (expires_at IS NULL OR expires_at >= ?)
                ORDER BY occurred_at DESC
                LIMIT ?
                """,
                (chat_id, user_id, ts, safe_limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_containment(
        self,
        chat_id: int,
        user_id: int,
        blocked_until: float,
        reason: str,
        now: float | None = None,
    ) -> None:
        ts = time.time() if now is None else now
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO containments
                (chat_id, user_id, blocked_until, reason, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    blocked_until=excluded.blocked_until,
                    reason=excluded.reason,
                    updated_at=excluded.updated_at
                """,
                (chat_id, user_id, blocked_until, reason, ts),
            )
            self._conn.commit()

    def containment_until(
        self,
        chat_id: int,
        user_id: int,
        now: float | None = None,
    ) -> float:
        ts = time.time() if now is None else now
        with self._lock:
            row = self._conn.execute(
                """
                SELECT blocked_until
                FROM containments
                WHERE chat_id=? AND user_id=?
                """,
                (chat_id, user_id),
            ).fetchone()
            if not row:
                return 0.0
            blocked_until = float(row["blocked_until"])
            if blocked_until <= ts:
                self._conn.execute(
                    "DELETE FROM containments WHERE chat_id=? AND user_id=?",
                    (chat_id, user_id),
                )
                self._conn.commit()
                return 0.0
        return blocked_until

    def clear_containment(self, chat_id: int, user_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM containments WHERE chat_id=? AND user_id=?",
                (chat_id, user_id),
            )
            self._conn.commit()

    def record_recent_message(
        self,
        chat_id: int,
        user_id: int,
        message_id: int,
        created_at: float,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO recent_messages
                (chat_id, user_id, message_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, user_id, message_id, created_at),
            )
            self._conn.commit()

    def prune_recent_messages(self, before: float) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM recent_messages WHERE created_at < ?",
                (before,),
            )
            self._conn.commit()
            return int(cursor.rowcount)

    def count_recent_messages(
        self,
        chat_id: int,
        user_id: int,
        since: float,
    ) -> int:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM recent_messages
                WHERE chat_id=? AND user_id=? AND created_at >= ?
                """,
                (chat_id, user_id, since),
            ).fetchone()
        return int(row["count"]) if row else 0

    def chat_recent_activity(
        self,
        chat_id: int,
        since: float,
    ) -> tuple[int, int]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COUNT(*) AS messages,
                       COUNT(DISTINCT user_id) AS users
                FROM recent_messages
                WHERE chat_id=? AND created_at >= ?
                """,
                (chat_id, since),
            ).fetchone()
        if not row:
            return 0, 0
        return int(row["messages"]), int(row["users"])

    def recent_message_ids(
        self,
        chat_id: int,
        user_id: int,
        since: float,
    ) -> list[int]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT message_id
                FROM recent_messages
                WHERE chat_id=? AND user_id=? AND created_at >= ?
                ORDER BY created_at ASC
                """,
                (chat_id, user_id, since),
            ).fetchall()
        return [int(row["message_id"]) for row in rows]

    def clear_recent_messages(self, chat_id: int, user_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM recent_messages WHERE chat_id=? AND user_id=?",
                (chat_id, user_id),
            )
            self._conn.commit()

    def create_incident(
        self,
        *,
        chat_id: int | None,
        user_id: int | None,
        category: str,
        severity: Severity | str,
        source: str,
        evidence: dict[str, Any] | None = None,
        note: str = "",
        status: str = "open",
        now: float | None = None,
    ) -> str:
        ts = time.time() if now is None else now
        incident_id = uuid.uuid4().hex
        severity_value = (
            severity.value
            if isinstance(severity, Severity)
            else str(severity)
        )
        if severity_value not in {item.value for item in Severity}:
            raise ValueError("invalid incident severity")
        if status not in {"open", "resolved", "ignored"}:
            raise ValueError("invalid incident status")

        safe_note = str(note)[:2000]
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO incidents (
                    id, chat_id, user_id, category, severity, status,
                    source, created_at, updated_at, evidence_json, note
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    chat_id,
                    user_id,
                    category,
                    severity_value,
                    status,
                    source,
                    ts,
                    ts,
                    _json(evidence),
                    safe_note,
                ),
            )
            self._conn.commit()
        return incident_id

    def redact_resolved_user_reports(self, before: float) -> int:
        redacted_evidence = '{"retention_redacted":true}'
        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE incidents
                SET evidence_json=?, note=''
                WHERE category='user_report'
                  AND status IN ('resolved', 'ignored')
                  AND updated_at < ?
                  AND evidence_json <> ?
                """,
                (
                    redacted_evidence,
                    before,
                    redacted_evidence,
                ),
            )
            self._conn.commit()
        return int(cursor.rowcount)

    def get_incident(
        self,
        incident_id_or_prefix: str,
    ) -> dict[str, Any] | None:
        value = incident_id_or_prefix.strip()
        if not value:
            return None

        with self._lock:
            exact = self._conn.execute(
                """
                SELECT *
                FROM incidents
                WHERE id=?
                """,
                (value,),
            ).fetchone()
            if exact:
                return dict(exact)

            rows = self._conn.execute(
                """
                SELECT *
                FROM incidents
                WHERE id LIKE ?
                ORDER BY created_at DESC
                LIMIT 2
                """,
                (value + "%",),
            ).fetchall()

        if len(rows) == 1:
            return dict(rows[0])
        return None

    def set_incident_status(
        self,
        incident_id_or_prefix: str,
        status: str,
    ) -> bool:
        if status not in {"open", "resolved", "ignored"}:
            raise ValueError("invalid incident status")

        incident = self.get_incident(incident_id_or_prefix)
        if not incident:
            return False

        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE incidents
                SET status=?, updated_at=?
                WHERE id=?
                """,
                (status, time.time(), incident["id"]),
            )
            self._conn.commit()
        return cursor.rowcount > 0

    def record_action(
        self,
        *,
        incident_id: str | None,
        chat_id: int | None,
        user_id: int | None,
        action_type: str,
        actor_type: str,
        actor_id: str | None,
        reason: str,
        success: bool,
        metadata: dict[str, Any] | None = None,
        now: float | None = None,
    ) -> str:
        action_id = uuid.uuid4().hex
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO actions (
                    id, incident_id, chat_id, user_id, action_type,
                    actor_type, actor_id, reason, success,
                    created_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action_id,
                    incident_id,
                    chat_id,
                    user_id,
                    action_type,
                    actor_type,
                    actor_id,
                    reason,
                    1 if success else 0,
                    now or time.time(),
                    _json(metadata),
                ),
            )
            self._conn.commit()
        return action_id

    def list_incidents(self, limit: int = 10) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 50))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, chat_id, user_id, category, severity,
                       status, source, created_at, note
                FROM incidents
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def user_summary(self, chat_id: int, user_id: int) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            user = self._conn.execute(
                """
                SELECT *
                FROM users
                WHERE chat_id=? AND user_id=?
                """,
                (chat_id, user_id),
            ).fetchone()
            incidents = self._conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM incidents
                WHERE chat_id=? AND user_id=?
                """,
                (chat_id, user_id),
            ).fetchone()
        return {
            "user": dict(user) if user else None,
            "active_strikes": self.count_active_strikes(chat_id, user_id, now),
            "incidents": int(incidents["count"]) if incidents else 0,
            "contained_until": self.containment_until(chat_id, user_id, now),
        }

    def set_setting(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO settings(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    updated_at=excluded.updated_at
                """,
                (key, value, time.time()),
            )
            self._conn.commit()

    def get_setting(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key=?",
                (key,),
            ).fetchone()
        return str(row["value"]) if row else None

    def claim_idempotency_key(
        self,
        key: str,
        *,
        ttl_seconds: int,
        now: float | None = None,
    ) -> bool:
        value = key.strip()
        if not value:
            raise ValueError("idempotency key must not be empty")

        ts = time.time() if now is None else now
        expires_at = ts + max(60, int(ttl_seconds))

        with self._lock:
            cursor = self._conn.execute(
                """
                INSERT INTO idempotency_keys(key, created_at, expires_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    created_at=excluded.created_at,
                    expires_at=excluded.expires_at
                WHERE idempotency_keys.expires_at <= ?
                """,
                (value[:200], ts, expires_at, ts),
            )
            self._conn.commit()

        return cursor.rowcount == 1

    def prune_idempotency_keys(
        self,
        before: float | None = None,
    ) -> int:
        cutoff = time.time() if before is None else before
        with self._lock:
            cursor = self._conn.execute(
                """
                DELETE FROM idempotency_keys
                WHERE expires_at <= ?
                """,
                (cutoff,),
            )
            self._conn.commit()
        return int(cursor.rowcount)

    def get_operating_state(self) -> OperatingState:
        raw = self.get_setting("operating_state") or OperatingState.NORMAL.value
        try:
            return OperatingState(raw)
        except ValueError:
            return OperatingState.SAFE_MODE

    def set_operating_state(self, state: OperatingState) -> None:
        self.set_setting("operating_state", state.value)

    def set_domain(self, domain: str, disposition: str, source: str) -> None:
        if disposition not in {"allow", "block"}:
            raise ValueError("invalid domain disposition")

        normalized = domain.lower().strip().strip(".")
        if not normalized:
            raise ValueError("empty domain")

        with self._lock:
            self._conn.execute(
                """
                INSERT INTO domains(domain, disposition, source, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(domain) DO UPDATE SET
                    disposition=excluded.disposition,
                    source=excluded.source,
                    updated_at=excluded.updated_at
                """,
                (normalized, disposition, source, time.time()),
            )
            self._conn.commit()

    def domain_disposition(self, domain: str) -> str | None:
        normalized = domain.lower().strip().strip(".")
        with self._lock:
            row = self._conn.execute(
                "SELECT disposition FROM domains WHERE domain=?",
                (normalized,),
            ).fetchone()
        return str(row["disposition"]) if row else None

    def record_knowledge_gap(
        self,
        *,
        question_hash: str,
        sample_text: str,
    ) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO knowledge_gaps (
                    question_hash, sample_text, seen_count,
                    status, first_seen, last_seen
                )
                VALUES (?, ?, 1, 'open', ?, ?)
                ON CONFLICT(question_hash) DO UPDATE SET
                    sample_text=excluded.sample_text,
                    seen_count=knowledge_gaps.seen_count + 1,
                    last_seen=excluded.last_seen,
                    status=CASE
                        WHEN knowledge_gaps.status='ignored' THEN 'ignored'
                        ELSE 'open'
                    END
                """,
                (
                    question_hash,
                    sample_text[:500],
                    now,
                    now,
                ),
            )
            self._conn.commit()

    def prune_knowledge_gaps(self, before: float) -> int:
        with self._lock:
            cursor = self._conn.execute(
                """
                DELETE FROM knowledge_gaps
                WHERE last_seen < ?
                """,
                (before,),
            )
            self._conn.commit()
        return int(cursor.rowcount)

    def list_knowledge_gaps(
        self,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 50))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT question_hash, sample_text, seen_count,
                       status, first_seen, last_seen
                FROM knowledge_gaps
                WHERE status='open'
                ORDER BY seen_count DESC, last_seen DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_knowledge_gap_status(
        self,
        question_hash: str,
        status: str,
    ) -> bool:
        if status not in {"open", "resolved", "ignored"}:
            raise ValueError("invalid knowledge gap status")
        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE knowledge_gaps
                SET status=?, last_seen=?
                WHERE question_hash=?
                """,
                (status, time.time(), question_hash),
            )
            self._conn.commit()
        return cursor.rowcount > 0

    def schedule_message(
        self,
        *,
        chat_id: int,
        send_at: float,
        text: str,
        created_by: int | None,
    ) -> str:
        schedule_id = uuid.uuid4().hex
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO scheduled_messages (
                    id, chat_id, send_at, text, status,
                    created_by, created_at
                )
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    schedule_id,
                    chat_id,
                    send_at,
                    text,
                    created_by,
                    time.time(),
                ),
            )
            self._conn.commit()
        return schedule_id

    def due_scheduled_messages(
        self,
        now: float | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        ts = time.time() if now is None else now
        safe_limit = max(1, min(int(limit), 100))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, chat_id, send_at, text, created_by,
                       attempts, next_attempt_at
                FROM scheduled_messages
                WHERE status='pending'
                  AND COALESCE(next_attempt_at, send_at) <= ?
                ORDER BY COALESCE(next_attempt_at, send_at) ASC
                LIMIT ?
                """,
                (ts, safe_limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def claim_scheduled_message(
        self,
        schedule_id: str,
        now: float | None = None,
    ) -> int | None:
        ts = time.time() if now is None else now
        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE scheduled_messages
                SET status='sending',
                    attempts=attempts + 1,
                    claimed_at=?,
                    last_error_type=NULL
                WHERE id=?
                  AND status='pending'
                  AND COALESCE(next_attempt_at, send_at) <= ?
                """,
                (ts, schedule_id, ts),
            )
            if cursor.rowcount != 1:
                self._conn.commit()
                return None

            row = self._conn.execute(
                """
                SELECT attempts
                FROM scheduled_messages
                WHERE id=?
                """,
                (schedule_id,),
            ).fetchone()
            self._conn.commit()

        return int(row["attempts"]) if row else None

    def mark_scheduled_message(
        self,
        schedule_id: str,
        *,
        success: bool,
        max_attempts: int,
        retry_seconds: int,
        error_type: str | None = None,
        now: float | None = None,
    ) -> str:
        ts = time.time() if now is None else now
        safe_max_attempts = max(1, int(max_attempts))
        safe_retry_seconds = max(10, int(retry_seconds))

        with self._lock:
            row = self._conn.execute(
                """
                SELECT attempts, status
                FROM scheduled_messages
                WHERE id=?
                """,
                (schedule_id,),
            ).fetchone()
            if not row:
                return "missing"

            current_status = str(row["status"])
            if current_status != "sending":
                return current_status

            attempts = int(row["attempts"] or 0)
            if success:
                status = "sent"
                next_attempt_at = None
                sent_at = ts
                last_error_type = None
            elif attempts >= safe_max_attempts:
                status = "failed"
                next_attempt_at = None
                sent_at = None
                last_error_type = (
                    error_type or "delivery_error"
                )[:120]
            else:
                status = "pending"
                next_attempt_at = ts + safe_retry_seconds
                sent_at = None
                last_error_type = (
                    error_type or "delivery_error"
                )[:120]

            self._conn.execute(
                """
                UPDATE scheduled_messages
                SET status=?, sent_at=?,
                    next_attempt_at=?, last_error_type=?,
                    claimed_at=NULL
                WHERE id=? AND status='sending'
                """,
                (
                    status,
                    sent_at,
                    next_attempt_at,
                    last_error_type,
                    schedule_id,
                ),
            )
            self._conn.commit()
        return status

    def cancel_scheduled_message(
        self,
        schedule_id_or_prefix: str,
        *,
        chat_id: int | None = None,
    ) -> bool:
        value = schedule_id_or_prefix.strip()
        if not value:
            return False

        chat_clause = "" if chat_id is None else " AND chat_id=?"
        with self._lock:
            params: list[Any] = [value, value + "%"]
            if chat_id is not None:
                params.append(chat_id)

            rows = self._conn.execute(
                """
                SELECT id
                FROM scheduled_messages
                WHERE (id=? OR id LIKE ?)
                  AND status IN ('pending', 'failed', 'uncertain')
                """
                + chat_clause
                + """
                ORDER BY created_at DESC
                LIMIT 2
                """,
                tuple(params),
            ).fetchall()
            unique_ids = list(dict.fromkeys(str(row["id"]) for row in rows))
            if len(unique_ids) != 1:
                return False

            update_params: list[Any] = [unique_ids[0]]
            update_clause = ""
            if chat_id is not None:
                update_clause = " AND chat_id=?"
                update_params.append(chat_id)

            cursor = self._conn.execute(
                """
                UPDATE scheduled_messages
                SET status='cancelled', next_attempt_at=NULL,
                    claimed_at=NULL
                WHERE id=? AND status IN ('pending', 'failed', 'uncertain')
                """
                + update_clause,
                tuple(update_params),
            )
            self._conn.commit()
        return cursor.rowcount > 0

    def retry_scheduled_message(
        self,
        schedule_id_or_prefix: str,
        now: float | None = None,
    ) -> bool:
        value = schedule_id_or_prefix.strip()
        if not value:
            return False
        ts = time.time() if now is None else now

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id
                FROM scheduled_messages
                WHERE (id=? OR id LIKE ?)
                  AND status IN ('failed', 'uncertain')
                ORDER BY created_at DESC
                LIMIT 2
                """,
                (value, value + "%"),
            ).fetchall()
            unique_ids = list(dict.fromkeys(str(row["id"]) for row in rows))
            if len(unique_ids) != 1:
                return False

            cursor = self._conn.execute(
                """
                UPDATE scheduled_messages
                SET status='pending', attempts=0,
                    next_attempt_at=?, last_error_type=NULL,
                    claimed_at=NULL
                WHERE id=? AND status IN ('failed', 'uncertain')
                """,
                (ts, unique_ids[0]),
            )
            self._conn.commit()
        return cursor.rowcount > 0

    def quarantine_stale_delivery_claims(
        self,
        *,
        now: float | None = None,
        stale_after_seconds: int | None = 300,
    ) -> dict[str, int]:
        ts = time.time() if now is None else now
        cutoff = (
            None
            if stale_after_seconds is None
            else ts - max(0, int(stale_after_seconds))
        )

        with self._lock:
            with self._transaction_locked(immediate=True):
                scheduled = self._conn.execute(
                    """
                    UPDATE scheduled_messages
                    SET status='uncertain',
                        next_attempt_at=NULL,
                        last_error_type='stale_claim_after_crash',
                        claimed_at=NULL
                    WHERE status='sending'
                      AND (
                        ? IS NULL
                        OR claimed_at IS NULL
                        OR claimed_at <= ?
                      )
                    """,
                    (cutoff, cutoff),
                ).rowcount

                recurring = self._conn.execute(
                    """
                    UPDATE recurring_messages
                    SET status='paused',
                        last_error_type='stale_claim_after_crash',
                        claimed_at=NULL
                    WHERE status='sending'
                      AND (
                        ? IS NULL
                        OR claimed_at IS NULL
                        OR claimed_at <= ?
                      )
                    """,
                    (cutoff, cutoff),
                ).rowcount

        return {
            "scheduled_uncertain": int(scheduled),
            "recurring_paused": int(recurring),
        }

    def list_scheduled_messages(
        self,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 50))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, chat_id, send_at, status, attempts,
                       next_attempt_at, last_error_type, claimed_at,
                       created_at, sent_at
                FROM scheduled_messages
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def schedule_recurring_message(
        self,
        *,
        chat_id: int,
        first_send_at: float,
        interval_seconds: int,
        text: str,
        created_by: int | None,
    ) -> str:
        schedule_id = uuid.uuid4().hex
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO recurring_messages (
                    id, chat_id, interval_seconds, next_send_at,
                    text, status, created_by, created_at
                )
                VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    schedule_id,
                    chat_id,
                    max(300, int(interval_seconds)),
                    first_send_at,
                    text[:3500],
                    created_by,
                    time.time(),
                ),
            )
            self._conn.commit()
        return schedule_id

    def due_recurring_messages(
        self,
        now: float | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        ts = time.time() if now is None else now
        safe_limit = max(1, min(int(limit), 100))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, chat_id, interval_seconds,
                       next_send_at, text, created_by,
                       consecutive_failures, last_error_type
                FROM recurring_messages
                WHERE status='active' AND next_send_at <= ?
                ORDER BY next_send_at ASC
                LIMIT ?
                """,
                (ts, safe_limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def claim_recurring_message(
        self,
        schedule_id: str,
        now: float | None = None,
    ) -> bool:
        ts = time.time() if now is None else now
        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE recurring_messages
                SET status='sending',
                    claimed_at=?,
                    last_error_type=NULL
                WHERE id=?
                  AND status='active'
                  AND next_send_at <= ?
                """,
                (ts, schedule_id, ts),
            )
            self._conn.commit()
        return cursor.rowcount == 1

    def advance_recurring_message(
        self,
        schedule_id: str,
        *,
        success: bool,
        max_failures: int,
        retry_seconds: int,
        error_type: str | None = None,
        now: float | None = None,
    ) -> str:
        ts = time.time() if now is None else now
        safe_max_failures = max(1, int(max_failures))
        safe_retry_seconds = max(10, int(retry_seconds))

        with self._lock:
            row = self._conn.execute(
                """
                SELECT interval_seconds, next_send_at,
                       consecutive_failures, status, last_sent_at
                FROM recurring_messages
                WHERE id=?
                """,
                (schedule_id,),
            ).fetchone()
            if not row:
                return "missing"

            current_status = str(row["status"])
            if current_status != "sending":
                return current_status

            interval = max(300, int(row["interval_seconds"]))
            next_at = float(row["next_send_at"])

            if success:
                while next_at <= ts:
                    next_at += interval
                status = "active"
                failures = 0
                last_error_type = None
                last_sent_at = ts
            else:
                failures = int(row["consecutive_failures"] or 0) + 1
                last_error_type = (error_type or "delivery_error")[:120]
                last_sent_at = row["last_sent_at"]
                if failures >= safe_max_failures:
                    status = "paused"
                else:
                    status = "active"
                    next_at = ts + min(interval, safe_retry_seconds)

            self._conn.execute(
                """
                UPDATE recurring_messages
                SET status=?, next_send_at=?, last_sent_at=?,
                    consecutive_failures=?, last_error_type=?,
                    claimed_at=NULL
                WHERE id=? AND status='sending'
                """,
                (
                    status,
                    next_at,
                    last_sent_at,
                    failures,
                    last_error_type,
                    schedule_id,
                ),
            )
            self._conn.commit()
        return status

    def resume_recurring_message(
        self,
        schedule_id_or_prefix: str,
        now: float | None = None,
    ) -> bool:
        value = schedule_id_or_prefix.strip()
        if not value:
            return False
        ts = time.time() if now is None else now

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, interval_seconds, next_send_at, last_error_type
                FROM recurring_messages
                WHERE (id=? OR id LIKE ?)
                  AND status='paused'
                ORDER BY created_at DESC
                LIMIT 2
                """,
                (value, value + "%"),
            ).fetchall()

            unique: dict[str, sqlite3.Row] = {
                str(row["id"]): row
                for row in rows
            }
            if len(unique) != 1:
                return False

            resolved_id, row = next(iter(unique.items()))
            last_error_type = str(row["last_error_type"] or "")

            if last_error_type == "stale_claim_after_crash":
                interval = max(300, int(row["interval_seconds"]))
                next_at = float(row["next_send_at"])
                while next_at <= ts:
                    next_at += interval
            else:
                next_at = ts

            cursor = self._conn.execute(
                """
                UPDATE recurring_messages
                SET status='active', consecutive_failures=0,
                    next_send_at=?, last_error_type=NULL,
                    claimed_at=NULL
                WHERE id=? AND status='paused'
                """,
                (next_at, resolved_id),
            )
            self._conn.commit()
        return cursor.rowcount > 0

    def list_recurring_messages(
        self,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 50))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, chat_id, interval_seconds, next_send_at,
                       status, consecutive_failures, last_error_type,
                       claimed_at, created_at, last_sent_at
                FROM recurring_messages
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def cancel_recurring_message(
        self,
        schedule_id_or_prefix: str,
        *,
        chat_id: int | None = None,
    ) -> bool:
        value = schedule_id_or_prefix.strip()
        if not value:
            return False

        chat_clause = "" if chat_id is None else " AND chat_id=?"
        with self._lock:
            exact_params: list[Any] = [value]
            if chat_id is not None:
                exact_params.append(chat_id)

            exact = self._conn.execute(
                """
                SELECT id
                FROM recurring_messages
                WHERE id=? AND status IN ('active', 'paused')
                """
                + chat_clause,
                tuple(exact_params),
            ).fetchone()

            if exact:
                resolved_id = str(exact["id"])
            else:
                prefix_params: list[Any] = [value + "%"]
                if chat_id is not None:
                    prefix_params.append(chat_id)
                rows = self._conn.execute(
                    """
                    SELECT id
                    FROM recurring_messages
                    WHERE id LIKE ? AND status IN ('active', 'paused')
                    """
                    + chat_clause
                    + """
                    ORDER BY created_at DESC
                    LIMIT 2
                    """,
                    tuple(prefix_params),
                ).fetchall()
                if len(rows) != 1:
                    return False
                resolved_id = str(rows[0]["id"])

            update_params: list[Any] = [resolved_id]
            update_clause = ""
            if chat_id is not None:
                update_clause = " AND chat_id=?"
                update_params.append(chat_id)

            cursor = self._conn.execute(
                """
                UPDATE recurring_messages
                SET status='cancelled', claimed_at=NULL
                WHERE id=? AND status IN ('active', 'paused')
                """
                + update_clause,
                tuple(update_params),
            )
            self._conn.commit()
        return cursor.rowcount > 0

    def create_ama(
        self,
        *,
        chat_id: int,
        title: str,
        created_by: int | None,
    ) -> str:
        ama_id = uuid.uuid4().hex
        now = time.time()
        with self._lock:
            with self._transaction_locked(immediate=True):
                existing = self._conn.execute(
                    """
                    SELECT id
                    FROM ama_sessions
                    WHERE chat_id=? AND status='open'
                    LIMIT 1
                    """,
                    (chat_id,),
                ).fetchone()
                if existing:
                    raise ValueError(
                        "an AMA is already open for this chat"
                    )
                self._conn.execute(
                    """
                    INSERT INTO ama_sessions (
                        id, chat_id, title, status,
                        created_by, created_at
                    )
                    VALUES (?, ?, ?, 'open', ?, ?)
                    """,
                    (
                        ama_id,
                        chat_id,
                        title[:200],
                        created_by,
                        now,
                    ),
                )
        return ama_id

    def active_ama(self, chat_id: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT id, chat_id, title, created_by, created_at
                FROM ama_sessions
                WHERE chat_id=? AND status='open'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (chat_id,),
            ).fetchone()
        return dict(row) if row else None

    def add_ama_question(
        self,
        *,
        ama_id: str,
        chat_id: int,
        user_id: int,
        question: str,
    ) -> str:
        question_id = uuid.uuid4().hex
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO ama_questions (
                    id, ama_id, chat_id, user_id,
                    question, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    question_id,
                    ama_id,
                    chat_id,
                    user_id,
                    question[:1000],
                    time.time(),
                ),
            )
            self._conn.commit()
        return question_id

    def list_ama_questions(
        self,
        ama_id: str,
        limit: int = 30,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 100))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, user_id, question, status, created_at
                FROM ama_questions
                WHERE ama_id=?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (ama_id, safe_limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def close_ama(self, chat_id: int) -> dict[str, Any] | None:
        with self._lock:
            with self._transaction_locked(immediate=True):
                row = self._conn.execute(
                    """
                    SELECT id, chat_id, title, created_by, created_at
                    FROM ama_sessions
                    WHERE chat_id=? AND status='open'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (chat_id,),
                ).fetchone()
                if not row:
                    return None

                active = dict(row)
                now = time.time()
                self._conn.execute(
                    """
                    UPDATE ama_sessions
                    SET status='closed', closed_at=?
                    WHERE id=? AND status='open'
                    """,
                    (now, active["id"]),
                )
                self._conn.execute(
                    """
                    UPDATE ama_questions
                    SET status='closed'
                    WHERE ama_id=? AND status='pending'
                    """,
                    (active["id"],),
                )
        return active

    def prune_ama_questions(self, before: float) -> int:
        with self._lock:
            cursor = self._conn.execute(
                """
                DELETE FROM ama_questions
                WHERE ama_id IN (
                    SELECT id FROM ama_sessions
                    WHERE status='closed'
                      AND closed_at IS NOT NULL
                      AND closed_at < ?
                )
                """,
                (before,),
            )
            self._conn.commit()
        return int(cursor.rowcount)

    def prune_ai_events(self, before: float) -> int:
        with self._lock:
            cursor = self._conn.execute(
                """
                DELETE FROM ai_events
                WHERE created_at < ?
                """,
                (before,),
            )
        return int(cursor.rowcount)

    def prune_completed_scheduled_messages(
        self,
        before: float,
    ) -> int:
        with self._lock:
            cursor = self._conn.execute(
                """
                DELETE FROM scheduled_messages
                WHERE status IN ('sent', 'failed', 'cancelled')
                  AND COALESCE(sent_at, created_at) < ?
                """,
                (before,),
            )
        return int(cursor.rowcount)

    def prune_closed_ama_sessions(
        self,
        before: float,
    ) -> int:
        with self._lock:
            cursor = self._conn.execute(
                """
                DELETE FROM ama_sessions
                WHERE status='closed'
                  AND closed_at IS NOT NULL
                  AND closed_at < ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM ama_questions
                      WHERE ama_questions.ama_id=ama_sessions.id
                  )
                """,
                (before,),
            )
        return int(cursor.rowcount)

    def prune_expired_containments(
        self,
        now: float | None = None,
    ) -> int:
        ts = time.time() if now is None else now
        with self._lock:
            cursor = self._conn.execute(
                """
                DELETE FROM containments
                WHERE blocked_until <= ?
                """,
                (ts,),
            )
        return int(cursor.rowcount)

    def ai_latency_stats(
        self,
        since: float,
    ) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT latency_ms
                FROM ai_events
                WHERE created_at >= ?
                  AND success=1
                  AND latency_ms > 0
                ORDER BY latency_ms ASC
                """,
                (since,),
            ).fetchall()
        values = [int(row["latency_ms"]) for row in rows]
        if not values:
            return {"count": 0, "avg_ms": 0, "p95_ms": 0}
        avg = int(sum(values) / len(values))
        index = min(
            len(values) - 1,
            max(0, ((95 * len(values) + 99) // 100) - 1),
        )
        return {
            "count": len(values),
            "avg_ms": avg,
            "p95_ms": values[index],
        }

    def ai_tokens_since(self, since: float) -> int:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COALESCE(
                    SUM(input_tokens + output_tokens),
                    0
                ) AS tokens
                FROM ai_events
                WHERE created_at >= ? AND success=1
                """,
                (since,),
            ).fetchone()
        return int(row["tokens"]) if row else 0

    def record_ai_event(
        self,
        *,
        chat_id: int | None,
        user_id: int | None,
        purpose: str,
        model: str,
        success: bool,
        category: str | None = None,
        risk: float | None = None,
        requires_human: bool | None = None,
        latency_ms: int = 0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        input_hash: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        event_id = uuid.uuid4().hex
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO ai_events (
                    id, chat_id, user_id, purpose, model, success,
                    category, risk, requires_human, latency_ms,
                    input_tokens, output_tokens, input_hash,
                    created_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    chat_id,
                    user_id,
                    purpose,
                    model,
                    1 if success else 0,
                    category,
                    risk,
                    None if requires_human is None else (1 if requires_human else 0),
                    latency_ms,
                    input_tokens,
                    output_tokens,
                    input_hash,
                    time.time(),
                    _json(metadata),
                ),
            )
            self._conn.commit()
        return event_id

    def operational_stats_since(
        self,
        since: float,
    ) -> dict[str, int]:
        queries = {
            "new_users": (
                "SELECT COUNT(*) AS count FROM users WHERE first_seen >= ?"
            ),
            "strikes": (
                "SELECT COUNT(*) AS count FROM strikes WHERE occurred_at >= ?"
            ),
            "incidents": (
                "SELECT COUNT(*) AS count FROM incidents WHERE created_at >= ?"
            ),
            "open_incidents": (
                "SELECT COUNT(*) AS count FROM incidents "
                "WHERE created_at >= ? AND status='open'"
            ),
            "actions": (
                "SELECT COUNT(*) AS count FROM actions WHERE created_at >= ?"
            ),
            "ai_events": (
                "SELECT COUNT(*) AS count FROM ai_events WHERE created_at >= ?"
            ),
        }

        result: dict[str, int] = {}
        with self._lock:
            for key, query in queries.items():
                row = self._conn.execute(query, (since,)).fetchone()
                result[key] = int(row["count"]) if row else 0
        return result

    def community_stats(self) -> dict[str, int]:
        queries = {
            "pending_scheduled": (
                "SELECT COUNT(*) AS count FROM scheduled_messages "
                "WHERE status='pending'"
            ),
            "active_recurring": (
                "SELECT COUNT(*) AS count FROM recurring_messages "
                "WHERE status='active'"
            ),
            "paused_recurring": (
                "SELECT COUNT(*) AS count FROM recurring_messages "
                "WHERE status='paused'"
            ),
            "failed_scheduled": (
                "SELECT COUNT(*) AS count FROM scheduled_messages "
                "WHERE status='failed'"
            ),
            "uncertain_scheduled": (
                "SELECT COUNT(*) AS count FROM scheduled_messages "
                "WHERE status='uncertain'"
            ),
            "sending_scheduled": (
                "SELECT COUNT(*) AS count FROM scheduled_messages "
                "WHERE status='sending'"
            ),
            "sending_recurring": (
                "SELECT COUNT(*) AS count FROM recurring_messages "
                "WHERE status='sending'"
            ),
            "open_amas": (
                "SELECT COUNT(*) AS count FROM ama_sessions "
                "WHERE status='open'"
            ),
            "pending_ama_questions": (
                "SELECT COUNT(*) AS count FROM ama_questions "
                "WHERE status='pending'"
            ),
        }
        result: dict[str, int] = {}
        with self._lock:
            for key, query in queries.items():
                row = self._conn.execute(query).fetchone()
                result[key] = int(row["count"]) if row else 0
        return result

    def stats(self) -> dict[str, int]:
        tables = (
            "users",
            "strikes",
            "incidents",
            "actions",
            "ai_events",
            "knowledge_gaps",
            "idempotency_keys",
            "recurring_messages",
            "ama_sessions",
            "ama_questions",
        )
        result: dict[str, int] = {}
        with self._lock:
            for table in tables:
                row = self._conn.execute(
                    f"SELECT COUNT(*) AS count FROM {table}"
                ).fetchone()
                result[table] = int(row["count"]) if row else 0
        return result
