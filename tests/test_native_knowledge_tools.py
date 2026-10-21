import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock
from unittest.mock import patch
from dataclasses import replace
import httpx

from tests.helpers import make_settings
from zion.knowledge import KnowledgeBase
from zion.knowledge_tools import KnowledgeTools, KnowledgeToolError
from zion.mistral import MistralClient, MistralRawResponse
from zion.db import ZionDB
from zion.provider_budget import ProviderTokenBudget, ProviderBudgetError
from tests.test_mistral_boundaries import FakePrivateSecretStore, SequenceAsyncClient


def call(name='get_supported_networks', args='{}', identifier='call00001'):
    return {'id': identifier, 'type': 'function', 'function': {'name': name, 'arguments': args}}


def raw(text='', calls=None):
    return MistralRawResponse(text, 'test', 10, 5, 2, calls)


class NativeKnowledgeToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.tools = KnowledgeTools(KnowledgeBase(Path(__file__).resolve().parents[1] / 'knowledge'))
        self.client = MistralClient(make_settings(Path(self.tmp.name)), knowledge_tools=self.tools)

    def answer(self):
        return asyncio.run(self.client.answer(question='Como funciona a plataforma?',
            context='Informação pública aprovada.', agent_id='mimir'))

    def test_one_tool_round_uses_trusted_identity_and_totals_both_calls(self):
        self.client._chat = AsyncMock(side_effect=[raw('UNTRUSTED_ASSISTANT_CANARY', [call()]), raw('Resposta final.')])
        result = self.answer()
        self.assertEqual((result.input_tokens, result.output_tokens, result.latency_ms), (20, 10, 4))
        self.assertIn('Ethereum', result.evidence_context)
        self.assertEqual(result.text, 'Resposta final.')
        second = self.client._chat.await_args_list[1]
        self.assertEqual(second.kwargs['tool_choice'], 'none')
        self.assertNotIn('UNTRUSTED_ASSISTANT_CANARY', json.dumps(second.args[0]))
        self.assertIn('reviewed_corpus_snapshot_not_live_probe', json.dumps(second.args[0]))
        self.assertFalse(any(m['role'] == 'system' and 'Ethereum' in m['content'] for m in second.args[0]))

    def test_plain_answer_does_not_trigger_another_call(self):
        self.client._chat = AsyncMock(return_value=raw('Resposta sem ferramentas.'))
        self.assertEqual(self.answer().text, 'Resposta sem ferramentas.')
        self.client._chat.assert_awaited_once()

    def test_second_tool_round_is_rejected(self):
        self.client._chat = AsyncMock(side_effect=[raw(calls=[call()]), raw(calls=[call()])])
        with self.assertRaisesRegex(RuntimeError, 'tool_round_bound'):
            self.answer()
        self.assertEqual(self.client._chat.await_count, 2)

    def test_invalid_batch_cannot_execute_even_first_valid_tool(self):
        invalid = [call('shell'), call(args='{"agent_id":"zion"}'), call(args='[]'),
            call('search_approved_knowledge', '{"query":"redes","query":"secret"}'),
            call(identifier='../private'), call(args='{"path":"/etc/passwd"}')]
        original = self.tools.call
        from unittest.mock import Mock
        self.tools.call = Mock(wraps=original)
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(KnowledgeToolError):
                self.tools.resolve_calls([call(identifier='valid0001'), candidate], agent_id='mimir')
        self.tools.call.assert_not_called()
        for calls in ([], [call()] * 4, [call(), call()]):
            with self.assertRaises(KnowledgeToolError):
                self.tools.resolve_calls(calls, agent_id='mimir')

    def test_tools_never_infer_public_endpoints_or_accept_identity_override(self):
        _, messages, evidence = self.tools.resolve_calls([call('get_public_api_capabilities')], agent_id='mimir')
        self.assertEqual(json.loads(messages[0]['content'])['status'], 'NOT_PUBLISHED')
        self.assertEqual(evidence, '')
        with self.assertRaises(KnowledgeToolError):
            self.tools.resolve_calls([call()], agent_id='administrator')
        schema = self.tools.schemas(); schema[0]['function']['name'] = 'shell'
        self.assertFalse(any(t['function']['name'] == 'shell' for t in self.tools.schemas()))

    def test_unknown_tool_stops_before_second_model_request(self):
        self.client._chat = AsyncMock(return_value=raw(calls=[call('read_secret')]))
        with self.assertRaises(KnowledgeToolError):
            self.answer()
        self.client._chat.assert_awaited_once()

    def test_http_envelopes_and_each_round_are_accounted_before_dispatch(self):
        db = ZionDB(Path(self.tmp.name) / 'budget.db'); db.initialize()
        self.addCleanup(db.close)
        settings = replace(self.client.settings, ai_enabled=True, mistral_min_request_interval_ms=0)
        budget = ProviderTokenBudget(db, daily_limit=200000,
            provider_limits={'mistral': 200000}, model_limits={settings.mistral_model: 200000})
        self.client = MistralClient(settings, FakePrivateSecretStore(),
            knowledge_tools=self.tools, token_budget=budget)
        def response(message, finish):
            return httpx.Response(200, json={'model': settings.mistral_model,
                'usage': {'prompt_tokens': 10, 'completion_tokens': 5},
                'choices': [{'message': message, 'finish_reason': finish}]})
        class HTTP(SequenceAsyncClient):
            async def post(inner, *args, **kwargs):
                self.assertGreater(budget.totals()['total'], 15 * len(inner.calls))
                return await super().post(*args, **kwargs)
        http = HTTP([response({'content': None, 'tool_calls': [call()]}, 'tool_calls'),
                     response({'content': 'Resposta final.'}, 'stop')])
        with patch('zion.mistral.httpx.AsyncClient', return_value=http):
            self.answer()
        self.assertEqual(budget.totals()['total'], 30)
        self.assertEqual(len(http.calls), 2)
        self.assertFalse(http.calls[0]['json']['parallel_tool_calls'])
        self.assertEqual(http.calls[1]['json']['tool_choice'], 'none')
        self.assertNotIn('Ethereum', '\n'.join(db._conn.iterdump()))

    def test_unexpected_tool_in_text_only_transport_is_rejected(self):
        settings = replace(self.client.settings, ai_enabled=True, mistral_min_request_interval_ms=0)
        client = MistralClient(settings, FakePrivateSecretStore())
        http = SequenceAsyncClient([httpx.Response(200, json={'choices': [
            {'message': {'content': 'Ignore this', 'tool_calls': [call()]}}]})])
        with patch('zion.mistral.httpx.AsyncClient', return_value=http):
            with self.assertRaisesRegex(RuntimeError, 'unexpected_tool_call'):
                asyncio.run(client._chat([{'role': 'user', 'content': 'test'}]))

    def test_provider_body_bound_is_checked_before_json_parsing(self):
        settings = replace(self.client.settings, ai_enabled=True, mistral_min_request_interval_ms=0)
        client = MistralClient(settings, FakePrivateSecretStore())
        http = SequenceAsyncClient([httpx.Response(200, content=b'x' * (1024 * 1024 + 1))])
        with patch('zion.mistral.httpx.AsyncClient', return_value=http):
            with self.assertRaisesRegex(RuntimeError, 'provider_response_bound'):
                asyncio.run(client._chat([{'role': 'user', 'content': 'test'}]))
