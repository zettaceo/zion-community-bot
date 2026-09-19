from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from telegram.constants import ChatMemberStatus
from telegram.ext import ApplicationHandlerStop

from tests.helpers import make_settings
from zion.telegram_app import Runtime, command_guard_handler, moderation_handler


class FakeBot:
    def __init__(self) -> None:
        self.deleted: list[tuple[int, int]] = []
        self.sent: list[tuple[int, str]] = []
        self.restricted: list[tuple[int, int]] = []
        self.banned: list[tuple[int, int]] = []

    async def get_chat_member(self, chat_id: int, user_id: int):
        return SimpleNamespace(status=ChatMemberStatus.MEMBER)

    async def delete_message(self, *, chat_id: int, message_id: int):
        self.deleted.append((chat_id, message_id))

    async def send_message(self, *, chat_id: int, text: str):
        self.sent.append((chat_id, text))

    async def restrict_chat_member(
        self,
        *,
        chat_id: int,
        user_id: int,
        permissions,
        until_date,
    ):
        self.restricted.append((chat_id, user_id))

    async def ban_chat_member(
        self,
        *,
        chat_id: int,
        user_id: int,
        revoke_messages: bool,
    ):
        self.banned.append((chat_id, user_id))


class FakeApplication:
    def __init__(self, runtime: Runtime) -> None:
        self.bot_data = {"zion_runtime": runtime}
        self.tasks = []

    def create_task(self, coro, *, update=None):
        task = asyncio.create_task(coro)
        self.tasks.append(task)
        return task


class FakeContext:
    def __init__(self, runtime: Runtime) -> None:
        self.bot = FakeBot()
        self.application = FakeApplication(runtime)


def fake_update(
    *,
    user_id: int,
    text: str | None,
    message_id: int = 10,
):
    user = SimpleNamespace(
        id=user_id,
        username=f"user{user_id}",
        first_name=f"User {user_id}",
        language_code="pt",
    )
    chat = SimpleNamespace(
        id=-100123,
        type="supergroup",
    )
    message = SimpleNamespace(
        message_id=message_id,
        text=text,
        caption=None,
    )
    return SimpleNamespace(
        effective_message=message,
        effective_user=user,
        effective_chat=chat,
    )


class ModerationPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "knowledge").mkdir()
        self.settings = make_settings(self.root)
        self.runtime = Runtime(self.settings)
        self.context = FakeContext(self.runtime)

    def tearDown(self) -> None:
        self.runtime.db.close()
        self.temp.cleanup()

    def test_member_unauthorized_link_is_deleted(self) -> None:
        update = fake_update(
            user_id=2,
            text="veja https://example.com/agora",
        )
        asyncio.run(moderation_handler(update, self.context))

        self.assertIn(
            (update.effective_chat.id, update.effective_message.message_id),
            self.context.bot.deleted,
        )

    def test_admin_link_keeps_admin_exemption(self) -> None:
        update = fake_update(
            user_id=1,
            text="admin https://example.com/status",
        )
        asyncio.run(moderation_handler(update, self.context))

        self.assertEqual(self.context.bot.deleted, [])

    def test_admin_wallet_secret_is_still_protected(self) -> None:
        update = fake_update(
            user_id=1,
            text=(
                "seed phrase: alpha beta gamma delta epsilon zeta "
                "eta theta iota kappa lambda mu"
            ),
        )
        asyncio.run(moderation_handler(update, self.context))

        self.assertIn(
            (update.effective_chat.id, update.effective_message.message_id),
            self.context.bot.deleted,
        )
        incidents = self.runtime.db.list_incidents()
        self.assertEqual(incidents[0]["category"], "possible_wallet_secret")

    def test_command_link_cannot_bypass_link_policy(self) -> None:
        update = fake_update(
            user_id=2,
            text="/ask veja https://example.com/agora",
            message_id=20,
        )

        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(command_guard_handler(update, self.context))

        self.assertIn(
            (update.effective_chat.id, update.effective_message.message_id),
            self.context.bot.deleted,
        )

    def test_admin_command_wallet_secret_is_protected(self) -> None:
        update = fake_update(
            user_id=1,
            text=(
                "/ask seed phrase: alpha beta gamma delta epsilon zeta "
                "eta theta iota kappa lambda mu"
            ),
            message_id=21,
        )

        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(command_guard_handler(update, self.context))

        self.assertIn(
            (update.effective_chat.id, update.effective_message.message_id),
            self.context.bot.deleted,
        )

    def test_non_text_messages_still_trigger_flood(self) -> None:
        for message_id in (30, 31):
            update = fake_update(
                user_id=3,
                text=None,
                message_id=message_id,
            )
            asyncio.run(moderation_handler(update, self.context))

        third = fake_update(
            user_id=3,
            text=None,
            message_id=32,
        )
        asyncio.run(moderation_handler(third, self.context))

        self.assertIn(
            (third.effective_chat.id, third.effective_user.id),
            self.context.bot.restricted,
        )
        self.assertTrue(
            {
                (third.effective_chat.id, 30),
                (third.effective_chat.id, 31),
                (third.effective_chat.id, 32),
            }.issubset(set(self.context.bot.deleted))
        )

    def test_normal_member_message_passes(self) -> None:
        update = fake_update(
            user_id=2,
            text="Eu tenho uma dúvida normal sobre o projeto.",
        )
        asyncio.run(moderation_handler(update, self.context))

        self.assertEqual(self.context.bot.deleted, [])


if __name__ == "__main__":
    unittest.main()
