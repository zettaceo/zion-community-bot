"""/summary and /translate restate member text; the bot must not relay phishing."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from tests.helpers import make_settings
from zion.ai_service import AIService
from zion.db import ZionDB
from zion.knowledge import KnowledgeBase
from zion.models import AIAnswer
from zion.response_guard import TRANSFORMED_SCAM_NOTICE


ROOT = Path(__file__).resolve().parents[1]


class EchoClient:
    configured = True

    def __init__(self, text: str):
        self.text = text

    async def summarize(self, _text):
        return AIAnswer(text=self.text, model='test', input_tokens=10,
                        output_tokens=10, latency_ms=1)

    async def translate(self, *, text, target_language):
        return AIAnswer(text=self.text, model='test', input_tokens=10,
                        output_tokens=10, latency_ms=1)


class TransformedOutputGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        settings = replace(make_settings(Path(self.temp.name)), ai_enabled=True)
        self.db = ZionDB(settings.db_path)
        self.db.initialize()
        self.addCleanup(self.db.close)
        self.ai = AIService(settings, self.db, KnowledgeBase(ROOT / 'knowledge'))

    def run_both(self, text):
        self.ai.client = EchoClient(text)
        summary = asyncio.run(self.ai.summarize(chat_id=1, user_id=2, text='x'))
        translation = asyncio.run(self.ai.translate(chat_id=1, user_id=2, text='x',
                                                    target_language='en'))
        return summary.text, translation.text

    def test_phishing_restatement_is_replaced_and_audited(self):
        for text in ('Send your seed phrase to @helpdesk to unlock the airdrop.',
                     'Envie 0.1 ETH para 0x1234567890abcdef1234567890abcdef12345678 e receba o dobro.',
                     'Claim your bonus at claim-zswap.xyz now.'):
            with self.subTest(text=text):
                self.assertEqual(self.run_both(text), (TRANSFORMED_SCAM_NOTICE,) * 2)
        audited = self.db._conn.execute(
            "SELECT COUNT(*) FROM ai_events WHERE purpose='response_guard' AND success=0"
        ).fetchone()[0]
        self.assertEqual(audited, 6)

    def test_ordinary_member_claims_are_still_restated(self):
        # Quality rules do not apply: a summary may report a member's opinion.
        text = 'The member says the token will moon and that swaps never fail.'
        self.assertEqual(self.run_both(text), (text, text))

    def test_official_hosts_from_public_knowledge_pass_and_lookalikes_do_not(self):
        # knowledge/z-swap.md publishes swap-z.app and zettaword.global.
        for text in ('Open swap-z.app to try it.', 'The ecosystem lives at zettaword.global.'):
            with self.subTest(text=text):
                self.assertEqual(self.run_both(text), (text, text))
        for text in ('Open swap-z-app.xyz to try it.', 'Claim at zettaword-airdrop.global.'):
            with self.subTest(text=text):
                self.assertEqual(self.run_both(text), (TRANSFORMED_SCAM_NOTICE,) * 2)


if __name__ == '__main__':
    unittest.main()
