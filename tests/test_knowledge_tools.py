from __future__ import annotations
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest

from zion.agents import AgentId
from zion.knowledge import KnowledgeBase, KnowledgeClassification, KnowledgeSourceStatus
from zion.knowledge_tools import KnowledgeTools, KnowledgeToolError, TOOL_NAMES
from zion.language_recovery import recover_language


class KnowledgeToolsTests(unittest.TestCase):
    def setUp(self):
        self.knowledge = KnowledgeBase(Path(__file__).resolve().parents[1] / 'knowledge')
        self.tools = KnowledgeTools(self.knowledge)

    def test_registry_cannot_execute_or_override_authority(self):
        for name in ('shell', 'sql', 'read_file', '__dict__', '/etc/passwd'):
            with self.subTest(name=name), self.assertRaises(KnowledgeToolError):
                self.tools.call(name, {}, agent_id=AgentId.MIMIR)
        for args in ({'query': 'redes', 'agent_id': 'mimir'}, {'path': '/etc/passwd'}, {'query': 'a'*6001}):
            with self.subTest(args=list(args)), self.assertRaises(KnowledgeToolError):
                self.tools.call('search_approved_knowledge', args, agent_id=AgentId.ZION)
        with self.assertRaises(KnowledgeToolError):
            self.tools.call('get_plan_matrix', {}, agent_id='admin')

    def test_fixed_operations_and_no_public_endpoints_inference(self):
        for name in TOOL_NAMES - {'search_approved_knowledge'}:
            result = self.tools.call(name, {}, agent_id=AgentId.MIMIR)
            self.assertEqual(result.classification, 'PUBLIC')
            self.assertLessEqual(len(result.render()), 8000)
        api = self.tools.call('get_public_api_capabilities', {}, agent_id=AgentId.MIMIR)
        self.assertEqual(api.status, 'NOT_PUBLISHED')
        self.assertEqual(api.evidence, ())
        with self.assertRaises(KnowledgeToolError):
            self.tools.call('get_public_api_capabilities', {'url': 'https://example.test'}, agent_id=AgentId.MIMIR)

    def test_classification_status_and_agent_checked_even_if_search_regresses(self):
        original = self.knowledge.chunks[0]
        allowed = replace(original.authority, classification=KnowledgeClassification.PUBLIC,
                          status=KnowledgeSourceStatus.CURRENT, allowed_agents=frozenset({AgentId.MIMIR}))
        safe = replace(original, text='Approved public text', authority=allowed)
        forbidden = [replace(safe, text='DO NOT DISCLOSE', authority=replace(allowed, classification=c))
                     for c in KnowledgeClassification if c is not KnowledgeClassification.PUBLIC]
        forbidden.append(replace(safe, text='STALE', authority=replace(allowed, status=KnowledgeSourceStatus.SUPERSEDED)))
        kb = SimpleNamespace(load_errors=[], search=lambda *a, **kw: forbidden+[safe])
        tools = KnowledgeTools(kb)
        result = tools.call('get_supported_networks', {}, agent_id=AgentId.MIMIR)
        self.assertEqual([i.text for i in result.evidence], ['Approved public text'])
        self.assertNotIn(original.source, result.render())
        self.assertFalse(tools.call('get_supported_networks', {}, agent_id=AgentId.EIR).evidence)

    def test_invalid_source_fails_closed_and_large_lists_are_not_truncated(self):
        chunk = next(c for c in self.knowledge.chunks if c.authority.classification is KnowledgeClassification.PUBLIC)
        chunk = replace(chunk, text='x'*9000)
        kb = SimpleNamespace(load_errors=[], search=lambda *a, **kw: [chunk])
        tools = KnowledgeTools(kb)
        self.assertFalse(tools.call('get_plan_matrix', {}, agent_id=next(iter(chunk.authority.allowed_agents))).evidence)
        kb.load_errors=['bad manifest']
        self.assertEqual(tools.call('get_plan_matrix', {}, agent_id=AgentId.ZION).status, 'SOURCE_INVALID')

    def test_short_cm_alias_uses_phrase_context(self):
        self.assertEqual(recover_language('cm funciona swap?').canonical, 'como funciona swap?')
        self.assertEqual(recover_language('parceria cm vcs').canonical, 'parceria com voces')
        self.assertIn('https://example.test/cm', recover_language('https://example.test/cm funciona').canonical)
