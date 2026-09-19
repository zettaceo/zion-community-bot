from __future__ import annotations

import asyncio
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tests.helpers import make_settings
from zion.ai_service import AIService, sanitize_for_ai
from zion.db import ZionDB
from zion.knowledge import KnowledgeBase
from zion.mistral import MistralClient, MistralRawResponse, _parse_json_object


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

    def test_classification_schema_is_clamped_and_validated(self) -> None:
        settings = replace(
            self.settings,
            ai_enabled=True,
            mistral_api_key="fake-key-for-test-only",
        )
        client = MistralClient(settings)

        async def fake_chat(messages, **kwargs):
            return MistralRawResponse(
                text=(
                    '{"category":"unexpected_category",'
                    '"risk":2.5,'
                    '"requires_human":"false",'
                    '"rationale":"test",'
                    '"language":"pt"}'
                ),
                model="fake",
                input_tokens=10,
                output_tokens=5,
                latency_ms=1,
            )

        client._chat = fake_chat
        result = asyncio.run(
            client.classify("mensagem normal")
        )

        self.assertEqual(result.category, "other")
        self.assertEqual(result.risk, 1.0)
        self.assertFalse(result.requires_human)
        self.assertEqual(result.input_tokens, 10)
        self.assertEqual(result.output_tokens, 5)
        self.assertEqual(result.latency_ms, 1)


    def test_observe_classification_tokens_count_toward_budget(self) -> None:
        from zion.models import AIClassification

        settings = replace(
            self.settings,
            ai_enabled=True,
            ai_observe=True,
            mistral_api_key="fake-key-for-test-only",
        )
        ai = AIService(settings, self.db, self.knowledge)

        class FakeClassifier:
            configured = True

            async def classify(self, text: str):
                return AIClassification(
                    category="normal",
                    risk=0.1,
                    requires_human=False,
                    model="fake-model",
                    input_tokens=20,
                    output_tokens=5,
                    latency_ms=3,
                )

        ai.client = FakeClassifier()

        result = asyncio.run(
            ai.classify(
                chat_id=1,
                user_id=2,
                text="mensagem normal para observar",
            )
        )

        self.assertIsNotNone(result)
        self.assertEqual(self.db.ai_tokens_since(0), 25)

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

    def test_circuit_breaker_opens_and_persists(self) -> None:
        (self.root / "knowledge" / "official.md").write_text(
            "# Guardian\nGuardian flood protection is active.\n",
            encoding="utf-8",
        )
        knowledge = KnowledgeBase(self.settings.knowledge_dir)
        settings = replace(
            self.settings,
            ai_enabled=True,
            mistral_api_key="fake-key-for-test-only",
            ai_circuit_failures=2,
            ai_circuit_seconds=120,
        )
        ai = AIService(settings, self.db, knowledge)

        class FailingClient:
            configured = True

            def __init__(self) -> None:
                self.calls = 0

            async def answer(self, *, question: str, context: str):
                self.calls += 1
                raise RuntimeError("provider unavailable")

        client = FailingClient()
        ai.client = client

        first = asyncio.run(
            ai.answer(
                chat_id=1,
                user_id=2,
                question="Guardian flood",
            )
        )
        second = asyncio.run(
            ai.answer(
                chat_id=1,
                user_id=2,
                question="Guardian flood",
            )
        )

        self.assertIn("indisponível", first.text)
        self.assertIn("indisponível", second.text)
        self.assertTrue(ai.circuit_open())
        self.assertEqual(client.calls, 2)

        third = asyncio.run(
            ai.answer(
                chat_id=1,
                user_id=2,
                question="Guardian flood",
            )
        )
        self.assertIn("proteção automática", third.text)
        self.assertEqual(client.calls, 2)

        restored = AIService(settings, self.db, knowledge)
        self.assertTrue(restored.circuit_open())

    def test_circuit_success_resets_failure_counter(self) -> None:
        settings = replace(
            self.settings,
            ai_enabled=True,
            mistral_api_key="fake-key-for-test-only",
            ai_circuit_failures=3,
        )
        ai = AIService(settings, self.db, self.knowledge)
        ai._record_provider_failure()
        self.assertEqual(ai._circuit_failures, 1)

        ai._record_provider_success()

        self.assertEqual(ai._circuit_failures, 0)
        self.assertFalse(ai.circuit_open())
        self.assertEqual(
            self.db.get_setting("ai_circuit_failures"),
            "0",
        )

    def test_sanitize_for_ai_redacts_telegram_url_token(self) -> None:
        fake = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
        value = sanitize_for_ai(
            "https://api.telegram.org/bot" + fake + "/getMe"
        )
        self.assertNotIn(fake, value)


if __name__ == "__main__":
    unittest.main()
