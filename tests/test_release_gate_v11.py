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
            'candidate_head="$(/usr/bin/git -C "$SCRIPT_ROOT" rev-parse HEAD',
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

    def test_release_gates_reject_nonignored_untracked_files(self) -> None:
        deployment = self.read("scripts/deployment-preflight.sh")
        predeploy = self.read("scripts/predeploy-v11.sh")
        apply = self.read("scripts/apply-zion-v1.sh")
        first_upgrade = self.read("docs/V1.1-FIRST-UPGRADE.md")

        for text in (deployment, predeploy, apply, first_upgrade):
            self.assertIn(
                "status --porcelain --untracked-files=all",
                text,
            )

        self.assertIn("candidate_status=", deployment)
        self.assertIn("production_status=", deployment)
        self.assertIn("CANDIDATE_STATUS=", predeploy)
        self.assertIn("WORKTREE_STATUS=", apply)

    def test_strict_deployment_preflight_requires_healthy_current_service(
        self,
    ) -> None:
        text = self.read("scripts/deployment-preflight.sh")

        self.assertIn(
            'fail "zion.service is not active; treat existing outage before release"',
            text,
        )
        self.assertIn('elif [[ "$REPORT_ONLY" == true ]]', text)

    def test_deployment_preflight_uses_strict_env_boundary(self) -> None:
        text = self.read("scripts/deployment-preflight.sh")

        self.assertIn("scripts/check-env-boundary.py", text)
        self.assertIn('--env "$ENV_FILE"', text)
        self.assertIn('--allowlist "$SCRIPT_ROOT/.env.example"', text)
        self.assertIn('--owner "$EXPECTED_USER"', text)
        self.assertIn(
            "production .env boundary validation failed",
            text,
        )

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
        self.assertIn(
            "ReadOnlyPaths=/home/zetta/zion-community-bot",
            unit,
        )
        self.assertNotIn(
            "ReadWritePaths=/home/zetta/zion-community-bot",
            unit,
        )
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
        self.assertIn('BACKUP_REAL="$(readlink -f -- "$BACKUP_DIR"', text)
        self.assertIn(
            'if [[ "$BACKUP_REAL" != "$BACKUP_DIR" ]]',
            text,
        )

    def test_dashboard_installer_uses_isolated_runtime_and_state(self) -> None:
        text = self.read("scripts/apply-dashboard.sh")

        self.assertIn(
            'RUNTIME_BASE="/home/zetta/.local/share/zion-community-bot/runtimes"',
            text,
        )
        self.assertIn('CURRENT_RUNTIME="$RUNTIME_BASE/current"', text)
        self.assertIn('PYTHON="$CURRENT_RUNTIME/bin/python"', text)
        self.assertIn(
            'DB="$STATE_DIR/zion.db"',
            text,
        )
        self.assertIn(
            "zion-dashboard.service Wi-Fi interface diverge from bot config",
            text,
        )

    def test_remote_git_proofs_neutralize_user_ssh_config(self) -> None:
        safe_ssh = (
            "/usr/bin/ssh -F /dev/null -o BatchMode=yes "
            "-o StrictHostKeyChecking=yes -o ProxyCommand=none "
            "-o ProxyJump=none -o PermitLocalCommand=no"
        )
        for relative in (
            "scripts/deployment-preflight.sh",
            "scripts/verify-approved-release.sh",
            "scripts/apply-dashboard.sh",
        ):
            with self.subTest(relative=relative):
                text = self.read(relative)
                self.assertIn(
                    f'SAFE_GIT_SSH_COMMAND="{safe_ssh}"',
                    text,
                )
                self.assertIn(
                    '-c "core.sshCommand=$SAFE_GIT_SSH_COMMAND"',
                    text,
                )
                self.assertIn("-c ssh.variant=ssh", text)
                self.assertIn("GIT_TERMINAL_PROMPT=0", text)

        first_upgrade = self.read("docs/V1.1-FIRST-UPGRADE.md")
        self.assertIn(
            f'SAFE_GIT_SSH_COMMAND="{safe_ssh}"',
            first_upgrade,
        )
        self.assertIn(
            '-c "core.sshCommand=$SAFE_GIT_SSH_COMMAND"',
            first_upgrade,
        )
        self.assertIn("-c ssh.variant=ssh", first_upgrade)
        self.assertIn("credential.helper executável inseguro", first_upgrade)
        self.assertIn("GIT_SSL_NO_VERIFY", first_upgrade)

    def test_first_upgrade_bootstraps_gates_from_detached_candidate(
        self,
    ) -> None:
        text = self.read("docs/V1.1-FIRST-UPGRADE.md")

        self.assertIn("GIT_NO_REPLACE_OBJECTS=1", text)
        self.assertIn("core.hooksPath=/dev/null", text)
        self.assertIn(
            'worktree add --detach "$CANDIDATE_ROOT" "$ZION_DEPLOY_COMMIT"',
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

    def test_first_upgrade_prechecks_git_boundary_before_worktree_checkout(
        self,
    ) -> None:
        text = self.read("docs/V1.1-FIRST-UPGRADE.md")

        self.assertIn("BOOTSTRAP_CHECKER=", text)
        self.assertIn(
            'show "$ZION_DEPLOY_COMMIT:scripts/check-git-release-boundary.py"',
            text,
        )
        self.assertIn(
            '/usr/bin/python3 -I "$BOOTSTRAP_CHECKER" --root "$PROD_ROOT"',
            text,
        )
        self.assertIn("/usr/bin/git -c core.hooksPath=/dev/null", text)
        checker_run = text.index(
            '/usr/bin/python3 -I "$BOOTSTRAP_CHECKER" --root "$PROD_ROOT"'
        )
        worktree_add = text.index(
            'worktree add --detach "$CANDIDATE_ROOT" "$ZION_DEPLOY_COMMIT"'
        )
        self.assertLess(checker_run, worktree_add)
        self.assertIn("GIT_CONFIG_NOSYSTEM=1", text)
        self.assertIn("GIT_CONFIG_GLOBAL=/dev/null", text)

    def test_release_tree_has_no_tracked_gitattributes_before_bootstrap(
        self,
    ) -> None:
        tracked = subprocess.check_output(
            ["/usr/bin/git", "ls-files", "-z"],
            cwd=ROOT,
        ).decode("utf-8").split("\0")
        self.assertFalse(
            any(
                path == ".gitattributes" or path.endswith("/.gitattributes")
                for path in tracked
                if path
            )
        )

    def test_bootstrap_and_cutover_neutralize_git_hooks(self) -> None:
        first_upgrade = self.read("docs/V1.1-FIRST-UPGRADE.md")
        deploy_model = self.read("docs/DEPLOYMENT-MODEL.md")
        verifier = self.read("scripts/verify-approved-release.sh")

        for text in (first_upgrade, deploy_model):
            self.assertIn("GIT_NO_REPLACE_OBJECTS=1", text)
            self.assertIn("core.hooksPath=/dev/null", text)

        self.assertIn("GIT_NO_REPLACE_OBJECTS=1", verifier)
        self.assertIn("core.hooksPath=/dev/null", verifier)
        self.assertIn("worktree add --detach", verifier)

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

    def test_candidate_worktrees_reject_ignored_env_files(self) -> None:
        deployment = self.read("scripts/deployment-preflight.sh")
        predeploy = self.read("scripts/predeploy-v11.sh")

        self.assertIn('$SCRIPT_ROOT/.env', deployment)
        self.assertIn("candidate worktree must not contain an ignored .env", deployment)
        self.assertIn('$ROOT/.env', predeploy)
        self.assertIn(
            "candidate worktree não pode conter .env local ignorado",
            predeploy,
        )

    def test_python_release_runtime_is_pinned_to_312(self) -> None:
        runtime = self.read("scripts/check-runtime.py")

        self.assertIn('python_version[:2] == (3, 12)', runtime)
        self.assertIn(
            "audited ZION v1.1 runtime requires Python 3.12.x",
            runtime,
        )

    def test_env_example_covers_every_bot_config_key(self) -> None:
        import re

        config = self.read("zion/config.py")
        example = self.read(".env.example")

        configured = set(
            re.findall(
                r'(?:os\.getenv|_bool|_int|_float|_csv|_int_set|_domain_set)'
                r'\(\s*"([A-Z0-9_]+)"',
                config,
            )
        )
        allowlisted = {
            match.group(1)
            for line in example.splitlines()
            if (
                match := re.match(
                    r"^([A-Z][A-Z0-9_]*)=",
                    line,
                )
            )
        }
        self.assertFalse(configured - allowlisted)

    def test_release_runtime_is_prepared_per_exact_sha(self) -> None:
        prepare = self.read("scripts/prepare-release-runtime.sh")
        deployment = self.read("scripts/deployment-preflight.sh")
        predeploy = self.read("scripts/predeploy-v11.sh")
        apply = self.read("scripts/apply-zion-v1.sh")

        self.assertIn('RUNTIME_DIR="$RUNTIME_BASE/$EXPECTED"', prepare)
        self.assertIn("runtime/current was NOT switched", prepare)
        self.assertIn("python3", prepare)
        self.assertIn("-m venv", prepare)
        self.assertIn("-r \"$ROOT/requirements.lock\"", prepare)
        self.assertIn("pip --isolated install", prepare)
        self.assertIn("--no-deps", prepare)
        self.assertIn("--require-hashes", prepare)
        self.assertIn("--only-binary=:all:", prepare)
        self.assertIn("--index-url https://pypi.org/simple", prepare)
        self.assertIn('chmod -R a-w "$TMP_RUNTIME"', prepare)

        self.assertIn(
            'RUNTIME_DIR="$RUNTIME_BASE/$EXPECTED"',
            deployment,
        )
        self.assertIn(
            'RUNTIME_BASE/$EXPECTED_COMMIT/bin/python',
            predeploy,
        )
        self.assertIn(
            'RUNTIME_DIR="$RUNTIME_BASE/$EXPECTED_COMMIT"',
            apply,
        )
        self.assertIn(
            'mv -Tf "$TMP_CURRENT" "$CURRENT_RUNTIME"',
            apply,
        )

    def test_predeploy_validates_installed_dashboard_before_downtime(
        self,
    ) -> None:
        text = self.read("scripts/predeploy-v11.sh")

        self.assertIn("DASHBOARD_LOAD_STATE", text)
        self.assertIn(
            'systemd-analyze verify "$ROOT/systemd/zion-dashboard.service"',
            text,
        )
        self.assertIn("dashboard_systemd_unit=OK", text)

    def test_runtime_current_accepts_only_known_rollback_provenance(self) -> None:
        text = self.read("scripts/prepare-release-runtime.sh")

        self.assertIn("validate_previous_runtime_target", text)
        self.assertIn('if [[ "$target" == "$LEGACY_RUNTIME" ]]', text)
        self.assertIn(
            "runtime legado só é aceito antes do primeiro cutover v1.1",
            text,
        )
        self.assertIn('"$RUNTIME_BASE"/*', text)
        self.assertIn("runtime anterior não possui identidade SHA", text)
        self.assertIn("release-sha.txt", text)

    def test_ci_and_runtime_use_audited_dependency_lock(self) -> None:
        ci = self.read(".github/workflows/ci.yml")
        runtime = self.read("scripts/check-runtime.py")
        prepare = self.read("scripts/prepare-release-runtime.sh")
        lock = self.read("requirements.lock")

        self.assertIn("pip --isolated install", ci)
        self.assertIn("--no-deps", ci)
        self.assertIn("--require-hashes", ci)
        self.assertIn("--only-binary=:all:", ci)
        self.assertIn("--index-url https://pypi.org/simple", ci)
        self.assertIn("-r requirements.lock", ci)
        self.assertIn("cache-dependency-path: requirements.lock", ci)
        self.assertNotIn("requirements.txt", ci)
        self.assertIn("verify_runtime_lock()", runtime)
        self.assertIn(
            "runtime package differs from audited lock",
            runtime,
        )

        expected = (
            "python-telegram-bot==22.8",
            "python-dotenv==1.2.3",
            "httpx==0.28.1",
            "idna==3.20",
            "httpcore==1.0.9",
            "anyio==4.15.1",
            "certifi==2026.7.22",
            "h11==0.16.0",
            "typing_extensions==4.16.0",
        )
        for item in expected:
            self.assertIn(item, lock)

        import re

        entries = [
            line.strip()
            for line in lock.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertEqual(len(entries), len(expected))
        for entry in entries:
            self.assertRegex(
                entry,
                re.compile(
                    r"^[A-Za-z0-9][A-Za-z0-9._-]*"
                    r"==[A-Za-z0-9][A-Za-z0-9._+!-]*"
                    r" --hash=sha256:[0-9a-f]{64}$"
                ),
            )

        self.assertIn("LOCK_ENTRY_RE", runtime)
        self.assertIn("sha256 wheel hash required", runtime)
        self.assertIn("requirements-lock.sha256", prepare)
        self.assertIn('"$LOCK_SHA"', prepare)

    def test_apply_uses_installed_service_layout_as_db_authority(self) -> None:
        apply = self.read("scripts/apply-zion-v1.sh")
        predeploy = self.read("scripts/predeploy-v11.sh")

        self.assertIn("PREVIOUS_SERVICE_STATE_LAYOUT", apply)
        self.assertIn(
            'grep -Fq "ZION_DB_PATH=$TARGET_DB" "$SERVICE_DST"',
            apply,
        )
        self.assertIn(
            "source = target_db if state_layout else settings.db_path.expanduser()",
            apply,
        )
        self.assertIn("PROD_SERVICE_STATE_LAYOUT", predeploy)
        self.assertIn(
            'grep -Fq "ZION_DB_PATH=$STATE_DB" "$INSTALLED_SERVICE"',
            predeploy,
        )

    def test_apply_revalidates_state_env_and_worktree_at_cutover(self) -> None:
        text = self.read("scripts/apply-zion-v1.sh")

        self.assertIn('STATE_REAL="$(readlink -f -- "$STATE_DIR"', text)
        self.assertIn(
            'if [[ "$STATE_REAL" != "$STATE_DIR" ]]',
            text,
        )
        self.assertIn('"source_db", source_db_raw', text)
        self.assertIn('"target_db", target_db_raw', text)
        self.assertIn("must not be a symlink", text)
        self.assertIn('sha256sum -c "$DEST/env.sha256"', text)
        self.assertIn("HEAD mudou durante o cutover", text)
        self.assertIn("worktree mudou durante o cutover", text)
        self.assertIn("runtime/current mudou durante o cutover", text)

    def test_installed_dashboard_participates_in_same_cutover(self) -> None:
        text = self.read("scripts/apply-zion-v1.sh")

        self.assertIn('DASHBOARD_INSTALLED=false', text)
        self.assertIn('DASHBOARD_SHOULD_START=false', text)
        self.assertIn(
            "systemctl is-enabled --quiet zion-dashboard.service",
            text,
        )
        self.assertIn(
            "dashboard instalado deve estar parado no mesmo cutover",
            text,
        )
        self.assertIn("zion-dashboard.service.installed", text)
        self.assertIn('"$DASHBOARD_SRC"', text)
        self.assertIn('"$DASHBOARD_DST"', text)
        self.assertIn(
            'if [[ "$DASHBOARD_SHOULD_START" == true ]]',
            text,
        )
        self.assertIn("systemctl start zion-dashboard.service", text)
        self.assertIn(
            "zion-dashboard.service não ficou ativo",
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
