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
                mistral_api_key="",
                runtime_lock_path=root / "runtime.lock",
            )

            issues = settings.configuration_issues()
            self.assertIn("operator_allowlist_empty", issues)
            self.assertIn("ai_enabled_without_key", issues)
            self.assertIn("runtime_lock_inside_worktree", issues)


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


if __name__ == "__main__":
    unittest.main()
