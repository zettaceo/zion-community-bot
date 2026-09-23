from __future__ import annotations

import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from tests.helpers import make_settings
from zion.config import Settings, _bool, _int_set


class SettingsTests(unittest.TestCase):
    def test_invalid_boolean_fails_fast(self) -> None:
        with patch.dict(
            os.environ,
            {"ZION_TEST_BOOL": "tru"},
            clear=False,
        ):
            with self.assertRaises(ValueError):
                _bool("ZION_TEST_BOOL")

    def test_operator_id_set_ignores_non_positive_values(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ZION_TEST_IDS": "-100123,0,7782078379,garbage",
            },
            clear=False,
        ):
            self.assertEqual(
                _int_set("ZION_TEST_IDS"),
                frozenset({7782078379}),
            )

    def test_configuration_issues_are_empty_for_healthy_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = make_settings(root)
            shared_lock = (
                root.parent
                / "shared-zion-state"
                / "runtime.lock"
            )
            settings = replace(
                settings,
                runtime_lock_path=shared_lock,
            )
            self.assertEqual(settings.configuration_issues(), ())

    def test_configuration_issues_surface_operator_and_ai_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = replace(
                make_settings(root),
                admin_user_ids=frozenset(),
                ai_enabled=True,
                ai_observe=True,
                legacy_mistral_api_key_present=True,
                runtime_lock_path=root / "runtime.lock",
            )

            issues = settings.configuration_issues()
            self.assertIn("operator_allowlist_empty", issues)
            self.assertIn("deprecated_mistral_api_key_present", issues)
            self.assertIn("runtime_lock_inside_worktree", issues)


    def test_configuration_issues_surface_incoherent_health_cadence(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = replace(
                make_settings(root),
                health_check_interval_seconds=7200,
                health_alert_repeat_seconds=3600,
            )

            self.assertIn(
                "health_check_slower_than_alert_repeat",
                settings.configuration_issues(),
            )

    def test_allowed_domains_use_nontransitional_idna2008(self) -> None:
        with patch.dict(
            os.environ,
            {"ALLOWED_DOMAINS": "faß.de"},
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertIn("xn--fa-hia.de", settings.allowed_domains)
        self.assertNotIn("fass.de", settings.allowed_domains)

    def test_allowed_domains_are_normalized_to_idna(self) -> None:
        env = {
            "ALLOWED_DOMAINS": "Example.COM.,例え.テスト,https://bad.example",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = Settings.from_env()

        self.assertIn("example.com", settings.allowed_domains)
        self.assertIn(
            "xn--r8jz45g.xn--zckzah",
            settings.allowed_domains,
        )
        self.assertNotIn(
            "https://bad.example",
            settings.allowed_domains,
        )

    def test_deprecated_mistral_env_secret_is_detected_and_scrubbed(self) -> None:
        synthetic = "synthetic-env-mistral-material-123456"
        with patch.dict(
            os.environ,
            {"MISTRAL_API_KEY": synthetic},
            clear=False,
        ):
            settings = Settings.from_env()
            self.assertTrue(settings.legacy_mistral_api_key_present)
            self.assertNotIn("MISTRAL_API_KEY", os.environ)

        self.assertNotIn(synthetic, repr(settings))

    def test_mistral_secret_path_env_override_is_ignored(self) -> None:
        with patch.dict(
            os.environ,
            {
                "ZION_MISTRAL_SECRET_PATH": "/tmp/unsafe-secret-location",
            },
            clear=False,
        ):
            settings = Settings.from_env()

        expected = (
            Path.home()
            / ".local"
            / "state"
            / "zion-community-bot"
            / "secrets"
            / "mistral-api-key"
        )
        self.assertEqual(settings.mistral_secret_path, expected)

    def test_mistral_secret_path_inside_worktree_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = replace(
                make_settings(root),
                mistral_secret_path=root / "secrets" / "mistral-api-key",
            )
            self.assertIn(
                "mistral_secret_inside_worktree",
                settings.configuration_issues(),
            )


if __name__ == "__main__":
    unittest.main()
