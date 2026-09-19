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

if __name__ == "__main__":
    unittest.main()
