from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from tests.helpers import make_settings
from zion.db import SUPPORTED_SCHEMA_VERSION, ZION_APPLICATION_ID, ZionDB
from zion.health import HealthService
from zion.telegram_identity_store import TelegramIdentityStore


class HealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = make_settings(self.root)
        self.db = ZionDB(self.settings.db_path)
        self.db.initialize()
        self.health = HealthService(self.settings, self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_integrity_cache_tracks_health_check_cadence(self) -> None:
        settings = replace(
            self.settings,
            health_check_interval_seconds=60,
        )
        health = HealthService(settings, self.db)
        health._integrity_checked_at = 100.0
        calls = 0
        original = self.db.verify_integrity

        def counted(*args, **kwargs):
            nonlocal calls
            calls += 1
            return original(*args, **kwargs)

        self.db.verify_integrity = counted
        try:
            with patch(
                "zion.health.time.monotonic",
                return_value=159.0,
            ):
                health._integrity_status()
            self.assertEqual(calls, 0)

            with patch(
                "zion.health.time.monotonic",
                return_value=160.0,
            ):
                health._integrity_status()
            self.assertEqual(calls, 1)
        finally:
            self.db.verify_integrity = original

    def test_integrity_cache_never_exceeds_five_minutes(self) -> None:
        settings = replace(
            self.settings,
            health_check_interval_seconds=900,
        )
        health = HealthService(settings, self.db)
        self.assertEqual(health._integrity_cache_seconds, 300)

    def test_private_sensitive_files_are_healthy(self) -> None:
        env_path = self.root / ".env"
        env_path.write_text("TEST=1\n", encoding="utf-8")
        os.chmod(env_path, 0o600)

        snapshot = self.health.snapshot()
        self.assertTrue(
            snapshot.details["sensitive_files_private"]
        )

    def test_diagnostics_include_sqlite_integrity(self) -> None:
        diagnostics = self.health.diagnostics()
        self.assertTrue(diagnostics["db_ok"])
        self.assertTrue(diagnostics["sqlite_integrity_ok"])
        self.assertEqual(
            diagnostics["sqlite_integrity_result"].lower(),
            "ok",
        )
        self.assertGreaterEqual(diagnostics["db_size_mb"], 0)
        self.assertEqual(
            diagnostics["schema_version"],
            SUPPORTED_SCHEMA_VERSION,
        )
        self.assertEqual(
            diagnostics["schema_version_supported"],
            SUPPORTED_SCHEMA_VERSION,
        )
        self.assertTrue(diagnostics["schema_version_ok"])
        self.assertEqual(
            diagnostics["sqlite_pragmas"]["journal_mode"],
            "wal",
        )
        self.assertEqual(
            diagnostics["sqlite_pragmas"]["foreign_keys"],
            1,
        )
        self.assertTrue(diagnostics["sqlite_foreign_keys_ok"])
        self.assertEqual(
            diagnostics["sqlite_foreign_key_violations"],
            [],
        )
        self.assertEqual(
            diagnostics["sqlite_pragmas"]["synchronous"],
            2,
        )
        self.assertEqual(
            diagnostics["sqlite_pragmas"]["wal_autocheckpoint"],
            1000,
        )
        self.assertEqual(
            diagnostics["sqlite_pragmas"]["journal_size_limit"],
            16777216,
        )
        self.assertEqual(
            diagnostics["sqlite_pragmas"]["trusted_schema"],
            0,
        )
        self.assertEqual(
            diagnostics["sqlite_pragmas"]["application_id"],
            ZION_APPLICATION_ID,
        )
        self.assertGreaterEqual(
            diagnostics["sqlite_pragmas"]["busy_timeout_ms"],
            5000,
        )
        self.assertEqual(
            diagnostics["ai_latency_24h"],
            {"count": 0, "avg_ms": 0, "p95_ms": 0},
        )

    def test_foreign_key_violation_fails_database_health(self) -> None:
        self.db._conn.execute("PRAGMA foreign_keys=OFF")
        self.db._conn.execute(
            """
            INSERT INTO ama_questions(
                id, ama_id, chat_id, user_id,
                question, status, created_at
            )
            VALUES (
                'orphan-health', 'missing-session',
                1, 2, 'orphan', 'pending', 1
            )
            """
        )
        self.db._conn.execute("PRAGMA foreign_keys=ON")

        snapshot = self.health.snapshot()

        self.assertFalse(snapshot.db_ok)
        self.assertFalse(
            snapshot.details["sqlite_foreign_keys_ok"]
        )
        self.assertGreater(
            len(
                snapshot.details[
                    "sqlite_foreign_key_violations"
                ]
            ),
            0,
        )

    def test_database_and_wal_size_thresholds_are_reported(self) -> None:
        settings = replace(
            self.settings,
            db_warn_mb=0,
            wal_warn_mb=0,
        )
        health = HealthService(settings, self.db)
        snapshot = health.snapshot()

        self.assertTrue(snapshot.details["db_large"])
        self.assertTrue(snapshot.details["wal_large"])
        self.assertIn("db_file_mb", snapshot.details)
        self.assertIn("wal_size_mb", snapshot.details)

    def test_world_readable_env_is_reported(self) -> None:
        env_path = self.root / ".env"
        env_path.write_text("TEST=1\n", encoding="utf-8")
        os.chmod(env_path, 0o644)

        snapshot = self.health.snapshot()
        self.assertFalse(
            snapshot.details["sensitive_files_private"]
        )

    def test_secondary_identity_health_exposes_only_safe_status(self) -> None:
        class FakeIdentityStore:
            secret_value = "999999" + ":NEVER_EXPOSE_THIS_TELEGRAM_TOKEN"

            @staticmethod
            def status_all():
                from zion.agents import AgentId

                return {
                    AgentId.MIMIR: TelegramIdentityStore.CONFIGURED,
                    AgentId.EIR: TelegramIdentityStore.MISSING,
                    AgentId.FREYR: TelegramIdentityStore.CONFIGURED,
                }

        health = HealthService(
            self.settings,
            self.db,
            telegram_identity_store=FakeIdentityStore(),
        )
        snapshot = health.snapshot()
        statuses = snapshot.details["telegram_identity_status"]

        self.assertEqual(
            statuses,
            {
                "mimir": "CONFIGURED",
                "eir": "MISSING",
                "freyr": "CONFIGURED",
            },
        )
        self.assertNotIn(
            FakeIdentityStore.secret_value,
            repr(snapshot.details),
        )

    def test_unsafe_secondary_identity_store_fails_sensitive_health(self) -> None:
        class UnsafeIdentityStore:
            @staticmethod
            def status_all():
                from zion.agents import AgentId

                return {
                    AgentId.MIMIR: TelegramIdentityStore.UNSAFE,
                    AgentId.EIR: TelegramIdentityStore.MISSING,
                    AgentId.FREYR: TelegramIdentityStore.MISSING,
                }

        health = HealthService(
            self.settings,
            self.db,
            telegram_identity_store=UnsafeIdentityStore(),
        )
        self.assertFalse(
            health.snapshot().details["sensitive_files_private"]
        )


if __name__ == "__main__":
    unittest.main()
