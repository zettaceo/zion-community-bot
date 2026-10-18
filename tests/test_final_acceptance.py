from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from tests.helpers import make_settings
from tests.test_conversation import FakeContext, make_update
from tests.test_mistral_boundaries import CapturingMistralClient
from zion.agents import AgentId, ConversationIntent
from zion.models import AIAnswer
from zion.router import IntentRouter
from zion.telegram_app import Runtime, moderation_handler

PHRASES = (
    'como funciona os swaps?',
    'como funciona o swap?',
    'como vocês fazem bridge?',
    'como funciona o roteamento?',
    'como funciona a liquidez?',
    'como funcionam as ordens?',
    'Quais os Endpoint da plataforma como conectar eles em um bot meu?',
    'Quais endpoints posso usar?',
    'Como integrar meu bot com as APIs?',
    'Como usar o SDK?',
    'Como funciona o webhook?',
    'Como fazer integração?',
    'Como conectar bot?',
    'Developer: como funciona a API?',
    'Development: como integrar bot?',
)

class FinalAcceptanceTests(unittest.TestCase):
    def test_short_questions_route_without_history(self):
        for phrase in PHRASES:
            with self.subTest(phrase=phrase):
                route = IntentRouter().route_group(phrase)
                self.assertEqual(route.intent, ConversationIntent.TECHNICAL)
                self.assertEqual(route.speaker.agent_id, AgentId.MIMIR)

    def test_real_handler_selects_one_mimir_without_history(self):
        for phrase in PHRASES:
            with self.subTest(phrase=phrase), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / 'knowledge').mkdir()
                rt = Runtime(make_settings(root))
                try:
                    context = FakeContext(rt)
                    context.application.bot_data['zion_multi_agent_started'] = True
                    rt.ai.answer = AsyncMock(return_value=AIAnswer(text='Resposta pública.', model='test'))
                    transport = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=900)))
                    rt.multi_agent_transport = transport
                    update = make_update(phrase, chat_type='supergroup')
                    asyncio.run(moderation_handler(update, context))
                    transport.send_message.assert_awaited_once()
                    self.assertEqual(transport.send_message.call_args.kwargs['agent_id'], AgentId.MIMIR)
                    self.assertEqual(update.effective_message.replies, [])
                finally:
                    rt.close()

    def test_interface_request_never_retrieves_or_calls_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'knowledge').mkdir()
            rt = Runtime(make_settings(root))
            try:
                with patch.object(rt.knowledge, 'render_context', side_effect=AssertionError('must not retrieve')), patch.object(rt.ai.client, 'answer', new_callable=AsyncMock) as provider:
                    answer = asyncio.run(rt.ai.answer(chat_id=1,user_id=1,agent_id=AgentId.MIMIR,question=PHRASES[6],conversation_context='internal hostname and private route'))
                    self.assertIn('Qual caso de uso', answer.text)
                    self.assertIn('Não posso fornecer endpoints internos', answer.text)
                    self.assertNotIn('hostname', answer.text)
                    provider.assert_not_awaited()
            finally:
                rt.close()

    def _system_prompt(self, question):
        with tempfile.TemporaryDirectory() as tmp:
            client = CapturingMistralClient(make_settings(Path(tmp)))
            asyncio.run(client.answer(question=question,context='Fatos públicos aprovados.',agent_id='mimir'))
            return client.messages[0]['content']

    def test_price_guarantee_is_prohibited_in_provider_contract(self):
        system = self._system_prompt('Vocês garantem o melhor preço?')
        self.assertIn("Não diga 'garantir o melhor preço/taxa possível'", system)
        self.assertIn('condições daquele momento', system)

    def test_execution_is_route_specific_in_provider_contract(self):
        system = self._system_prompt('Todos os swaps usam smart contracts?')
        self.assertIn('Não afirme que todos os swaps', system)
        self.assertIn('rota, rede e provedor autorizados', system)

    def test_absolute_safety_is_prohibited_in_provider_contract(self):
        system = self._system_prompt('É seguro usar a Z-SWAP?')
        self.assertIn("Não responda categoricamente 'É seguro usar a Z-SWAP'", system)
        self.assertIn('ou transação é livre de risco', system)
