from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from zion.db import ZionDB


class BackupVerifierScriptTests(unittest.TestCase):
    def test_verifier_accepts_valid_backup_and_rejects_bad_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_path = root / "source.db"
            backup_path = root / "backup.db"

            db = ZionDB(source_path)
            db.initialize()
            try:
                db.record_user_event(
                    chat_id=1,
                    user_id=2,
                    event_type="backup-verifier",
                )
                db.backup_to(backup_path)
            finally:
                db.close()

            digest = hashlib.sha256(
                backup_path.read_bytes()
            ).hexdigest()

            repo = Path(__file__).resolve().parent.parent
            script = repo / "scripts" / "verify-sqlite-backup.py"

            good = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    str(backup_path),
                    "--sha256",
                    digest,
                ],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertIn("ZION SQLITE BACKUP: OK", good.stdout)

            bad = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    str(backup_path),
                    "--sha256",
                    "0" * 64,
                ],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(bad.returncode, 3)
            self.assertIn("SHA-256 mismatch", bad.stderr)


if __name__ == "__main__":
    unittest.main()
