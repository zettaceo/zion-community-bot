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

if __name__ == "__main__":
    unittest.main()
