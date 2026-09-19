from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_settings
from zion.ai_service import AIService, sanitize_for_ai
from zion.db import ZionDB
from zion.knowledge import KnowledgeBase
from zion.mistral import _parse_json_object


class AITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "knowledge").mkdir()
        self.settings = make_settings(self.root)
        self.db = ZionDB(self.settings.db_path)
        self.db.initialize()
        self.knowledge = KnowledgeBase(
            self.settings.knowledge_dir
        )
        self.ai = AIService(
            self.settings,
            self.db,
            self.knowledge,
        )

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_json_parser_accepts_fenced_json(self) -> None:
        fence = chr(96) * 3
        parsed = _parse_json_object(
            fence
            + 'json\n{"category":"normal","risk":0.1}\n'
            + fence
        )
        self.assertEqual(parsed["category"], "normal")
        self.assertEqual(parsed["risk"], 0.1)

    def test_no_knowledge_records_gap_without_provider_call(self) -> None:
        answer = asyncio.run(
            self.ai.answer(
                chat_id=1,
                user_id=2,
                question="Existe um recurso oficial que não está documentado?",
            )
        )
        self.assertIn(
            "informação oficial suficiente",
            answer.text,
        )
        gaps = self.db.list_knowledge_gaps()
        self.assertEqual(len(gaps), 1)

    def test_budget_remaining_uses_recorded_tokens(self) -> None:
        self.db.record_ai_event(
            chat_id=1,
            user_id=2,
            purpose="test",
            model="test",
            success=True,
            input_tokens=100,
            output_tokens=50,
        )
        remaining = self.ai.budget_remaining()
        self.assertEqual(
            remaining,
            self.settings.ai_daily_token_budget - 150,
        )

    def test_sanitize_for_ai_redacts_telegram_url_token(self) -> None:
        fake = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
        value = sanitize_for_ai(
            "https://api.telegram.org/bot" + fake + "/getMe"
        )
        self.assertNotIn(fake, value)


if __name__ == "__main__":
    unittest.main()
