from __future__ import annotations

import tempfile
import unittest
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

from zion.knowledge import KnowledgeBase
from zion.knowledge_tools import KnowledgeTools


def write_manifest(
    root: Path,
    *,
    files: list[str] | None = None,
    classification: str = "PUBLIC",
    status: str = "CURRENT",
    allowed_agents: list[str] | None = None,
) -> None:
    selected = files or sorted(
        path.name
        for path in root.glob("*.md")
        if path.name.lower() not in {"readme.md", "manifest.md"}
    )
    agents = allowed_agents or ["zion", "mimir", "eir", "freyr"]
    payload = {
        "schema_version": 1,
        "sources": [
            {
                "file": filename,
                "classification": classification,
                "status": status,
                "version": "test-v1",
                "source_identity": "test-fixture",
                "allowed_agents": agents,
            }
            for filename in selected
        ],
    }
    (root / "MANIFEST.md").write_text(
        "# Test manifest\n\n```json\n"
        + json.dumps(payload)
        + "\n```\n",
        encoding="utf-8",
    )


class KnowledgeTests(unittest.TestCase):
    def test_natural_charging_question_retrieves_published_fee_policy(self):
        kb = KnowledgeBase(ROOT / "knowledge")
        for question in (
            "Vocês cobram mais?",
            "Uniswap faz isso. Binance também. Vocês cobram mais?",
        ):
            with self.subTest(question=question):
                context = kb.render_context(question, agent_id="zion")
                self.assertIn("platform fee", context)
                self.assertIn("EVM", context)
                tool_context = KnowledgeTools(kb).call(
                    "search_approved_knowledge", {"query": question},
                    agent_id="zion",
                ).render()
                self.assertIn("platform fee", tool_context)
                self.assertIn("EVM", tool_context)

    def test_solana_fees_retrieve_current_qualified_policy_for_every_agent(self):
        kb = KnowledgeBase(ROOT / "knowledge")
        for agent in ("zion", "mimir", "eir", "freyr"):
            with self.subTest(agent=agent):
                rendered = " ".join(kb.render_context(
                    "Quais as taxas Solana Jupiter LI.FI?", agent_id=agent,
                ).split())
                for fact in (
                    "Free/Thrall 1,00%", "Pro/Drengr 0,50%",
                    "Trader/Berserkr 0,25%", "Pilot/Einherjar 0,10%",
                    "USDC ou SOL", "Outros pares Solana não têm",
                    "LI.FI saindo da Solana", "swap prossegue sem",
                ):
                    self.assertIn(fact, rendered)
                self.assertNotIn("platform fee da Z-SWAP está atualmente desabilitada", rendered)

    def test_partnership_pricing_criticism_prioritizes_business_scope(self):
        kb = KnowledgeBase(ROOT / 'knowledge')
        hits = kb.search('A parceria está cara, concorrentes fazem a mesma coisa', agent_id='freyr')
        self.assertEqual(hits[0].heading, 'Comunidade e parcerias')
        self.assertIn('Uma conversa não equivale', hits[0].text)
        self.assertNotIn('taxa', hits[0].text.casefold())

    def test_exact_competitive_objection_retrieves_institutional_value_before_market_data(self):
        kb = KnowledgeBase(ROOT / 'knowledge')
        hits = kb.search('Concerteza deve ter plataformas mais baratas, que oferecem a mesma coisa que a zswap e já consolidadas no mercado', agent_id='zion')
        self.assertIn('Posicionamento institucional', hits[0].heading)
        self.assertIn('produto antes de promessa', {h.heading.casefold() for h in hits})

    def test_retrieval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "official.md").write_text(
                "# Security\nNever share a seed phrase.\n\n"
                "# Fees\nFees must come from official documentation.\n",
                encoding="utf-8",
            )
            write_manifest(root)
            kb = KnowledgeBase(root)
            results = kb.search("seed phrase security")
            self.assertTrue(results)
            self.assertEqual(results[0].heading, "Security")


    def test_maintainer_readme_is_not_loaded_as_public_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text(
                "# Maintainer\ninternal maintenance instructions\n",
                encoding="utf-8",
            )
            (root / "public.md").write_text(
                "# Product\npublic product fact\n",
                encoding="utf-8",
            )
            write_manifest(root)
            kb = KnowledgeBase(root)
            self.assertNotIn(
                "internal maintenance instructions",
                kb.render_context("maintainer internal maintenance"),
            )
            self.assertIn(
                "public product fact",
                kb.render_context("product public fact"),
            )

    def test_stopword_only_query_returns_no_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "official.md").write_text(
                "# Security\nNever share a seed phrase.\n",
                encoding="utf-8",
            )
            write_manifest(root)
            kb = KnowledgeBase(root)
            self.assertEqual(
                kb.search("what is the and of"),
                [],
            )

    def test_weak_incidental_overlap_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "official.md").write_text(
                "# Security\nOfficial support channels are documented here.\n",
                encoding="utf-8",
            )
            write_manifest(root)
            kb = KnowledgeBase(root)
            self.assertEqual(
                kb.search(
                    "support banana orange zebra alpha beta"
                ),
                [],
            )

    def test_symlinked_knowledge_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root.parent / f"{root.name}-outside.md"
            outside.write_text(
                "# Secret\nThis file must not be loaded.\n",
                encoding="utf-8",
            )
            try:
                (root / "linked.md").symlink_to(outside)
                write_manifest(root)
                kb = KnowledgeBase(root)
                self.assertEqual(kb.chunks, [])
                self.assertEqual(len(kb.load_errors), 1)
            finally:
                outside.unlink(missing_ok=True)

    def test_invalid_utf8_knowledge_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "broken.md").write_bytes(b"\xff\xfe\xfd")
            write_manifest(root)
            kb = KnowledgeBase(root)
            self.assertEqual(kb.chunks, [])
            self.assertEqual(len(kb.load_errors), 1)

    def test_render_context_is_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "official.md").write_text(
                "# Guardian\n" + ("guardian " * 3000),
                encoding="utf-8",
            )
            write_manifest(root)
            kb = KnowledgeBase(root)
            rendered = kb.render_context(
                "guardian",
                max_chars=500,
            )
            self.assertLessEqual(len(rendered), 500)
            self.assertIn("[Contexto oficial: Guardian]", rendered)
            self.assertNotIn("official.md", rendered)

    def test_missing_manifest_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "unclassified.md").write_text(
                "# Private\nThis must never enter context.\n",
                encoding="utf-8",
            )
            kb = KnowledgeBase(root)
            self.assertEqual(kb.chunks, [])
            self.assertEqual(len(kb.load_errors), 1)

    def test_unclassified_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "approved.md").write_text(
                "# Product\nApproved public fact.\n",
                encoding="utf-8",
            )
            (root / "forgotten.md").write_text(
                "# Internal\nForgotten private fact.\n",
                encoding="utf-8",
            )
            write_manifest(root, files=["approved.md"])
            kb = KnowledgeBase(root)
            self.assertIn("Approved public fact", kb.render_context("product"))
            self.assertNotIn("Forgotten private fact", kb.render_context("private"))
            self.assertTrue(
                any("forgotten.md" in error for error in kb.load_errors)
            )

    def test_internal_secret_and_noncurrent_sources_never_retrieve(self) -> None:
        for classification, status in (
            ("INTERNAL", "CURRENT"),
            ("SECRET", "CURRENT"),
            ("PUBLIC", "HISTORICAL"),
            ("PUBLIC", "SUPERSEDED"),
            ("PUBLIC", "EXCLUDED"),
        ):
            with self.subTest(classification=classification, status=status):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / "restricted.md").write_text(
                        "# Restricted\nUnique forbidden material.\n",
                        encoding="utf-8",
                    )
                    write_manifest(
                        root,
                        classification=classification,
                        status=status,
                    )
                    kb = KnowledgeBase(root)
                    self.assertEqual(
                        kb.render_context("unique forbidden material"),
                        "",
                    )

    def test_controlled_source_is_filtered_by_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "controlled.md").write_text(
                "# Architecture\nApproved controlled architecture summary.\n",
                encoding="utf-8",
            )
            write_manifest(
                root,
                classification="CONTROLLED",
                allowed_agents=["mimir"],
            )
            kb = KnowledgeBase(root)
            self.assertEqual(
                kb.render_context(
                    "approved controlled architecture",
                    agent_id="zion",
                ),
                "",
            )
            self.assertIn(
                "Approved controlled architecture summary",
                kb.render_context(
                    "approved controlled architecture",
                    agent_id="mimir",
                ),
            )

    def test_unknown_agent_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "public.md").write_text(
                "# Product\nPublic fact.\n",
                encoding="utf-8",
            )
            write_manifest(root)
            kb = KnowledgeBase(root)
            self.assertEqual(
                kb.render_context("public fact", agent_id="unknown"),
                "",
            )

    def test_product_knowledge_answers_basic_z_swap_question(self) -> None:
        root = Path(__file__).resolve().parents[1] / "knowledge"
        kb = KnowledgeBase(root)

        rendered = kb.render_context("O que é a Z-SWAP?")

        self.assertIn("plataforma não custodial", rendered)
        self.assertNotIn("z-swap.md", rendered)

    def test_product_knowledge_answers_pilot_benefits(self) -> None:
        root = Path(__file__).resolve().parents[1] / "knowledge"
        kb = KnowledgeBase(root)

        rendered = kb.render_context(
            "Quais são os benefícios do plano piloto?"
        )

        self.assertIn("30 análises do ZION por dia", rendered)
        self.assertIn("até 10 mesas de papel adiante", rendered)
        self.assertIn("Automação avançada do Pilot pertence ao roadmap", rendered)
        self.assertNotIn("Autopilot CEX disponível", rendered)
        self.assertNotIn("z-swap.md", rendered)

    def test_exact_pro_plan_is_not_confused_with_pilot(self) -> None:
        root = Path(__file__).resolve().parents[1] / "knowledge"
        kb = KnowledgeBase(root)

        results = kb.search("Quais são as vantagens do plano Pro?")
        rendered = kb.render_context(
            "Quais são as vantagens do plano Pro?"
        )

        self.assertEqual(results[0].heading, "Plano Pro ou profissional")
        self.assertIn("10 análises do ZION por dia", rendered)
        self.assertIn("O Pro não inclui mesas de papel adiante", rendered)
        self.assertNotIn(
            "[Contexto oficial: Plano Pilot ou plano piloto]",
            rendered,
        )

    def test_professional_alias_retrieves_pro_plan(self) -> None:
        root = Path(__file__).resolve().parents[1] / "knowledge"
        kb = KnowledgeBase(root)

        results = kb.search("O plano profissional tem papel adiante?")

        self.assertEqual(results[0].heading, "Plano Pro ou profissional")

    def test_plan_overview_names_all_four_distinct_levels(self) -> None:
        root = Path(__file__).resolve().parents[1] / "knowledge"
        kb = KnowledgeBase(root)

        rendered = kb.render_context("Quais são os planos?")

        self.assertIn("Free, Pro, Trader e Pilot", rendered)
        self.assertIn("Pro nunca significa Pilot", rendered)

    def test_trader_and_pilot_comparison_retrieves_both(self) -> None:
        root = Path(__file__).resolve().parents[1] / "knowledge"
        kb = KnowledgeBase(root)

        rendered = kb.render_context(
            "Qual a diferença entre Trader e Pilot?"
        )
        flat = " ".join(rendered.split())

        self.assertIn("Trader sobe para 25 análises", flat)
        self.assertIn("Pilot sobe para 30 análises", flat)
        self.assertIn(
            "[Contexto oficial: Plano Trader]",
            rendered,
        )
        self.assertIn(
            "[Contexto oficial: Plano Pilot ou plano piloto]",
            rendered,
        )

    def test_current_plan_matrix_contains_canonical_product_facts(self):
        root = Path(__file__).resolve().parents[1] / "knowledge"
        text = (root / "z-swap-plans.md").read_text(encoding="utf-8")
        flat = " ".join(text.split())

        expected = (
            "Free, Pro, Trader e Pilot",
            "5 análises do ZION por dia",
            "10 análises do ZION por dia",
            "25 análises do ZION por dia",
            "30 análises do ZION por dia",
            "platform fee EVM pública é 0,50%",
            "platform fee EVM pública é 0,25%",
            "platform fee EVM pública é 0,10%",
            "Outros pares Solana não têm platform fee da Z-SWAP",
            "exatamente 36 meses de Premium",
            "A venda não está aberta",
            "preços públicos finais ainda não foram anunciados",
        )
        for fact in expected:
            with self.subTest(fact=fact):
                self.assertIn(fact, flat)

        self.assertNotIn("/home/", text)
        self.assertNotIn("src/", text)
        for superseded in (
            "US$ 7,90 por mês",
            "US$ 20,90 por mês",
            "US$ 159 por mês",
            "1,5 SOL",
            "4 SOL",
            "30 SOL",
            "1.500 passes",
            "500 passes",
            "50 passes",
            "ou acesso até a versão 3",
        ):
            with self.subTest(superseded=superseded):
                self.assertNotIn(superseded, flat)

    def test_apn_canonical_source_preserves_all_21_pages(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (
            root / "docs" / "apn" / "Z-SWAP-APN-SOURCE.md"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "f11814ff833a86f974b4ddd0fc14ad2e9372afe52ffd4dff206315de3a8b5c4d",
            text,
        )
        for page in range(1, 22):
            with self.subTest(page=page):
                self.assertIn(f"## {page:02d} —", text)
        self.assertIn("docs/PITCH-DECK.md", text)
        self.assertIn("HISTORICAL / EXCLUDED", text)

    def test_technical_paper_source_is_mixed_and_exact_route_is_not_invented(self) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (
            root
            / "docs"
            / "technical-paper"
            / "Z-SWAP-TECHNICAL-PAPER-SOURCE.md"
        ).read_text(encoding="utf-8")

        self.assertIn("that exact file is absent", text)
        self.assertIn("67 planned sections", text)
        self.assertIn("| 42 | Database Security | INTERNAL |", text)
        self.assertIn("| 13 | Supported Network Architecture | PUBLIC |", text)
        self.assertIn("The raw source documents are never indexed directly", text)

    def test_apn_and_technical_projections_follow_agent_matrix(self) -> None:
        root = Path(__file__).resolve().parents[1] / "knowledge"
        kb = KnowledgeBase(root)

        apn = kb.render_context(
            "parcerias creators comunidades protocolos",
            agent_id="freyr",
        )
        self.assertIn("creators", apn)

        mimir = kb.render_context(
            "arquitetura pública roteamento DEX bridge",
            agent_id="mimir",
        )
        self.assertIn("camadas de execução, inteligência e risco", mimir)

        zion = kb.render_context(
            "arquitetura pública roteamento DEX bridge",
            agent_id="zion",
        )
        self.assertNotIn("camadas de execução, inteligência e risco", zion)

    def test_current_corpus_rejects_superseded_founder_and_autopilot_claims(self) -> None:
        root = Path(__file__).resolve().parents[1] / "knowledge"
        corpus = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(root.glob("*.md"))
            if path.name != "MANIFEST.md"
        )

        self.assertNotIn("acesso até a versão 3", corpus)
        self.assertNotIn("Autopilot CEX é um recurso de automação em corretoras centralizadas. Começa no plano Pro", corpus)
        self.assertNotIn("oferta planejada de 1.500 passes", corpus)
        self.assertIn("uso público permanece desabilitado", corpus)



class ZSwapKnowledgeCorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kb = KnowledgeBase(ROOT / "knowledge")

    def test_zswap_networks_are_retrievable(self) -> None:
        query = "Quais redes a Z-SWAP suporta atualmente?"
        results = self.kb.search(query)
        context = self.kb.render_context(query)

        self.assertTrue(results)
        self.assertIn("redes", results[0].heading.lower())
        for network in (
            "Ethereum",
            "BNB Chain",
            "Polygon",
            "Base",
            "Arbitrum",
            "Optimism",
            "Avalanche",
            "Solana",
        ):
            with self.subTest(network=network):
                self.assertIn(network, context)

        self.assertIn("ZETTA Chain", context)
        self.assertIn("coming soon", context)

    def test_zswap_tier_fee_is_retrievable(self) -> None:
        context = self.kb.render_context(
            "qual a taxa de swap do plano Pilot em EVM"
        )
        self.assertIn("Pilot", context)
        self.assertIn("0,10%", context)
        self.assertIn("EVM", context)

    def test_zswap_cex_list_is_retrievable(self) -> None:
        context = self.kb.render_context(
            "quais corretoras CEX exchanges são suportadas"
        )
        self.assertIn("Binance", context)
        self.assertIn("Coinbase Advanced", context)
        self.assertIn("Gate.io", context)
        self.assertIn("HTX", context)

    def test_zswap_future_surface_is_not_presented_as_live(self) -> None:
        context = self.kb.render_context(
            "launchpad governance já estão lançados disponíveis"
        )
        self.assertIn("pre-launch", context)

    def test_pro_indicator_suite_is_retrievable(self) -> None:
        context = self.kb.render_context(
            "quais indicadores técnicos tem no Terminal Pro EMA RSI MACD"
        )
        self.assertIn("EMA 200", context)
        self.assertIn("RSI 14", context)
        self.assertIn("MACD 12/26/9", context)
        self.assertIn("Bollinger Bands", context)

    def test_terminal_pro_order_query_ranks_canonical_section_first(self) -> None:
        results = self.kb.search(
            "Quais tipos de ordem existem no Terminal Pro?"
        )
        self.assertTrue(results)
        self.assertEqual(results[0].heading, "Painel de ordens")

    def test_terminal_pro_order_list_is_exact_and_complete(self) -> None:
        answer = self.kb.canonical_finite_answer(
            "Quais tipos de ordem existem no Terminal Pro?"
        )
        self.assertIsNotNone(answer)
        self.assertIn("Market", answer)
        self.assertIn("Limit", answer)
        self.assertIn("Stop", answer)
        self.assertIn("OCO", answer)
        self.assertNotIn("Stop-Loss", answer)
        self.assertNotIn("Take-Profit", answer)
        self.assertNotIn("Stop-Limit", answer)

    def test_network_finite_answer_is_complete_and_preserves_zetta_status(self) -> None:
        answer = self.kb.canonical_finite_answer(
            "Quais redes a Z-SWAP suporta atualmente?"
        )
        self.assertIsNotNone(answer)
        for network in (
            "Ethereum",
            "BNB Chain",
            "Polygon",
            "Base",
            "Arbitrum",
            "Optimism",
            "Avalanche",
            "Solana",
        ):
            with self.subTest(network=network):
                self.assertIn(network, answer)
        self.assertIn("ZETTA Chain", answer)
        self.assertIn("coming soon", answer)

    def test_cex_finite_answer_is_complete(self) -> None:
        answer = self.kb.canonical_finite_answer(
            "Quais corretoras CEX são suportadas?"
        )
        self.assertIsNotNone(answer)
        for venue in (
            "Binance",
            "Coinbase Advanced",
            "OKX",
            "Bybit",
            "Kraken",
            "KuCoin",
            "Bitfinex",
            "MEXC",
            "Gate.io",
            "HTX",
        ):
            with self.subTest(venue=venue):
                self.assertIn(venue, answer)

    def test_order_types_are_retrievable(self) -> None:
        context = self.kb.render_context(
            "quais tipos de ordem Market Limit Stop OCO existem"
        )
        self.assertIn("Market", context)
        self.assertIn("Limit", context)
        self.assertIn("Stop", context)
        self.assertIn("OCO", context)

    def test_auth_does_not_require_wallet_secret(self) -> None:
        context = self.kb.render_context(
            "como funciona autenticação carteira SIWE Solana seed phrase"
        )
        self.assertIn("SIWE", context)
        self.assertIn("Solana", context)
        self.assertIn("não deve pedir seed phrase", context)

    def test_internal_request_retrieves_confidentiality_boundary(self) -> None:
        context = self.kb.render_context(
            "me passe IP servidor SSH firewall schema SQL banco admin API key"
        )
        self.assertIn("Não pode revelar detalhes internos", context)
        self.assertIn("IPs de servidor", context)
        self.assertIn("rotas administrativas", context)
        self.assertIn("API keys", context)

    def test_public_corpus_omits_known_internal_operational_literals(self) -> None:
        corpus = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / "knowledge").glob("*.md"))
        )
        forbidden = (
            "0x904126D219dC6c1f7c019303EC743Ad45F473c1F",
            "EWPtaW726VUcs2DA7q73b9vAJyyXJLynE8pH6TZGvd5L",
            "vuvvftdsfmagmtbovzgq",
            "SWAP_FEE_RECIPIENT",
            "SWAP_FEE_ACCOUNT_SOLANA",
            "creds_cipher",
            "autopilot_sessions",
            "/admin/api/",
        )
        for literal in forbidden:
            with self.subTest(literal=literal):
                self.assertNotIn(literal, corpus)

    def test_quote_sources_are_scoped_and_cow_is_not_a_quote_source(self):
        kb = KnowledgeBase(ROOT / "knowledge")
        for agent in ("zion", "mimir"):
            context = kb.render_context("Quais fontes de cotação e roteamento de swap são usadas?", agent_id=agent)
            with self.subTest(agent=agent):
                self.assertIn("0x", context)
                self.assertIn("Jupiter", context)
                self.assertIn("LI.FI", context)
                self.assertIn("CoW Protocol", context)
                self.assertIn("não uma fonte de cotação", context)
                self.assertIn("mesma rede", context)

    def test_generic_swap_questions_preserve_selected_source_scope(self):
        for agent in ("zion", "mimir"):
            for question in ("Swaps e pontes", "O que é possível fazer na Z-SWAP?"):
                with self.subTest(agent=agent, question=question):
                    context = self.kb.render_context(question, agent_id=agent)
                    self.assertIn("fonte", context)
                    self.assertIn("todas as fontes em cada pedido", context)
                    self.assertNotIn("compara as cotações disponíveis", context)
                    self.assertNotIn("comparar cotações de diferentes fontes", context)

    def test_portfolio_question_preserves_unknown_value_and_partial_total(self):
        for agent in ("zion", "mimir", "eir"):
            with self.subTest(agent=agent):
                chunks = self.kb.search(
                    "Portfolio saldo indisponível preço desconhecido", agent_id=agent
                )
                self.assertTrue(chunks)
                self.assertEqual(chunks[0].heading, "Portfolio")
                context = chunks[0].text
                self.assertIn("não devem ser tratados como", context)
                self.assertIn("zero", context)
                self.assertIn("total parcial", context)
                self.assertIn("não comprova o patrimônio", context)
                self.assertNotIn("indistinguível de saldo vazio", context)

    def test_loaded_corpus_content_does_not_embed_repository_or_commit_provenance(self):
        import re
        kb = KnowledgeBase(ROOT / "knowledge")
        for chunk in kb.chunks:
            with self.subTest(heading=chunk.heading):
                self.assertNotIn("zetta-world/swap-z-app", chunk.text)
                self.assertNotIn("zettaceo/zion-community-bot", chunk.text)
                self.assertIsNone(re.search(r"\b[a-f0-9]{40}\b", chunk.text))

if __name__ == "__main__":
    unittest.main()
