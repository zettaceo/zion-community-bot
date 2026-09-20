from __future__ import annotations

import asyncio
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import make_settings
from zion.db import ZionDB
from zion.guardian import Guardian, normalize_policy_domain
from zion.logging_safe import contains_high_confidence_credential
from telegram.constants import ChatMemberStatus
from telegram.ext import ApplicationHandlerStop

from zion.telegram_app import (
    Runtime,
    command_guard_handler,
    is_admin,
    moderation_handler,
    require_admin,
    telegram_entity_domains,
    telegram_external_urls,
)


class TelegramLinkSurfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = replace(
            make_settings(self.root),
            allow_links=True,
            allowed_domains=frozenset({"fass.de", "z-swap.example"}),
        )
        self.db = ZionDB(self.settings.db_path)
        self.db.initialize()
        self.addCleanup(self.db.close)
        self.guardian = Guardian(self.settings, self.db)

    def test_idna2008_sharp_s_does_not_inherit_ascii_allowlist(self) -> None:
        normalized = normalize_policy_domain("https://faß.de/login")
        self.assertEqual(normalized, "xn--fa-hia.de")
        self.assertNotEqual(normalized, "fass.de")

        decision = self.guardian.evaluate_links("https://faß.de/login")
        self.assertTrue(decision.should_delete)
        self.assertEqual(decision.unauthorized_domains, ["xn--fa-hia.de"])

    def test_inline_keyboard_urls_participate_in_domain_policy(self) -> None:
        button = SimpleNamespace(
            url="https://evil.example/path",
            login_url=None,
            web_app=None,
        )
        message = SimpleNamespace(
            entities=[],
            caption_entities=[],
            reply_markup=SimpleNamespace(inline_keyboard=[[button]]),
        )

        urls = telegram_external_urls(message)
        domains = telegram_entity_domains(message)

        self.assertEqual(urls, ["https://evil.example/path"])
        self.assertEqual(domains, ["evil.example"])
        decision = self.guardian.evaluate_links("", extra_domains=domains)
        self.assertTrue(decision.should_delete)

    def test_login_and_webapp_urls_are_inspected(self) -> None:
        message = SimpleNamespace(
            entities=[],
            caption_entities=[],
            reply_markup=SimpleNamespace(
                inline_keyboard=[[
                    SimpleNamespace(
                        url=None,
                        login_url=SimpleNamespace(
                            url="https://login.evil.example/auth"
                        ),
                        web_app=SimpleNamespace(
                            url="https://web.evil.example/app"
                        ),
                    )
                ]]
            ),
        )

        self.assertEqual(
            telegram_entity_domains(message),
            ["login.evil.example", "web.evil.example"],
        )

    def test_hidden_url_credentials_are_visible_to_secret_detector(self) -> None:
        hidden = SimpleNamespace(
            type="text_link",
            url=(
                "https://z-swap.example/support?"
                "api_key=example-secret-value-123456"
            ),
        )
        message = SimpleNamespace(
            entities=[hidden],
            caption_entities=[],
            reply_markup=None,
        )

        surface = "\n".join(("safe label", *telegram_external_urls(message)))
        self.assertTrue(contains_high_confidence_credential(surface))


class FakeMessage:
    def __init__(self, text: str, *, message_id: int = 1) -> None:
        self.message_id = message_id
        self.text = text
        self.caption = None
        self.entities = []
        self.caption_entities = []
        self.reply_markup = None
        self.reply_to_message = None
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class FakeBot:
    def __init__(self, status=ChatMemberStatus.MEMBER) -> None:
        self.status = status
        self.member_calls = 0
        self.deleted: list[tuple[int, int]] = []
        self.sent: list[tuple[int, str]] = []

    async def get_chat_member(self, *, chat_id: int, user_id: int):
        self.member_calls += 1
        return SimpleNamespace(status=self.status)

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
    def __init__(self, runtime: Runtime, bot: FakeBot) -> None:
        self.application = FakeApplication(runtime)
        self.bot = bot
        self.args: list[str] = []


def make_update(*, user_id: int, chat_type: str, text: str, message_id: int = 1):
    return SimpleNamespace(
        update_id=message_id,
        effective_user=SimpleNamespace(
            id=user_id,
            username=f"user{user_id}",
            first_name=f"User {user_id}",
            language_code="pt",
        ),
        effective_chat=SimpleNamespace(
            id=123 if chat_type == "private" else -100123,
            type=chat_type,
        ),
        effective_message=FakeMessage(text, message_id=message_id),
    )


class AuthorizationAndPrivateBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / "knowledge").mkdir()
        self.runtime = Runtime(make_settings(root))
        self.addCleanup(self.runtime.close)

    def test_private_chat_never_infers_admin_from_telegram_role(self) -> None:
        bot = FakeBot(ChatMemberStatus.ADMINISTRATOR)
        context = FakeContext(self.runtime, bot)
        ordinary = make_update(
            user_id=2,
            chat_type="private",
            text="/status",
        )
        explicit = make_update(
            user_id=1,
            chat_type="private",
            text="/status",
            message_id=2,
        )

        self.assertFalse(asyncio.run(is_admin(ordinary, context)))
        self.assertTrue(asyncio.run(is_admin(explicit, context)))
        self.assertEqual(bot.member_calls, 0)

    def test_privileged_command_revalidates_cached_group_admin(self) -> None:
        bot = FakeBot(ChatMemberStatus.ADMINISTRATOR)
        context = FakeContext(self.runtime, bot)
        update = make_update(
            user_id=2,
            chat_type="supergroup",
            text="/ban",
        )

        self.assertTrue(asyncio.run(is_admin(update, context)))
        self.assertEqual(bot.member_calls, 1)

        bot.status = ChatMemberStatus.MEMBER
        self.assertFalse(asyncio.run(require_admin(update, context)))
        self.assertEqual(bot.member_calls, 2)
        self.assertTrue(update.effective_message.replies)

    def test_private_command_skips_group_link_policy(self) -> None:
        bot = FakeBot()
        context = FakeContext(self.runtime, bot)
        update = make_update(
            user_id=2,
            chat_type="private",
            text="/ask veja https://evil.example/path",
        )

        asyncio.run(command_guard_handler(update, context))

        self.assertEqual(bot.deleted, [])
        self.assertEqual(bot.member_calls, 0)

    def test_private_ordinary_message_skips_group_link_policy(self) -> None:
        bot = FakeBot()
        context = FakeContext(self.runtime, bot)
        update = make_update(
            user_id=2,
            chat_type="private",
            text="veja https://evil.example/path",
        )

        asyncio.run(moderation_handler(update, context))

        self.assertEqual(bot.deleted, [])
        self.assertEqual(bot.member_calls, 0)

    def test_private_command_still_blocks_exposed_credential(self) -> None:
        bot = FakeBot()
        context = FakeContext(self.runtime, bot)
        update = make_update(
            user_id=2,
            chat_type="private",
            text="/ask API key: example-secret-value-123456",
        )

        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(command_guard_handler(update, context))

        self.assertEqual(
            bot.deleted,
            [(update.effective_chat.id, update.effective_message.message_id)],
        )
        incidents = self.runtime.db.list_incidents()
        self.assertEqual(
            incidents[0]["category"],
            "possible_credential_exposure",
        )


if __name__ == "__main__":
    unittest.main()
