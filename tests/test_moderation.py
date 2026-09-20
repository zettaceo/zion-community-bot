from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from telegram.constants import ChatMemberStatus
from telegram.ext import ApplicationHandlerStop

from tests.helpers import make_settings
from zion.telegram_app import (
    Runtime,
    command_guard_handler,
    command_idempotency_guard_handler,
    is_operator,
    moderation_handler,
    telegram_entity_domains,
    telegram_entity_link_evidence,
)


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
    update_id: int | None = None,
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
        update_id=message_id if update_id is None else update_id,
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
        self.runtime.close()
        self.temp.cleanup()

    def test_duplicate_command_update_is_suppressed(self) -> None:
        update = fake_update(
            user_id=1,
            text="/status",
            message_id=77,
            update_id=9001,
        )

        asyncio.run(
            command_idempotency_guard_handler(
                update,
                self.context,
            )
        )

        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(
                command_idempotency_guard_handler(
                    update,
                    self.context,
                )
            )

    def test_command_idempotency_db_failure_is_fail_closed(self) -> None:
        update = fake_update(
            user_id=1,
            text="/status",
            message_id=78,
            update_id=9002,
        )
        original = self.runtime.db.claim_idempotency_key

        def fail(*args, **kwargs):
            raise RuntimeError("forced idempotency failure")

        self.runtime.db.claim_idempotency_key = fail
        try:
            with self.assertRaises(ApplicationHandlerStop):
                asyncio.run(
                    command_idempotency_guard_handler(
                        update,
                        self.context,
                    )
                )
        finally:
            self.runtime.db.claim_idempotency_key = original

    def test_command_idempotency_failure_still_deletes_secret(self) -> None:
        update = fake_update(
            user_id=1,
            text="/status API key: example-secret-value-123456",
            message_id=89,
            update_id=9003,
        )
        original = self.runtime.db.claim_idempotency_key
        claim_attempted = False

        def fail(*args, **kwargs):
            nonlocal claim_attempted
            claim_attempted = True
            raise RuntimeError("forced idempotency failure")

        self.runtime.db.claim_idempotency_key = fail
        try:
            with self.assertRaises(ApplicationHandlerStop):
                asyncio.run(
                    command_idempotency_guard_handler(
                        update,
                        self.context,
                    )
                )
        finally:
            self.runtime.db.claim_idempotency_key = original

        self.assertFalse(claim_attempted)
        self.assertIn(
            (update.effective_chat.id, update.effective_message.message_id),
            self.context.bot.deleted,
        )

    def test_telegram_url_entities_are_extracted(self) -> None:
        url_entity = SimpleNamespace(
            type="url",
            url=None,
        )
        hidden_entity = SimpleNamespace(
            type="text_link",
            url="https://hidden.example/path",
        )
        message = SimpleNamespace(
            entities=[url_entity, hidden_entity],
            caption_entities=[],
            parse_entity=lambda entity: "bare.example",
            parse_caption_entity=lambda entity: "",
        )

        domains = telegram_entity_domains(message)

        self.assertIn("bare.example", domains)
        self.assertIn("hidden.example", domains)

    def test_hidden_tg_scheme_is_blocked(self) -> None:
        hidden_entity = SimpleNamespace(
            type="text_link",
            url="tg://resolve?domain=example",
        )
        update = fake_update(
            user_id=2,
            text="clique aqui",
            message_id=79,
        )
        update.effective_message.entities = [hidden_entity]
        update.effective_message.caption_entities = []
        update.effective_message.parse_entity = lambda entity: ""
        update.effective_message.parse_caption_entity = lambda entity: ""

        domains, schemes = telegram_entity_link_evidence(
            update.effective_message
        )
        self.assertEqual(domains, [])
        self.assertEqual(schemes, ["tg"])

        asyncio.run(moderation_handler(update, self.context))

        self.assertIn(
            (update.effective_chat.id, update.effective_message.message_id),
            self.context.bot.deleted,
        )
        incidents = self.runtime.db.list_incidents()
        self.assertEqual(incidents[0]["category"], "unauthorized_link")
        self.assertEqual(incidents[0]["severity"], "medium")

    def test_caption_hidden_link_is_checked(self) -> None:
        hidden_entity = SimpleNamespace(
            type="text_link",
            url="https://hidden.example/path",
        )
        update = fake_update(
            user_id=2,
            text=None,
            message_id=80,
        )
        update.effective_message.caption = "imagem"
        update.effective_message.entities = []
        update.effective_message.caption_entities = [hidden_entity]
        update.effective_message.parse_entity = lambda entity: ""
        update.effective_message.parse_caption_entity = lambda entity: ""

        asyncio.run(moderation_handler(update, self.context))

        self.assertIn(
            (update.effective_chat.id, update.effective_message.message_id),
            self.context.bot.deleted,
        )

    def test_fullwidth_obfuscated_link_is_deleted(self) -> None:
        update = fake_update(
            user_id=2,
            text="veja ｈｔｔｐｓ：／／evil.example/path",
            message_id=81,
        )
        asyncio.run(moderation_handler(update, self.context))

        self.assertIn(
            (update.effective_chat.id, update.effective_message.message_id),
            self.context.bot.deleted,
        )

    def test_link_entity_overflow_fails_closed(self) -> None:
        entities = [
            SimpleNamespace(
                type="text_link",
                url=f"https://host{index}.example/path",
            )
            for index in range(21)
        ]
        message = SimpleNamespace(
            entities=entities,
            caption_entities=[],
            parse_entity=lambda entity: "",
            parse_caption_entity=lambda entity: "",
        )

        domains, schemes = telegram_entity_link_evidence(message)

        self.assertEqual(len(domains), 20)
        self.assertIn("too-many-link-entities", schemes)

    def test_unparseable_url_entity_fails_closed(self) -> None:
        url_entity = SimpleNamespace(
            type="url",
            url=None,
        )
        update = fake_update(
            user_id=2,
            text="clique",
            message_id=83,
            update_id=5083,
        )
        update.effective_message.entities = [url_entity]
        update.effective_message.caption_entities = []

        def broken_parser(entity):
            raise ValueError("forced parser failure")

        update.effective_message.parse_entity = broken_parser
        update.effective_message.parse_caption_entity = lambda entity: ""

        domains, schemes = telegram_entity_link_evidence(
            update.effective_message
        )
        self.assertEqual(domains, [])
        self.assertIn("unparseable-url-entity", schemes)

        asyncio.run(moderation_handler(update, self.context))

        self.assertIn(
            (update.effective_chat.id, update.effective_message.message_id),
            self.context.bot.deleted,
        )

    def test_explicit_operator_allowlist(self) -> None:
        operator = fake_update(
            user_id=1,
            text="/status",
        )
        member = fake_update(
            user_id=2,
            text="/status",
        )

        self.assertTrue(is_operator(operator, self.context))
        self.assertFalse(is_operator(member, self.context))

    def test_duplicate_moderation_update_does_not_repeat_action(self) -> None:
        first = fake_update(
            user_id=2,
            text="veja https://duplicate.example/path",
            message_id=88,
            update_id=5001,
        )
        duplicate = fake_update(
            user_id=2,
            text="veja https://duplicate.example/path",
            message_id=88,
            update_id=5001,
        )

        asyncio.run(moderation_handler(first, self.context))
        asyncio.run(moderation_handler(duplicate, self.context))

        self.assertEqual(
            self.context.bot.deleted.count(
                (first.effective_chat.id, first.effective_message.message_id)
            ),
            1,
        )
        incidents = [
            item
            for item in self.runtime.db.list_incidents(limit=10)
            if item["category"] == "unauthorized_link"
        ]
        self.assertEqual(len(incidents), 1)

    def test_unicode_lookalike_link_is_medium_severity_incident(self) -> None:
        update = fake_update(
            user_id=2,
            text="https://еxample.com/login",
            message_id=84,
            update_id=5084,
        )
        asyncio.run(moderation_handler(update, self.context))

        incidents = self.runtime.db.list_incidents(limit=10)
        self.assertEqual(incidents[0]["category"], "unauthorized_link")
        self.assertEqual(incidents[0]["severity"], "medium")

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

    def test_admin_hidden_entity_credential_is_still_protected(self) -> None:
        hidden_entity = SimpleNamespace(
            type="text_link",
            url=(
                "https://trusted.example/path?"
                "api_key=example-secret-value-123456"
            ),
        )
        update = fake_update(
            user_id=1,
            text="documentação",
            message_id=82,
            update_id=5082,
        )
        update.effective_message.entities = [hidden_entity]
        update.effective_message.caption_entities = []
        update.effective_message.parse_entity = lambda entity: ""
        update.effective_message.parse_caption_entity = lambda entity: ""

        asyncio.run(moderation_handler(update, self.context))

        self.assertIn(
            (update.effective_chat.id, update.effective_message.message_id),
            self.context.bot.deleted,
        )
        incidents = self.runtime.db.list_incidents()
        self.assertEqual(
            incidents[0]["category"],
            "possible_credential_exposure",
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

    def test_admin_credential_exposure_is_still_protected(self) -> None:
        update = fake_update(
            user_id=1,
            text="API key: example-secret-value-123456",
            message_id=19,
        )
        asyncio.run(moderation_handler(update, self.context))

        self.assertIn(
            (update.effective_chat.id, update.effective_message.message_id),
            self.context.bot.deleted,
        )
        incidents = self.runtime.db.list_incidents()
        self.assertEqual(
            incidents[0]["category"],
            "possible_credential_exposure",
        )

    def test_admin_command_credential_is_protected(self) -> None:
        update = fake_update(
            user_id=1,
            text="/announce API key: example-secret-value-123456",
            message_id=20,
        )
        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(command_guard_handler(update, self.context))

        self.assertIn(
            (update.effective_chat.id, update.effective_message.message_id),
            self.context.bot.deleted,
        )

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
