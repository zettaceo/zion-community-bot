import asyncio
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from tests.helpers import make_settings
from tests.test_mistral_boundaries import FakePrivateSecretStore
from zion.db import ZionDB
from zion.evaluation import evaluate_case
from zion.evaluation_budget import EvaluationBudget, PRICES
from zion.evaluation_native import NativeEvaluationClient
from zion.knowledge import KnowledgeBase
from zion.knowledge_tools import KnowledgeTools
from zion.mistral import MistralClient, MistralRawResponse

ROOT = Path(__file__).resolve().parents[1]
MODEL = 'ministral-8b-2512'


class NativeEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.db = ZionDB(Path(self.tmp.name) / 'evaluation.db'); self.db.initialize()
        self.addCleanup(self.db.close)
        self.budget = EvaluationBudget(self.db)
        self.knowledge = KnowledgeBase(ROOT / 'knowledge')
        self.settings = replace(make_settings(Path(self.tmp.name)), mistral_model=MODEL,
            mistral_rate_limit_retries=0, mistral_max_tokens=700)
        self.client = NativeEvaluationClient(self.settings, FakePrivateSecretStore(),
            knowledge_tools=KnowledgeTools(self.knowledge), budget=self.budget)
        price = EvaluationBudget.price(MODEL, PRICES[MODEL].verified_on)
        self.pricing = patch.object(EvaluationBudget, 'price', return_value=price)
        self.pricing.start(); self.addCleanup(self.pricing.stop)
        self.case = {'id': 'native', 'turns': ['Como funciona o swap?'],
                     'expected_speaker': 'mimir', 'required_terms': []}

    def run_case(self):
        return asyncio.run(evaluate_case(self.case, knowledge=self.knowledge,
            provider=self.client, model=MODEL, budget=self.budget))

    def entries(self):
        return list(json.loads(self.db.get_setting(self.budget.STATE_KEY))['entries'].values())

    def test_two_native_calls_each_reserve_before_network_and_settle_once(self):
        calls = []
        async def chat(messages, **kwargs):
            calls.append((messages, kwargs))
            entries = self.entries()
            self.assertEqual(len(entries), len(calls))
            self.assertEqual(sum(e['status'] == 'reserved' for e in entries), 1)
            if len(calls) == 1:
                tool = {'id': 'call00001', 'type': 'function', 'function':
                        {'name': 'get_supported_networks', 'arguments': '{}'}}
                return MistralRawResponse('', MODEL, 20, 10, 1, [tool])
            self.assertEqual(kwargs['tool_choice'], 'none')
            self.assertTrue(any(m['role'] == 'tool' for m in messages))
            return MistralRawResponse('Consulte a disponibilidade da rota.', MODEL, 30, 15, 2)
        with patch.object(MistralClient, '_chat', side_effect=chat):
            result = self.run_case()
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        self.assertEqual(result['human_review'], 'PENDING')
        self.assertEqual(result['native_requests'], 2)
        self.assertEqual(result['input_tokens'], 50)
        self.assertTrue(all(e['status'] == 'settled' for e in self.entries()))
        self.assertEqual(self.budget.total_micro_usd(), result['estimated_micro_usd'])

    def test_uncertain_second_call_retains_reservation_and_withholds_error_body(self):
        count = 0
        async def chat(messages, **kwargs):
            nonlocal count
            count += 1
            if count == 1:
                tool = {'id': 'call00001', 'type': 'function', 'function':
                        {'name': 'get_supported_networks', 'arguments': '{}'}}
                return MistralRawResponse('', MODEL, 20, 10, 1, [tool])
            raise RuntimeError('PRIVATE_PROVIDER_BODY')
        with patch.object(MistralClient, '_chat', side_effect=chat):
            result = self.run_case()
        self.assertEqual(result['status'], 'PROVIDER_FAIL')
        self.assertNotIn('PRIVATE_PROVIDER_BODY', str(result))
        self.assertEqual(sorted(e['status'] for e in self.entries()), ['reserved', 'settled'])
        self.assertEqual(count, 2)
        self.assertEqual(result['usage_outcome'], 'uncertain_reserved')

    def test_zero_budget_stops_before_first_native_request(self):
        self.budget.TOTAL_CAP = 0
        with patch.object(MistralClient, '_chat') as network:
            result = self.run_case()
        network.assert_not_called()
        self.assertEqual(result['usage_outcome'], 'no_uncertain_charge')
        self.assertEqual(result['native_requests'], 0)
        self.assertEqual(result['status'], 'PROVIDER_FAIL')

    def test_second_request_budget_denial_does_not_send_completion(self):
        calls = 0
        async def chat(messages, **kwargs):
            nonlocal calls
            calls += 1
            self.budget.TOTAL_CAP = 0
            tool = {'id': 'call00001', 'type': 'function', 'function':
                    {'name': 'get_supported_networks', 'arguments': '{}'}}
            return MistralRawResponse('', MODEL, 20, 10, 1, [tool])
        with patch.object(MistralClient, '_chat', side_effect=chat):
            result = self.run_case()
        self.assertEqual(calls, 1)
        self.assertEqual(result['usage_outcome'], 'no_uncertain_charge')
        self.assertEqual(result['native_requests'], 1)
        self.assertEqual(len(self.entries()), 1)
        self.assertEqual(self.entries()[0]['status'], 'settled')
        self.assertEqual(result['status'], 'PROVIDER_FAIL')

    def test_retry_configuration_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'evaluation_retries_forbidden'):
            NativeEvaluationClient(replace(self.settings, mistral_rate_limit_retries=1),
                FakePrivateSecretStore(), knowledge_tools=KnowledgeTools(self.knowledge),
                budget=self.budget)
