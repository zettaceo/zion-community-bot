"""Owner-approved Kimi K3 escalation: composition, scope and fail-safes."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.helpers import make_settings
from zion.ai_service import AIService
from zion.db import ZionDB
from zion.escalation import (KIMI_MODEL, approval_expiry, build_ai_composition,
                             escalation_status)
from zion.evaluation_budget import PRICES
from zion.knowledge import KnowledgeBase
from zion.models import AIAnswer
from zion.provider_budget import ProviderTokenBudget
from zion.providers import Completion
from zion.runtime_cost import RuntimeCostBudget
from zion.secret_store import SecretStore

ROOT = Path(__file__).resolve().parents[1]


class Store:
    def __init__(self, status=SecretStore.PRIVATE):
        self._status = status

    def status(self):
        return self._status

    def read(self):
        return 'synthetic-kimi-key-for-tests-0000000000'


class FakeKimi:
    configured = True

    def __init__(self):
        self.calls = []

    async def complete(self, messages, *, max_tokens):
        self.calls.append(messages)
        return Completion('Resposta do K3 baseada na fonte pública.', KIMI_MODEL, 900, 80, 5)


class FakeMistral:
    configured = True

    def __init__(self):
        self.calls = 0

    async def answer(self, **_kwargs):
        self.calls += 1
        return AIAnswer(text='Resposta do Ministral.', model='ministral-8b-2512',
                        input_tokens=10, output_tokens=5, latency_ms=1)


class EscalationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = replace(make_settings(Path(temp.name)), ai_enabled=True,
                            knowledge_dir=ROOT / 'knowledge', ai_daily_token_budget=1000000)
        self.db = ZionDB(self.base.db_path)
        self.db.initialize()
        self.addCleanup(self.db.close)
        tomorrow = (date.today() + timedelta(days=2)).isoformat()
        self.active = replace(self.base, kimi_escalation_enabled=True,
                              kimi_approval_until=tomorrow, ai_daily_usd_cap=2.0)

    def test_off_by_default_keeps_the_baseline_only_service(self):
        self.assertEqual(escalation_status(self.base, Store()), 'off')
        self.assertEqual(build_ai_composition(self.base, self.db, Store()), {})

    def test_every_missing_condition_blocks(self):
        yesterday = (date.today() - timedelta(days=2)).isoformat()
        cases = {
            'blocked:approval_date_missing': replace(self.active, kimi_approval_until=''),
            'blocked:approval_expired': replace(self.active, kimi_approval_until=yesterday),
            'blocked:price_unknown': replace(self.active, mistral_model='unpriced-model'),
        }
        for expected, settings in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(escalation_status(settings, Store()), expected)
                self.assertEqual(build_ai_composition(settings, self.db, Store()), {})
        self.assertEqual(escalation_status(self.active, Store(SecretStore.MISSING)),
                         'blocked:credential_unavailable')

    def test_approval_expires_at_end_of_day_utc(self):
        self.assertIsNone(approval_expiry('amanhã'))
        self.assertEqual(approval_expiry('2026-11-02') - approval_expiry('2026-11-01'), 86400)

    def service(self):
        composition = build_ai_composition(self.active, self.db, Store())
        self.assertEqual(set(composition), {'generation_policy', 'completion_providers',
                                            'runtime_cost_budget'})
        kimi = FakeKimi()
        composition['completion_providers'] = {('kimi', KIMI_MODEL): kimi}
        ai = AIService(self.active, self.db, KnowledgeBase(ROOT / 'knowledge'), **composition)
        ai.client = FakeMistral()
        return ai, kimi

    def ask(self, ai, question, agent='zion'):
        today = PRICES[KIMI_MODEL].verified_on
        with patch.object(ProviderTokenBudget, 'today', return_value=today), \
                patch.object(RuntimeCostBudget, 'today', return_value=today):
            return asyncio.run(ai.answer(chat_id=1, user_id=2, question=question, agent_id=agent))

    def test_only_hard_public_turns_go_to_k3_without_history(self):
        ai, kimi = self.service()
        answer = self.ask(ai, 'Concerteza deve ter plataformas mais baratas, que oferecem '
                              'a mesma coisa que a zswap e já consolidadas no mercado')
        self.assertEqual(answer.model, KIMI_MODEL)
        # One generation, then one grounding review of that reply.
        self.assertEqual(len(kimi.calls), 2)
        sent = str(kimi.calls[0])
        self.assertNotIn('User:', sent)
        simple = self.ask(ai, 'Quais redes a Z-SWAP suporta atualmente?')
        self.assertNotEqual(simple.model, KIMI_MODEL)
        self.assertEqual(len(kimi.calls), 2)

    def test_spent_kimi_budget_falls_back_to_the_baseline_answer(self):
        ai, kimi = self.service()
        ai.runtime_cost_budget.request_limit = 1
        answer = self.ask(ai, 'Concerteza deve ter plataformas mais baratas, que oferecem '
                              'a mesma coisa que a zswap e já consolidadas no mercado')
        self.assertEqual(kimi.calls, [])
        self.assertNotIn('limite de uso', answer.text)


if __name__ == '__main__':
    unittest.main()
