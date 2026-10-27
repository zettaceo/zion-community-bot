from __future__ import annotations

import asyncio
from contextlib import ExitStack, redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from zion.db import ZionDB
from zion.evaluation_budget import EvaluationBudget, PRICES
from zion.evaluation_conversations import bounded_history, evaluate_conversation, load_conversations
from zion.knowledge import KnowledgeBase
from zion.providers import Completion, ProviderError

ROOT = Path(__file__).resolve().parents[1]


class ConversationEvaluationTests(unittest.TestCase):
    def test_cli_selects_one_conversation_without_provider_call_by_default(self):
        command = [sys.executable, str(ROOT / 'scripts/evaluate-cognitive-v2.py'),
                   '--conversation-id', 'conversation-debate']
        result = subprocess.run(command, cwd=ROOT, capture_output=True,
                                text=True, check=True)
        self.assertIn('selected=1 provider_calls=0', result.stdout)

    def test_named_live_conversation_dispatches_and_persists_first_turn_with_fake_provider(self):
        spec = importlib.util.spec_from_file_location(
            'zion_cognitive_evaluator', ROOT / 'scripts/evaluate-cognitive-v2.py')
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        args = SimpleNamespace(native_mistral=False, model='kimi-k3',
                               conversations=False, conversation_id='conversation-debate',
                               case_ids=None, full=False, live=True)
        for postprocess_failure in (False, True):
            with self.subTest(postprocess_failure=postprocess_failure):
                calls = []

                class FakeProvider:
                    configured = True

                    async def complete(self, messages, *, max_tokens):
                        calls.append(messages)
                        return Completion('Veja /home/private', 'kimi-k3', 10, 10, 1)

                with tempfile.TemporaryDirectory() as tmp:
                    (Path(tmp) / '.local/state/zion-community-bot').mkdir(parents=True)
                    price = EvaluationBudget.price('kimi-k3', PRICES['kimi-k3'].verified_on)
                    with ExitStack() as stack:
                        stack.enter_context(patch.object(module.Path, 'home', return_value=Path(tmp)))
                        stores = stack.enter_context(patch.object(module, 'ProviderSecretStore'))
                        stores.return_value.for_provider.return_value = object()
                        stack.enter_context(patch.object(
                            module, 'KimiCompletionProvider', return_value=FakeProvider()))
                        stack.enter_context(patch.object(EvaluationBudget, 'price', return_value=price))
                        stack.enter_context(redirect_stdout(StringIO()))
                        if postprocess_failure:
                            stack.enter_context(patch(
                                'zion.evaluation.validate_public_response',
                                side_effect=KeyError('private error marker')))
                        exit_code = asyncio.run(module.run(args))
                    self.assertEqual(exit_code, 1)
                    self.assertEqual(len(calls), 1)
                    files = list((Path(tmp) / '.local/state/zion-community-bot/evaluations/cognitive-v2').glob('*.jsonl'))
                    self.assertEqual(len(files), 1)
                    results = [json.loads(line) for line in files[0].read_text().splitlines()]
                    self.assertEqual(len(results), 1)
                    self.assertNotIn('/home/private', str(results))
                    self.assertNotIn('private error marker', str(results))
                    if postprocess_failure:
                        self.assertEqual(results[0]['status'], 'HARNESS_FAIL')
                        self.assertEqual(results[0]['error_type'], 'KeyError')
                    else:
                        self.assertEqual(results[0]['conversation_id'], 'conversation-debate')
                        self.assertEqual(results[0]['turn'], 1)
                        self.assertEqual(results[0]['status'], 'AUTOMATED_FAIL')
                        self.assertEqual(results[0]['response'], '[WITHHELD_BY_OUTPUT_GUARD]')

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
                price = EvaluationBudget.price('ministral-8b-2512',
                                               PRICES['ministral-8b-2512'].verified_on)
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


