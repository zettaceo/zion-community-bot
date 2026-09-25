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
    "GIT_SSH_VARIANT",
    "GIT_ASKPASS",
    "GIT_PROXY_COMMAND",
    "GIT_EXEC_PATH",
    "GIT_SSL_NO_VERIFY",
    "GIT_SSL_CAINFO",
    "GIT_SSL_CAPATH",
    "SSH_ASKPASS",
    "SSH_ASKPASS_REQUIRE",
)


class GitReleaseBoundaryTests(unittest.TestCase):
    def git(self, root: Path, *args: str) -> None:
        subprocess.run(
            ["git", "-C", str(root), *args],
            text=True,
            capture_output=True,
            check=True,
        )

    def git_path(self, root: Path, relative: str) -> Path:
        path = Path(
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "rev-parse",
                    "--git-path",
                    relative,
                ],
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
        )
        if not path.is_absolute():
            path = root / path
        return path

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
            hooks = self.git_path(root, "hooks")
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

    def test_local_info_exclude_rule_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            exclude = self.git_path(root, "info/exclude")
            exclude.parent.mkdir(parents=True, exist_ok=True)
            with exclude.open("a", encoding="utf-8") as handle:
                handle.write("shadow.py\n")

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("local Git exclude rules", result.stderr)

    def test_local_info_attribute_rule_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            attributes = self.git_path(root, "info/attributes")
            attributes.parent.mkdir(parents=True, exist_ok=True)
            attributes.write_text(
                "tracked.txt filter=attacker\n",
                encoding="utf-8",
            )

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("local Git attribute rules", result.stderr)

    def test_core_excludes_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            self.git(
                root,
                "config",
                "core.excludesFile",
                "/tmp/zion-global-ignore",
            )

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("core.excludesFile is configured", result.stderr)

    def test_core_fsmonitor_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            self.git(
                root,
                "config",
                "core.fsmonitor",
                "/tmp/zion-fsmonitor",
            )

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("core.fsmonitor is configured", result.stderr)

    def test_core_ssh_command_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            self.git(
                root,
                "config",
                "core.sshCommand",
                "/tmp/zion-fake-ssh",
            )

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("core.sshCommand is configured", result.stderr)

    def test_absolute_credential_helper_execution_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            marker = root / "credential-helper-ran"
            helper = root / "helper.sh"
            helper.write_text(
                "#!/bin/sh\n"
                f"printf x > {str(marker)!r}\n"
                "exit 1\n",
                encoding="utf-8",
            )
            helper.chmod(0o700)
            self.git(root, "config", "credential.helper", str(helper))

            env = os.environ.copy()
            env["GIT_TERMINAL_PROMPT"] = "0"
            subprocess.run(
                ["git", "-C", str(root), "credential", "fill"],
                input="protocol=https\nhost=github.com\n\n",
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertTrue(marker.is_file())

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe credential.helper", result.stderr)

    def test_shell_credential_helper_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            self.git(
                root,
                "config",
                "credential.helper",
                "!printf attacker >/tmp/zion-credential-helper-test",
            )

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe credential.helper", result.stderr)

    def test_core_askpass_config_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            self.git(
                root,
                "config",
                "core.askPass",
                "/tmp/zion-askpass",
            )

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("core.askPass is configured", result.stderr)

    def test_named_system_credential_helper_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            self.git(
                root,
                "config",
                "credential.helper",
                "cache --timeout=60",
            )

            result = self.run_check(root)

            self.assertEqual(result.returncode, 0, result.stderr)

    def test_ssh_askpass_environment_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)

            result = self.run_check(
                root,
                extra_env={"SSH_ASKPASS": "/tmp/zion-ssh-askpass"},
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SSH_ASKPASS", result.stderr)

    def test_ssh_variant_config_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            self.git(root, "config", "ssh.variant", "plink")

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ssh.variant is configured", result.stderr)

    def test_git_ssh_variant_environment_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)

            result = self.run_check(
                root,
                extra_env={"GIT_SSH_VARIANT": "plink"},
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("GIT_SSH_VARIANT", result.stderr)

    def test_http_ssl_verify_false_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            self.git(root, "config", "http.sslVerify", "false")

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("TLS verification", result.stderr)

    def test_http_ssl_verify_true_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            self.git(root, "config", "http.sslVerify", "true")

            result = self.run_check(root)

            self.assertEqual(result.returncode, 0, result.stderr)

    def test_custom_http_ca_override_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            self.git(root, "config", "http.sslCAInfo", "/tmp/custom-ca.pem")

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("custom Git HTTP CA overrides", result.stderr)

    def test_ignored_importable_bytecode_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            (root / ".gitignore").write_text(
                "*.pyc\n",
                encoding="utf-8",
            )
            self.git(root, "add", ".gitignore")
            self.git(root, "commit", "-m", "ignore bytecode")
            (root / "telegram.pyc").write_bytes(b"shadow")

            status = subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "status",
                    "--porcelain",
                    "--untracked-files=all",
                ],
                text=True,
                capture_output=True,
                check=True,
            ).stdout
            self.assertEqual(status, "")

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "ignored untracked importable code",
                result.stderr,
            )
            self.assertIn("telegram.pyc", result.stderr)

    def test_ignored_legacy_venv_code_is_not_treated_as_repo_shadowing(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            (root / ".gitignore").write_text(
                ".venv/\n",
                encoding="utf-8",
            )
            self.git(root, "add", ".gitignore")
            self.git(root, "commit", "-m", "ignore legacy venv")
            package = root / ".venv" / "lib"
            package.mkdir(parents=True)
            (package / "telegram.pyc").write_bytes(b"venv-bytecode")

            result = self.run_check(root)

            self.assertEqual(result.returncode, 0, result.stderr)

    def test_assume_unchanged_index_entry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            self.git(root, "update-index", "--assume-unchanged", "tracked.txt")
            (root / "tracked.txt").write_text(
                "tampered\n",
                encoding="utf-8",
            )

            status = subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "status",
                    "--porcelain",
                    "--untracked-files=all",
                ],
                text=True,
                capture_output=True,
                check=True,
            ).stdout
            self.assertEqual(status, "")

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "assume-unchanged/skip-worktree",
                result.stderr,
            )
            self.assertIn("tracked.txt", result.stderr)

    def test_skip_worktree_index_entry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            self.git(root, "update-index", "--skip-worktree", "tracked.txt")
            (root / "tracked.txt").write_text(
                "tampered\n",
                encoding="utf-8",
            )

            status = subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "status",
                    "--porcelain",
                    "--untracked-files=all",
                ],
                text=True,
                capture_output=True,
                check=True,
            ).stdout
            self.assertEqual(status, "")

            result = self.run_check(root)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "assume-unchanged/skip-worktree",
                result.stderr,
            )
            self.assertIn("tracked.txt", result.stderr)

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

    def test_askpass_environment_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)

            result = self.run_check(
                root,
                extra_env={"GIT_ASKPASS": "/tmp/zion-askpass"},
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("GIT_ASKPASS", result.stderr)


if __name__ == "__main__":
    unittest.main()
