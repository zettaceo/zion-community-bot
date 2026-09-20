from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check-git-release-boundary.py"
FORBIDDEN_GIT_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_REPLACE_REF_BASE",
    "GIT_CONFIG",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_SYSTEM",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT",
    "GIT_INDEX_FILE",
    "GIT_NAMESPACE",
    "GIT_SSH",
    "GIT_SSH_COMMAND",
    "GIT_SSL_NO_VERIFY",
)


class GitReleaseBoundaryTests(unittest.TestCase):
    def git(self, root: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(root), *args],
            text=True,
            capture_output=True,
            check=True,
        )

    def make_repo(self, root: Path) -> None:
        self.git(root, "init")
        self.git(root, "config", "user.email", "zion-test@example.invalid")
        self.git(root, "config", "user.name", "ZION Test")
        (root / "tracked.txt").write_text("zion\n", encoding="utf-8")
        self.git(root, "add", "tracked.txt")
        self.git(root, "commit", "-m", "initial")

    def run_check(
        self,
        root: Path,
        *,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        for name in FORBIDDEN_GIT_ENV:
            env.pop(name, None)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [
                sys.executable,
                "-I",
                str(SCRIPT),
                "--root",
                str(root),
            ],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_clean_local_git_state_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)

            result = self.run_check(root)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("git release boundary: OK", result.stdout)

    def test_active_local_hook_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            hooks = Path(
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(root),
                        "rev-parse",
                        "--git-path",
                        "hooks",
                    ],
                    text=True,
                    capture_output=True,
                    check=True,
                ).stdout.strip()
            )
            if not hooks.is_absolute():
                hooks = root / hooks
            hooks.mkdir(parents=True, exist_ok=True)
            hook = hooks / "post-checkout"
            hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            hook.chmod(0o700)

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("active local Git hooks", result.stderr)

    def test_custom_hooks_path_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            self.git(root, "config", "core.hooksPath", "/tmp/zion-hooks")

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("core.hooksPath is configured", result.stderr)

    def test_replace_ref_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            first = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()

            (root / "tracked.txt").write_text("second\n", encoding="utf-8")
            self.git(root, "add", "tracked.txt")
            self.git(root, "commit", "-m", "second")
            second = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()

            self.git(root, "replace", second, first)

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Git replace refs", result.stderr)

    def test_url_rewrite_config_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            self.git(
                root,
                "config",
                "url.https://attacker.invalid/.insteadOf",
                "https://github.com/",
            )

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("url.*.insteadOf", result.stderr)

    def test_remote_uploadpack_override_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            self.git(
                root,
                "config",
                "remote.origin.uploadpack",
                "/tmp/fake-upload-pack",
            )

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("remote.origin.uploadpack", result.stderr)

    def test_config_parameters_environment_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)

            result = self.run_check(
                root,
                extra_env={
                    "GIT_CONFIG_PARAMETERS": (
                        "'core.hooksPath=/tmp/zion-hooks'"
                    )
                },
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("GIT_CONFIG_PARAMETERS", result.stderr)

    def test_forbidden_git_environment_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)

            result = self.run_check(
                root,
                extra_env={"GIT_SSH_COMMAND": "ssh -F /tmp/attacker"},
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("GIT_SSH_COMMAND", result.stderr)


if __name__ == "__main__":
    unittest.main()
