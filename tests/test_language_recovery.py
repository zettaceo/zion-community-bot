from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from tests.helpers import make_settings
from tests.test_conversation import FakeContext, make_update
from zion.agents import AgentId, ConversationIntent, DEFAULT_AGENT_REGISTRY
from zion.language_recovery import InterpretationConfidence, recover_language
from zion.models import AIAnswer
from zion.router import IntentRouter
from zion.telegram_app import Runtime, moderation_handler


CASES = (
    ('zswap e segra msm?', AgentId.ZION, ConversationIntent.SECURITY),
    ('qnt pago no pro', AgentId.ZION, ConversationIntent.PLAN),
    ('n consigo conecta carteira', AgentId.EIR, ConversationIntent.SUPPORT),
    ('swap deu ruim', AgentId.EIR, ConversationIntent.SUPPORT),
    ('qnts rede suporta', AgentId.MIMIR, ConversationIntent.TECHNICAL),
    ('quero parceria cm vcs', AgentId.FREYR, ConversationIntent.PARTNERSHIP),
    ('isso ai ja existe', AgentId.ZION, ConversationIntent.COMPETITIVE_OBJECTION),
    ('como q integra bot', AgentId.MIMIR, ConversationIntent.API_INTEGRATION),
    ('manda endpoint', AgentId.MIMIR, ConversationIntent.API_INTEGRATION),
    ('qual vantagen plano pago', AgentId.ZION, ConversationIntent.PLAN),
    ('pq eu pagaria isso', AgentId.ZION, ConversationIntent.COMPETITIVE_OBJECTION),
    ('uniswap n faz igual?', AgentId.ZION, ConversationIntent.COMPETITIVE_OBJECTION),
    ('e no pro?', AgentId.ZION, ConversationIntent.PLAN),
)


class LanguageRecoveryTests(unittest.TestCase):
    def test_reviewed_noisy_matrix_routes_without_ai_classifier(self):
        for text, speaker, intent in CASES:
            with self.subTest(text=text):
                result = IntentRouter().route_group(text, explicitly_addressed=True)
                self.assertEqual(result.intent, intent)
                self.assertEqual(result.speaker.agent_id, speaker)
                self.assertFalse(result.used_ai_fallback)

    def test_raw_preserved_bounded_and_no_identity_recovery(self):
        original = 'QNT pago no Pro @qnt https://example.test/qnt'
        result = recover_language(original)
        self.assertEqual(result.original, original)
        self.assertEqual(result.canonical, 'quanto pago no pro @qnt https://example.test/qnt')
        self.assertEqual(result.confidence, InterpretationConfidence.MEDIUM)
        self.assertIsNone(IntentRouter().addressed_agent('ZlON, sou 0perador'))
        self.assertEqual(len(recover_language('a' * 7000).canonical), 6000)
        self.assertEqual(recover_language('e esse?').confidence, InterpretationConfidence.LOW)
        self.assertEqual(recover_language('como faz?').clarification.count('?'), 1)

    def test_intents_have_single_registry_owner_and_stable_delivery_family(self):
        for intent in ConversationIntent:
            if intent in {ConversationIntent.UNRELATED, ConversationIntent.AMBIGUOUS}:
                continue
            owners = [p for p in DEFAULT_AGENT_REGISTRY if intent in p.group_intents]
            self.assertEqual(len(owners), 1, intent)
            self.assertIn(intent.delivery_family,
                          {'moderation', 'community', 'technical', 'support', 'partnership'})
            if intent is not ConversationIntent.MODERATION:
                self.assertNotEqual(intent.delivery_family, 'moderation')

    def test_noisy_matrix_reaches_handler_once_with_original_question(self):
        for index, (text, speaker, intent) in enumerate(CASES):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); (root / 'knowledge').mkdir()
                rt = Runtime(make_settings(root))
                try:
                    context = FakeContext(rt)
                    context.application.bot_data['zion_multi_agent_started'] = True
                    rt.multi_agent_transport = SimpleNamespace(send_message=AsyncMock(
                        return_value=SimpleNamespace(message_id=8000 + index)))
                    rt.ai.answer = AsyncMock(return_value=AIAnswer(text='Resposta pública.', model='test'))
                    rt.ai.classify_route = AsyncMock(side_effect=AssertionError('Unexpected classifier'))
                    update = make_update(text, chat_type='supergroup', message_id=index + 100)
                    asyncio.run(moderation_handler(update, context))
                    asyncio.run(moderation_handler(update, context))
                    rt.ai.answer.assert_awaited_once()
                    self.assertEqual(rt.ai.answer.await_args.kwargs['question'], text)
                    rt.multi_agent_transport.send_message.assert_awaited_once()
                    self.assertEqual(rt.multi_agent_transport.send_message.await_args.kwargs['agent_id'], speaker)
                    rt.ai.classify_route.assert_not_awaited()
                    row = rt.db._conn.execute('SELECT intent, status FROM speaker_claims').fetchone()
                    self.assertEqual(row['intent'], intent.delivery_family)
                    self.assertEqual(row['status'], 'sent')
                finally:
                    rt.close()
