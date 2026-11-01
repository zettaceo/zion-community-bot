import asyncio
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from tests.helpers import make_settings
from tests.test_conversation import FakeContext, make_update
from tests.test_mistral_boundaries import FakePrivateSecretStore, SequenceAsyncClient
from zion.telegram_app import Runtime, moderation_handler


class CognitiveDeliveryTests(unittest.TestCase):
    def test_native_two_request_answer_still_has_one_speaker_under_duplicate_intake(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = replace(make_settings(root), ai_enabled=True,
                ai_daily_token_budget=200000, mistral_min_request_interval_ms=0)
            (root / 'knowledge' / 'official.md').write_text(
                '# Roteamento\nO roteamento depende da rede e da rota.\n\n# Redes\nEthereum é uma rede suportada.\n')
            rt = Runtime(settings)
            try:
                ctx = FakeContext(rt)
                ctx.application.bot_data['zion_multi_agent_started'] = True
                rt.ai.client.secret_store = FakePrivateSecretStore()
                rt.multi_agent_transport = SimpleNamespace(send_message=AsyncMock(
                    return_value=SimpleNamespace(message_id=900)))
                def response(message, finish):
                    return httpx.Response(200, json={'model': settings.mistral_model,
                        'usage': {'prompt_tokens': 10, 'completion_tokens': 5},
                        'choices': [{'message': message, 'finish_reason': finish}]})
                # One community triage reading (duplicate intake is read once),
                # then the two-request native answer.
                http = SequenceAsyncClient([
                    response({'content': '{"addressed": true, "intent": "technical", "risks": [], '
                              '"language": "pt", "confidence": 0.9}'}, 'stop'),
                    response({'content': None, 'tool_calls': [{'id': 'call00001', 'type': 'function',
                        'function': {'name': 'get_supported_networks', 'arguments': '{}'}}]}, 'tool_calls'),
                    response({'content': 'Ethereum é uma rede suportada.'}, 'stop')])
                async def run():
                    await asyncio.gather(*[moderation_handler(make_update(
                        'Como funciona o roteamento?', chat_type='supergroup', message_id=42), ctx)
                        for _ in range(2)])
                with patch('zion.mistral.httpx.AsyncClient', return_value=http):
                    asyncio.run(run())
                self.assertEqual(len(http.calls), 3)
                rt.multi_agent_transport.send_message.assert_awaited_once()
                self.assertEqual(rt.ai.provider_token_budget.totals()['total'], 45)
                self.assertEqual(rt.ai.tokens_used_today(), 45)
            finally:
                rt.close()
