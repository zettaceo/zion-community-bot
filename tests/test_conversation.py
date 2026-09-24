from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram.constants import ChatMemberStatus

from tests.helpers import make_settings
from zion.models import AIAnswer
from zion.telegram_app import (
    Runtime,
    moderation_handler,
    natural_conversation_question,
    telegram_ai_reply_text,
)


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
    id = 999
    username = "zion_bot"

    def __init__(self) -> None:
        self.deleted: list[tuple[int, int]] = []
        self.sent: list[tuple[int, str]] = []

    async def get_chat_member(self, *, chat_id: int, user_id: int):
        return SimpleNamespace(status=ChatMemberStatus.MEMBER)

    async def delete_message(self, *, chat_id: int, message_id: int):
        self.deleted.append((chat_id, message_id))

    async def send_message(self, *, chat_id: int, text: str):
        self.sent.append((chat_id, text))

    async def restrict_chat_member(self, **kwargs):
        return None

    async def ban_chat_member(self, **kwargs):
        return None


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


def make_update(
    text: str,
    *,
    chat_type: str,
    message_id: int = 1,
    reply_to_bot: bool = False,
    user_id: int = 2,
):
    message = FakeMessage(text, message_id=message_id)
    if reply_to_bot:
        message.reply_to_message = SimpleNamespace(
            message_id=message_id - 1,
            from_user=SimpleNamespace(
                id=FakeBot.id,
                username=FakeBot.username,
            ),
        )
    return SimpleNamespace(
        update_id=message_id,
        effective_user=SimpleNamespace(
            id=user_id,
            username="carlos",
            first_name="Carlos",
            language_code="pt",
        ),
        effective_chat=SimpleNamespace(
            id=20 if chat_type == "private" else -10020,
            type=chat_type,
        ),
        effective_message=message,
    )


class ConversationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / "knowledge").mkdir()
        self.runtime = Runtime(make_settings(root))
        self.addCleanup(self.runtime.close)
        self.context = FakeContext(self.runtime)
        self.runtime.ai.answer = AsyncMock(
            return_value=AIAnswer(
                text="**Resposta clara** sobre a Z-SWAP.",
                model="test-model",
            )
        )

    def test_private_message_is_a_natural_question(self) -> None:
        update = make_update(
            "O que é a Z-SWAP?",
            chat_type="private",
        )

        asyncio.run(moderation_handler(update, self.context))

        self.runtime.ai.answer.assert_awaited_once_with(
            chat_id=20,
            user_id=2,
            question="O que é a Z-SWAP?",
        )
        self.assertEqual(
            update.effective_message.replies,
            ["Resposta clara sobre a Z-SWAP."],
        )

    def test_group_product_question_needs_no_command(self) -> None:
        update = make_update(
            "O que é a Z-SWAP?",
            chat_type="supergroup",
        )

        asyncio.run(moderation_handler(update, self.context))

        self.runtime.ai.answer.assert_awaited_once()
        self.assertEqual(len(update.effective_message.replies), 1)

    def test_group_reply_to_zion_continues_conversation(self) -> None:
        update = make_update(
            "Pode explicar de forma mais simples?",
            chat_type="supergroup",
            reply_to_bot=True,
        )

        question = natural_conversation_question(
            update,
            self.context,
            update.effective_message.text,
        )

        self.assertEqual(question, "Pode explicar de forma mais simples?")

    def test_group_follow_up_without_command_keeps_recent_context(self) -> None:
        first = make_update(
            "O que é a Z-SWAP?",
            chat_type="supergroup",
            message_id=10,
        )
        follow_up = make_update(
            "Me fala em uma frase quais os benefícios do plano Pilot",
            chat_type="supergroup",
            message_id=11,
        )

        asyncio.run(moderation_handler(first, self.context))
        asyncio.run(moderation_handler(follow_up, self.context))

        self.assertEqual(self.runtime.ai.answer.await_count, 2)
        follow_up_call = self.runtime.ai.answer.await_args_list[1]
        self.assertEqual(
            follow_up_call.kwargs["question"],
            "Me fala em uma frase quais os benefícios do plano Pilot",
        )
        self.assertIn("O que é a Z-SWAP?", follow_up_call.kwargs["context_query"])
        self.assertIn(
            "ZION: Resposta clara sobre a Z-SWAP.",
            follow_up_call.kwargs["conversation_context"],
        )
        self.assertEqual(len(follow_up.effective_message.replies), 1)

    def test_group_pilot_question_needs_no_prior_context(self) -> None:
        update = make_update(
            "Me fala os benefícios do plano piloto",
            chat_type="supergroup",
            message_id=12,
        )

        asyncio.run(moderation_handler(update, self.context))

        self.runtime.ai.answer.assert_awaited_once_with(
            chat_id=-10020,
            user_id=2,
            question="Me fala os benefícios do plano piloto",
        )
        self.assertEqual(len(update.effective_message.replies), 1)

    def test_group_pro_question_needs_no_prior_context(self) -> None:
        update = make_update(
            "Quais as vantagens do plano Pro?",
            chat_type="supergroup",
            message_id=13,
        )

        asyncio.run(moderation_handler(update, self.context))

        self.runtime.ai.answer.assert_awaited_once_with(
            chat_id=-10020,
            user_id=2,
            question="Quais as vantagens do plano Pro?",
        )
        self.assertEqual(len(update.effective_message.replies), 1)

    def test_user_correction_about_pro_continues_active_topic(self) -> None:
        first = make_update(
            "Quais as vantagens do plano Pilot?",
            chat_type="supergroup",
            message_id=14,
        )
        correction = make_update(
            "Mais eu perguntei pelo Pro",
            chat_type="supergroup",
            message_id=15,
        )

        asyncio.run(moderation_handler(first, self.context))
        self.runtime.ai.answer.reset_mock()
        asyncio.run(moderation_handler(correction, self.context))

        self.runtime.ai.answer.assert_awaited_once()
        call = self.runtime.ai.answer.await_args
        self.assertEqual(
            call.kwargs["question"],
            "Mais eu perguntei pelo Pro",
        )
        self.assertIn(
            "Quais as vantagens do plano Pilot?",
            call.kwargs["conversation_context"],
        )
        self.assertEqual(
            call.kwargs["context_query"],
            "Mais eu perguntei pelo Pro",
        )
        self.assertEqual(len(correction.effective_message.replies), 1)

    def test_recent_conversation_does_not_capture_unrelated_chatter(self) -> None:
        first = make_update(
            "O que é a Z-SWAP?",
            chat_type="supergroup",
            message_id=20,
        )
        unrelated = make_update(
            "Vou almoçar e volto depois.",
            chat_type="supergroup",
            message_id=21,
        )

        asyncio.run(moderation_handler(first, self.context))
        self.runtime.ai.answer.reset_mock()
        asyncio.run(moderation_handler(unrelated, self.context))

        self.runtime.ai.answer.assert_not_awaited()
        self.assertEqual(unrelated.effective_message.replies, [])

    def test_recent_conversation_is_shared_with_other_member(self) -> None:
        first = make_update(
            "O que é a Z-SWAP?",
            chat_type="supergroup",
            message_id=30,
            user_id=2,
        )
        other_user = make_update(
            "E quanto custa?",
            chat_type="supergroup",
            message_id=31,
            user_id=3,
        )

        asyncio.run(moderation_handler(first, self.context))
        self.runtime.ai.answer.reset_mock()
        asyncio.run(moderation_handler(other_user, self.context))

        self.runtime.ai.answer.assert_awaited_once()
        call = self.runtime.ai.answer.await_args
        self.assertEqual(call.kwargs["user_id"], 3)
        self.assertEqual(call.kwargs["question"], "E quanto custa?")
        self.assertIn("O que é a Z-SWAP?", call.kwargs["context_query"])
        self.assertIn(
            "Resposta clara sobre a Z-SWAP.",
            call.kwargs["conversation_context"],
        )
        self.assertEqual(len(other_user.effective_message.replies), 1)

    def test_other_member_can_challenge_active_topic_without_project_name(self):
        first = make_update(
            "Quais são os benefícios do plano Pilot?",
            chat_type="supergroup",
            message_id=40,
            user_id=2,
        )
        criticism = make_update(
            "Não concordo, isso não faz sentido.",
            chat_type="supergroup",
            message_id=41,
            user_id=3,
        )

        asyncio.run(moderation_handler(first, self.context))
        self.runtime.ai.answer.reset_mock()
        asyncio.run(moderation_handler(criticism, self.context))

        self.runtime.ai.answer.assert_awaited_once()
        call = self.runtime.ai.answer.await_args
        self.assertEqual(
            call.kwargs["question"],
            "Não concordo, isso não faz sentido.",
        )
        self.assertIn(
            "Quais são os benefícios do plano Pilot?",
            call.kwargs["conversation_context"],
        )
        self.assertEqual(len(criticism.effective_message.replies), 1)

    def test_other_member_can_add_a_related_comment(self) -> None:
        self.runtime.ai.answer.return_value = AIAnswer(
            text="O Pilot inclui suporte prioritário.",
            model="test-model",
        )
        first = make_update(
            "Quais são os benefícios do plano Pilot?",
            chat_type="supergroup",
            message_id=50,
            user_id=2,
        )
        contribution = make_update(
            "Esse suporte prioritário é muito útil.",
            chat_type="supergroup",
            message_id=51,
            user_id=3,
        )

        asyncio.run(moderation_handler(first, self.context))
        self.runtime.ai.answer.reset_mock()
        asyncio.run(moderation_handler(contribution, self.context))

        self.runtime.ai.answer.assert_awaited_once()
        self.assertEqual(len(contribution.effective_message.replies), 1)

    def test_project_question_does_not_require_project_name(self) -> None:
        update = make_update(
            "Quais redes são suportadas?",
            chat_type="supergroup",
            message_id=60,
            user_id=3,
        )

        asyncio.run(moderation_handler(update, self.context))

        self.runtime.ai.answer.assert_awaited_once_with(
            chat_id=-10020,
            user_id=3,
            question="Quais redes são suportadas?",
        )
        self.assertEqual(len(update.effective_message.replies), 1)

    def test_active_topic_does_not_capture_unrelated_question(self) -> None:
        first = make_update(
            "O que é a Z-SWAP?",
            chat_type="supergroup",
            message_id=70,
            user_id=2,
        )
        unrelated = make_update(
            "Alguém sabe que horas são?",
            chat_type="supergroup",
            message_id=71,
            user_id=3,
        )

        asyncio.run(moderation_handler(first, self.context))
        self.runtime.ai.answer.reset_mock()
        asyncio.run(moderation_handler(unrelated, self.context))

        self.runtime.ai.answer.assert_not_awaited()
        self.assertEqual(unrelated.effective_message.replies, [])

    def test_unaddressed_group_chatter_is_not_answered(self) -> None:
        update = make_update(
            "Vou almoçar e volto depois.",
            chat_type="supergroup",
        )

        asyncio.run(moderation_handler(update, self.context))

        self.runtime.ai.answer.assert_not_awaited()
        self.assertEqual(update.effective_message.replies, [])

    def test_short_group_greeting_gets_a_human_reply(self) -> None:
        update = make_update(
            "Boa tarde",
            chat_type="supergroup",
        )

        asyncio.run(moderation_handler(update, self.context))

        self.runtime.ai.answer.assert_not_awaited()
        self.assertEqual(
            update.effective_message.replies,
            ["Boa tarde! Como posso ajudar com a Z-SWAP?"],
        )

    def test_guardian_blocks_unsafe_link_before_conversation(self) -> None:
        update = make_update(
            "O que é a Z-SWAP? https://evil.example/path",
            chat_type="supergroup",
        )

        asyncio.run(moderation_handler(update, self.context))

        self.runtime.ai.answer.assert_not_awaited()
        self.assertEqual(
            self.context.bot.deleted,
            [(-10020, update.effective_message.message_id)],
        )

    def test_private_duplicate_does_not_repeat_provider_call(self) -> None:
        update = make_update(
            "Explique a Z-SWAP",
            chat_type="private",
            message_id=77,
        )

        asyncio.run(moderation_handler(update, self.context))
        asyncio.run(moderation_handler(update, self.context))

        self.runtime.ai.answer.assert_awaited_once()
        self.assertEqual(len(update.effective_message.replies), 1)

    def test_plain_text_removes_markdown_and_internal_paths(self) -> None:
        rendered = telegram_ai_reply_text(
            "# **Resposta**\n"
            "Veja /home/zetta/projeto/knowledge/product.md.\n"
            "- Primeiro ponto\n\n"
            "Fontes ZION:\n- product.md — Produto"
        )

        self.assertIn("Resposta", rendered)
        self.assertIn("• Primeiro ponto", rendered)
        self.assertNotIn("**", rendered)
        self.assertNotIn("/home/", rendered)
        self.assertNotIn(".md", rendered)
        self.assertNotIn("Fontes ZION", rendered)


if __name__ == "__main__":
    unittest.main()
