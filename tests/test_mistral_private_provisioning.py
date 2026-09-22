from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telegram.ext import ApplicationHandlerStop

from tests.helpers import make_settings
from zion.mistral import MistralCredentialInvalid
from zion.secret_store import SecretStore
from zion.telegram_app import (
    Runtime,
    ai_status_command,
    clear_mistral_key_command,
    mistral_secret_capture_handler,
    set_mistral_key_command,
)


SECRET_A = "synthetic-private-mistral-material-123456"
SECRET_B = "synthetic-private-mistral-material-654321"


class FakeMessage:
    def __init__(self, *, message_id: int, text: str = "") -> None:
        self.message_id = message_id
        self.text = text
        self.caption = None
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class FakeBot:
    def __init__(self, *, delete_ok: bool = True) -> None:
        self.delete_ok = delete_ok
        self.deleted: list[tuple[int, int]] = []
        self.sent: list[tuple[int, str]] = []

    async def delete_message(self, *, chat_id: int, message_id: int):
        if not self.delete_ok:
            raise RuntimeError("synthetic delete failure")
        self.deleted.append((chat_id, message_id))

    async def send_message(self, *, chat_id: int, text: str) -> None:
        self.sent.append((chat_id, text))


class FakeContext:
    def __init__(
        self,
        rt: Runtime,
        *,
        args: list[str] | None = None,
        bot: FakeBot | None = None,
    ) -> None:
        self.args = args or []
        self.bot = bot or FakeBot()
        self.application = SimpleNamespace(
            bot_data={"zion_runtime": rt}
        )


def make_update(
    *,
    user_id: int,
    chat_id: int = 1001,
    chat_type: str = "private",
    message_id: int = 1,
    text: str = "",
):
    return SimpleNamespace(
        effective_user=SimpleNamespace(
            id=user_id,
            username=f"user{user_id}",
            first_name=f"User {user_id}",
            language_code="pt",
        ),
        effective_chat=SimpleNamespace(
            id=chat_id,
            type=chat_type,
        ),
        effective_message=FakeMessage(
            message_id=message_id,
            text=text,
        ),
    )


class MistralPrivateProvisioningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "knowledge").mkdir()
        self.settings = replace(
            make_settings(self.root),
            ai_enabled=True,
            admin_user_ids=frozenset({1}),
        )
        self.rt = Runtime(self.settings)

    def tearDown(self) -> None:
        self.rt.close()
        self.temp.cleanup()

    def arm(self) -> tuple[FakeContext, object]:
        update = make_update(user_id=1)
        context = FakeContext(self.rt)
        asyncio.run(set_mistral_key_command(update, context))
        return context, update

    def test_unauthorized_private_user_cannot_arm_capture(self) -> None:
        update = make_update(user_id=2)
        context = FakeContext(self.rt)

        asyncio.run(set_mistral_key_command(update, context))

        self.assertEqual(self.rt.mistral_secret_captures, {})
        self.assertTrue(update.effective_message.replies)
        self.assertIn(
            "operadores explícitos",
            update.effective_message.replies[0],
        )

    def test_explicit_operator_in_group_is_redirected_to_private(self) -> None:
        update = make_update(
            user_id=1,
            chat_id=-100123,
            chat_type="supergroup",
        )
        context = FakeContext(self.rt)

        asyncio.run(set_mistral_key_command(update, context))

        self.assertEqual(self.rt.mistral_secret_captures, {})
        self.assertIn(
            "chat privado",
            update.effective_message.replies[0],
        )

    def test_secret_must_not_be_supplied_as_command_argument(self) -> None:
        update = make_update(user_id=1)
        context = FakeContext(self.rt, args=[SECRET_A])

        asyncio.run(set_mistral_key_command(update, context))

        self.assertEqual(self.rt.mistral_secret_captures, {})
        self.assertEqual(context.bot.deleted, [(1001, 1)])
        self.assertNotIn(SECRET_A, str(context.bot.sent))
        self.assertNotIn(
            SECRET_A,
            "\n".join(update.effective_message.replies),
        )

    def test_private_operator_arms_two_minute_capture(self) -> None:
        _, update = self.arm()
        key = (update.effective_chat.id, update.effective_user.id)

        deadline = self.rt.mistral_secret_captures[key]
        remaining = deadline - time.monotonic()

        self.assertGreater(remaining, 115)
        self.assertLessEqual(remaining, 120)

    def test_expired_capture_does_not_consume_message(self) -> None:
        context, update = self.arm()
        key = (update.effective_chat.id, update.effective_user.id)
        self.rt.mistral_secret_captures[key] = time.monotonic() - 1

        secret_update = make_update(
            user_id=1,
            message_id=2,
            text=SECRET_A,
        )
        asyncio.run(
            mistral_secret_capture_handler(secret_update, context)
        )

        self.assertNotIn(key, self.rt.mistral_secret_captures)
        self.assertEqual(context.bot.deleted, [])
        self.assertIsNone(self.rt.secret_store.read())

    def test_different_user_or_chat_cannot_satisfy_capture(self) -> None:
        context, update = self.arm()
        key = (update.effective_chat.id, update.effective_user.id)

        other_user = make_update(
            user_id=2,
            chat_id=update.effective_chat.id,
            message_id=2,
            text=SECRET_A,
        )
        asyncio.run(
            mistral_secret_capture_handler(other_user, context)
        )

        other_chat = make_update(
            user_id=1,
            chat_id=9999,
            message_id=3,
            text=SECRET_A,
        )
        asyncio.run(
            mistral_secret_capture_handler(other_chat, context)
        )

        self.assertIn(key, self.rt.mistral_secret_captures)
        self.assertEqual(context.bot.deleted, [])
        self.assertIsNone(self.rt.secret_store.read())

    def test_command_text_never_becomes_secret_candidate(self) -> None:
        context, update = self.arm()
        key = (update.effective_chat.id, update.effective_user.id)
        command_update = make_update(
            user_id=1,
            message_id=2,
            text="/status",
        )

        asyncio.run(
            mistral_secret_capture_handler(command_update, context)
        )

        self.assertIn(key, self.rt.mistral_secret_captures)
        self.assertEqual(context.bot.deleted, [])
        self.assertIsNone(self.rt.secret_store.read())

    def test_process_restart_discards_pending_capture(self) -> None:
        _, update = self.arm()
        key = (update.effective_chat.id, update.effective_user.id)
        self.assertIn(key, self.rt.mistral_secret_captures)

        self.rt.close()
        self.rt = Runtime(self.settings)
        context = FakeContext(self.rt)
        secret_update = make_update(
            user_id=1,
            message_id=2,
            text=SECRET_A,
        )

        asyncio.run(
            mistral_secret_capture_handler(secret_update, context)
        )

        self.assertEqual(self.rt.mistral_secret_captures, {})
        self.assertEqual(context.bot.deleted, [])
        self.assertIsNone(self.rt.secret_store.read())

    def test_delete_failure_fails_closed_before_validation_or_store(self) -> None:
        context, _ = self.arm()
        context.bot.delete_ok = False
        secret_update = make_update(
            user_id=1,
            message_id=2,
            text=SECRET_A,
        )

        with patch.object(
            self.rt.ai.client,
            "validate_api_key",
            new=AsyncMock(),
        ) as validate:
            with self.assertRaises(ApplicationHandlerStop):
                asyncio.run(
                    mistral_secret_capture_handler(
                        secret_update,
                        context,
                    )
                )

        validate.assert_not_awaited()
        self.assertIsNone(self.rt.secret_store.read())
        self.assertTrue(context.bot.sent)
        self.assertNotIn(SECRET_A, str(context.bot.sent))

    def test_success_deletes_before_store_and_never_writes_secret_to_db(self) -> None:
        context, _ = self.arm()
        secret_update = make_update(
            user_id=1,
            message_id=2,
            text=SECRET_A,
        )

        with patch.object(
            self.rt.ai.client,
            "validate_api_key",
            new=AsyncMock(return_value=None),
        ):
            with self.assertRaises(ApplicationHandlerStop):
                asyncio.run(
                    mistral_secret_capture_handler(
                        secret_update,
                        context,
                    )
                )

        self.assertEqual(context.bot.deleted, [(1001, 2)])
        self.assertEqual(self.rt.secret_store.read(), SECRET_A)
        self.assertNotIn(SECRET_A, str(context.bot.sent))

        row = self.rt.db._conn.execute(
            "SELECT action_type, metadata_json FROM actions "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(row["action_type"], "mistral_key_set")
        self.assertNotIn(SECRET_A, row["metadata_json"])

        for suffix in ("", "-wal", "-shm"):
            path = Path(str(self.settings.db_path) + suffix)
            if path.exists():
                self.assertNotIn(SECRET_A.encode("utf-8"), path.read_bytes())

    def test_invalid_rotation_preserves_previous_secret(self) -> None:
        self.rt.secret_store.write_atomic(SECRET_A)
        context, _ = self.arm()
        secret_update = make_update(
            user_id=1,
            message_id=2,
            text=SECRET_B,
        )

        with patch.object(
            self.rt.ai.client,
            "validate_api_key",
            new=AsyncMock(
                side_effect=MistralCredentialInvalid(
                    "synthetic invalid credential"
                )
            ),
        ):
            with self.assertRaises(ApplicationHandlerStop):
                asyncio.run(
                    mistral_secret_capture_handler(
                        secret_update,
                        context,
                    )
                )

        self.assertEqual(self.rt.secret_store.read(), SECRET_A)
        self.assertNotIn(SECRET_B, str(context.bot.sent))

    def test_audit_failure_reverts_new_secret_publication(self) -> None:
        context, _ = self.arm()
        secret_update = make_update(
            user_id=1,
            message_id=2,
            text=SECRET_A,
        )

        with patch.object(
            self.rt.ai.client,
            "validate_api_key",
            new=AsyncMock(return_value=None),
        ), patch.object(
            self.rt.db,
            "record_action",
            side_effect=RuntimeError("synthetic audit failure"),
        ):
            with self.assertRaises(ApplicationHandlerStop):
                asyncio.run(
                    mistral_secret_capture_handler(
                        secret_update,
                        context,
                    )
                )

        self.assertIsNone(self.rt.secret_store.read())
        self.assertNotIn(SECRET_A, str(context.bot.sent))
        self.assertTrue(
            any("revertida" in text for _, text in context.bot.sent)
        )

    def test_audit_failure_reverts_rotation_to_previous_secret(self) -> None:
        self.rt.secret_store.write_atomic(SECRET_A)
        context, _ = self.arm()
        secret_update = make_update(
            user_id=1,
            message_id=2,
            text=SECRET_B,
        )

        with patch.object(
            self.rt.ai.client,
            "validate_api_key",
            new=AsyncMock(return_value=None),
        ), patch.object(
            self.rt.db,
            "record_action",
            side_effect=RuntimeError("synthetic audit failure"),
        ):
            with self.assertRaises(ApplicationHandlerStop):
                asyncio.run(
                    mistral_secret_capture_handler(
                        secret_update,
                        context,
                    )
                )

        self.assertEqual(self.rt.secret_store.read(), SECRET_A)
        self.assertNotIn(SECRET_B, str(context.bot.sent))

    def test_clear_audit_failure_restores_previous_secret(self) -> None:
        self.rt.secret_store.write_atomic(SECRET_A)
        update = make_update(user_id=1)
        context = FakeContext(self.rt, args=["CONFIRM"])

        with patch.object(
            self.rt.db,
            "record_action",
            side_effect=RuntimeError("synthetic audit failure"),
        ):
            asyncio.run(clear_mistral_key_command(update, context))

        self.assertEqual(self.rt.secret_store.read(), SECRET_A)
        self.assertTrue(
            any(
                "restaurada" in reply
                for reply in update.effective_message.replies
            )
        )

    def test_clear_requires_private_confirmation_and_needs_no_restart(self) -> None:
        self.rt.secret_store.write_atomic(SECRET_A)
        before_id = id(self.rt)

        first = make_update(user_id=1)
        first_context = FakeContext(self.rt)
        asyncio.run(clear_mistral_key_command(first, first_context))
        self.assertEqual(self.rt.secret_store.read(), SECRET_A)
        self.assertIn("CONFIRM", first.effective_message.replies[0])

        confirm = make_update(user_id=1, message_id=2)
        confirm_context = FakeContext(self.rt, args=["CONFIRM"])
        asyncio.run(clear_mistral_key_command(confirm, confirm_context))

        self.assertIsNone(self.rt.secret_store.read())
        self.assertEqual(id(self.rt), before_id)

    def test_aistatus_exposes_state_but_never_secret(self) -> None:
        self.rt.secret_store.write_atomic(SECRET_A)
        update = make_update(user_id=1)
        context = FakeContext(self.rt)

        asyncio.run(ai_status_command(update, context))

        output = update.effective_message.replies[0]
        self.assertIn("API credential: CONFIGURED", output)
        self.assertIn("LOCAL PROTECTED STORE", output)
        self.assertNotIn(SECRET_A, output)


if __name__ == "__main__":
    unittest.main()
