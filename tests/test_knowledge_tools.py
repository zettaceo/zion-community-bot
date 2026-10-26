from __future__ import annotations
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest

from zion.agents import AgentId
from zion.knowledge import KnowledgeBase, KnowledgeClassification, KnowledgeSourceStatus
from zion.knowledge_tools import KnowledgeTools, KnowledgeToolError, TOOL_NAMES
from zion.language_recovery import recover_language


_COMPARISON_QUERY = ('Qual a diferença da Z-SWAP para outras plataformas?\n'
                     'Isso já existe.\nUniswap faz isso.')


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

    def test_product_comparison_carries_precise_feature_status(self):
        result = self.tools.call('search_approved_knowledge',
            {'query': _COMPARISON_QUERY}, agent_id=AgentId.ZION)
        headings = [item.heading for item in result.evidence]
        self.assertEqual(headings.count('Produto antes de promessa'), 1)
        self.assertEqual(headings.count('Beta'), 1)
        self.assertIn('Portfolio e Orders estão parcialmente disponíveis', result.render())
        self.assertIn('Terminal Pro está marcado como beta', result.render())
        self.assertLessEqual(len(result.render()), 8000)
        feature_result = self.tools.call('search_approved_knowledge',
            {'query': 'Qual a diferença do Terminal Pro da Z-SWAP para outras plataformas?'},
            agent_id=AgentId.ZION)
        self.assertIn('Terminal Pro está marcado como beta', feature_result.render())
        natural_comparison = self.tools.call('search_approved_knowledge',
            {'query': 'O que a Z-SWAP oferece que a Uniswap não oferece?'},
            agent_id=AgentId.ZION)
        self.assertIn('Produto antes de promessa',
                      [item.heading for item in natural_comparison.evidence])
        self.assertIn('Beta', [item.heading for item in natural_comparison.evidence])

    def test_comparison_status_companions_require_public_current_agent_authority(self):
        generic = next(chunk for chunk in self.knowledge.chunks
                       if chunk.heading == 'Z-SWAP — Posicionamento institucional público')
        portfolio = next(chunk for chunk in self.knowledge.chunks
                         if chunk.heading == 'Produto antes de promessa')
        beta = next(chunk for chunk in self.knowledge.chunks
                    if chunk.heading == 'Beta' and chunk.source == 'zswap-status.md')
        for authority in (
            replace(beta.authority, classification=KnowledgeClassification.CONTROLLED),
            replace(beta.authority, status=KnowledgeSourceStatus.SUPERSEDED),
            replace(beta.authority, allowed_agents=frozenset({AgentId.EIR})),
        ):
            with self.subTest(authority=authority):
                kb = SimpleNamespace(load_errors=[], chunks=[portfolio, replace(beta, authority=authority)],
                    search=lambda *a, **kw: [generic])
                result = KnowledgeTools(kb).call('search_approved_knowledge',
                    {'query': _COMPARISON_QUERY}, agent_id=AgentId.ZION)
                self.assertEqual([item.heading for item in result.evidence], [generic.heading])

    def test_exact_plan_comparison_does_not_force_product_status(self):
        generic = next(chunk for chunk in self.knowledge.chunks
                       if chunk.heading == 'Z-SWAP — Posicionamento institucional público')
        statuses = [chunk for chunk in self.knowledge.chunks
                    if (chunk.source, chunk.heading) in {
                        ('zswap-apn.md', 'Produto antes de promessa'),
                        ('zswap-status.md', 'Beta'),
                    }]
        kb = SimpleNamespace(load_errors=[], chunks=statuses,
            search=lambda *a, **kw: [generic])
        result = KnowledgeTools(kb).call('search_approved_knowledge',
            {'query': 'Qual a diferença do plano Pro para o Pilot da Z-SWAP?'},
            agent_id=AgentId.ZION)
        self.assertEqual([item.heading for item in result.evidence], [generic.heading])

    def test_comparison_status_capacity_is_reserved_and_atomic(self):
        generic = next(chunk for chunk in self.knowledge.chunks
                       if chunk.heading == 'Z-SWAP — Posicionamento institucional público')
        statuses = [chunk for chunk in self.knowledge.chunks
                    if (chunk.source, chunk.heading) in {
                        ('zswap-apn.md', 'Produto antes de promessa'),
                        ('zswap-status.md', 'Beta'),
                    }]
        oversized_generic = replace(generic, text='x' * 7900)
        kb = SimpleNamespace(load_errors=[], chunks=statuses,
            search=lambda *a, **kw: [oversized_generic])
        result = KnowledgeTools(kb).call('search_approved_knowledge',
            {'query': _COMPARISON_QUERY}, agent_id=AgentId.ZION)
        self.assertEqual([item.heading for item in result.evidence],
                         ['Produto antes de promessa', 'Beta'])
        self.assertLessEqual(len(result.render()), 8000)

        oversized_beta = replace(statuses[1], text='x' * 8000)
        kb.chunks = [statuses[0], oversized_beta]
        kb.search = lambda *a, **kw: [generic]
        result = KnowledgeTools(kb).call('search_approved_knowledge',
            {'query': _COMPARISON_QUERY}, agent_id=AgentId.ZION)
        self.assertEqual([item.heading for item in result.evidence], [generic.heading])

    def test_comparison_status_and_complete_fee_matrix_both_fit(self):
        generic = next(chunk for chunk in self.knowledge.chunks
                       if chunk.heading == 'Z-SWAP — Posicionamento institucional público')
        statuses = [chunk for chunk in self.knowledge.chunks
                    if (chunk.source, chunk.heading) in {
                        ('zswap-apn.md', 'Produto antes de promessa'),
                        ('zswap-status.md', 'Beta'),
                    }]
        plans = [next(chunk for chunk in self.knowledge.chunks
                      if chunk.heading.startswith('Plano ' + tier))
                 for tier in ('Free', 'Pro', 'Trader', 'Pilot')]
        kb = SimpleNamespace(load_errors=[], chunks=[*plans, *statuses],
            search=lambda *a, **kw: [replace(generic, text='x' * 7000), *plans[:2]])
        result = KnowledgeTools(kb).call('search_approved_knowledge',
            {'query': _COMPARISON_QUERY + '\nVocês cobram mais?'}, agent_id=AgentId.ZION)
        headings = [item.heading for item in result.evidence]
        self.assertIn('Produto antes de promessa', headings)
        self.assertIn('Beta', headings)
        self.assertEqual([heading.split()[1] for heading in headings if heading.startswith('Plano ')],
                         ['Free', 'Pro', 'Trader', 'Pilot'])
        self.assertLessEqual(len(result.render()), 8000)

    def test_broad_plan_retrieval_keeps_all_four_public_fee_sections(self):
        query = 'Então qual vantagem? Isso é marketing. Me dá prova, sem prometer desempenho.'
        result = self.tools.call('search_approved_knowledge', {'query': query}, agent_id=AgentId.MIMIR)
        headings = [item.heading for item in result.evidence]
        for tier in ('Free', 'Pro', 'Trader', 'Pilot'):
            with self.subTest(tier=tier):
                self.assertTrue(any(heading.startswith('Plano ' + tier) for heading in headings))
        trader = next(item for item in result.evidence if item.heading == 'Plano Trader')
        self.assertIn('0,25%', trader.text)
        self.assertLessEqual(len(result.render()), 8000)

    def test_exact_tier_query_does_not_expand_fee_plan_siblings(self):
        result = self.tools.call('search_approved_knowledge',
            {'query': 'Qual a platform fee EVM do plano Pro?'}, agent_id=AgentId.MIMIR)
        plan_headings = [item.heading for item in result.evidence if item.heading.startswith('Plano ')]
        self.assertTrue(any(heading.startswith('Plano Pro') for heading in plan_headings))
        self.assertFalse(any(heading.startswith(('Plano Free', 'Plano Trader', 'Plano Pilot'))
                             for heading in plan_headings))

    def test_fee_siblings_require_same_public_current_agent_authorized_source(self):
        plans = {tier: next(chunk for chunk in self.knowledge.chunks
                            if chunk.heading.startswith('Plano ' + tier))
                 for tier in ('Free', 'Pro', 'Trader', 'Pilot')}
        free, pro = plans['Free'], plans['Pro']
        trader = replace(plans['Trader'], text='CONTROLLED SIBLING 0,25%',
            authority=replace(plans['Trader'].authority,
                              classification=KnowledgeClassification.CONTROLLED))
        pilot = replace(plans['Pilot'], text='STALE SIBLING 0,10%',
            authority=replace(plans['Pilot'].authority,
                              status=KnowledgeSourceStatus.SUPERSEDED))
        kb = SimpleNamespace(load_errors=[], chunks=[free, pro, trader, pilot],
            search=lambda *a, **kw: [free, pro])
        result = KnowledgeTools(kb).call('search_approved_knowledge',
            {'query': 'Explique vantagens dos planos'}, agent_id=AgentId.MIMIR)
        self.assertEqual([item.heading for item in result.evidence],
                         [free.heading, pro.heading])
        self.assertNotIn('CONTROLLED SIBLING', result.render())
        self.assertNotIn('STALE SIBLING', result.render())

    def test_fee_siblings_are_never_truncated_to_fit_the_evidence_bound(self):
        plans = {tier: next(chunk for chunk in self.knowledge.chunks
                            if chunk.heading.startswith('Plano ' + tier))
                 for tier in ('Free', 'Pro', 'Trader', 'Pilot')}
        huge_trader = replace(plans['Trader'], text=plans['Trader'].text + 'x' * 8000)
        kb = SimpleNamespace(load_errors=[],
            chunks=[plans['Free'], plans['Pro'], huge_trader, plans['Pilot']],
            search=lambda *a, **kw: [plans['Free'], plans['Pro']])
        result = KnowledgeTools(kb).call('search_approved_knowledge',
            {'query': 'Explique vantagens dos planos'}, agent_id=AgentId.MIMIR)
        self.assertFalse(any(item.heading.startswith('Plano ') for item in result.evidence))
        self.assertLessEqual(len(result.render()), 8000)

    def test_fee_sibling_capacity_is_reserved_before_other_broad_hits(self):
        plans = {tier: next(chunk for chunk in self.knowledge.chunks
                            if chunk.heading.startswith('Plano ' + tier))
                 for tier in ('Free', 'Pro', 'Trader', 'Pilot')}
        generic = next(chunk for chunk in self.knowledge.chunks
                       if chunk.heading == 'Z-SWAP — Guia Público de Recursos')
        generic = replace(generic, text='PUBLIC OVERVIEW ' + 'x' * 7000)
        kb = SimpleNamespace(load_errors=[], chunks=list(plans.values()),
            search=lambda *a, **kw: [generic, plans['Free'], plans['Pro']])
        result = KnowledgeTools(kb).call('search_approved_knowledge',
            {'query': 'Explique vantagens dos planos'}, agent_id=AgentId.MIMIR)
        headings = [item.heading for item in result.evidence]
        self.assertEqual([heading.split()[1] for heading in headings],
                         ['Free', 'Pro', 'Trader', 'Pilot'])
        self.assertLessEqual(len(result.render()), 8000)

    def test_fee_siblings_do_not_cross_agent_allowlist(self):
        plans = {tier: next(chunk for chunk in self.knowledge.chunks
                            if chunk.heading.startswith('Plano ' + tier))
                 for tier in ('Free', 'Pro', 'Trader', 'Pilot')}
        unauthorized_trader = replace(plans['Trader'],
            authority=replace(plans['Trader'].authority,
                              allowed_agents=frozenset({AgentId.EIR})))
        kb = SimpleNamespace(load_errors=[],
            chunks=[plans['Free'], plans['Pro'], unauthorized_trader, plans['Pilot']],
            search=lambda *a, **kw: [plans['Free'], plans['Pro']])
        result = KnowledgeTools(kb).call('search_approved_knowledge',
            {'query': 'Explique vantagens dos planos'}, agent_id=AgentId.MIMIR)
        self.assertEqual([item.heading for item in result.evidence],
                         [plans['Free'].heading, plans['Pro'].heading])
