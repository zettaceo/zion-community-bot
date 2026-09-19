from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
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


if __name__ == "__main__":
    unittest.main()
