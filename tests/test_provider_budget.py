import asyncio
import concurrent.futures
import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

import httpx

from tests.helpers import make_settings
from tests.test_mistral_boundaries import FakePrivateSecretStore, SequenceAsyncClient
from zion.db import ZionDB
from zion.mistral import MistralClient
from zion.provider_budget import ProviderTokenBudget, ProviderBudgetError


DAY = date(2026, 10, 20)


class ProviderBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = ZionDB(self.root / 'test.db'); self.db.initialize()
        self.addCleanup(self.db.close)
        self.budget = self.policy(self.db)

    def policy(self, db, cap=100):
        return ProviderTokenBudget(db, daily_limit=cap,
            provider_limits={'mistral': cap, 'kimi': cap},
            model_limits={'model-a': cap, 'model-b': cap})

    def test_reservation_survives_restart_without_a_response(self):
        ref = self.budget.reserve('mistral', 'model-a', 80, today=DAY)
        other = ZionDB(self.root / 'test.db')
        try:
            restarted = self.policy(other)
            with self.assertRaises(ProviderBudgetError):
                restarted.reserve('kimi', 'model-b', 21, today=DAY)
            restarted.settle(ref, 20, 10)
            self.assertEqual(restarted.totals(today=DAY)['total'], 30)
            with self.assertRaises(ProviderBudgetError):
                restarted.settle(ref, 20, 10)
        finally:
            other.close()

    def test_provider_and_model_caps_are_independent_of_global(self):
        for providers, models, blocked in (
            ({'mistral': 50, 'kimi': 100}, {'model-a': 100, 'model-b': 100}, ('mistral', 'model-b')),
            ({'mistral': 100, 'kimi': 100}, {'model-a': 50, 'model-b': 100}, ('kimi', 'model-a')),
        ):
            self.db._conn.execute('DELETE FROM settings WHERE key=?', (ProviderTokenBudget.KEY,))
            budget = ProviderTokenBudget(self.db, daily_limit=100,
                provider_limits=providers, model_limits=models)
            budget.reserve('mistral', 'model-a', 40, today=DAY)
            with self.assertRaises(ProviderBudgetError):
                budget.reserve(*blocked, 20, today=DAY)
            budget.reserve('kimi', 'model-b', 20, today=DAY)

    def test_uncertain_retains_charge_and_no_prompt_data_is_stored(self):
        ref = self.budget.reserve('mistral', 'model-a', 80, today=DAY)
        self.budget.retain_uncertain(ref)
        self.assertEqual(self.budget.totals(today=DAY)['total'], 80)
        state = json.loads(self.db.get_setting(self.budget.KEY))
        self.assertFalse(state['pending'])
        self.assertEqual(set(state), {'version', 'poisoned', 'days', 'pending'})

    def test_parallel_connections_cannot_overspend(self):
        def attempt(_):
            db = ZionDB(self.root / 'test.db')
            try:
                self.policy(db).reserve('mistral', 'model-a', 30, today=DAY)
                return True
            except ProviderBudgetError:
                return False
            finally:
                db.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(attempt, range(12)))
        self.assertEqual(sum(results), 3)
        self.assertEqual(self.budget.totals(today=DAY)['total'], 90)

    def test_midnight_settles_original_day_and_clock_rollback_fails_closed(self):
        ref = self.budget.reserve('mistral', 'model-a', 80, today=DAY)
        tomorrow = date(2026, 10, 21)
        self.budget.reserve('mistral', 'model-a', 50, today=tomorrow)
        self.budget.settle(ref, 15, 5)
        self.assertEqual(self.budget.totals(today=DAY)['total'], 20)
        self.assertEqual(self.budget.totals(today=tomorrow)['total'], 50)
        with self.assertRaises(ProviderBudgetError):
            self.budget.reserve('mistral', 'model-a', 1, today=DAY)

    def test_usage_overrun_poison_is_persistent(self):
        ref = self.budget.reserve('mistral', 'model-a', 50, today=DAY)
        with self.assertRaises(ProviderBudgetError):
            self.budget.settle(ref, 60, 1)
        with self.assertRaises(ProviderBudgetError):
            self.policy(self.db).reserve('kimi', 'model-b', 1, today=DAY)

    def test_corrupt_state_and_unapproved_model_fail_closed(self):
        with self.assertRaises(ProviderBudgetError):
            self.budget.reserve('mistral', 'unapproved', 1, today=DAY)
        self.db.set_setting(self.budget.KEY, '{broken')
        with self.assertRaises(ProviderBudgetError):
            self.budget.reserve('mistral', 'model-a', 1, today=DAY)

    def test_ai_service_exposes_ledger_failure_and_does_not_double_count(self):
        from zion.ai_service import AIService
        from zion.knowledge import KnowledgeBase
        settings = replace(make_settings(self.root), ai_daily_token_budget=1000)
        ai = AIService(settings, self.db, KnowledgeBase(self.root / 'missing-knowledge'))
        ref = ai.provider_token_budget.reserve('mistral', settings.mistral_model, 500)
        ai.provider_token_budget.retain_uncertain(ref)
        with patch.object(ai, 'tokens_used_today', return_value=300):
            self.assertEqual(ai.budget_remaining(), 500)
        self.db.set_setting(ProviderTokenBudget.KEY, '{broken')
        self.assertFalse(ai.accounting_healthy)
        self.assertEqual(ai.budget_remaining(), 0)
        self.assertFalse(ai.budget_available())

    def client(self, cap=100000):
        settings = replace(make_settings(self.root), ai_enabled=True,
            mistral_min_request_interval_ms=0, mistral_rate_limit_retries=1)
        budget = ProviderTokenBudget(self.db, daily_limit=cap,
            provider_limits={'mistral': cap}, model_limits={settings.mistral_model: cap})
        return MistralClient(settings, FakePrivateSecretStore(), token_budget=budget)

    @staticmethod
    def ok_response():
        return httpx.Response(200, json={'choices': [{'message': {'content': 'Resposta pública'}}],
            'usage': {'prompt_tokens': 20, 'completion_tokens': 10}})

    def test_wire_attempt_is_reserved_before_send_and_usage_settled(self):
        client = self.client()
        outer = self
        class CheckingClient(SequenceAsyncClient):
            async def post(self, *args, **kwargs):
                outer.assertGreater(client.token_budget.totals()['total'], 30)
                return await super().post(*args, **kwargs)
        http = CheckingClient([self.ok_response()])
        with patch('zion.mistral.httpx.AsyncClient', return_value=http):
            asyncio.run(client._chat([{'role': 'user', 'content': 'synthetic-only'}]))
        self.assertEqual(client.token_budget.totals()['total'], 30)
        self.assertNotIn('synthetic-only', self.db.get_setting(ProviderTokenBudget.KEY))

    def test_provider_cannot_change_the_approved_model_in_its_response(self):
        client = self.client()
        data = self.ok_response().json()
        data['model'] = 'unapproved-model'
        http = SequenceAsyncClient([httpx.Response(200, json=data)])
        with patch('zion.mistral.httpx.AsyncClient', return_value=http):
            with self.assertRaises(ProviderBudgetError):
                asyncio.run(client._chat([{'role': 'user', 'content': 'synthetic'}]))
        self.assertGreater(client.token_budget.totals()['total'], 30)
        self.assertNotIn('unapproved-model', client.token_budget.totals()['models'])

    def test_admission_failure_sends_nothing(self):
        client = self.client(cap=1)
        http = SequenceAsyncClient([])
        with patch('zion.mistral.httpx.AsyncClient', return_value=http):
            with self.assertRaises(ProviderBudgetError):
                asyncio.run(client._chat([{'role': 'user', 'content': 'synthetic'}]))
        self.assertFalse(http.calls)

    def test_429_retry_does_not_erase_first_attempt_reservation(self):
        client = self.client()
        http = SequenceAsyncClient([httpx.Response(429, headers={'retry-after': '0'}), self.ok_response()])
        with patch('zion.mistral.httpx.AsyncClient', return_value=http):
            asyncio.run(client._chat([{'role': 'user', 'content': 'synthetic'}]))
        self.assertEqual(len(http.calls), 2)
        self.assertGreater(client.token_budget.totals()['total'], 4096)
        self.assertFalse(json.loads(self.db.get_setting(ProviderTokenBudget.KEY))['pending'])

    def test_timeout_and_cancellation_retain_reserved_charge(self):
        for error in (httpx.ReadTimeout('synthetic'), asyncio.CancelledError()):
            with self.subTest(error=type(error).__name__):
                client = self.client()
                class FailingHTTP(SequenceAsyncClient):
                    async def post(self, *args, **kwargs):
                        raise error
                before = client.token_budget.totals()['total']
                with patch('zion.mistral.httpx.AsyncClient', return_value=FailingHTTP([])):
                    with self.assertRaises(type(error)):
                        asyncio.run(client._chat([{'role': 'user', 'content': 'synthetic'}]))
                self.assertGreater(client.token_budget.totals()['total'], before)
