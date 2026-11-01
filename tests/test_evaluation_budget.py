from __future__ import annotations
import concurrent.futures
from datetime import date
from pathlib import Path
import tempfile
import unittest

from zion.db import ZionDB
from zion.evaluation_budget import EvaluationBudget, EvaluationBudgetError, PRICES
from zion.providers import Completion

TODAY = PRICES['kimi-k2.6'].verified_on
MESSAGES = [{'role': 'user', 'content': 'Pergunta sintética'}]


class EvaluationBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'evaluation.db'
        self.db = ZionDB(self.path); self.db.initialize(); self.addCleanup(self.db.close)
        self.budget = EvaluationBudget(self.db)

    def test_stronger_mistral_uses_verified_price_and_shared_budget(self):
        mistral_verified_on = date(2026, 10, 19)
        price = EvaluationBudget.price('mistral-large-2512', mistral_verified_on)
        self.assertEqual(price.cost(1000, 500), 1500)
        reservation = self.budget.reserve('mistral-large-2512',
            [{'role': 'user', 'content': 'synthetic ' * 1000}], 700,
            today=mistral_verified_on)
        self.assertGreater(self.budget.total_micro_usd(), 1500)
        charged = self.budget.settle(reservation,
            Completion('Approved answer', 'mistral-large-2512', 1000, 500, 1))
        self.assertEqual(charged, 1500)
        self.assertEqual(self.budget.total_micro_usd(), 1500)

    def test_uncertain_charge_survives_new_connection_and_settlement_is_once(self):
        reservation = self.budget.reserve('kimi-k2.6', MESSAGES, 128, today=TODAY)
        reserved = self.budget.total_micro_usd()
        self.assertEqual(self.budget.charge_for(reservation), reserved)
        other = ZionDB(self.path)
        try:
            restarted = EvaluationBudget(other)
            self.assertEqual(restarted.total_micro_usd(), reserved)
            actual = restarted.settle(reservation, Completion('public', 'kimi-k2.6', 10, 5, 1))
            self.assertLess(actual, reserved)
            self.assertEqual(restarted.charge_for(reservation), actual)
            with self.assertRaises(EvaluationBudgetError):
                restarted.settle(reservation, Completion('public', 'kimi-k2.6', 10, 5, 1))
        finally:
            other.close()

    def test_racing_connections_cannot_exceed_cap(self):
        # All workers use the same SQLite ledger, not an in-memory lock.
        self.budget.DAILY_CAP = 100000
        def reserve_once(_):
            db = ZionDB(self.path)
            try:
                budget = EvaluationBudget(db); budget.DAILY_CAP = 100000
                try:
                    budget.reserve('kimi-k2.6', MESSAGES, 128, today=TODAY)
                    return True
                except EvaluationBudgetError:
                    return False
            finally:
                db.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(reserve_once, range(30)))
        self.assertTrue(any(results)); self.assertFalse(all(results))
        self.assertLessEqual(self.budget.total_micro_usd(), 100000)

    def test_corrupt_state_and_stale_or_unknown_prices_fail_closed(self):
        for model, day in [('invented', TODAY), ('kimi-k3', date(2026, 10, 22)),
                           ('kimi-k3', date(2026, 10, 18))]:
            with self.assertRaises(EvaluationBudgetError):
                self.budget.reserve(model, MESSAGES, 128, today=day)
        self.db.set_setting(self.budget.STATE_KEY, '{broken')
        with self.assertRaises(EvaluationBudgetError):
            self.budget.reserve('kimi-k2.6', MESSAGES, 128, today=TODAY)

    def test_usage_overrun_is_persisted_and_blocks_future_requests(self):
        reservation = self.budget.reserve('kimi-k2.6', MESSAGES, 128, today=TODAY)
        with self.assertRaises(EvaluationBudgetError):
            self.budget.settle(reservation, Completion('public', 'kimi-k2.6', 100000, 10000, 1))
        with self.assertRaises(EvaluationBudgetError):
            EvaluationBudget(self.db).reserve('kimi-k2.6', MESSAGES, 128, today=TODAY)

    def test_provider_model_switch_does_not_reset_shared_daily_or_total_caps(self):
        self.budget.DAILY_CAP = 1
        with self.assertRaises(EvaluationBudgetError):
            self.budget.reserve('kimi-k2.6', MESSAGES, 128, today=TODAY)
        with self.assertRaises(EvaluationBudgetError):
            self.budget.reserve('kimi-k3', MESSAGES, 128, today=TODAY)
        self.budget.DAILY_CAP = 2000000; self.budget.TOTAL_CAP = 1
        with self.assertRaises(EvaluationBudgetError):
            self.budget.reserve('kimi-k2.6', MESSAGES, 128, today=TODAY)
