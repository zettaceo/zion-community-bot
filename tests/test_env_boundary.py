from __future__ import annotations

import os
import pwd
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check-env-boundary.py"


class EnvironmentBoundaryTests(unittest.TestCase):
    def run_check(
        self,
        env_path: Path,
        allowlist_path: Path,
    ) -> subprocess.CompletedProcess[str]:
        owner = pwd.getpwuid(os.getuid()).pw_name
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--env",
                str(env_path),
                "--allowlist",
                str(allowlist_path),
                "--owner",
                owner,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def write_private(self, path: Path, text: str) -> None:
        path.write_text(text, encoding="utf-8")
        path.chmod(0o600)

    def test_accepts_allowlisted_keys_without_printing_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowlist = root / ".env.example"
            env_file = root / ".env"
            secret = "123456789:ABCDEF_secret_value"

            self.write_private(
                allowlist,
                "TELEGRAM_BOT_TOKEN=\nZION_AI_ENABLED=false\n",
            )
            self.write_private(
                env_file,
                (
                    f"TELEGRAM_BOT_TOKEN={secret}\n"
                    "ZION_AI_ENABLED=false\n"
                ),
            )

            result = self.run_check(env_file, allowlist)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("environment boundary: OK", result.stdout)
            self.assertNotIn(secret, result.stdout)
            self.assertNotIn(secret, result.stderr)

    def test_rejects_unknown_key_without_printing_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowlist = root / ".env.example"
            env_file = root / ".env"
            secret = "/tmp/attacker-module-path"

            self.write_private(
                allowlist,
                "TELEGRAM_BOT_TOKEN=\n",
            )
            self.write_private(
                env_file,
                (
                    "TELEGRAM_BOT_TOKEN=test\n"
                    f"PYTHONPATH={secret}\n"
                ),
            )

            result = self.run_check(env_file, allowlist)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("PYTHONPATH", result.stderr)
            self.assertNotIn(secret, result.stdout)
            self.assertNotIn(secret, result.stderr)

    def test_rejects_duplicate_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowlist = root / ".env.example"
            env_file = root / ".env"

            self.write_private(
                allowlist,
                "TELEGRAM_BOT_TOKEN=\n",
            )
            self.write_private(
                env_file,
                "TELEGRAM_BOT_TOKEN=a\nTELEGRAM_BOT_TOKEN=b\n",
            )

            result = self.run_check(env_file, allowlist)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate key TELEGRAM_BOT_TOKEN", result.stderr)

    def test_rejects_export_syntax(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowlist = root / ".env.example"
            env_file = root / ".env"

            self.write_private(
                allowlist,
                "TELEGRAM_BOT_TOKEN=\n",
            )
            self.write_private(
                env_file,
                "export TELEGRAM_BOT_TOKEN=test\n",
            )

            result = self.run_check(env_file, allowlist)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("export syntax is not allowed", result.stderr)

    def test_rejects_group_or_world_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowlist = root / ".env.example"
            env_file = root / ".env"

            self.write_private(
                allowlist,
                "TELEGRAM_BOT_TOKEN=\n",
            )
            self.write_private(
                env_file,
                "TELEGRAM_BOT_TOKEN=test\n",
            )
            env_file.chmod(0o640)

            result = self.run_check(env_file, allowlist)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("mode must be 0600", result.stderr)

    def test_rejects_symlinked_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowlist = root / ".env.example"
            target = root / "real.env"
            link = root / ".env"

            self.write_private(
                allowlist,
                "TELEGRAM_BOT_TOKEN=\n",
            )
            self.write_private(
                target,
                "TELEGRAM_BOT_TOKEN=test\n",
            )
            link.symlink_to(target)

            result = self.run_check(link, allowlist)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("regular non-symlink", result.stderr)

    def test_rejects_hardlinked_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowlist = root / ".env.example"
            env_file = root / ".env"
            second = root / "copy.env"

            self.write_private(
                allowlist,
                "TELEGRAM_BOT_TOKEN=\n",
            )
            self.write_private(
                env_file,
                "TELEGRAM_BOT_TOKEN=test\n",
            )
            os.link(env_file, second)

            result = self.run_check(env_file, allowlist)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must not have hard links", result.stderr)

    def test_rejects_malformed_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowlist = root / ".env.example"
            env_file = root / ".env"

            self.write_private(
                allowlist,
                "TELEGRAM_BOT_TOKEN=\n",
            )
            self.write_private(
                env_file,
                "TELEGRAM_BOT_TOKEN\n",
            )

            result = self.run_check(env_file, allowlist)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid assignment", result.stderr)


if __name__ == "__main__":
    unittest.main()
