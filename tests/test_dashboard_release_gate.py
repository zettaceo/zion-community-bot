from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class DashboardReleaseGateTests(unittest.TestCase):
    def test_dashboard_bootstrap_is_pinned_to_approved_release(self) -> None:
        text = (ROOT / "scripts" / "apply-dashboard.sh").read_text(
            encoding="utf-8"
        )

        required = (
            "ZION_DEPLOY_COMMIT",
            "ZION_GITHUB_GATES_PROVEN",
            'LOCAL_PROD_BRANCH="zion-v1-prod"',
            'APPROVED_REF="origin/zion-v1"',
            "zettaceo/zion-community-bot",
            "ls-remote --exit-code origin",
            "check-git-release-boundary.py",
            "status --porcelain --untracked-files=all",
            'RUNTIME_DIR="$RUNTIME_BASE/$EXPECTED"',
            "release-sha.txt",
            "ZION_VALIDATION_PYTHON",
            "zion.service",
            "trap rollback ERR",
        )
        for value in required:
            self.assertIn(value, text)

        self.assertIn(
            "dashboard já está instalado; atualizações devem passar "
            "pelo release controlado principal",
            text,
        )

    def test_dashboard_bootstrap_revalidates_before_sudo(self) -> None:
        text = (ROOT / "scripts" / "apply-dashboard.sh").read_text(
            encoding="utf-8"
        )

        revalidation = text.index(
            "[5/8] Revalidando inputs imediatamente antes do sudo"
        )
        first_install = text.index(
            "sudo /usr/bin/install",
            revalidation,
        )
        self.assertGreater(first_install, revalidation)
        self.assertIn(
            "HEAD mudou durante o bootstrap do dashboard",
            text[revalidation:first_install],
        )
        self.assertIn(
            "worktree mudou durante o bootstrap do dashboard",
            text[revalidation:first_install],
        )
        self.assertIn(
            "runtime/current mudou durante o bootstrap do dashboard",
            text[revalidation:first_install],
        )


if __name__ == "__main__":
    unittest.main()
