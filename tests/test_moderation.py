from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from telegram.constants import ChatMemberStatus

from tests.helpers import make_settings
from zion.telegram_app import Runtime, moderation_handler


class FakeBot:
    def __init__(self) -> None:
        self.deleted: list[tuple[int, int]] = []
        self.sent: list[tuple[int, str]] = []

    async def get_chat_member(self, chat_id: int, user_id: int):
        return SimpleNamespace(status=ChatMemberStatus.MEMBER)

    async def delete_message(self, *, chat_id: int, message_id: int):
        self.deleted.append((chat_id, message_id))

    async def send_message(self, *, chat_id: int, text: str):
        self.sent.append((chat_id, text))


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


def fake_update(*, user_id: int, text: str, message_id: int = 10):
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

    def test_normal_member_message_passes(self) -> None:
        update = fake_update(
            user_id=2,
            text="Eu tenho uma dúvida normal sobre o projeto.",
        )
        asyncio.run(moderation_handler(update, self.context))

        self.assertEqual(self.context.bot.deleted, [])


if __name__ == "__main__":
    unittest.main()
