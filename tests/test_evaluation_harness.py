from __future__ import annotations
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.helpers import write_test_knowledge_manifest
from zion.db import ZionDB
from zion.evaluation import evaluate_case, load_cases, public_context
from zion.evaluation_budget import EvaluationBudget, PRICES
from zion.knowledge import KnowledgeBase
from zion.providers import Completion, ProviderError


class EvaluationHarnessTests(unittest.TestCase):
    def test_dataset_is_versioned_synthetic_and_never_auto_accepted(self):
        cases = load_cases(Path(__file__).resolve().parents[1] / 'evaluations/cognitive-v2.jsonl')
        self.assertEqual(len(cases), 108)
        self.assertGreaterEqual(len({c['category'] for c in cases}), 17)
        self.assertEqual(len([c for c in cases if c['category'] == 'competitive_objection']), 3)
        self.assertTrue(all(c['human_review_required'] for c in cases))
        self.assertTrue(any(len(c['turns']) == 4 for c in cases))

    def test_single_turn_gold_routes_without_classifier(self):
        from zion.router import IntentRouter
        cases = load_cases(Path(__file__).resolve().parents[1] / 'evaluations/cognitive-v2.jsonl')
        for case in cases:
            if len(case['turns']) != 1:
                continue
            with self.subTest(case=case['id']):
                decision = IntentRouter().route_group(case['turns'][0], explicitly_addressed=True)
                self.assertIsNotNone(decision.speaker)
                self.assertEqual(decision.speaker.agent_id.value, case['expected_speaker'])
                self.assertFalse(decision.used_ai_fallback)

    def test_generation_followup_uses_user_history_but_resets_explicit_topic(self):
        from zion.evaluation import evaluation_context_query
        self.assertIn('Minha ordem sumiu', evaluation_context_query(
            ['Minha ordem sumiu', 'Isso é caro e não funciona, resolve agora']))
        changed = evaluation_context_query(['Como faço parceria?', 'Como funciona o swap?'])
        self.assertNotIn('parceria', changed)
        self.assertEqual(changed, 'Como funciona o swap?')

    def test_reserves_before_network_and_failure_is_not_refunded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); knowledge = KnowledgeBase(root / 'knowledge')
            db = ZionDB(root / 'evaluation.db'); db.initialize()
            try:
                budget = EvaluationBudget(db)
                class Provider:
                    async def complete(self, messages, *, max_tokens):
                        assert budget.total_micro_usd() > 0
                        assert not db._conn.in_transaction
                        raise ProviderError('timeout')
                case = {'id': 'synthetic', 'turns': ['Como funciona o swap?'],
                        'expected_speaker': 'mimir', 'required_terms': []}
                with patch.object(EvaluationBudget, 'price', return_value=EvaluationBudget.price('kimi-k2.6', PRICES['kimi-k2.6'].verified_on)):
                    result = asyncio.run(evaluate_case(case, knowledge=knowledge, provider=Provider(), model='kimi-k2.6', budget=budget))
                self.assertEqual(result['status'], 'PROVIDER_FAIL')
                self.assertGreater(budget.total_micro_usd(), 0)
                self.assertEqual(result['human_review'], 'PENDING')
            finally:
                db.close()

    def test_evaluation_excludes_controlled_sources_before_prompt(self):
        # Production corpus includes CONTROLLED technical projections; an
        # evaluated provider must see PUBLIC only even for MIMIR.
        from zion.knowledge import KnowledgeClassification
        knowledge = KnowledgeBase(Path(__file__).resolve().parents[1] / 'knowledge')
        for chunk in knowledge.chunks:
            if chunk.authority.classification is KnowledgeClassification.CONTROLLED:
                context = public_context(knowledge, chunk.heading, 'mimir')
                self.assertNotIn(chunk.text, context)

    def test_provider_error_body_and_rejected_answer_are_not_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); db = ZionDB(root / 'evaluation.db'); db.initialize()
            try:
                class Provider:
                    async def complete(self, messages, *, max_tokens):
                        return Completion('Veja /home/operator/private', 'kimi-k2.6', 10, 10, 1)
                case = {'id': 'synthetic', 'turns': ['Como funciona o swap?'],
                        'expected_speaker': 'mimir', 'required_terms': []}
                with patch.object(EvaluationBudget, 'price', return_value=EvaluationBudget.price('kimi-k2.6', PRICES['kimi-k2.6'].verified_on)):
                    result = asyncio.run(evaluate_case(case, knowledge=KnowledgeBase(root / 'knowledge'),
                        provider=Provider(), model='kimi-k2.6', budget=EvaluationBudget(db)))
                self.assertEqual(result['status'], 'AUTOMATED_FAIL')
                self.assertNotIn('/home/operator', str(result))
            finally:
                db.close()
