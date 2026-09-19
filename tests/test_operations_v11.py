from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from tests.helpers import make_settings
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
    def test_unchanged_alert_is_bounded_then_repeated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            rt = Runtime(make_settings(Path(tmp)))
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
                rt.db.close()

    def test_failed_delivery_alerts_and_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = replace(
                make_settings(Path(tmp)),
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
                rt.db.close()


if __name__ == "__main__":
    unittest.main()
