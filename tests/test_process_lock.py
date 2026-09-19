from __future__ import annotations

import stat
import tempfile
import unittest
from pathlib import Path

from zion.process_lock import ProcessLock


class ProcessLockTests(unittest.TestCase):
    def test_second_runtime_lock_is_rejected_then_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state" / "runtime.lock"
            first = ProcessLock(path)
            try:
                self.assertTrue(first.acquired)
                self.assertEqual(
                    stat.S_IMODE(path.stat().st_mode),
                    0o600,
                )
                with self.assertRaises(RuntimeError):
                    ProcessLock(path)
            finally:
                first.close()

            second = ProcessLock(path)
            try:
                self.assertTrue(second.acquired)
            finally:
                second.close()


if __name__ == "__main__":
    unittest.main()
