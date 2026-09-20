from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class V11ReleaseGateTests(unittest.TestCase):
    def read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_deployment_preflight_separates_candidate_and_production_roots(
        self,
    ) -> None:
        text = self.read("scripts/deployment-preflight.sh")

        self.assertIn("SCRIPT_ROOT=", text)
        self.assertIn("BASH_SOURCE[0]", text)
        self.assertIn(
            'candidate_head="$(git -C "$SCRIPT_ROOT" rev-parse HEAD',
            text,
        )
        self.assertIn('candidate_head" == "$EXPECTED"', text)
        self.assertIn(
            '$SCRIPT_ROOT/scripts/remote-access-preflight.sh',
            text,
        )
        self.assertIn('$SCRIPT_ROOT/scripts/predeploy-v11.sh', text)
        self.assertNotIn(
            '$ROOT/scripts/remote-access-preflight.sh',
            text,
        )
        self.assertNotIn('$ROOT/scripts/predeploy-v11.sh', text)

    def test_strict_deployment_preflight_requires_healthy_current_service(
        self,
    ) -> None:
        text = self.read("scripts/deployment-preflight.sh")

        self.assertIn(
            'fail "zion.service is not active; treat existing outage before release"',
            text,
        )
        self.assertIn('elif [[ "$REPORT_ONLY" == true ]]', text)

    def test_deployment_preflight_rejects_hardlinked_env(self) -> None:
        text = self.read("scripts/deployment-preflight.sh")

        self.assertIn("env_links=", text)
        self.assertIn('[[ "$env_links" == "1" ]]', text)
        self.assertIn(".env hard-link count=", text)

    def test_predeploy_models_production_defaults_from_production_root(
        self,
    ) -> None:
        text = self.read("scripts/predeploy-v11.sh")

        self.assertIn('PROD_ROOT="$PROD_ROOT"', text)
        self.assertIn('CANDIDATE_ROOT="$ROOT"', text)
        self.assertIn(
            'os.environ.setdefault("ZION_DB_PATH", str(prod_root / "zion.db"))',
            text,
        )
        self.assertIn('"ZION_STATE_FILE"', text)
        self.assertIn('"ZION_KNOWLEDGE_DIR"', text)
        self.assertIn('"ZION_LOG_PATH"', text)

    def test_predeploy_uses_candidate_knowledge_for_default_repo_path(
        self,
    ) -> None:
        text = self.read("scripts/predeploy-v11.sh")

        self.assertIn(
            "if configured_knowledge == default_prod_knowledge:",
            text,
        )
        self.assertIn(
            'knowledge_path = candidate_root / "knowledge"',
            text,
        )
        self.assertIn("knowledge = KnowledgeBase(knowledge_path)", text)

    def test_predeploy_requires_active_production(self) -> None:
        text = self.read("scripts/predeploy-v11.sh")

        self.assertIn(
            'if ! /usr/bin/systemctl is-active --quiet "$SERVICE"; then',
            text,
        )
        self.assertIn("trate como incidente antes do release", text)

    def test_predeploy_rejects_dashboard_db_divergence(self) -> None:
        text = self.read("scripts/predeploy-v11.sh")

        self.assertIn("ZION_DASHBOARD_DB_PATH", text)
        self.assertIn("DASHBOARD_DB_PATH", text)
        self.assertIn("PROD_DB_PATH", text)
        self.assertIn(
            'if [[ "$DASHBOARD_DB_PATH" != "$PROD_DB_PATH" ]]',
            text,
        )
        self.assertIn("dashboard aponta para DB diferente do bot", text)

    def test_predeploy_rejects_hardlinked_env(self) -> None:
        text = self.read("scripts/predeploy-v11.sh")

        self.assertIn("info.st_nlink != 1", text)
        self.assertIn("production .env must not have hard links", text)

    def test_apply_requires_zetta_and_single_link_env(self) -> None:
        text = self.read("scripts/apply-zion-v1.sh")

        self.assertIn('EXPECTED_USER="zetta"', text)
        self.assertIn(
            'if [[ "$(id -un)" != "$EXPECTED_USER" ]]',
            text,
        )
        self.assertIn("info.st_nlink != 1", text)
        self.assertIn(".env não pode possuir hard links", text)

    def test_apply_backups_live_outside_bot_writable_paths(self) -> None:
        text = self.read("scripts/apply-zion-v1.sh")
        unit = self.read("systemd/zion.service")

        backup_path = (
            "/home/zetta/.local/share/"
            "zion-community-bot/deploy-backups"
        )
        self.assertIn(f'BACKUP_DIR="{backup_path}"', text)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertNotIn(
            "ReadWritePaths=/home/zetta/.local/share/zion-community-bot",
            unit,
        )
        self.assertNotIn(
            "ReadWritePaths=/home/zetta/.local/share",
            unit,
        )

    def test_apply_backup_directory_is_private_and_not_symlinked(self) -> None:
        text = self.read("scripts/apply-zion-v1.sh")

        self.assertIn('if [[ -L "$BACKUP_DIR" ]]', text)
        self.assertIn('chmod 700 "$BACKUP_DIR"', text)
        self.assertIn("stat -c '%U' \"$BACKUP_DIR\"", text)
        self.assertIn("$BASHPID", text)

    def test_dashboard_installer_refuses_config_divergence(self) -> None:
        text = self.read("scripts/apply-dashboard.sh")

        self.assertIn(
            "zion-dashboard.service DB path diverge from bot config",
            text,
        )
        self.assertIn(
            "zion-dashboard.service Wi-Fi interface diverge from bot config",
            text,
        )

    def test_first_upgrade_bootstraps_gates_from_detached_candidate(
        self,
    ) -> None:
        text = self.read("docs/V1.1-FIRST-UPGRADE.md")

        self.assertIn(
            'git worktree add --detach "$CANDIDATE_ROOT" "$ZION_DEPLOY_COMMIT"',
            text,
        )
        self.assertIn(
            '"$CANDIDATE_ROOT/scripts/deployment-preflight.sh"',
            text,
        )
        self.assertIn(
            '"$CANDIDATE_ROOT/scripts/verify-approved-release.sh"',
            text,
        )
        self.assertIn("fast-forward", text)
        self.assertIn("zion-v1-prod", text)

    def test_first_upgrade_never_authorizes_production_merge(self) -> None:
        text = self.read("docs/V1.1-FIRST-UPGRADE.md")

        self.assertIn(
            "This document does **not** authorize merging PR #2.",
            text,
        )
        self.assertIn("protection/ruleset is enabled and verified", text)

    def test_release_audit_records_external_gates_without_claiming_them(
        self,
    ) -> None:
        text = self.read("docs/V1.1-RELEASE-AUDIT.md")

        self.assertIn("currently reports", text)
        self.assertIn("unprotected", text)
        self.assertIn(
            "No repository CI result is allowed to claim those gates have passed.",
            text,
        )

    def test_deployment_preflight_report_only_remains_read_only(self) -> None:
        script = ROOT / "scripts" / "deployment-preflight.sh"
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["ZION_PROD_ROOT"] = str(Path(tmp) / "old-production")
            env["ZION_REMOTE_USER"] = os.environ.get("USER", "runner")
            env["ZION_DEPLOY_COMMIT"] = "0" * 40

            result = subprocess.run(
                ["bash", str(script), "--report-only"],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn(
                "No production file was modified.",
                result.stdout,
            )


if __name__ == "__main__":
    unittest.main()
