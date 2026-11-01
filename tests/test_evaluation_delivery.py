from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from tests.helpers import make_settings
from zion.db import ZionDB
from zion.evaluation import load_cases
from zion.evaluation_budget import EvaluationBudget, PRICES
from zion.evaluation_delivery import (BASELINE_MODEL,
                                      BaselineDeliveryEvaluationService,
                                      DeliveryEvaluationService,
                                      PublicEvaluationKnowledge,
                                      evaluate_delivery_case)
from zion.knowledge import KnowledgeClassification
from zion.provider_budget import ProviderTokenBudget
from zion.providers import Completion, ProviderError
from zion.runtime_cost import RuntimeCostBudget
from zion.secret_store import SecretStore


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


class _SyntheticMistralKey:
    def status(self):
        return SecretStore.PRIVATE

    def read(self):
        return 'synthetic-mistral-key-for-baseline-probe-123456'


class _MistralHTTP:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def post(self, url, *, headers, json):
        self.calls.append(json)
        return self.responses.pop(0)


def _mistral_ok(text, model=BASELINE_MODEL):
    return httpx.Response(200, json={
        'model': model,
        'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}],
        'usage': {'prompt_tokens': 900, 'completion_tokens': 60, 'total_tokens': 960},
    })


class BaselineDeliveryEvaluationTests(unittest.TestCase):
    """The production model through the production AIService/MistralClient path."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        # Same daily token budget as the probe script; the helper's small
        # default would block a retry after the first uncertain attempt.
        self.settings = replace(make_settings(root), ai_enabled=True,
                                ai_daily_token_budget=1000000,
                                mistral_min_request_interval_ms=0,
                                mistral_rate_limit_max_delay_seconds=0.0)
        self.db = ZionDB(root / 'evaluation-baseline.db')
        self.db.initialize()
        self.addCleanup(self.db.close)
        self.knowledge = PublicEvaluationKnowledge(ROOT / 'knowledge')

    def costs(self, *, request_limit=50000, daily_limit=500000):
        return RuntimeCostBudget(self.db, daily_limit=daily_limit,
            provider_limits={'mistral': daily_limit},
            model_limits={BASELINE_MODEL: daily_limit},
            request_limit=request_limit,
            prices={BASELINE_MODEL: PRICES[BASELINE_MODEL]})

    def service(self, costs):
        service = BaselineDeliveryEvaluationService(
            self.settings, self.db, self.knowledge, runtime_cost_budget=costs)
        service.secret_store = service.client.secret_store = _SyntheticMistralKey()
        return service

    def evaluate(self, case_id, service, responses):
        http = _MistralHTTP(responses)
        with patch('zion.mistral.httpx.AsyncClient', return_value=http), \
                patch.object(RuntimeCostBudget, 'today', return_value=PRICES[BASELINE_MODEL].verified_on), \
                patch.object(ProviderTokenBudget, 'today', return_value=PRICES[BASELINE_MODEL].verified_on):
            return asyncio.run(evaluate_delivery_case(CASES[case_id], service=service)), http

    def test_only_reviewed_production_model_is_accepted(self):
        with self.assertRaisesRegex(ValueError, 'delivery_probe_model_not_reviewed'):
            BaselineDeliveryEvaluationService(
                replace(self.settings, mistral_model='mistral-large-2512'),
                self.db, self.knowledge, runtime_cost_budget=self.costs())

    def test_ga_small_model_runs_the_same_path_with_its_own_price(self):
        model = 'mistral-small-2603'
        settings = replace(self.settings, mistral_model=model)
        costs = RuntimeCostBudget(self.db, daily_limit=500000,
            provider_limits={'mistral': 500000}, model_limits={model: 500000},
            request_limit=50000, prices={model: PRICES[model]})
        service = BaselineDeliveryEvaluationService(
            settings, self.db, self.knowledge, runtime_cost_budget=costs)
        service.secret_store = service.client.secret_store = _SyntheticMistralKey()
        http = _MistralHTTP([_mistral_ok(
            'A Z-SWAP compara rotas disponíveis conforme as condições do momento.', model=model)])
        with patch('zion.mistral.httpx.AsyncClient', return_value=http), \
                patch.object(ProviderTokenBudget, 'today', return_value=PRICES[model].verified_on):
            result = asyncio.run(evaluate_delivery_case(CASES['v2-001'], service=service))
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        self.assertEqual(http.calls[0]['model'], model)
        self.assertEqual(result['estimated_micro_usd'], PRICES[model].cost(900, 60))

    def test_baseline_generation_is_review_required_with_its_own_charge(self):
        costs = self.costs()
        result, http = self.evaluate('v2-001', self.service(costs), [
            _mistral_ok('A Z-SWAP compara rotas disponíveis conforme as condições do momento.')])
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        self.assertEqual(result['model'], BASELINE_MODEL)
        self.assertEqual(result['provider_calls'], 1)
        self.assertEqual(len(http.calls), 1)
        self.assertEqual(http.calls[0]['model'], BASELINE_MODEL)
        expected = PRICES[BASELINE_MODEL].cost(900, 60)
        self.assertEqual(result['estimated_micro_usd'], expected)
        with patch.object(ProviderTokenBudget, 'today', return_value=PRICES[BASELINE_MODEL].verified_on):
            self.assertEqual(costs.totals()['total'], expected)

    def test_rate_limit_retry_counts_every_attempt_and_keeps_uncertain_charge(self):
        costs = self.costs()
        result, http = self.evaluate('v2-001', self.service(costs), [
            httpx.Response(429, headers={'Retry-After': '0'}),
            _mistral_ok('A Z-SWAP compara rotas disponíveis conforme as condições do momento.')])
        self.assertEqual(len(http.calls), 2)
        self.assertEqual(result['provider_calls'], 2)
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        # The rate-limited attempt keeps its full worst-rate reservation.
        self.assertGreater(result['estimated_micro_usd'], PRICES[BASELINE_MODEL].cost(900, 60))

    def test_provider_failure_is_not_a_pass_and_withholds_fallback(self):
        result, _ = self.evaluate('v2-001', self.service(self.costs()), [
            httpx.Response(500)])
        self.assertEqual(result['status'], 'PROVIDER_FAIL')
        self.assertEqual(result['response'], '[WITHHELD_BY_OUTPUT_GUARD]')
        self.assertGreater(result['estimated_micro_usd'], 0)

    def test_request_cap_blocks_before_any_http_request(self):
        result, http = self.evaluate('v2-001', self.service(self.costs(request_limit=1)), [])
        self.assertEqual(http.calls, [])
        self.assertEqual(result['status'], 'BUDGET_BLOCKED')
        self.assertEqual(result['provider_calls'], 0)

    def test_guard_rejected_generation_is_automated_fail(self):
        result, _ = self.evaluate('v2-001', self.service(self.costs()), [
            _mistral_ok('A Z-SWAP garante lucro em todos os swaps e nunca falha.')])
        self.assertEqual(result['status'], 'AUTOMATED_FAIL')
        self.assertEqual(result['response'], '[WITHHELD_BY_OUTPUT_GUARD]')

    def test_unexpected_response_model_is_not_a_pass(self):
        result, _ = self.evaluate('v2-001', self.service(self.costs()), [
            _mistral_ok('Resposta.', model='mistral-large-2512')])
        self.assertNotIn(result['status'], {'REVIEW_REQUIRED', 'LOCAL_REVIEW_REQUIRED'})

    def test_open_circuit_is_reported_as_such_not_as_harness_failure(self):
        service = self.service(self.costs())
        with patch.object(type(service), 'circuit_open', return_value=True):
            result, http = self.evaluate('v2-001', service, [])
        self.assertEqual(http.calls, [])
        self.assertEqual(result['status'], 'CIRCUIT_OPEN')

    def test_local_wallet_case_needs_no_provider_or_credential_use(self):
        result, http = self.evaluate('v2-041', self.service(self.costs()), [])
        self.assertEqual(http.calls, [])
        self.assertEqual(result['status'], 'LOCAL_REVIEW_REQUIRED')
        self.assertEqual(result['estimated_micro_usd'], 0)
