from __future__ import annotations

import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
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
                self.assertEqual(
                    stat.S_IMODE(path.parent.stat().st_mode),
                    0o700,
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

    def test_lock_path_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state"
            state.mkdir()
            target = state / "target.lock"
            target.write_text("", encoding="utf-8")
            link = state / "runtime.lock"
            link.symlink_to(target)

            with self.assertRaises(RuntimeError):
                ProcessLock(link)

    def test_lock_descriptor_is_not_inheritable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state" / "runtime.lock"
            lock = ProcessLock(path)
            try:
                self.assertFalse(os.get_inheritable(lock._fd))
            finally:
                lock.close()

    def test_sigkill_releases_kernel_lock_for_restart(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state" / "runtime.lock"
            root = Path(__file__).resolve().parent.parent

            code = (
                "import sys,time;"
                "from pathlib import Path;"
                "from zion.process_lock import ProcessLock;"
                "lock=ProcessLock(Path(sys.argv[1]));"
                "print('READY', flush=True);"
                "time.sleep(30)"
            )

            env = os.environ.copy()
            env["PYTHONPATH"] = str(root)

            child = subprocess.Popen(
                [sys.executable, "-c", code, str(path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            try:
                ready = child.stdout.readline().strip()
                self.assertEqual(ready, "READY")

                with self.assertRaises(RuntimeError):
                    ProcessLock(path)

                os.kill(child.pid, signal.SIGKILL)
                child.wait(timeout=5)

                deadline = time.time() + 2
                restarted = None
                while time.time() < deadline:
                    try:
                        restarted = ProcessLock(path)
                        break
                    except RuntimeError:
                        time.sleep(0.02)

                self.assertIsNotNone(restarted)
                if restarted is not None:
                    restarted.close()
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
