from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class SystemdContractTests(unittest.TestCase):
    def test_main_service_keeps_network_and_sandbox_contract(self) -> None:
        text = (ROOT / "systemd" / "zion.service").read_text(
            encoding="utf-8"
        )

        required = (
            "User=zetta",
            "WorkingDirectory=/home/zetta/zion-community-bot",
            "EnvironmentFile=/home/zetta/zion-community-bot/.env",
            "getent hosts api.telegram.org",
            "TimeoutStartSec=0",
            "UMask=0077",
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "PrivateDevices=true",
            "ProtectSystem=strict",
            "ProtectKernelTunables=true",
            "ProtectKernelModules=true",
            "ProtectControlGroups=true",
            "RestrictSUIDSGID=true",
            "LockPersonality=true",
            "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
            "ReadWritePaths=/home/zetta/zion-community-bot",
            (
                "ReadWritePaths=/home/zetta/.local/state/"
                "zion-community-bot"
            ),
        )
        for value in required:
            self.assertIn(value, text)

    def test_dashboard_does_not_load_bot_secrets(self) -> None:
        text = (
            ROOT / "systemd" / "zion-dashboard.service"
        ).read_text(encoding="utf-8")

        self.assertNotIn("EnvironmentFile=", text)
        self.assertIn(
            "Environment=ZION_DASHBOARD_BIND=127.0.0.1",
            text,
        )
        self.assertIn("ProtectSystem=strict", text)
        self.assertIn("NoNewPrivileges=true", text)
        self.assertIn(
            (
                "ReadWritePaths=/home/zetta/.local/state/"
                "zion-community-bot"
            ),
            text,
        )
        self.assertNotIn(
            "ReadWritePaths=/home/zetta/zion-community-bot\n",
            text,
        )


if __name__ == "__main__":
    unittest.main()
