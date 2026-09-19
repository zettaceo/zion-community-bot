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


if __name__ == "__main__":
    unittest.main()
