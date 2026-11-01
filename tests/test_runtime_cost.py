import tempfile
import unittest
from datetime import date
from pathlib import Path

from zion.db import ZionDB
from zion.evaluation_budget import PriceSnapshot
from zion.provider_budget import ProviderTokenBudget, ProviderBudgetError
from zion.runtime_cost import RuntimeCostBudget, RequestAdmission

DAY = date(2026, 10, 20)


class RuntimeCostTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.db = ZionDB(Path(tmp.name) / 'cost.db'); self.db.initialize(); self.addCleanup(self.db.close)
        self.tokens = ProviderTokenBudget(self.db, daily_limit=10000,
            provider_limits={'mistral': 10000}, model_limits={'model': 10000})
        self.costs = self.policy()
        self.admission = RequestAdmission(self.tokens, self.costs)

    def policy(self, price=1000000, request=2000):
        return RuntimeCostBudget(self.db, daily_limit=5000, request_limit=request,
            provider_limits={'mistral': 5000}, model_limits={'model': 4000},
            prices={'model': PriceSnapshot('model', price, price*2, DAY)})

    def test_compound_reservation_and_settlement_keep_separate_units(self):
        ref = self.admission.reserve('mistral', 'model', 100, today=DAY)
        self.assertEqual(self.admission.totals(today=DAY)['total'], 100)
        self.assertEqual(self.costs.totals(today=DAY)['total'], 240)
        self.admission.settle(ref, 20, 10)
        self.assertEqual(self.admission.totals(today=DAY)['total'], 30)
        self.assertEqual(self.costs.totals(today=DAY)['total'], 48)

    def test_cost_denial_rolls_back_token_reservation_atomically(self):
        with self.assertRaises(ProviderBudgetError):
            self.admission.reserve('mistral', 'model', 1000, today=DAY)
        self.assertEqual(self.tokens.totals(today=DAY)['total'], 0)
        self.assertEqual(self.costs.totals(today=DAY)['total'], 0)

    def test_restart_uses_frozen_price_not_new_rate(self):
        ref = self.costs.reserve('mistral', 'model', 100, today=DAY)
        self.policy(price=9000000).settle(ref, 20, 10)
        self.assertEqual(self.costs.totals(today=DAY)['total'], 48)

    def test_stale_price_and_clock_regression_block_new_calls(self):
        for day in (date(2026, 10, 19), date(2026, 10, 22)):
            with self.assertRaisesRegex(ProviderBudgetError, 'price_missing_or_stale'):
                self.admission.reserve('mistral', 'model', 100, today=day)
        self.assertEqual(self.tokens.totals(today=DAY)['total'], 0)

    def test_unknown_outcome_retains_both_charges_after_restart(self):
        ref = self.admission.reserve('mistral', 'model', 100, today=DAY)
        self.admission.retain_uncertain(ref)
        self.assertEqual(self.tokens.totals(today=DAY)['total'], 100)
        self.assertEqual(self.policy().totals(today=DAY)['total'], 240)

    def test_overrun_poison_is_not_rolled_back(self):
        ref = self.costs.reserve('mistral', 'model', 10, today=DAY)
        with self.assertRaises(ProviderBudgetError):
            self.costs.settle(ref, 100, 100)
        with self.assertRaises(ProviderBudgetError):
            self.policy().reserve('mistral', 'model', 1, today=DAY)

    def test_invalid_currency_policy_never_means_unlimited(self):
        with self.assertRaises(ValueError):
            self.policy(request=0)
        with self.assertRaises(ValueError):
            self.policy(price=-1)
