from __future__ import annotations

import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

from zion.knowledge import KnowledgeBase


class KnowledgeTests(unittest.TestCase):
    def test_retrieval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "official.md").write_text(
                "# Security\nNever share a seed phrase.\n\n"
                "# Fees\nFees must come from official documentation.\n",
                encoding="utf-8",
            )
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
                kb = KnowledgeBase(root)
                self.assertEqual(kb.chunks, [])
                self.assertEqual(len(kb.load_errors), 1)
            finally:
                outside.unlink(missing_ok=True)

    def test_invalid_utf8_knowledge_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "broken.md").write_bytes(b"\xff\xfe\xfd")
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
            kb = KnowledgeBase(root)
            rendered = kb.render_context(
                "guardian",
                max_chars=500,
            )
            self.assertLessEqual(len(rendered), 500)
            self.assertIn("[Contexto oficial: Guardian]", rendered)
            self.assertNotIn("official.md", rendered)

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

        self.assertIn("suporte direto prioritário", rendered)
        self.assertIn("status Founder", rendered)
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

        self.assertIn("Trader sobe para 25 análises", rendered)
        self.assertIn("Pilot sobe para 30 análises", rendered)
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

        expected = (
            "Free, Pro, Trader e Pilot",
            "5 análises do ZION por dia",
            "10 análises do ZION por dia",
            "25 análises do ZION por dia",
            "30 análises do ZION por dia",
            "US$ 7,90 por mês",
            "US$ 20,90 por mês",
            "US$ 159 por mês",
            "taxa de swap do Pro nas redes EVM é 0,5%",
            "taxa de swap do Trader nas redes EVM é 0,25%",
            "taxa de swap do Pilot nas redes EVM é 0,10%",
            "decisão atual do produto é não cobrar taxa de integração",
        )
        for fact in expected:
            with self.subTest(fact=fact):
                self.assertIn(fact, text)

        self.assertNotIn("/home/", text)
        self.assertNotIn("src/", text)



class ZSwapKnowledgeCorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.kb = KnowledgeBase(ROOT / "knowledge")

    def test_zswap_networks_are_retrievable(self) -> None:
        context = self.kb.render_context(
            "quais redes blockchains a Z-SWAP suporta"
        )
        self.assertIn("Ethereum", context)
        self.assertIn("Solana", context)
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

if __name__ == "__main__":
    unittest.main()
