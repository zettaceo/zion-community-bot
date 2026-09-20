from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from tests.helpers import make_settings
from zion.db import ZionDB
from zion.guardian import Guardian, normalize_policy_domain
from zion.logging_safe import contains_high_confidence_credential
from zion.telegram_app import telegram_entity_domains, telegram_external_urls


class TelegramLinkSurfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = replace(
            make_settings(self.root),
            allow_links=True,
            allowed_domains=frozenset({"fass.de", "z-swap.example"}),
        )
        self.db = ZionDB(self.settings.db_path)
        self.db.initialize()
        self.addCleanup(self.db.close)
        self.guardian = Guardian(self.settings, self.db)

    def test_idna2008_sharp_s_does_not_inherit_ascii_allowlist(self) -> None:
        normalized = normalize_policy_domain("https://faß.de/login")
        self.assertEqual(normalized, "xn--fa-hia.de")
        self.assertNotEqual(normalized, "fass.de")

        decision = self.guardian.evaluate_links("https://faß.de/login")
        self.assertTrue(decision.should_delete)
        self.assertEqual(decision.unauthorized_domains, ["xn--fa-hia.de"])

    def test_inline_keyboard_urls_participate_in_domain_policy(self) -> None:
        button = SimpleNamespace(
            url="https://evil.example/path",
            login_url=None,
            web_app=None,
        )
        message = SimpleNamespace(
            entities=[],
            caption_entities=[],
            reply_markup=SimpleNamespace(inline_keyboard=[[button]]),
        )

        urls = telegram_external_urls(message)
        domains = telegram_entity_domains(message)

        self.assertEqual(urls, ["https://evil.example/path"])
        self.assertEqual(domains, ["evil.example"])
        decision = self.guardian.evaluate_links("", extra_domains=domains)
        self.assertTrue(decision.should_delete)

    def test_login_and_webapp_urls_are_inspected(self) -> None:
        message = SimpleNamespace(
            entities=[],
            caption_entities=[],
            reply_markup=SimpleNamespace(
                inline_keyboard=[[
                    SimpleNamespace(
                        url=None,
                        login_url=SimpleNamespace(
                            url="https://login.evil.example/auth"
                        ),
                        web_app=SimpleNamespace(
                            url="https://web.evil.example/app"
                        ),
                    )
                ]]
            ),
        )

        self.assertEqual(
            telegram_entity_domains(message),
            ["login.evil.example", "web.evil.example"],
        )

    def test_hidden_url_credentials_are_visible_to_secret_detector(self) -> None:
        hidden = SimpleNamespace(
            type="text_link",
            url=(
                "https://z-swap.example/support?"
                "api_key=example-secret-value-123456"
            ),
        )
        message = SimpleNamespace(
            entities=[hidden],
            caption_entities=[],
            reply_markup=None,
        )

        surface = "\n".join(("safe label", *telegram_external_urls(message)))
        self.assertTrue(contains_high_confidence_credential(surface))


if __name__ == "__main__":
    unittest.main()
