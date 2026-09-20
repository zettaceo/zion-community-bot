from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts" / "check-python-release-env.py"

RELEASE_SHELLS = (
    "scripts/validate.sh",
    "scripts/apply-zion-v1.sh",
    "scripts/predeploy-v11.sh",
    "scripts/prepare-release-runtime.sh",
    "scripts/deployment-preflight.sh",
    "scripts/verify-approved-release.sh",
    "scripts/apply-dashboard.sh",
)


class PythonReleaseEnvironmentTests(unittest.TestCase):
    def clean_env(self) -> dict[str, str]:
        return {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("PYTHON")
        }

    def run_checker(
        self,
        *,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = self.clean_env()
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, "-I", str(CHECKER)],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_clean_python_environment_passes(self) -> None:
        result = self.run_checker()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("python release environment: OK", result.stdout)

    def test_pythonpath_is_rejected_before_release_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            attack = Path(tmp)
            marker = attack / "marker.txt"
            (attack / "sqlite3.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n",
                encoding="utf-8",
            )
            probe = attack / "probe.py"
            probe.write_text("import sqlite3\n", encoding="utf-8")

            env = self.clean_env()
            env["PYTHONPATH"] = str(attack)
            plain = subprocess.run(
                [sys.executable, str(probe)],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(plain.returncode, 0, plain.stderr)
            self.assertTrue(marker.is_file())

            result = self.run_checker(
                extra_env={"PYTHONPATH": str(attack)}
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("PYTHONPATH", result.stderr)

    def test_pythonwarnings_is_rejected_fail_closed(self) -> None:
        result = self.run_checker(
            extra_env={"PYTHONWARNINGS": "default"}
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PYTHONWARNINGS", result.stderr)

    def test_release_shells_check_python_environment(self) -> None:
        for relative in RELEASE_SHELLS:
            with self.subTest(relative=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("check-python-release-env.py", text)
                self.assertIn('"/usr/bin/python3"', text)

    def test_validation_checks_before_setting_pycache_prefix(self) -> None:
        text = (ROOT / "scripts" / "validate.sh").read_text(
            encoding="utf-8"
        )

        checker = text.index("check-python-release-env.py")
        pycache = text.index("export PYTHONPYCACHEPREFIX")
        self.assertLess(checker, pycache)

    def test_preflight_never_executes_runtime_when_python_env_is_dirty(
        self,
    ) -> None:
        text = (ROOT / "scripts" / "deployment-preflight.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("PYTHON_ENV_CLEAN=false", text)
        self.assertIn("PYTHON_ENV_CLEAN=true", text)
        self.assertIn(
            'if [[ "$PYTHON_ENV_CLEAN" != true ]]',
            text,
        )
        self.assertIn(
            "runtime validation skipped because Python environment is contaminated",
            text,
        )

    def test_remote_access_python_probes_use_isolated_mode(self) -> None:
        for relative in (
            "scripts/apply-ssh-hardening.sh",
            "scripts/remote-access-preflight.sh",
        ):
            with self.subTest(relative=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("/usr/bin/python3 -I -", text)
                self.assertNotIn("\npython3 - ", text)
                self.assertNotIn("elif python3 - ", text)
                self.assertNotIn("if python3 - ", text)


if __name__ == "__main__":
    unittest.main()
