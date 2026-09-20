from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class LegacyMutationPathTests(unittest.TestCase):
    def test_legacy_bot_installer_is_fail_closed(self) -> None:
        text = (ROOT / "scripts" / "apply-systemd.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("está desabilitado no release v1.1", text)
        self.assertIn("exit 64", text)
        self.assertNotIn("systemctl restart", text)
        self.assertNotIn("sudo /usr/bin/install", text)

    def test_legacy_wifi_installer_is_fail_closed(self) -> None:
        text = (ROOT / "scripts" / "apply-wifi-guardian.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("está desabilitado no release v1.1", text)
        self.assertIn("autorização explícita", text)
        self.assertIn("exit 64", text)
        self.assertNotIn("systemctl enable", text)
        self.assertNotIn("sudo /usr/bin/install", text)


if __name__ == "__main__":
    unittest.main()
