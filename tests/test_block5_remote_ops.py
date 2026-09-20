from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class Block5RemoteOperationsTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_remote_access_preflight_is_read_only_and_strict(self) -> None:
        text = self.read("scripts/remote-access-preflight.sh")

        self.assertIn("set -uo pipefail", text)
        self.assertIn("--report-only", text)
        self.assertIn("authorized_keys", text)
        self.assertIn("sshd -T", text)
        self.assertIn("100.64.0.0/10", text)
        self.assertIn("router/NAT", text)
        self.assertIn("No configuration was changed.", text)

        forbidden = (
            "tailscale up",
            "systemctl restart",
            "systemctl stop",
            "systemctl start",
            "sudo /usr/bin/install",
            "sudo /usr/bin/systemctl",
            "ufw ",
            "iptables ",
            "nft add",
            "git pull",
            "git merge",
            "git reset",
        )
        for value in forbidden:
            self.assertNotIn(value, text)

    def test_remote_access_preflight_report_only_and_strict_exit(self) -> None:
        script = ROOT / "scripts" / "remote-access-preflight.sh"
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["HOME"] = tmp
            env["ZION_SSH_DIR"] = str(Path(tmp) / "missing-ssh")
            env["ZION_AUTHORIZED_KEYS"] = str(
                Path(tmp) / "missing-ssh" / "authorized_keys"
            )
            env["ZION_SSHD_DROPIN"] = str(
                Path(tmp) / "missing-zion-sshd.conf"
            )
            env["ZION_REMOTE_USER"] = os.environ.get("USER", "runner")

            report = subprocess.run(
                ["bash", str(script), "--report-only"],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(report.returncode, 0)
            self.assertIn("No configuration was changed.", report.stdout)

            strict = subprocess.run(
                ["bash", str(script)],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(strict.returncode, 2)

    def test_authoritative_sshd_template_is_key_only_and_no_forwarding(
        self,
    ) -> None:
        text = self.read("ops/sshd/99-zion-remote.conf")

        required = (
            "PermitRootLogin no",
            "PubkeyAuthentication yes",
            "AuthenticationMethods publickey",
            "PasswordAuthentication no",
            "KbdInteractiveAuthentication no",
            "PermitEmptyPasswords no",
            "StrictModes yes",
            "AuthorizedKeysFile .ssh/authorized_keys",
            "AllowUsers zetta",
            "AllowAgentForwarding no",
            "AllowTcpForwarding no",
            "AllowStreamLocalForwarding no",
            "X11Forwarding no",
            "GatewayPorts no",
            "PermitTunnel no",
            "PermitUserEnvironment no",
        )
        for value in required:
            self.assertIn(value, text)

    def test_ssh_hardening_installer_is_guarded_and_reload_only(self) -> None:
        text = self.read("scripts/apply-ssh-hardening.sh")

        self.assertIn("ZION_REMOTE_ACCESS_PROVEN", text)
        self.assertIn("ZION_HOSTKEY_PROVEN", text)
        self.assertIn("ZION_PHYSICAL_CONSOLE", text)
        self.assertIn("100.64.0.0/10", text)
        self.assertIn("fd7a:115c:a1e0::/48", text)
        self.assertIn("/usr/sbin/sshd -t", text)
        self.assertIn("systemctl reload", text)
        self.assertIn("trap rollback ERR", text)
        self.assertIn("MANTENHA ESTA SESSÃO ABERTA", text)

        self.assertNotIn("systemctl restart", text)
        self.assertNotIn("systemctl stop", text)
        self.assertNotIn("reboot", text)
        self.assertNotIn("ufw ", text)
        self.assertNotIn("iptables ", text)
        self.assertNotIn("tailscale up", text)

    def test_deployment_preflight_is_commit_pinned_and_read_only(self) -> None:
        text = self.read("scripts/deployment-preflight.sh")

        required = (
            "ZION_DEPLOY_COMMIT",
            "^[0-9a-fA-F]{40}$",
            "origin/zion-v1",
            "zettaceo/zion-community-bot",
            "ls-remote --exit-code origin",
            "zion-v1-prod",
            "merge-base --is-ancestor",
            "ZION_GITHUB_GATES_PROVEN",
            "ZION_REMOTE_NETWORK_PROVEN",
            "actions\\.runner\\.",
            "Runner\\.Listener",
            "remote-access-preflight.sh",
            "No production file was modified.",
        )
        for value in required:
            self.assertIn(value, text)

        forbidden = (
            "git fetch",
            "git pull",
            "git merge ",
            "git reset",
            "git checkout",
            "git switch",
            "systemctl stop",
            "systemctl start",
            "systemctl restart",
            "sudo ",
        )
        for value in forbidden:
            self.assertNotIn(value, text)

    def test_deployment_preflight_report_only_does_not_require_host(
        self,
    ) -> None:
        script = ROOT / "scripts" / "deployment-preflight.sh"
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["ZION_PROD_ROOT"] = str(Path(tmp) / "not-a-repo")
            env["ZION_DEPLOY_COMMIT"] = "0" * 40
            env["ZION_REMOTE_USER"] = os.environ.get("USER", "runner")

            result = subprocess.run(
                ["bash", str(script), "--report-only"],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0)
            self.assertIn("No production file was modified.", result.stdout)

    def test_approved_release_verifier_uses_temporary_detached_worktree(
        self,
    ) -> None:
        text = self.read("scripts/verify-approved-release.sh")

        required = (
            "ZION_DEPLOY_COMMIT",
            "origin/zion-v1",
            "zettaceo/zion-community-bot",
            "ls-remote --exit-code origin",
            "ZION_GITHUB_GATES_PROVEN",
            "worktree add --detach",
            "worktree remove --force",
            "predeploy-v11.sh",
            "ZION_EXPECTED_COMMIT",
            "ZION_RUNTIME_PYTHON",
            "No production service was stopped/restarted.",
        )
        for value in required:
            self.assertIn(value, text)

        forbidden = (
            "systemctl stop",
            "systemctl start",
            "systemctl restart",
            "git reset",
            "git merge ",
            "git checkout",
            "git switch",
            "sudo ",
        )
        for value in forbidden:
            self.assertNotIn(value, text)

    def test_predeploy_requires_exact_approved_release(self) -> None:
        text = self.read("scripts/predeploy-v11.sh")

        self.assertIn("ZION_EXPECTED_COMMIT", text)
        self.assertIn('APPROVED_REF="origin/zion-v1"', text)
        self.assertNotIn("ZION_APPROVED_REF:-", text)
        self.assertIn('HEAD_SHA" != "$EXPECTED_COMMIT', text)
        self.assertIn('APPROVED_SHA" != "$EXPECTED_COMMIT', text)
        self.assertIn("ZION_VALIDATION_PYTHON", text)
        self.assertIn("Nenhum serviço foi parado/reiniciado.", text)

        self.assertNotIn("systemctl stop", text)
        self.assertNotIn("systemctl start", text)
        self.assertNotIn("systemctl restart", text)

    def test_predeploy_requires_private_zetta_owned_env(self) -> None:
        text = self.read("scripts/predeploy-v11.sh")

        self.assertIn('env_path.owner() != "zetta"', text)
        self.assertIn("production .env owner must be zetta", text)
        self.assertIn("mode & 0o077", text)

    def test_deployment_preflight_fixes_local_production_branch(self) -> None:
        text = self.read("scripts/deployment-preflight.sh")

        self.assertIn('LOCAL_PROD_BRANCH="zion-v1-prod"', text)
        self.assertNotIn("ZION_LOCAL_PROD_BRANCH", text)

    def test_apply_deploy_requires_exact_production_sha_and_rollback_metadata(
        self,
    ) -> None:
        text = self.read("scripts/apply-zion-v1.sh")

        self.assertIn("ZION_EXPECTED_COMMIT", text)
        self.assertIn('APPROVED_REF="origin/zion-v1"', text)
        self.assertNotIn("ZION_APPROVED_REF:-", text)
        self.assertIn('LOCAL_PROD_BRANCH="zion-v1-prod"', text)
        self.assertIn("ZION_PREVIOUS_COMMIT", text)
        self.assertIn("ZION_GITHUB_GATES_PROVEN", text)
        self.assertIn("zettaceo/zion-community-bot", text)
        self.assertIn("ls-remote --exit-code origin", text)
        self.assertIn("rollback-head.txt", text)
        self.assertIn("approved-sha.txt", text)
        self.assertIn('CURRENT_HEAD" != "$EXPECTED_COMMIT', text)
        self.assertIn('APPROVED_SHA" != "$EXPECTED_COMMIT', text)

    def test_remote_runbook_requires_out_of_band_host_key_pinning(self) -> None:
        text = self.read("docs/REMOTE-ACCESS.md")

        self.assertIn("out-of-band", text)
        self.assertIn("StrictHostKeyChecking yes", text)
        self.assertNotIn("StrictHostKeyChecking accept-new", text)
        self.assertIn("second independent session", text)
        self.assertIn("Do not treat `ssh-keyscan` by itself as identity proof", text)

    def test_deployment_model_rejects_unpinned_and_self_hosted_release(
        self,
    ) -> None:
        text = self.read("docs/DEPLOYMENT-MODEL.md")

        self.assertIn("full 40-character Git commit SHA", text)
        self.assertIn("origin/zion-v1", text)
        self.assertIn("git merge --ff-only", text)
        self.assertIn("Do not install a GitHub Actions self-hosted runner", text)
        self.assertIn("ZION_GITHUB_GATES_PROVEN=YES", text)
        self.assertIn("ZION_REMOTE_NETWORK_PROVEN=YES", text)

    def test_github_gate_document_does_not_claim_protection_is_applied(
        self,
    ) -> None:
        text = self.read("docs/GITHUB-DEPLOY-GATES.md")

        self.assertIn("repository-admin action required", text)
        self.assertIn("require a pull request", text)
        self.assertIn("require GitHub Actions status check `validate`", text)
        self.assertIn("block force pushes", text)
        self.assertIn("block branch deletion", text)

    def test_ci_remains_github_hosted_and_read_only(self) -> None:
        text = self.read(".github/workflows/ci.yml")

        self.assertIn("runs-on: ubuntu-latest", text)
        self.assertNotIn("runs-on: self-hosted", text)
        self.assertIn("permissions:\n  contents: read", text)


if __name__ == "__main__":
    unittest.main()
