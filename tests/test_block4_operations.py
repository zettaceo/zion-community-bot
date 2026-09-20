from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import time
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.helpers import make_settings
from zion.admin_dashboard import _status_payload
from zion.db import ZionDB
from zion.health import HealthService
from zion.telegram_app import (
    Runtime,
    diagnostics_command,
    hourly_operations_cycle,
    operational_alert_cycle,
    record_update_lag,
    update_lag_stats,
)


class FakeBot:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.attempts = 0
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, *, chat_id: int, text: str) -> None:
        self.attempts += 1
        if self.fail:
            raise RuntimeError("synthetic Telegram failure")
        self.sent.append((chat_id, text))


class FakeApplication:
    def __init__(self, rt: Runtime, *, fail: bool = False) -> None:
        self.bot = FakeBot(fail=fail)
        self.bot_data = {"zion_runtime": rt}


class FakeMessage:
    def __init__(self) -> None:
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class Block4OperationsTests(unittest.TestCase):
    @staticmethod
    def _settings(root: Path, **changes):
        knowledge = root / "knowledge"
        knowledge.mkdir(exist_ok=True)
        (knowledge / "official.md").write_text(
            "# Operations\nOfficial ZION operations guidance.\n",
            encoding="utf-8",
        )
        settings = replace(
            make_settings(root),
            wifi_interface="lo",
            disk_warn_mb=1,
        )
        return replace(settings, **changes) if changes else settings

    def test_pragma_read_failure_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = ZionDB(root / "zion.db")
            db.initialize()
            health = HealthService(make_settings(root), db)

            def fail():
                raise RuntimeError("synthetic pragma failure")

            db.runtime_pragmas = fail
            try:
                diagnostics = health.diagnostics()
                self.assertFalse(diagnostics["sqlite_pragma_read_ok"])
                self.assertFalse(diagnostics["sqlite_pragmas_ok"])
                self.assertEqual(
                    diagnostics["sqlite_pragma_issues"],
                    [],
                )
            finally:
                db.close()

    def test_application_id_zero_is_operational_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = Runtime(self._settings(root))
            app = FakeApplication(rt)
            original = rt.db.runtime_pragmas

            def zero_application_id():
                values = dict(original())
                values["application_id"] = 0
                return values

            rt.db.runtime_pragmas = zero_application_id
            try:
                asyncio.run(operational_alert_cycle(app, rt))
                self.assertEqual(app.bot.attempts, 1)
                self.assertIn(
                    "sqlite_application_id_mismatch",
                    app.bot.sent[0][1],
                )
            finally:
                rt.close()

    def test_pragma_read_failure_generates_alert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = Runtime(self._settings(root))
            app = FakeApplication(rt)

            def fail():
                raise RuntimeError("synthetic pragma failure")

            rt.db.runtime_pragmas = fail
            try:
                asyncio.run(operational_alert_cycle(app, rt))
                self.assertEqual(app.bot.attempts, 1)
                self.assertIn(
                    "sqlite_pragmas_unavailable",
                    app.bot.sent[0][1],
                )
            finally:
                rt.close()

    def test_failed_alert_delivery_remains_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = Runtime(self._settings(root))
            rt.housekeeping_last_error = "RuntimeError"
            app = FakeApplication(rt, fail=True)

            try:
                asyncio.run(operational_alert_cycle(app, rt))
                asyncio.run(operational_alert_cycle(app, rt))

                self.assertEqual(app.bot.attempts, 2)
                self.assertIsNone(rt.health_alert_signature)
                self.assertEqual(rt.health_alert_last_sent_at, 0.0)
                self.assertIsNone(
                    rt.db.get_setting("health_alert_signature")
                )
            finally:
                rt.close()

    def test_successful_alert_delivery_is_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = Runtime(self._settings(root))
            rt.housekeeping_last_error = "RuntimeError"
            app = FakeApplication(rt)

            try:
                asyncio.run(operational_alert_cycle(app, rt))
                asyncio.run(operational_alert_cycle(app, rt))

                self.assertEqual(app.bot.attempts, 1)
                self.assertEqual(
                    rt.health_alert_signature,
                    "housekeeping_failed",
                )
                self.assertGreater(rt.health_alert_last_sent_at, 0)
            finally:
                rt.close()

    def test_failed_recovery_delivery_remains_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = Runtime(self._settings(root))
            rt.housekeeping_last_error = "RuntimeError"
            app = FakeApplication(rt)

            try:
                asyncio.run(operational_alert_cycle(app, rt))
                self.assertEqual(app.bot.attempts, 1)
                self.assertEqual(
                    rt.health_alert_signature,
                    "housekeeping_failed",
                )

                rt.housekeeping_last_error = None
                app.bot.fail = True

                asyncio.run(operational_alert_cycle(app, rt))
                asyncio.run(operational_alert_cycle(app, rt))

                self.assertEqual(app.bot.attempts, 3)
                self.assertEqual(
                    rt.health_alert_signature,
                    "housekeeping_failed",
                )
            finally:
                rt.close()

    def test_housekeeping_failure_does_not_block_health_alert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = Runtime(self._settings(root))
            app = FakeApplication(rt)

            def fail(*args, **kwargs):
                raise RuntimeError("synthetic housekeeping failure")

            rt.db.prune_knowledge_gaps = fail
            try:
                asyncio.run(
                    hourly_operations_cycle(
                        app,
                        rt,
                        now=time.time(),
                    )
                )
                self.assertEqual(
                    rt.housekeeping_last_error,
                    "RuntimeError",
                )
                self.assertEqual(app.bot.attempts, 1)
                self.assertIn(
                    "housekeeping_failed",
                    app.bot.sent[0][1],
                )
            finally:
                rt.close()

    def test_disabled_ai_does_not_raise_provider_alert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = Runtime(self._settings(root))
            rt.ai._circuit_failures = 99
            rt.ai._circuit_open_until = time.time() + 3600
            app = FakeApplication(rt)

            try:
                asyncio.run(operational_alert_cycle(app, rt))
                self.assertEqual(app.bot.attempts, 0)
            finally:
                rt.close()

    def test_diagnostics_exposes_ai_state_without_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._settings(
                root,
                ai_enabled=True,
                mistral_api_key="synthetic-key-material",
                ai_daily_token_budget=1000,
            )
            rt = Runtime(settings)
            rt.ai._circuit_failures = 2
            rt.ai._circuit_open_until = time.time() + 60

            message = FakeMessage()
            update = SimpleNamespace(
                effective_user=SimpleNamespace(id=1),
                effective_message=message,
            )
            context = SimpleNamespace(
                application=SimpleNamespace(
                    bot_data={"zion_runtime": rt}
                )
            )

            try:
                asyncio.run(diagnostics_command(update, context))
                self.assertEqual(len(message.replies), 1)
                output = message.replies[0]
                self.assertIn("AI accounting:", output)
                self.assertIn(
                    "AI tokens UTC used/budget/remaining:",
                    output,
                )
                self.assertIn("AI circuit: OPEN", output)
                self.assertIn("AI provider failures: 2/3", output)
                self.assertIn("NO-SAMPLES", output)
                self.assertNotIn("synthetic-key-material", output)
            finally:
                rt.close()

    def test_update_lag_sample_is_bounded_and_nonnegative(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = Runtime(self._settings(root))
            context = SimpleNamespace(
                application=SimpleNamespace(
                    bot_data={"zion_runtime": rt}
                )
            )

            try:
                future = datetime.now(timezone.utc) + timedelta(seconds=30)
                record_update_lag(
                    SimpleNamespace(
                        effective_message=SimpleNamespace(date=future)
                    ),
                    context,
                )
                for seconds in range(149):
                    record_update_lag(
                        SimpleNamespace(
                            effective_message=SimpleNamespace(
                                date=(
                                    datetime.now(timezone.utc)
                                    - timedelta(seconds=seconds)
                                )
                            )
                        ),
                        context,
                    )

                self.assertEqual(len(rt.update_lags), 100)
                self.assertTrue(all(value >= 0 for value in rt.update_lags))
                latest, p95 = update_lag_stats(rt)
                self.assertGreaterEqual(latest, 0)
                self.assertGreaterEqual(p95, 0)
            finally:
                rt.close()

    def test_integrity_probe_exception_still_reaches_alert_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = Runtime(self._settings(root))
            app = FakeApplication(rt)

            def fail(*args, **kwargs):
                raise RuntimeError("synthetic integrity probe failure")

            rt.db.verify_integrity = fail
            rt.health._integrity_checked_at = float("-inf")
            try:
                asyncio.run(operational_alert_cycle(app, rt))
                self.assertEqual(app.bot.attempts, 1)
                self.assertIn(
                    "database_or_integrity",
                    app.bot.sent[0][1],
                )
            finally:
                rt.close()

    def test_community_stats_failure_becomes_operational_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = Runtime(self._settings(root))
            app = FakeApplication(rt)

            def fail():
                raise RuntimeError("synthetic community stats failure")

            rt.db.community_stats = fail
            try:
                asyncio.run(operational_alert_cycle(app, rt))
                self.assertEqual(app.bot.attempts, 1)
                self.assertIn(
                    "community_stats_unavailable",
                    app.bot.sent[0][1],
                )
            finally:
                rt.close()

    def test_alert_persistence_read_failure_is_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = Runtime(self._settings(root))
            app = FakeApplication(rt)
            original = rt.db.get_setting

            def selective_failure(key: str):
                if key.startswith("health_alert_"):
                    raise RuntimeError(
                        "synthetic health alert persistence failure"
                    )
                return original(key)

            rt.db.get_setting = selective_failure
            try:
                asyncio.run(operational_alert_cycle(app, rt))
                self.assertEqual(app.bot.attempts, 1)
                self.assertIn(
                    "health_alert_persistence_unavailable",
                    app.bot.sent[0][1],
                )
            finally:
                rt.close()

    def test_disk_usage_failure_is_not_reported_as_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = Runtime(self._settings(root))
            app = FakeApplication(rt)

            try:
                with patch(
                    "zion.health.shutil.disk_usage",
                    side_effect=OSError("synthetic disk probe failure"),
                ):
                    diagnostics = rt.health.diagnostics()
                    self.assertFalse(diagnostics["disk_usage_ok"])

                    asyncio.run(operational_alert_cycle(app, rt))

                self.assertEqual(app.bot.attempts, 1)
                self.assertIn(
                    "disk_usage_unavailable",
                    app.bot.sent[0][1],
                )
            finally:
                rt.close()

    def test_ai_latency_query_failure_becomes_operational_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = Runtime(self._settings(root))
            app = FakeApplication(rt)

            def fail(*args, **kwargs):
                raise RuntimeError("synthetic latency query failure")

            rt.db.ai_latency_stats = fail
            try:
                asyncio.run(operational_alert_cycle(app, rt))
                self.assertEqual(app.bot.attempts, 1)
                self.assertIn(
                    "ai_latency_telemetry_unavailable",
                    app.bot.sent[0][1],
                )
            finally:
                rt.close()

    def test_schema_version_query_failure_becomes_operational_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = Runtime(self._settings(root))
            app = FakeApplication(rt)

            def fail():
                raise RuntimeError("synthetic schema query failure")

            rt.db.schema_version = fail
            try:
                asyncio.run(operational_alert_cycle(app, rt))
                self.assertEqual(app.bot.attempts, 1)
                self.assertIn(
                    "sqlite_schema_version_unavailable",
                    app.bot.sent[0][1],
                )
            finally:
                rt.close()

    def test_dashboard_rejects_wrong_application_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "zion.db"
            db = ZionDB(path)
            db.initialize()
            db.close()

            raw = sqlite3.connect(path)
            try:
                raw.execute("PRAGMA application_id=1234")
                raw.commit()
            finally:
                raw.close()

            readonly = ZionDB(path, readonly=True)
            try:
                payload = _status_payload(
                    readonly,
                    root_dir=root,
                    wifi_interface="lo",
                    started_monotonic=time.monotonic(),
                )
                self.assertEqual(payload["database"], "fail")
                self.assertFalse(payload["sqlite_application_id_ok"])
                self.assertEqual(payload["sqlite_application_id"], 1234)
            finally:
                readonly.close()

    def test_dashboard_fails_health_on_foreign_key_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "zion.db"
            db = ZionDB(path)
            db.initialize()
            db.close()

            raw = sqlite3.connect(path)
            try:
                raw.execute("PRAGMA foreign_keys=OFF")
                raw.execute(
                    """
                    INSERT INTO ama_questions(
                        id, ama_id, chat_id, user_id,
                        question, status, created_at
                    )
                    VALUES (
                        'block4-orphan', 'missing-session',
                        1, 2, 'orphan', 'pending', 1
                    )
                    """
                )
                raw.commit()
            finally:
                raw.close()

            readonly = ZionDB(path, readonly=True)
            try:
                payload = _status_payload(
                    readonly,
                    root_dir=root,
                    wifi_interface="lo",
                    started_monotonic=time.monotonic(),
                )
                self.assertEqual(payload["database"], "fail")
                self.assertFalse(payload["sqlite_foreign_keys_ok"])
                self.assertTrue(
                    payload["sqlite_foreign_key_violations"]
                )
                self.assertIn("database_file_mb", payload)
                self.assertIn("wal_size_mb", payload)
                self.assertIn("shm_size_mb", payload)
            finally:
                readonly.close()


if __name__ == "__main__":
    unittest.main()
