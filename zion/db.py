from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .models import OperatingState, Severity


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;

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

CREATE TABLE IF NOT EXISTS scheduled_messages (
    id TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    send_at REAL NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_by INTEGER,
    created_at REAL NOT NULL,
    sent_at REAL
);

CREATE INDEX IF NOT EXISTS idx_scheduled_pending
ON scheduled_messages(status, send_at);
"""


def _json(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"))


class ZionDB:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(path),
            timeout=5,
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row

    def initialize(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()
        if self.get_setting("operating_state") is None:
            self.set_setting("operating_state", OperatingState.NORMAL.value)

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
        ts = now or time.time()
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
        ts = now or time.time()
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
    ) -> int:
        ts = now or time.time()
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM strikes
                WHERE chat_id=?
                  AND user_id=?
                  AND (expires_at IS NULL OR expires_at >= ?)
                """,
                (chat_id, user_id, ts),
            ).fetchone()
        return int(row["count"]) if row else 0

    def set_containment(
        self,
        chat_id: int,
        user_id: int,
        blocked_until: float,
        reason: str,
        now: float | None = None,
    ) -> None:
        ts = now or time.time()
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
        ts = now or time.time()
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
        ts = now or time.time()
        incident_id = uuid.uuid4().hex
        severity_value = severity.value if isinstance(severity, Severity) else str(severity)
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
                    note,
                ),
            )
            self._conn.commit()
        return incident_id

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

    def get_operating_state(self) -> OperatingState:
        raw = self.get_setting("operating_state") or OperatingState.NORMAL.value
        try:
            return OperatingState(raw)
        except ValueError:
            return OperatingState.SAFE_MODE

    def set_operating_state(self, state: OperatingState) -> None:
        self.set_setting("operating_state", state.value)

    def set_domain(self, domain: str, disposition: str, source: str) -> None:
        normalized = domain.lower().strip().strip(".")
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
        ts = now or time.time()
        safe_limit = max(1, min(int(limit), 100))
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id, chat_id, send_at, text, created_by
                FROM scheduled_messages
                WHERE status='pending' AND send_at <= ?
                ORDER BY send_at ASC
                LIMIT ?
                """,
                (ts, safe_limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_scheduled_message(
        self,
        schedule_id: str,
        *,
        success: bool,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE scheduled_messages
                SET status=?, sent_at=?
                WHERE id=?
                """,
                (
                    "sent" if success else "failed",
                    time.time(),
                    schedule_id,
                ),
            )
            self._conn.commit()

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

    def stats(self) -> dict[str, int]:
        tables = (
            "users",
            "strikes",
            "incidents",
            "actions",
            "ai_events",
        )
        result: dict[str, int] = {}
        with self._lock:
            for table in tables:
                row = self._conn.execute(
                    f"SELECT COUNT(*) AS count FROM {table}"
                ).fetchone()
                result[table] = int(row["count"]) if row else 0
        return result
