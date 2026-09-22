from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class SSHFirewallContractTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_nft_policy_changes_only_tcp_22(self) -> None:
        text = self.read("ops/nftables/zion-ssh-private.nft")

        self.assertIn("table inet zion_ssh_guard", text)
        self.assertIn('iifname "lo" tcp dport 22 accept', text)
        self.assertIn(
            'iifname "tailscale0" tcp dport 22 accept',
            text,
        )
        self.assertIn("tcp dport 22 counter drop", text)
        self.assertIn("policy accept", text)
        self.assertNotIn("policy drop", text)
        self.assertNotIn("udp dport", text)

        loopback = text.index('iifname "lo" tcp dport 22 accept')
        tailscale = text.index(
            'iifname "tailscale0" tcp dport 22 accept'
        )
        drop = text.index("tcp dport 22 counter drop")
        self.assertLess(loopback, drop)
        self.assertLess(tailscale, drop)

    def test_validation_includes_firewall_runtime_helper(self) -> None:
        text = self.read("scripts/validate.sh")
        self.assertIn(
            "scripts/*.sh ops/nftables/*.sh",
            text,
        )

    def test_runtime_helper_never_flushes_unrelated_ruleset(self) -> None:
        text = self.read(
            "ops/nftables/zion-ssh-firewall-runtime.sh"
        )

        self.assertIn('TABLE_NAME="zion_ssh_guard"', text)
        self.assertIn('NFT="/usr/sbin/nft"', text)
        self.assertIn(
            'delete table "$TABLE_FAMILY" "$TABLE_NAME"',
            text,
        )
        self.assertNotIn("flush ruleset", text)
        self.assertNotIn("delete table inet filter", text)

    def test_installer_requires_explicit_safety_attestations(self) -> None:
        text = self.read("scripts/apply-ssh-firewall.sh")

        for variable in (
            "ZION_EXPECTED_COMMIT",
            "ZION_FIREWALL_CHANGE_AUTHORIZED",
            "ZION_REMOTE_ACCESS_PROVEN",
            "ZION_SECOND_SSH_PROVEN",
        ):
            with self.subTest(variable=variable):
                self.assertIn(variable, text)

        self.assertIn("check-git-release-boundary.py", text)
        self.assertIn("origin/zion-v1.1-dev", text)
        self.assertIn("status --porcelain --untracked-files=all", text)
        self.assertIn('candidate_head" != "$EXPECTED_COMMIT"', text)
        self.assertIn("sudo -n /usr/bin/true", text)
        self.assertIn("100.64.0.0/10", text)
        self.assertIn("fd7a:115c:a1e0::/48", text)
        self.assertIn("%U:%G:%a:%h", text)
        self.assertIn("root:root:$expected_mode:1", text)
        self.assertIn("root:root:600:1", text)
        self.assertIn("before_pid=", text)
        self.assertIn("after_pid=", text)
        self.assertIn("before_restarts=", text)
        self.assertIn("after_restarts=", text)
        self.assertIn("TERCEIRA sessão SSH", text)

    def test_installer_rolls_back_only_dedicated_guard(self) -> None:
        text = self.read("scripts/apply-ssh-firewall.sh")

        self.assertIn("rollback()", text)
        self.assertIn(
            'zion-ssh-firewall-runtime remove',
            text,
        )
        self.assertIn('rm -f "$UNIT_DST" "$RUNTIME_DST" "$RULESET_DST"', text)
        self.assertNotIn("nft flush ruleset", text)
        self.assertNotIn("iptables -F", text)
        self.assertNotIn("ip6tables -F", text)

    def test_systemd_unit_is_persistent_and_ordered_before_sshd(self) -> None:
        text = self.read("systemd/zion-ssh-firewall.service")

        self.assertIn("After=nftables.service tailscaled.service", text)
        self.assertIn("Before=ssh.service sshd.service", text)
        self.assertIn("Wants=tailscaled.service", text)
        self.assertIn("RemainAfterExit=yes", text)
        self.assertIn(
            "ExecStart=/usr/local/sbin/zion-ssh-firewall-runtime apply",
            text,
        )
        self.assertIn(
            "ExecStop=/usr/local/sbin/zion-ssh-firewall-runtime remove",
            text,
        )
        self.assertIn("WantedBy=multi-user.target", text)

    def test_strict_remote_preflight_requires_firewall_guard(self) -> None:
        text = self.read("scripts/remote-access-preflight.sh")

        self.assertIn("[7/8] Host SSH firewall", text)
        self.assertIn("zion_ssh_guard", text)
        self.assertIn(
            "dedicated Tailscale-only SSH nftables guard not proven",
            text,
        )
        self.assertIn(
            "zion-ssh-firewall.service active and enabled",
            text,
        )

    def test_firewall_helpers_are_executable_in_git_index(self) -> None:
        expected = {
            "ops/nftables/zion-ssh-firewall-runtime.sh",
            "scripts/apply-ssh-firewall.sh",
            "scripts/rollback-ssh-firewall.sh",
        }
        output = subprocess.check_output(
            ["/usr/bin/git", "ls-files", "--stage", "--", *sorted(expected)],
            cwd=ROOT,
            text=True,
        )

        modes = {}
        for line in output.splitlines():
            meta, path = line.split("\t", 1)
            modes[path] = meta.split()[0]

        self.assertEqual(set(modes), expected)
        for path in sorted(expected):
            with self.subTest(path=path):
                self.assertEqual(modes[path], "100755")

    def test_rollback_is_candidate_pinned_and_dedicated(self) -> None:
        text = self.read("scripts/rollback-ssh-firewall.sh")

        self.assertIn("ZION_FIREWALL_ROLLBACK_AUTHORIZED", text)
        self.assertIn("ZION_EXPECTED_COMMIT", text)
        self.assertIn("check-git-release-boundary.py", text)
        self.assertIn("origin/zion-v1.1-dev", text)
        self.assertIn("zion_ssh_guard", text)
        self.assertIn('rm -f "$UNIT_DST" "$RUNTIME_DST" "$RULESET_DST"', text)
        self.assertNotIn("flush ruleset", text)
        self.assertNotIn("iptables -F", text)
        self.assertIn("before_pid=", text)
        self.assertIn("after_pid=", text)

    def test_runbook_requires_third_session_after_firewall(self) -> None:
        text = self.read("docs/REMOTE-ACCESS.md")

        self.assertIn(
            "Phase 7 — reviewed host SSH firewall",
            text,
        )
        self.assertIn(
            "ZION_EXPECTED_COMMIT=<reviewed-40-character-zion-v1.1-dev-sha>",
            text,
        )
        self.assertIn(
            "ZION_FIREWALL_CHANGE_AUTHORIZED=YES",
            text,
        )
        self.assertIn(
            "open a **third** independent SSH session",
            text,
        )
        self.assertIn(
            "ZION_FIREWALL_ROLLBACK_AUTHORIZED=YES",
            text,
        )
        self.assertIn(
            "Router/NAT and Tailnet policy are not inferred "
            "from the host firewall",
            text,
        )


if __name__ == "__main__":
    unittest.main()
