from __future__ import annotations

import asyncio
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from zion.db import ZionDB
from zion.evaluation_budget import EvaluationBudget
from zion.evaluation_conversations import bounded_history, evaluate_conversation, load_conversations
from zion.knowledge import KnowledgeBase
from zion.providers import Completion, ProviderError

ROOT = Path(__file__).resolve().parents[1]


class ConversationEvaluationTests(unittest.TestCase):
    def test_dataset_has_long_synthetic_scenarios_for_all_four_agents(self):
        cases = load_conversations(ROOT / 'evaluations/cognitive-v2-conversations.jsonl')
        self.assertEqual({c['expected_speaker'] for c in cases}, {'zion', 'mimir', 'eir', 'freyr'})
        self.assertTrue(all(len(c['turns']) == 12 for c in cases))
        self.assertTrue(all(c['human_review_required'] for c in cases))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cases.jsonl'
            case = dict(cases[0], turns=cases[0]['turns'][:9])
            path.write_text(json.dumps(case))
            with self.assertRaises(ValueError):
                load_conversations(path)

    def test_history_is_whole_bounded_exchanges(self):
        pairs = [(str(i), 'answer-' + str(i) + 'x' * 1000) for i in range(20)]
        history = bounded_history(pairs)
        self.assertLessEqual(len(history), 6000)
        self.assertIn('answer-19', history)
        self.assertNotIn('answer-0', history)
        self.assertEqual(history.count('User:'), history.count('Assistant:'))
        self.assertEqual(bounded_history([('q', 'x' * 6001)]), '')

    def run_sequence(self, responses):
        captured = []
        class Provider:
            async def complete(self, messages, *, max_tokens):
                captured.append(messages)
                response = responses[len(captured) - 1]
                if isinstance(response, Exception):
                    raise response
                return Completion(response, 'ministral-8b-2512', 10, 10, 1)
        with tempfile.TemporaryDirectory() as tmp:
            db = ZionDB(Path(tmp) / 'evaluation.db'); db.initialize()
            try:
                budget = EvaluationBudget(db)
                case = {'id': 'synthetic', 'turns': ['Como funciona o swap?'] * 12,
                        'expected_speaker': 'mimir', 'human_review_required': True}
                async def collect():
                    return [r async for r in evaluate_conversation(case,
                        knowledge=KnowledgeBase(ROOT / 'knowledge'),
                        provider=Provider(), model='ministral-8b-2512', budget=budget)]
                price = EvaluationBudget.price('ministral-8b-2512', date(2026, 10, 25))
                with patch.object(EvaluationBudget, 'price', return_value=price):
                    results = asyncio.run(collect())
                self.assertGreater(budget.total_micro_usd(), 0)
                return results, captured
            finally:
                db.close()

    def test_real_generated_history_is_used_and_all_turns_need_human_review(self):
        responses = [f'Orientação sintética número {i}: revise a rede antes de confirmar.' for i in range(12)]
        results, captured = self.run_sequence(responses)
        self.assertEqual(len(results), 12)
        self.assertTrue(all(r['status'] == 'REVIEW_REQUIRED' for r in results))
        self.assertTrue(all(r['human_review'] == 'PENDING' for r in results))
        self.assertIn(responses[0], str(captured[1]))
        self.assertNotIn(responses[0], str(captured[-1]))
        self.assertEqual(results[-1]['turn'], 12)
        # A separate invocation never inherits this scenario's history.
        _, again = self.run_sequence([ProviderError('synthetic failure')])
        self.assertNotIn(responses[0], str(again[0]))

    def test_repeated_answer_stops_without_spending_for_remaining_turns(self):
        results, captured = self.run_sequence(['Confira a rede.', 'Confira a rede.'])
        self.assertEqual(len(captured), 2)
        self.assertEqual(results[-1]['status'], 'AUTOMATED_FAIL')
        self.assertEqual(results[-1]['sequence_failure'], 'empty_or_repeated_answer')
        self.assertEqual(results[-1]['planned_turns'], 12)

    def test_guard_and_provider_failures_stop_and_never_feed_rejected_history(self):
        for output in ('Veja /home/operator/private', ProviderError('private provider body')):
            with self.subTest(kind=type(output).__name__):
                results, captured = self.run_sequence([output])
                self.assertEqual(len(captured), 1)
                self.assertEqual(len(results), 1)
                self.assertNotIn('/home/operator/private', str(results))
                self.assertNotIn('private provider body', str(results))
                self.assertIn(results[0]['status'], {'AUTOMATED_FAIL', 'PROVIDER_FAIL'})
