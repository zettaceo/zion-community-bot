from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts" / "check-release-attestations.sh"


class ReleaseAttestationWaiverTests(unittest.TestCase):
    def run_checker(self, **values: str):
        env = {
            "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        }
        env.update(values)
        return subprocess.run(
            ["/usr/bin/bash", str(CHECKER)],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_fully_proven_path_passes_without_waiver(self) -> None:
        result = self.run_checker(
            ZION_GITHUB_GATES_PROVEN="YES",
            ZION_REMOTE_NETWORK_PROVEN="YES",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("github_governance=PROVEN", result.stdout)
        self.assertIn("remote_network=PROVEN", result.stdout)
        self.assertIn("external_waiver=NONE", result.stdout)

    def test_explicit_initial_go_live_waiver_passes(self) -> None:
        result = self.run_checker(
            ZION_GITHUB_GATES_WAIVED="YES",
            ZION_REMOTE_NETWORK_WAIVED="YES",
            ZION_INITIAL_GO_LIVE_WAIVER="YES",
            ZION_EXTERNAL_WAIVER_REASON=(
                "temporary initial go-live; external controls deferred"
            ),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("github_governance=WAIVED", result.stdout)
        self.assertIn("remote_network=WAIVED", result.stdout)
        self.assertIn("external_waiver=ACTIVE", result.stdout)

    def test_waiver_without_operator_ack_fails_closed(self) -> None:
        result = self.run_checker(
            ZION_GITHUB_GATES_WAIVED="YES",
            ZION_REMOTE_NETWORK_WAIVED="YES",
            ZION_EXTERNAL_WAIVER_REASON="synthetic temporary reason",
        )
        self.assertNotEqual(result.returncode, 0)

    def test_waiver_without_reason_fails_closed(self) -> None:
        result = self.run_checker(
            ZION_GITHUB_GATES_WAIVED="YES",
            ZION_REMOTE_NETWORK_WAIVED="YES",
            ZION_INITIAL_GO_LIVE_WAIVER="YES",
        )
        self.assertNotEqual(result.returncode, 0)

    def test_proven_and_waived_same_gate_is_rejected(self) -> None:
        result = self.run_checker(
            ZION_GITHUB_GATES_PROVEN="YES",
            ZION_GITHUB_GATES_WAIVED="YES",
            ZION_REMOTE_NETWORK_PROVEN="YES",
            ZION_INITIAL_GO_LIVE_WAIVER="YES",
            ZION_EXTERNAL_WAIVER_REASON="synthetic conflict",
        )
        self.assertNotEqual(result.returncode, 0)

    def test_unresolved_gate_without_proof_or_waiver_fails(self) -> None:
        result = self.run_checker(
            ZION_GITHUB_GATES_PROVEN="YES",
        )
        self.assertNotEqual(result.returncode, 0)

    def test_waiver_reason_must_be_single_line_and_bounded(self) -> None:
        multiline = self.run_checker(
            ZION_GITHUB_GATES_WAIVED="YES",
            ZION_REMOTE_NETWORK_WAIVED="YES",
            ZION_INITIAL_GO_LIVE_WAIVER="YES",
            ZION_EXTERNAL_WAIVER_REASON="line one\nline two",
        )
        self.assertNotEqual(multiline.returncode, 0)

        oversized = self.run_checker(
            ZION_GITHUB_GATES_WAIVED="YES",
            ZION_REMOTE_NETWORK_WAIVED="YES",
            ZION_INITIAL_GO_LIVE_WAIVER="YES",
            ZION_EXTERNAL_WAIVER_REASON="x" * 161,
        )
        self.assertNotEqual(oversized.returncode, 0)

    def test_checker_is_executable_in_git_index(self) -> None:
        output = subprocess.check_output(
            [
                "/usr/bin/git",
                "ls-files",
                "--stage",
                "--",
                "scripts/check-release-attestations.sh",
            ],
            cwd=ROOT,
            text=True,
        )
        mode = output.split()[0]
        self.assertEqual(mode, "100755")


if __name__ == "__main__":
    unittest.main()
