"""2026-11-19: the runtime budget would refuse every AI call from 2026-12-17 (prices
verified 2026-11-01 + 45 days) and nothing warned the operator. Health now does."""
from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
import unittest

from zion.escalation import KIMI_MODEL, PRICE_WARN_DAYS, RUNTIME_PRICE_AGE_DAYS, expiry_issues
from zion.evaluation_budget import PRICES


def settings(**kw):
    base = dict(kimi_escalation_enabled=True, mistral_model="ministral-8b-2512", kimi_approval_until="2099-01-31")
    base.update(kw)
    return SimpleNamespace(**base)


class ExpiryIssues(unittest.TestCase):
    def vence(self, model):
        return PRICES[model].verified_on + timedelta(days=RUNTIME_PRICE_AGE_DAYS)

    def test_longe_do_prazo_nao_avisa(self):
        hoje = min(self.vence("ministral-8b-2512"), self.vence(KIMI_MODEL)) - timedelta(days=PRICE_WARN_DAYS + 1)
        self.assertEqual(expiry_issues(settings(), today=hoje), [])

    def test_avisa_14_dias_antes_e_depois_de_vencer(self):
        m = "ministral-8b-2512"
        self.assertIn(f"ai_price_expires_soon:{m}", expiry_issues(settings(), today=self.vence(m) - timedelta(days=PRICE_WARN_DAYS)))
        self.assertIn(f"ai_price_expires_soon:{m}", expiry_issues(settings(), today=self.vence(m)))
        self.assertIn(f"ai_price_expired:{m}", expiry_issues(settings(), today=self.vence(m) + timedelta(days=1)))

    def test_modelo_sem_preco(self):
        self.assertIn("ai_price_unknown:modelo-x", expiry_issues(settings(mistral_model="modelo-x"), today=date(2026, 11, 21)))

    def test_aprovacao_do_kimi(self):
        s = settings(kimi_approval_until="2027-01-31")
        self.assertNotIn("kimi_approval_expires_soon", expiry_issues(s, today=date(2027, 1, 10)))
        self.assertIn("kimi_approval_expires_soon", expiry_issues(s, today=date(2027, 1, 20)))
        self.assertIn("kimi_approval_expired", expiry_issues(s, today=date(2027, 2, 1)))

    def test_escalacao_desligada_nao_tem_prazo(self):
        self.assertEqual(expiry_issues(settings(kimi_escalation_enabled=False), today=date(2030, 1, 1)), [])

    def test_tabela_atual_nao_avisa_hoje(self):
        self.assertEqual(expiry_issues(settings(kimi_approval_until="2027-01-31"), today=date(2026, 11, 21)), [])


if __name__ == "__main__":
    unittest.main()
