from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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
            "taxa de swap do Pilot nas redes EVM é 0,1%",
            "decisão atual do produto é não cobrar taxa de integração",
        )
        for fact in expected:
            with self.subTest(fact=fact):
                self.assertIn(fact, text)

        self.assertNotIn("/home/", text)
        self.assertNotIn("src/", text)

if __name__ == "__main__":
    unittest.main()
