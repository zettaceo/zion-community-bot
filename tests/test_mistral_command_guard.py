from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from telegram.ext import ApplicationHandlerStop

from zion.telegram_app import command_idempotency_guard_handler


SYNTHETIC_ARGUMENT = "synthetic-command-material-123456789"


class FakeBot:
    def __init__(self, *, fail_delete: bool = False) -> None:
        self.fail_delete = fail_delete
        self.deleted: list[tuple[int, int]] = []
        self.sent: list[tuple[int, str]] = []

    async def delete_message(self, *, chat_id: int, message_id: int):
        if self.fail_delete:
            raise RuntimeError("synthetic delete failure")
        self.deleted.append((chat_id, message_id))
        return True

    async def send_message(self, *, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


def make_update(separator: str = " ") -> SimpleNamespace:
    return SimpleNamespace(
        update_id=77,
        effective_chat=SimpleNamespace(id=1001, type="private"),
        effective_message=SimpleNamespace(
            message_id=55,
            text=f"/setmistralkey{separator}{SYNTHETIC_ARGUMENT}",
            caption=None,
        ),
    )


class MistralCommandArgumentGuardTests(unittest.TestCase):
    def test_argument_is_deleted_before_command_claim(self) -> None:
        for separator in (" ", "\t", "\n"):
            with self.subTest(separator=repr(separator)):
                bot = FakeBot()
                context = SimpleNamespace(
                    bot=bot,
                    application=SimpleNamespace(bot_data={}),
                )

                with self.assertRaises(ApplicationHandlerStop):
                    asyncio.run(
                        command_idempotency_guard_handler(
                            make_update(separator),
                            context,
                        )
                    )

                self.assertEqual(bot.deleted, [(1001, 55)])
                self.assertNotIn(SYNTHETIC_ARGUMENT, str(bot.sent))

    def test_argument_delete_failure_still_stops_processing(self) -> None:
        bot = FakeBot(fail_delete=True)
        context = SimpleNamespace(
            bot=bot,
            application=SimpleNamespace(bot_data={}),
        )

        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(
                command_idempotency_guard_handler(
                    make_update(),
                    context,
                )
            )

        self.assertEqual(bot.deleted, [])
        self.assertNotIn(SYNTHETIC_ARGUMENT, str(bot.sent))


if __name__ == "__main__":
    unittest.main()
