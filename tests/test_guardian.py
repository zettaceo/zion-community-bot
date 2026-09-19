from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_settings
from zion.db import ZionDB
from zion.models import OperatingState
from zion.guardian import (
    Guardian,
    detect_sensitive_content,
    extract_domains,
)


class GuardianTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = make_settings(self.root)
        self.db = ZionDB(self.settings.db_path)
        self.db.initialize()
        self.guardian = Guardian(self.settings, self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.temp.cleanup()

    def test_extract_domains(self) -> None:
        domains = extract_domains(
            "Veja https://example.com/a e t.me/ZSwapCommunity"
        )
        self.assertIn("example.com", domains)
        self.assertIn("t.me", domains)

    def test_links_blocked_by_default(self) -> None:
        decision = self.guardian.evaluate_links(
            "https://untrusted.example/path"
        )
        self.assertTrue(decision.should_delete)
        self.assertEqual(
            decision.unauthorized_domains,
            ["untrusted.example"],
        )

    def test_runtime_domain_allow(self) -> None:
        self.db.set_domain("trusted.example", "allow", "test")
        decision = self.guardian.evaluate_links(
            "https://trusted.example/path"
        )
        self.assertFalse(decision.should_delete)

    def test_runtime_parent_domain_allows_subdomain(self) -> None:
        self.db.set_domain("trusted.example", "allow", "test")
        decision = self.guardian.evaluate_links(
            "https://sub.trusted.example/path"
        )
        self.assertFalse(decision.should_delete)

    def test_secret_requires_sensitive_label(self) -> None:
        ordinary_hash = "0x" + ("a" * 64)
        self.assertFalse(
            detect_sensitive_content(ordinary_hash).detected
        )

    def test_seed_phrase_like_content_detected(self) -> None:
        text = (
            "seed phrase: alpha beta gamma delta epsilon zeta "
            "eta theta iota kappa lambda mu"
        )
        self.assertTrue(
            detect_sensitive_content(text).detected
        )

    def test_elevated_state_tightens_flood_threshold(self) -> None:
        self.db.set_operating_state(OperatingState.ELEVATED)
        now = 2000.0

        first = self.guardian.record_message(
            chat_id=10,
            user_id=30,
            message_id=10,
            now=now,
        )
        second = self.guardian.record_message(
            chat_id=10,
            user_id=30,
            message_id=11,
            now=now + 1,
        )
        third = self.guardian.record_message(
            chat_id=10,
            user_id=30,
            message_id=12,
            now=now + 2,
        )

        self.assertFalse(first.triggered)
        self.assertFalse(second.triggered)
        self.assertTrue(third.triggered)

    def test_flood_triggers_at_threshold(self) -> None:
        now = 1000.0

        first = self.guardian.record_message(
            chat_id=10,
            user_id=20,
            message_id=1,
            now=now,
        )
        second = self.guardian.record_message(
            chat_id=10,
            user_id=20,
            message_id=2,
            now=now + 1,
        )
        third = self.guardian.record_message(
            chat_id=10,
            user_id=20,
            message_id=3,
            now=now + 2,
        )

        self.assertFalse(first.triggered)
        self.assertFalse(second.triggered)
        self.assertTrue(third.triggered)
        self.assertEqual(third.strike_count, 1)
        self.assertEqual(third.message_ids, [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