class IndependentBenchmarkTests(unittest.TestCase):
    @staticmethod
    def _module():
        spec = importlib.util.spec_from_file_location(
            'zion_cognitive_evaluator', ROOT / 'scripts/evaluate-cognitive-v2.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @staticmethod
    def _case(case_id):
        return {'id': case_id, 'turns': ['Como funciona o swap?'],
                'expected_speaker': 'mimir', 'required_terms': [],
                'human_review_required': True}

    def _run_fake(self, *, responses, conversations=False, continue_independent_cases=True,
                  postprocess_failure=False):
        module = self._module()
        calls = []
        safe_reply = 'A Z-SWAP permite avaliar rotas públicas de swap conforme a rede e o provedor.'

        class FakeProvider:
            configured = True

            async def complete(self, messages, *, max_tokens):
                calls.append(messages)
                outcome = responses[len(calls) - 1]
                if isinstance(outcome, Exception):
                    raise outcome
                return Completion(outcome or safe_reply, 'kimi-k3', 10, 10, 1)

        async def no_sleep(_seconds):
            return None

        args = SimpleNamespace(native_mistral=False, model='kimi-k3', live=True,
                               full=not conversations, conversations=conversations,
                               conversation_id=None, case_ids=None,
                               continue_independent_cases=continue_independent_cases)
        cases = [self._case(f'case-{i}') for i in range(len(responses))]
        scenarios = [
            {'id': f'conversation-{i}', 'turns': ['Como funciona o swap?'] * 12,
             'expected_speaker': 'mimir', 'human_review_required': True}
            for i in range(2)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / '.local/state/zion-community-bot'
            state.mkdir(parents=True)
            price = EvaluationBudget.price('kimi-k3', PRICES['kimi-k3'].verified_on)
            with ExitStack() as stack:
                stack.enter_context(patch.object(module.Path, 'home', return_value=Path(tmp)))
                store = stack.enter_context(patch.object(module, 'ProviderSecretStore'))
                store.return_value.for_provider.return_value = object()
                stack.enter_context(patch.object(module, 'KimiCompletionProvider',
                                                 return_value=FakeProvider()))
                stack.enter_context(patch.object(module, 'load_cases', return_value=cases))
                stack.enter_context(patch.object(module, 'load_conversations',
                                                 return_value=scenarios))
                stack.enter_context(patch.object(EvaluationBudget, 'price', return_value=price))
                stack.enter_context(patch.object(module.asyncio, 'sleep', no_sleep))
                fsync = stack.enter_context(patch.object(module.os, 'fsync', wraps=module.os.fsync))
                if postprocess_failure:
                    stack.enter_context(patch('zion.evaluation.validate_public_response',
                                              side_effect=KeyError('private error marker')))
                stdout = StringIO()
                stack.enter_context(redirect_stdout(stdout))
                code = asyncio.run(module.run(args))
            evidence_files = list((state / 'evaluations/cognitive-v2').glob('*.jsonl'))
            self.assertEqual(len(evidence_files), 1)
            results = [json.loads(line) for line in evidence_files[0].read_text().splitlines()]
            db = ZionDB(state / 'evaluations/cognitive-v2/evaluation.db')
            db.initialize()
            try:
                budget_total = EvaluationBudget(db).total_micro_usd()
            finally:
                db.close()
            return code, results, len(calls), budget_total, fsync.call_count, stdout.getvalue()

    def test_opt_in_full_records_failures_and_continues_only_independent_cases(self):
        outcomes = ['Veja /home/private', None,
                    ProviderError('private provider body'), None]
        code, results, calls, budget, syncs, stdout = self._run_fake(responses=outcomes)
        self.assertEqual(code, 1)
        self.assertEqual(calls, 4)
        self.assertEqual([r['status'] for r in results],
                         ['AUTOMATED_FAIL', 'REVIEW_REQUIRED', 'PROVIDER_FAIL', 'REVIEW_REQUIRED'])
        self.assertEqual([r['id'] for r in results], ['case-0', 'case-1', 'case-2', 'case-3'])
        self.assertEqual(results[0]['response'], '[WITHHELD_BY_OUTPUT_GUARD]')
        self.assertNotIn('/home/private', str(results))
        self.assertNotIn('private provider body', str(results))
        self.assertGreater(budget, 0)
        self.assertGreaterEqual(syncs, len(results))
        self.assertIn('ACCEPTANCE=PENDING_HUMAN_REVIEW_AND_CORE_TELEGRAM_TESTS', stdout)

        # The existing --full mode remains fail-fast without the new flag.
        code, results, calls, _, _, _ = self._run_fake(
            responses=outcomes, continue_independent_cases=False)
        self.assertEqual(code, 1)
        self.assertEqual(calls, 1)
        self.assertEqual(len(results), 1)

    def test_opt_in_conversations_stop_failed_turn_but_start_next_scenario(self):
        code, results, calls, budget, syncs, _ = self._run_fake(
            conversations=True,
            responses=[None, 'Veja /home/private', ProviderError('private provider body')])
        self.assertEqual(code, 1)
        self.assertEqual(calls, 3)
        self.assertEqual([(r['conversation_id'], r['turn'], r['status']) for r in results], [
            ('conversation-0', 1, 'REVIEW_REQUIRED'),
            ('conversation-0', 2, 'AUTOMATED_FAIL'),
            ('conversation-1', 1, 'PROVIDER_FAIL'),
        ])
        self.assertGreater(budget, 0)
        self.assertGreaterEqual(syncs, len(results))

    def test_harness_failure_still_stops_entire_opt_in_run(self):
        code, results, calls, budget, syncs, _ = self._run_fake(
            responses=[None, None], postprocess_failure=True)
        self.assertEqual(code, 1)
        self.assertEqual(calls, 1)
        self.assertEqual([r['status'] for r in results], ['HARNESS_FAIL'])
        self.assertNotIn('private error marker', str(results))
        self.assertGreater(budget, 0)
        self.assertGreaterEqual(syncs, 1)

    def test_continuation_flag_requires_full_or_conversations(self):
        module = self._module()
        args = SimpleNamespace(native_mistral=False, model='kimi-k3',
                               conversations=False, conversation_id=None,
                               case_ids=None, full=False, live=False,
                               continue_independent_cases=True)
        with self.assertRaisesRegex(ValueError, 'independent_case_mode_requires_full_or_conversations'):
            asyncio.run(module.run(args))

    def test_opt_in_full_is_still_offline_without_live(self):
        result = subprocess.run([
            sys.executable, str(ROOT / 'scripts/evaluate-cognitive-v2.py'),
            '--full', '--continue-independent-cases',
        ], cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertIn('selected=108 provider_calls=0', result.stdout)
