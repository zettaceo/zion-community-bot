"""Regression for the first live Telegram acceptance of cognitive v2 (2026-11-01).

A member said they would paste "the 12 words I got when I created the wallet"
and asked whether they could; ZION stayed silent, as it did for a complaint and
a follow-up. The previous production commit behaved the same way.
"""
from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from tests.helpers import make_settings
from tests.test_conversation import FakeBot, FakeContext, make_update
from zion.conversation_state import explicit_topic
from zion.guardian import detect_sensitive_content
from zion.mnemonic import looks_like_bare_mnemonic, wordlists
from zion.models import AIAnswer
from zion.response_guard import validate_public_response
from zion.router import IntentRouter
from zion.telegram_app import Runtime, moderation_handler

SEED_EN = 'abandon ability able about above absent absorb abstract absurd abuse access accident'
SEED_PT = 'abacate abaixo abalar abater abduzir abelha aberto abismo abotoar abranger abreviar abrigar'


class BareMnemonicTests(unittest.TestCase):
    def test_wordlists_are_pinned_official_bip39(self):
        self.assertEqual([len(w) for w in wordlists()], [2048, 2048, 2048])

    def test_unlabelled_seed_is_detected_in_any_listed_language(self):
        numbered = ' '.join(f'{i}. {w}' for i, w in enumerate(SEED_EN.split(), 1))
        for text in (SEED_EN, SEED_PT, numbered, 'minhas palavras: ' + SEED_EN):
            with self.subTest(text=text[:30]):
                self.assertTrue(looks_like_bare_mnemonic(text))
                self.assertEqual(detect_sensitive_content(text).kind, 'possible_wallet_secret')

    def test_ordinary_text_and_the_official_corpus_are_not_seeds(self):
        self.assertFalse(looks_like_bare_mnemonic(
            'Como funciona os swaps na Z-SWAP? Quero trocar SOL por USDC na rede Solana hoje.'))
        self.assertFalse(looks_like_bare_mnemonic(' '.join(SEED_EN.split()[:11])))
        root = Path(__file__).resolve().parents[1] / 'knowledge'
        flagged = [p.name for p in root.glob('*.md') if looks_like_bare_mnemonic(p.read_text())]
        self.assertEqual(flagged, [])


class LiveConversationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / 'knowledge').mkdir()
        settings = replace(make_settings(root), flood_max_messages=1000,
                           flood_sustained_max_messages=1000)
        self.runtime = Runtime(settings)
        self.addCleanup(self.runtime.close)
        self.context = FakeContext(self.runtime)
        self.runtime.primary_bot = FakeBot()
        self.runtime.ai.answer = AsyncMock(return_value=AIAnswer(text='Resposta.', model='test'))
        self.message_id = 500

    def send(self, text, **kwargs):
        self.message_id += 1
        update = make_update(text, chat_type='supergroup', message_id=self.message_id, **kwargs)
        before = self.runtime.ai.answer.await_count
        asyncio.run(moderation_handler(update, self.context))
        replies = update.effective_message.replies + [t for _, t in self.context.bot.sent]
        self.context.bot.sent.clear()
        return replies, self.runtime.ai.answer.await_count > before

    def test_the_exact_live_conversation_never_leaves_the_member_unanswered(self):
        self.send('Como funciona os swaps?')
        self.send('Minha carteira não conecta')
        replies, ai = self.send('Vou mandar aqui unas 12 palavras que recebi quando criei a carteira')
        self.assertFalse(ai)
        self.assertIn('Não mande', replies[0])
        self.assertIn('seed phrase', replies[0])
        replies, ai = self.send('Posso mandar ?')
        self.assertFalse(ai, 'a permission question after a seed warning must not reach the model')
        self.assertTrue(replies[0].startswith('Não, não mande'))
        replies, _ = self.send('Oshi que atendimento horrível')
        self.assertIn('Desculpe', replies[0])
        replies, ai = self.send('E se eu quiser ser parceiro')
        self.assertTrue(ai and replies)
        replies, _ = self.send('Agora você responde né e as outras 3 mensagem que mandei pq ficou em silêncio?')
        self.assertIn('Desculpe', replies[0])

    def test_seed_warning_variants(self):
        for text in ('posso te passar minha seed pra vc verificar?', 'quer que eu mande a frase de recuperação?',
                     'devo colar as 24 palavras aqui?', 'can i send you my seed phrase'):
            with self.subTest(text=text):
                replies, ai = self.send(text)
                self.assertFalse(ai)
                self.assertIn('Não mande', replies[0])

    def test_member_continuity_covers_questions_not_chatter_or_replies_to_others(self):
        self.send('O que é a Z-SWAP?')
        _, ai = self.send('Vou almoçar e volto depois.')
        self.assertFalse(ai)
        replies, ai = self.send('e isso vale pra mim?')
        self.assertTrue(ai and replies)
        other = SimpleNamespace(message_id=1, from_user=SimpleNamespace(id=77, username='ana'))
        self.message_id += 1
        update = make_update('você viu isso?', chat_type='supergroup', message_id=self.message_id)
        update.effective_message.reply_to_message = other
        before = self.runtime.ai.answer.await_count
        asyncio.run(moderation_handler(update, self.context))
        self.assertEqual(self.runtime.ai.answer.await_count, before)

    def test_partner_wording_is_a_partnership_topic(self):
        for text in ('E se eu quiser ser parceiro', 'quero ser parceira da zswap'):
            with self.subTest(text=text):
                self.assertEqual(explicit_topic(text), 'partnership')
                self.assertEqual(IntentRouter().route_group(
                    text, explicitly_addressed=True, addressed_agent=None).intent.value,
                    'partnership')


class GuardGapTests(unittest.TestCase):
    def test_organization_future_promise_with_words_between(self):
        self.assertEqual(validate_public_response(
            'A Z-SWAP prioriza segurança: nunca pedirá sua seed phrase ou chave privada.',
            official_context='').reason, 'unsupported_universal_secret_promise')
        self.assertTrue(validate_public_response(
            'A Z-SWAP nunca deve pedir seed phrase.', official_context='').allowed)


if __name__ == '__main__':
    unittest.main()
