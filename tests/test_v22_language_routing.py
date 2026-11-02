from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from tests.helpers import make_settings
from zion.ai_service import AIService
from zion.db import ZionDB
from zion.knowledge import KnowledgeBase, _base_tokens
from zion.response_guard import public_fallback_for

from zion.agents import DEFAULT_AGENT_REGISTRY
from zion.grounding import remove_sentences
from zion.mistral import build_answer_messages, reply_language_instruction
from zion.telegram_app import _TRIAGE_AGENT


class TriageAgentMapTests(unittest.TestCase):
    def test_every_triage_target_may_speak_its_intent(self):
        # A target the arbiter refuses means silence for the member.
        for intent, (agent_id, conversation_intent) in _TRIAGE_AGENT.items():
            profile = DEFAULT_AGENT_REGISTRY.get(agent_id)
            with self.subTest(intent=intent):
                self.assertTrue(profile.can_speak_group)
                self.assertIn(conversation_intent, profile.group_intents)


class ReplyLanguageTests(unittest.TestCase):
    def test_chinese_question_names_chinese(self):
        self.assertIn('简体中文', reply_language_instruction('你能给我解释一下zswap的具体工作原理吗？'))

    def test_latin_question_follows_question_not_context(self):
        instruction = reply_language_instruction('how does it work?')
        self.assertIn('user_question', instruction)
        self.assertNotIn('简体中文', instruction)

    def test_answer_prompt_ends_with_language(self):
        system = build_answer_messages(question='zswap 怎么用？', context='x')[0]['content']
        self.assertIn('IDIOMA DA RESPOSTA: 简体中文', system.splitlines()[-1])


class RemoveSentenceListTests(unittest.TestCase):
    def test_list_is_renumbered_after_removal(self):
        text = 'Passos:\n1. Abra a carteira.\n2. Confira a rede.\n3. Assine.'
        self.assertEqual(remove_sentences(text, ('Abra a carteira.',)),
                         'Passos:\n1. Confira a rede.\n2. Assine.')

    def test_separate_lists_restart_numbering(self):
        text = 'A:\n1. um x.\n2. dois.\nB:\n1. tres y.\n2. quatro.'
        self.assertEqual(remove_sentences(text, ('um x.', 'tres y.')),
                         'A:\n1. dois.\nB:\n1. quatro.')


ROOT = Path(__file__).resolve().parents[1]


class PublicTopicContextTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        settings = replace(make_settings(Path(temp.name)), knowledge_dir=ROOT / 'knowledge')
        db = ZionDB(settings.db_path)
        db.initialize()
        self.addCleanup(db.close)
        self.ai = AIService(settings, db, KnowledgeBase(ROOT / 'knowledge'))

    def test_founder_pass_question_brings_public_facts(self):
        context = self.ai._public_topic_context('E pq eu deveria comprar o NFT do pass de fundador')
        self.assertIn('Founder Pass', context)
        self.assertIn('36 meses', context)


class ControlledContextReviewTests(PublicTopicContextTests):
    def test_controlled_context_never_reaches_external_reviewer(self):
        import asyncio
        from unittest.mock import AsyncMock, patch
        from zion.agents import AgentId
        from zion.models import AIAnswer
        context = self.ai.knowledge.render_context(
            'arquitetura de roteamento de cotação 0x jupiter lifi', agent_id=AgentId.MIMIR)
        self.assertTrue(self.ai._has_controlled_context(context))
        answer = AIAnswer('Texto qualquer da resposta.', 'ministral-8b-2512')
        approval = type('A', (), {'model': 'kimi-k3'})()
        with patch.object(self.ai, '_approved_candidate', return_value=(approval, object())), \
                patch.object(self.ai, 'review_grounding', new=AsyncMock()) as review:
            result = asyncio.run(self.ai._grounded(answer, context, 'h', None, None, AgentId.MIMIR))
        review.assert_not_called()
        self.assertEqual(result.text, answer.text)


class RetrievalVariantTests(unittest.TestCase):
    def test_ox_means_0x_and_fillers_are_ignored(self):
        tokens = _base_tokens('entao manda ai as rotas da ox')
        self.assertIn('0x', tokens)
        self.assertFalse({'entao', 'manda', 'ai'} & tokens)


class CostObjectionFallbackTests(unittest.TestCase):
    def test_cost_objection_gets_cost_reply_not_feature_list(self):
        reply = public_fallback_for('missing_feature_status', official_context='',
                                    question='deve ter plataformas mais baratas que cobram menos')
        self.assertIn('custo total', reply)
        self.assertNotIn('Terminal Pro', reply)


if __name__ == '__main__':
    unittest.main()


class FixedAnswerTranslationTests(unittest.TestCase):
    def test_known_fallbacks_are_translated(self):
        from zion.ai_service import UNGROUNDED_FALLBACK
        from zion.response_guard import PUBLIC_FALLBACK
        from zion.telegram_app import _translate_fixed_answer
        for text in (UNGROUNDED_FALLBACK, PUBLIC_FALLBACK):
            self.assertIn("official information", _translate_fixed_answer(text, 'en'))
            self.assertIn("información oficial", _translate_fixed_answer(text, 'es'))
            self.assertIn("官方信息", _translate_fixed_answer(text, 'zh'))
            self.assertIn("official information", _translate_fixed_answer(text, 'fr'))
            self.assertEqual(_translate_fixed_answer(text, 'pt'), text)

    def test_named_language_wins_over_script_guess(self):
        self.assertIn('italiano', reply_language_instruction('ciao, quanto costa?', 'it'))
