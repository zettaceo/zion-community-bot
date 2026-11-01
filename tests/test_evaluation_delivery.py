from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.helpers import make_settings
from zion.db import ZionDB
from zion.evaluation import load_cases
from zion.evaluation_budget import EvaluationBudget, PRICES
from zion.evaluation_delivery import (DeliveryEvaluationService,
                                      PublicEvaluationKnowledge,
                                      evaluate_delivery_case)
from zion.knowledge import KnowledgeClassification
from zion.providers import Completion, ProviderError


ROOT = Path(__file__).resolve().parents[1]
CASES = {case['id']: case for case in load_cases(ROOT / 'evaluations/cognitive-v2.jsonl')}


class FakeProvider:
    configured = True

    def __init__(self, text: str = 'A Z-SWAP compara rotas disponíveis conforme as condições do momento.',
                 error: bool = False):
        self.text = text
        self.error = error
        self.messages = []

    async def complete(self, messages, *, max_tokens):
        self.messages.append(messages)
        if self.error:
            raise ProviderError('provider_unavailable')
        return Completion(self.text, 'kimi-k3', 120, 30, 1)


class DeliveryEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.settings = make_settings(root)
        self.db = ZionDB(root / 'service.db')
        self.db.initialize()
        self.addCleanup(self.db.close)
        self.budget = EvaluationBudget(self.db)
        self.knowledge = PublicEvaluationKnowledge(ROOT / 'knowledge')

    def service(self, provider):
        return DeliveryEvaluationService(
            self.settings, self.db, self.knowledge,
            provider=provider, evaluation_budget=self.budget,
        )

    def evaluate(self, case_id, service):
        # The fixture pins the price only; no network or production ledger.
        with patch.object(EvaluationBudget, 'price', return_value=PRICES['kimi-k3']):
            return asyncio.run(evaluate_delivery_case(CASES[case_id], service=service))

    def test_wallet_case_is_delivered_locally_without_provider_or_cost(self):
        provider = FakeProvider(error=True)
        result = self.evaluate('v2-041', self.service(provider))
        self.assertEqual(result['status'], 'LOCAL_REVIEW_REQUIRED')
        self.assertEqual(result['model'], 'zion-local')
        self.assertEqual(result['provider_calls'], 0)
        self.assertEqual(result['estimated_micro_usd'], 0)
        self.assertEqual(provider.messages, [])
        self.assertIn('qual carteira', result['response'].casefold())
        self.assertIn('senha da carteira', result['response'])

    def test_finite_networks_are_expected_local_delivery_not_kimi_credit(self):
        provider = FakeProvider(error=True)
        for case_id in ('v2-021', 'v2-091'):
            with self.subTest(case_id=case_id):
                result = self.evaluate(case_id, self.service(provider))
                self.assertEqual(result['status'], 'LOCAL_REVIEW_REQUIRED')
                self.assertEqual(result['provider_calls'], 0)
                self.assertEqual(result['estimated_micro_usd'], 0)
        self.assertEqual(provider.messages, [])

    def test_unexpected_local_fallback_does_not_qualify_smoke(self):
        provider = FakeProvider(error=True)
        service = DeliveryEvaluationService(
            self.settings, self.db,
            PublicEvaluationKnowledge(Path(self.temp.name) / 'empty-knowledge'),
            provider=provider, evaluation_budget=self.budget,
        )
        result = self.evaluate('v2-001', service)
        self.assertEqual(result['status'], 'HARNESS_FAIL')
        self.assertEqual(result['provider_calls'], 0)

    def test_wallet_source_unavailable_cannot_qualify_local_delivery(self):
        service = DeliveryEvaluationService(
            self.settings, self.db,
            PublicEvaluationKnowledge(Path(self.temp.name) / 'empty-knowledge'),
            provider=FakeProvider(error=True), evaluation_budget=self.budget,
        )
        result = self.evaluate('v2-041', service)
        self.assertEqual(result['status'], 'HARNESS_FAIL')
        self.assertEqual(result['provider_calls'], 0)

    def test_provider_receives_only_public_current_knowledge_and_no_history(self):
        provider = FakeProvider()
        service = self.service(provider)
        result = self.evaluate('v2-001', service)
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        self.assertEqual(result['provider_calls'], 1)
        self.assertGreater(result['estimated_micro_usd'], 0)
        self.assertEqual(len(provider.messages), 1)
        self.assertTrue(all(c.authority.classification is KnowledgeClassification.PUBLIC
                            for c in self.knowledge.chunks))
        self.assertNotIn('User:', str(provider.messages[0]))
        self.assertFalse(self.db._conn.execute(
            'SELECT COUNT(*) FROM ai_events WHERE purpose=? AND success=0',
            ('response_guard',),
        ).fetchone()[0])

    def test_guard_fallback_cannot_turn_rejected_generation_into_pass(self):
        provider = FakeProvider(text='Consulte /home/operator/private para acessar a chave.')
        result = self.evaluate('v2-001', self.service(provider))
        self.assertEqual(result['status'], 'AUTOMATED_FAIL')
        self.assertEqual(result['response'], '[WITHHELD_BY_OUTPUT_GUARD]')
        self.assertEqual(result['provider_calls'], 1)
        self.assertGreater(result['estimated_micro_usd'], 0)

    def test_provider_failure_keeps_uncertain_reservation_and_withholds_fallback(self):
        provider = FakeProvider(error=True)
        result = self.evaluate('v2-001', self.service(provider))
        self.assertEqual(result['status'], 'PROVIDER_FAIL')
        self.assertEqual(result['provider_calls'], 1)
        self.assertEqual(result['response'], '[WITHHELD_BY_OUTPUT_GUARD]')
        self.assertGreater(result['estimated_micro_usd'], 0)
        self.assertEqual(result['error_type'], 'ProviderError')
        self.assertEqual(result['usage_outcome'], 'uncertain_reserved')

    def test_cost_cap_blocks_before_provider_request(self):
        provider = FakeProvider()
        self.budget.REQUEST_CAP = 1
        result = self.evaluate('v2-001', self.service(provider))
        self.assertEqual(result['status'], 'BUDGET_BLOCKED')
        self.assertEqual(result['provider_calls'], 0)
        self.assertEqual(provider.messages, [])

    def test_missing_service_accounting_event_is_harness_failure(self):
        provider = FakeProvider()
        service = self.service(provider)
        with patch.object(service, '_record_ai_event', return_value=False):
            result = self.evaluate('v2-001', service)
        self.assertEqual(result['status'], 'HARNESS_FAIL')
        self.assertEqual(result['provider_calls'], 1)

    def test_public_projection_stays_public_after_reload(self):
        self.assertEqual(self.knowledge.load_errors, [])
        self.assertTrue(self.knowledge.chunks)
        self.assertTrue(all(c.authority.classification is KnowledgeClassification.PUBLIC
                            for c in self.knowledge.chunks))
        self.knowledge.reload()
        self.assertTrue(all(c.authority.classification is KnowledgeClassification.PUBLIC
                            for c in self.knowledge.chunks))


if __name__ == '__main__':
    unittest.main()
