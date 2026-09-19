from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from tests.helpers import make_settings
from zion.db import ZionDB
from zion.telegram_app import Runtime, operational_alert_cycle


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, *, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


class FakeApplication:
    def __init__(self) -> None:
        self.bot = FakeBot()


class V11OperationalAlertTests(unittest.TestCase):
    @staticmethod
    def _healthy_settings(root: Path):
        knowledge = root / "knowledge"
        knowledge.mkdir(exist_ok=True)
        (knowledge / "official.md").write_text(
            "# Community\nOfficial ZION community guidance.\n",
            encoding="utf-8",
        )
        return make_settings(root)

    def test_runtime_rejects_second_instance_until_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._healthy_settings(root)

            first = Runtime(settings)
            try:
                with self.assertRaises(RuntimeError):
                    Runtime(settings)
            finally:
                first.close()

            restarted = Runtime(settings)
            try:
                self.assertTrue(restarted.process_lock.acquired)
            finally:
                restarted.close()

    def test_runtime_startup_quarantines_orphaned_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = self._healthy_settings(root)

            db = ZionDB(settings.db_path)
            db.initialize()
            try:
                scheduled_id = db.schedule_message(
                    chat_id=10,
                    send_at=1000.0,
                    text="unknown one-shot outcome",
                    created_by=1,
                )
                recurring_id = db.schedule_recurring_message(
                    chat_id=10,
                    first_send_at=1000.0,
                    interval_seconds=3600,
                    text="unknown recurring outcome",
                    created_by=1,
                )
                self.assertEqual(
                    db.claim_scheduled_message(
                        scheduled_id,
                        now=1000.0,
                    ),
                    1,
                )
                self.assertTrue(
                    db.claim_recurring_message(
                        recurring_id,
                        now=1000.0,
                    )
                )
            finally:
                db.close()

            rt = Runtime(settings)
            try:
                self.assertEqual(
                    rt.startup_delivery_recovery,
                    {
                        "scheduled_uncertain": 1,
                        "recurring_paused": 1,
                    },
                )
                scheduled = rt.db.list_scheduled_messages(limit=1)[0]
                recurring = rt.db.list_recurring_messages(limit=1)[0]
                self.assertEqual(scheduled["status"], "uncertain")
                self.assertEqual(recurring["status"], "paused")

                incidents = rt.db.list_incidents(limit=10)
                self.assertTrue(
                    any(
                        item["category"]
                        == "orphaned_delivery_claims_quarantined"
                        for item in incidents
                    )
                )
            finally:
                rt.close()

    def test_unchanged_alert_is_bounded_then_repeated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rt = Runtime(self._healthy_settings(root))
            app = FakeApplication()

            try:
                asyncio.run(operational_alert_cycle(app, rt))
                self.assertEqual(len(app.bot.sent), 1)
                self.assertIn(
                    "wifi_interface_missing",
                    app.bot.sent[0][1],
                )

                asyncio.run(operational_alert_cycle(app, rt))
                self.assertEqual(len(app.bot.sent), 1)

                rt.db.set_setting(
                    "health_alert_last_sent_at",
                    str(
                        time.time()
                        - rt.settings.health_alert_repeat_seconds
                        - 1
                    ),
                )
                asyncio.run(operational_alert_cycle(app, rt))
                self.assertEqual(len(app.bot.sent), 2)
            finally:
                rt.close()

    def test_database_alert_still_sends_when_persistence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = replace(
                self._healthy_settings(root),
                wifi_interface="lo",
                disk_warn_mb=1,
            )
            rt = Runtime(settings)
            app = FakeApplication()

            def fail(*args, **kwargs):
                raise RuntimeError("forced database failure")

            try:
                rt.db.ping = lambda: False
                rt.db.integrity_check = lambda: (False, "forced")
                rt.db.get_setting = fail
                rt.db.set_setting = fail
                rt.db.community_stats = fail
                rt.db.create_incident = fail
                rt.db.record_action = fail

                asyncio.run(operational_alert_cycle(app, rt))

                self.assertEqual(len(app.bot.sent), 1)
                self.assertIn(
                    "database_or_integrity",
                    app.bot.sent[0][1],
                )
            finally:
                rt.close()

    def test_failed_delivery_alerts_and_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = replace(
                self._healthy_settings(root),
                wifi_interface="lo",
                disk_warn_mb=1,
            )
            rt = Runtime(settings)
            app = FakeApplication()

            try:
                schedule_id = rt.db.schedule_message(
                    chat_id=10,
                    send_at=1000.0,
                    text="test",
                    created_by=1,
                )
                attempt = rt.db.claim_scheduled_message(
                    schedule_id,
                    now=1000.0,
                )
                self.assertEqual(attempt, 1)

                state = rt.db.mark_scheduled_message(
                    schedule_id,
                    success=False,
                    max_attempts=1,
                    retry_seconds=60,
                    error_type="NetworkError",
                    now=1000.0,
                )
                self.assertEqual(state, "failed")

                asyncio.run(operational_alert_cycle(app, rt))
                self.assertEqual(len(app.bot.sent), 1)
                self.assertIn(
                    "scheduled_delivery_failed",
                    app.bot.sent[0][1],
                )

                self.assertTrue(
                    rt.db.retry_scheduled_message(
                        schedule_id,
                        now=1100.0,
                    )
                )
                asyncio.run(operational_alert_cycle(app, rt))
                self.assertEqual(len(app.bot.sent), 2)
                self.assertIn(
                    "OPERATIONAL RECOVERY",
                    app.bot.sent[1][1],
                )
            finally:
                rt.close()


if __name__ == "__main__":
    unittest.main()
