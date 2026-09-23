from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class ValidationBoundaryTests(unittest.TestCase):
    def test_validation_bytecode_is_isolated_from_repository(self) -> None:
        text = (ROOT / "scripts" / "validate.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "mktemp -d /tmp/zion-validation-pycache.XXXXXX",
            text,
        )
        self.assertIn(
            'export PYTHONPYCACHEPREFIX="$PYCACHE_ROOT"',
            text,
        )
        self.assertIn(
            'trap \'rm -rf -- "$PYCACHE_ROOT"\' EXIT',
            text,
        )
        self.assertNotIn(
            "export PYTHONPYCACHEPREFIX=${PYTHONPYCACHEPREFIX",
            text,
        )


if __name__ == "__main__":
    unittest.main()
