from __future__ import annotations

import asyncio
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import make_settings
from zion.models import OperatingState
from zion.telegram_app import Runtime, welcome_handler


class FakeMessage:
    def __init__(self, members) -> None:
        self.new_chat_members = list(members)
        self.replies: list[str] = []
        self.date = None

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, *, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


class FakeContext:
    def __init__(self, runtime: Runtime) -> None:
        self.bot = FakeBot()
        self.application = SimpleNamespace(
            bot_data={"zion_runtime": runtime}
        )


def member(user_id: int, *, bot: bool = False):
    return SimpleNamespace(
        id=user_id,
        is_bot=bot,
        username=f"user{user_id}",
        first_name=f"User {user_id}",
        language_code="pt",
    )


def update_for(*members, update_id: int = 100):
    return SimpleNamespace(
        update_id=update_id,
        effective_chat=SimpleNamespace(
            id=-100500,
            type="supergroup",
        ),
        effective_message=FakeMessage(members),
    )


class RaidGuardianTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "knowledge").mkdir()
        self.settings = replace(
            make_settings(root),
            raid_max_joins=4,
            raid_window_seconds=60,
            raid_elevated_seconds=600,
        )
        self.runtime = Runtime(self.settings)
        self.context = FakeContext(self.runtime)

    def tearDown(self) -> None:
        self.runtime.close()
        self.temp.cleanup()

    def test_single_join_gets_one_welcome(self) -> None:
        update = update_for(member(10), update_id=1001)
        asyncio.run(welcome_handler(update, self.context))

        self.assertEqual(len(update.effective_message.replies), 1)
        self.assertIn(
            "User 10",
            update.effective_message.replies[0],
        )
        joins = self.runtime.db.count_user_events(
            chat_id=-100500,
            event_type="joined",
            since=0,
        )
        self.assertEqual(joins, 1)
        self.assertEqual(
            self.runtime.db.get_operating_state(),
            OperatingState.NORMAL,
        )

    def test_mass_join_batches_welcome_and_enters_elevated(self) -> None:
        members = [member(index) for index in range(20, 24)]
        update = update_for(*members, update_id=1002)

        asyncio.run(welcome_handler(update, self.context))

        # One service update with many new members must not make the bot
        # produce one welcome message per member.
        self.assertEqual(len(update.effective_message.replies), 1)
        self.assertIn(
            "4 novos membros",
            update.effective_message.replies[0],
        )
        self.assertEqual(len(self.context.bot.sent), 1)
        self.assertIn(
            "ELEVATED",
            self.context.bot.sent[0][1],
        )
        self.assertEqual(
            self.runtime.db.get_operating_state(),
            OperatingState.ELEVATED,
        )

        incidents = self.runtime.db.list_incidents(limit=10)
        raid = [
            item
            for item in incidents
            if item["category"] == "mass_join_detected"
        ]
        self.assertEqual(len(raid), 1)

        # Raid detection changes operating state only. It does not strike,
        # mute or ban each person who joined.
        self.assertEqual(
            self.runtime.db.stats().get("strikes", 0),
            0,
        )
        self.assertEqual(
            self.runtime.db.stats().get("containments", 0),
            0,
        )

    def test_duplicate_join_update_is_suppressed(self) -> None:
        first = update_for(
            member(30),
            member(31),
            update_id=1003,
        )
        duplicate = update_for(
            member(30),
            member(31),
            update_id=1003,
        )

        asyncio.run(welcome_handler(first, self.context))
        asyncio.run(welcome_handler(duplicate, self.context))

        joins = self.runtime.db.count_user_events(
            chat_id=-100500,
            event_type="joined",
            since=0,
        )
        self.assertEqual(joins, 2)
        self.assertEqual(len(first.effective_message.replies), 1)
        self.assertEqual(duplicate.effective_message.replies, [])

    def test_bot_only_join_does_not_affect_raid_counter(self) -> None:
        update = update_for(member(40, bot=True), update_id=1004)
        asyncio.run(welcome_handler(update, self.context))

        self.assertEqual(update.effective_message.replies, [])
        joins = self.runtime.db.count_user_events(
            chat_id=-100500,
            event_type="joined",
            since=0,
        )
        self.assertEqual(joins, 0)
        self.assertEqual(
            self.runtime.db.get_operating_state(),
            OperatingState.NORMAL,
        )


if __name__ == "__main__":
    unittest.main()
