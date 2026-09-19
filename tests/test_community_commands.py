from __future__ import annotations

import asyncio
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import make_settings
from zion.telegram_app import (
    Runtime,
    ama_open_command,
    ama_question_command,
    report_command,
)


class FakeMessage:
    def __init__(
        self,
        *,
        message_id: int,
        reply_to_message=None,
    ) -> None:
        self.message_id = message_id
        self.reply_to_message = reply_to_message
        self.text = None
        self.caption = None
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class FakeContext:
    def __init__(self, runtime: Runtime, args: list[str]) -> None:
        self.args = args
        self.bot = SimpleNamespace()
        self.application = SimpleNamespace(
            bot_data={"zion_runtime": runtime}
        )


def make_update(
    *,
    user_id: int,
    message_id: int = 1,
    reply_to_message=None,
):
    return SimpleNamespace(
        effective_user=SimpleNamespace(
            id=user_id,
            username=f"user{user_id}",
            first_name=f"User {user_id}",
            language_code="pt",
        ),
        effective_chat=SimpleNamespace(
            id=-100123,
            type="supergroup",
        ),
        effective_message=FakeMessage(
            message_id=message_id,
            reply_to_message=reply_to_message,
        ),
    )


class CommunityCommandRateLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "knowledge").mkdir()
        self.settings = replace(
            make_settings(root),
            report_requests_per_minute=1,
            ama_requests_per_minute=1,
        )
        self.runtime = Runtime(self.settings)

    def tearDown(self) -> None:
        self.runtime.close()
        self.temp.cleanup()

    def test_report_rate_limit_prevents_incident_spam(self) -> None:
        target = SimpleNamespace(
            message_id=99,
            from_user=SimpleNamespace(id=22),
        )
        first = make_update(
            user_id=2,
            message_id=10,
            reply_to_message=target,
        )
        second = make_update(
            user_id=2,
            message_id=11,
            reply_to_message=target,
        )

        asyncio.run(
            report_command(
                first,
                FakeContext(self.runtime, ["spam"]),
            )
        )
        asyncio.run(
            report_command(
                second,
                FakeContext(self.runtime, ["spam"]),
            )
        )

        incidents = self.runtime.db.list_incidents(limit=10)
        reports = [
            item
            for item in incidents
            if item["category"] == "user_report"
        ]
        self.assertEqual(len(reports), 1)
        self.assertTrue(
            any(
                "Limite temporário" in reply
                for reply in second.effective_message.replies
            )
        )

    def test_ama_rate_limit_applies_only_to_active_session(self) -> None:
        no_session = make_update(
            user_id=2,
            message_id=20,
        )
        asyncio.run(
            ama_question_command(
                no_session,
                FakeContext(self.runtime, ["primeira"]),
            )
        )
        self.assertTrue(
            any(
                "Não há AMA aberto" in reply
                for reply in no_session.effective_message.replies
            )
        )

        admin = make_update(
            user_id=1,
            message_id=21,
        )
        asyncio.run(
            ama_open_command(
                admin,
                FakeContext(self.runtime, ["Teste", "AMA"]),
            )
        )

        first = make_update(
            user_id=2,
            message_id=22,
        )
        second = make_update(
            user_id=2,
            message_id=23,
        )
        asyncio.run(
            ama_question_command(
                first,
                FakeContext(self.runtime, ["pergunta", "um"]),
            )
        )
        asyncio.run(
            ama_question_command(
                second,
                FakeContext(self.runtime, ["pergunta", "dois"]),
            )
        )

        active = self.runtime.db.active_ama(-100123)
        self.assertIsNotNone(active)
        questions = self.runtime.db.list_ama_questions(
            str(active["id"])
        )
        self.assertEqual(len(questions), 1)
        self.assertTrue(
            any(
                "Limite temporário" in reply
                for reply in second.effective_message.replies
            )
        )


if __name__ == "__main__":
    unittest.main()
