from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FIXED_PATH = "PATH=/usr/sbin:/usr/bin:/sbin:/bin"

CRITICAL_SHELL_SCRIPTS = (
    "scripts/apply-dashboard.sh",
    "scripts/apply-ssh-hardening.sh",
    "scripts/apply-zion-v1.sh",
    "scripts/deployment-preflight.sh",
    "scripts/predeploy-v11.sh",
    "scripts/prepare-release-runtime.sh",
    "scripts/remote-access-preflight.sh",
    "scripts/validate.sh",
    "scripts/verify-approved-release.sh",
)


class ExecutablePathBoundaryTests(unittest.TestCase):
    def test_critical_shell_scripts_pin_system_path(self) -> None:
        for relative in CRITICAL_SHELL_SCRIPTS:
            with self.subTest(relative=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(FIXED_PATH, text)
                self.assertIn("export PATH", text)
                self.assertLess(text.index("set "), text.index(FIXED_PATH))

    def test_python_git_callers_use_absolute_git(self) -> None:
        boundary = (ROOT / "scripts" / "check-git-release-boundary.py").read_text(encoding="utf-8")
        secret_scan = (ROOT / "scripts" / "secret_scan.py").read_text(encoding="utf-8")
        rehearsal = (ROOT / "scripts" / "rehearse-sqlite-copy.py").read_text(encoding="utf-8")
        self.assertIn('GIT_EXECUTABLE = "/usr/bin/git"', boundary)
        self.assertIn('[GIT_EXECUTABLE, "-C", str(root), *args]', boundary)
        self.assertIn('["/usr/bin/git", "ls-files", "-z"]', secret_scan)
        self.assertIn("['/usr/bin/git', 'rev-parse', 'HEAD']", rehearsal)

    def test_release_shells_use_absolute_git_for_git_operations(self) -> None:
        for relative in CRITICAL_SHELL_SCRIPTS:
            with self.subTest(relative=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                if "git " in text or "git -C" in text:
                    self.assertIn("/usr/bin/git", text)

    def test_validation_uses_absolute_git_for_sensitive_inventory(self) -> None:
        text = (ROOT / "scripts" / "validate.sh").read_text(encoding="utf-8")
        self.assertIn("/usr/bin/git ls-files", text)

    def test_ci_binds_validation_to_setup_python_runtime(self) -> None:
        text = (
            ROOT / ".github" / "workflows" / "ci.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'ZION_VALIDATION_PYTHON="$pythonLocation/bin/python" '
            "bash scripts/validate.sh",
            text,
        )


if __name__ == "__main__":
    unittest.main()
