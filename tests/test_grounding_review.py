"""AI grounding review: strict parsing, cut-or-withhold only, never approve."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.helpers import make_settings
from tests.test_kimi_escalation import FakeMistral, Store
from zion.ai_service import AIService, UNGROUNDED_FALLBACK
from zion.db import ZionDB
from zion.escalation import KIMI_MODEL, build_ai_composition
from zion.evaluation_budget import PRICES
from zion.grounding import parse_verdict, remove_sentences
from zion.knowledge import KnowledgeBase
from zion.models import AIAnswer
from zion.provider_budget import ProviderTokenBudget
from zion.providers import Completion
from zion.runtime_cost import RuntimeCostBudget

ROOT = Path(__file__).resolve().parents[1]
ANSWER = ('Na troca, a Z-SWAP seleciona a fonte de cotação conforme as redes envolvidas.\n\n'
          'O swap demora no máximo 30 segundos em qualquer rede.')


class ParseTests(unittest.TestCase):
    def test_quotes_must_occur_in_the_answer(self):
        self.assertIsNone(parse_verdict('{"supported": false, "unsupported_sentences": ["outra frase"], '
                                        '"reason": "x"}', ANSWER))
        verdict = parse_verdict('{"supported": false, "unsupported_sentences": ["O swap demora no máximo '
                                '30 segundos em qualquer rede."], "reason": "sem fonte"}', ANSWER)
        self.assertFalse(verdict.supported)

    def test_rejection_without_a_sentence_and_garbage_are_unreadable(self):
        for raw in ('{"supported": false, "unsupported_sentences": [], "reason": "x"}', 'ok', '{"supported": "no"}'):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_verdict(raw, ANSWER))

    def test_removal_keeps_paragraphs(self):
        text = remove_sentences('Primeira frase certa.\n\nSegunda inventada. Terceira certa.',
                                ('Segunda inventada.',))
        self.assertEqual(text, 'Primeira frase certa.\n\nTerceira certa.')


class ReviewerKimi:
    configured = True

    def __init__(self, verdict: str):
        self.verdict = verdict
        self.calls = 0

    async def complete(self, messages, *, max_tokens):
        self.calls += 1
        return Completion(self.verdict, KIMI_MODEL, 900, 60, 5)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.settings = replace(make_settings(Path(temp.name)), ai_enabled=True,
                                knowledge_dir=ROOT / 'knowledge', ai_daily_token_budget=1000000,
                                kimi_escalation_enabled=True, ai_daily_usd_cap=2.0,
                                kimi_approval_until=(date.today() + timedelta(days=2)).isoformat())
        self.db = ZionDB(self.settings.db_path)
        self.db.initialize()
        self.addCleanup(self.db.close)

    def run_answer(self, generated: str, verdict: str, *, approved=True):
        settings = self.settings if approved else replace(self.settings, kimi_escalation_enabled=False)
        composition = build_ai_composition(settings, self.db, Store())
        reviewer = ReviewerKimi(verdict)
        if composition:
            composition['completion_providers'] = {('kimi', KIMI_MODEL): reviewer}
        ai = AIService(settings, self.db, KnowledgeBase(ROOT / 'knowledge'), **composition)

        class Client(FakeMistral):
            async def answer(self, **_kwargs):
                return AIAnswer(text=generated, model='ministral-8b-2512', input_tokens=10,
                                output_tokens=5, latency_ms=1)

        ai.client = Client()
        today = PRICES[KIMI_MODEL].verified_on
        with patch.object(ProviderTokenBudget, 'today', return_value=today), \
                patch.object(RuntimeCostBudget, 'today', return_value=today):
            answer = asyncio.run(ai.answer(chat_id=1, user_id=2, question='Como funciona os swaps?',
                                           agent_id='mimir'))
        return answer, reviewer

    def test_ungrounded_sentence_is_cut(self):
        answer, reviewer = self.run_answer(ANSWER, '{"supported": false, "unsupported_sentences": '
                                           '["O swap demora no máximo 30 segundos em qualquer rede."], "reason": "x"}')
        self.assertEqual(reviewer.calls, 1)
        self.assertNotIn('30 segundos', answer.text)
        self.assertIn('fonte de cotação', answer.text)

    def test_mostly_ungrounded_reply_is_withheld(self):
        text = 'A Z-SWAP é parceira oficial da Binance e da Coinbase desde 2024.'
        answer, _ = self.run_answer(text, '{"supported": false, "unsupported_sentences": ["' + text
                                    + '"], "reason": "x"}')
        self.assertEqual(answer.text, UNGROUNDED_FALLBACK)

    def test_unreadable_review_keeps_the_guard_decision(self):
        answer, _ = self.run_answer(ANSWER.split('\n')[0], 'não sei')
        self.assertIn('fonte de cotação', answer.text)

    def test_no_review_without_the_approved_stronger_model(self):
        answer, reviewer = self.run_answer(ANSWER, '{"supported": false, "unsupported_sentences": '
                                           '["O swap demora no máximo 30 segundos em qualquer rede."], "reason": "x"}',
                                           approved=False)
        self.assertEqual(reviewer.calls, 0)

    def test_reviewer_cannot_approve_what_the_guard_rejected(self):
        bad = 'A Z-SWAP garante lucro em todos os swaps e a fonte de cotação depende das redes.'
        answer, _ = self.run_answer(bad, '{"supported": true, "unsupported_sentences": [], "reason": "ok"}')
        self.assertNotIn('garante lucro', answer.text)


if __name__ == '__main__':
    unittest.main()
