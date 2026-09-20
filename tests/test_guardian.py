from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tests.helpers import make_settings
from zion.db import ZionDB
from zion.models import OperatingState
from zion.guardian import (
    Guardian,
    detect_sensitive_content,
    extract_domains,
    normalize_link_target,
    normalize_policy_domain,
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

    def test_policy_domain_normalization(self) -> None:
        self.assertEqual(
            normalize_policy_domain("https://www.Example.com/path"),
            "example.com",
        )
        self.assertEqual(
            normalize_policy_domain("sub.example.com"),
            "sub.example.com",
        )
        self.assertIsNone(
            normalize_policy_domain("not a domain"),
        )

    def test_fullwidth_and_zero_width_link_is_normalized(self) -> None:
        domains = extract_domains(
            "Veja ｈｔｔｐｓ：／／exa\u200bmple.com/path"
        )
        self.assertEqual(domains, ["example.com"])

    def test_unicode_lookalike_remains_distinct_punycode(self) -> None:
        domain = normalize_policy_domain("еxample.com")
        self.assertIsNotNone(domain)
        self.assertNotEqual(domain, "example.com")
        self.assertTrue(domain.startswith("xn--"))

    def test_unsupported_clickable_scheme_is_classified(self) -> None:
        domain, scheme = normalize_link_target(
            "tg://resolve?domain=example"
        )
        self.assertIsNone(domain)
        self.assertEqual(scheme, "tg")

        decision = self.guardian.evaluate_links(
            "",
            unsupported_schemes=["tg"],
        )
        self.assertTrue(decision.should_delete)
        self.assertEqual(decision.unsupported_schemes, ["tg"])

    def test_malformed_http_target_fails_closed(self) -> None:
        domain, scheme = normalize_link_target("https://")
        self.assertIsNone(domain)
        self.assertEqual(scheme, "invalid-https")

        decision = self.guardian.evaluate_links(
            "",
            unsupported_schemes=[scheme],
        )
        self.assertTrue(decision.should_delete)

    def test_visible_non_http_scheme_is_blocked(self) -> None:
        decision = self.guardian.evaluate_links(
            "abra tg://resolve?domain=example"
        )
        self.assertTrue(decision.should_delete)
        self.assertEqual(decision.unsupported_schemes, ["tg"])

    def test_visible_ftp_scheme_is_blocked(self) -> None:
        decision = self.guardian.evaluate_links(
            "download ftp://evil.example/file"
        )
        self.assertTrue(decision.should_delete)
        self.assertEqual(decision.unsupported_schemes, ["ftp"])

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

    def test_allowed_domain_does_not_match_suffix_confusion(self) -> None:
        settings = replace(
            self.settings,
            allow_links=True,
            allowed_domains=frozenset({"example.com"}),
        )
        guardian = Guardian(settings, self.db)

        good = guardian.evaluate_links(
            "https://sub.example.com/path"
        )
        deceptive = guardian.evaluate_links(
            "https://example.com.evil.test/path"
        )

        self.assertFalse(good.should_delete)
        self.assertTrue(deceptive.should_delete)

    def test_runtime_block_overrides_environment_allow(self) -> None:
        settings = replace(
            self.settings,
            allow_links=True,
            allowed_domains=frozenset({"example.com"}),
        )
        guardian = Guardian(settings, self.db)
        self.db.set_domain("sub.example.com", "block", "test")

        decision = guardian.evaluate_links(
            "https://sub.example.com/path"
        )
        self.assertTrue(decision.should_delete)
        self.assertEqual(
            decision.unauthorized_domains,
            ["sub.example.com"],
        )

    def test_specific_runtime_allow_can_override_parent_block(self) -> None:
        self.db.set_domain("example.com", "block", "test")
        self.db.set_domain(
            "safe.example.com",
            "allow",
            "test",
        )

        safe = self.guardian.evaluate_links(
            "https://safe.example.com/path"
        )
        blocked = self.guardian.evaluate_links(
            "https://other.example.com/path"
        )

        self.assertFalse(safe.should_delete)
        self.assertTrue(blocked.should_delete)

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

    def test_multiline_seed_phrase_is_detected(self) -> None:
        text = (
            "seed phrase:\n"
            "alpha beta gamma delta epsilon zeta\n"
            "eta theta iota kappa lambda mu"
        )
        self.assertTrue(
            detect_sensitive_content(text).detected
        )

    def test_seed_phrase_with_trailing_comment_is_detected(self) -> None:
        text = (
            "seed phrase: alpha beta gamma delta epsilon zeta "
            "eta theta iota kappa lambda mu "
            "please help me recover this wallet"
        )
        self.assertTrue(
            detect_sensitive_content(text).detected
        )

    def test_zero_width_obfuscated_seed_label_is_detected(self) -> None:
        text = (
            "seed\u200b phrase: alpha beta gamma delta epsilon zeta "
            "eta theta iota kappa lambda mu"
        )
        self.assertTrue(
            detect_sensitive_content(text).detected
        )

    def test_unicode_mnemonic_words_are_detected(self) -> None:
        text = (
            "mnemonic: "
            "あいこくしん あいさつ あいだ あおぞら あかちゃん "
            "あきる あけがた あける あこがれる あさい あさひ "
            "あしあと"
        )
        decision = detect_sensitive_content(text)
        self.assertTrue(decision.detected)
        self.assertEqual(decision.kind, "possible_wallet_secret")

    def test_labeled_base58_private_key_is_detected(self) -> None:
        text = "private key: " + ("1" * 64)
        decision = detect_sensitive_content(text)
        self.assertTrue(decision.detected)
        self.assertEqual(decision.kind, "possible_private_key")

    def test_labeled_byte_array_private_key_is_detected(self) -> None:
        payload = ",".join(str(index) for index in range(64))
        decision = detect_sensitive_content(
            f"private key: [{payload}]"
        )
        self.assertTrue(decision.detected)
        self.assertEqual(decision.kind, "possible_private_key")

    def test_elevated_threshold_never_becomes_weaker_than_normal(self) -> None:
        settings = replace(
            self.settings,
            flood_max_messages=2,
        )
        guardian = Guardian(settings, self.db)
        self.db.set_operating_state(OperatingState.ELEVATED)

        first = guardian.record_message(
            chat_id=99,
            user_id=99,
            message_id=1,
            now=9000.0,
        )
        second = guardian.record_message(
            chat_id=99,
            user_id=99,
            message_id=2,
            now=9001.0,
        )

        self.assertFalse(first.triggered)
        self.assertTrue(second.triggered)

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
        self.assertTrue(second.triggered)
        self.assertFalse(third.triggered)

    def test_repeated_objective_flood_reaches_ban_threshold(self) -> None:
        settings = replace(
            self.settings,
            flood_max_messages=2,
            flood_mute_levels=(1, 2),
            flood_ban_after_strikes=2,
            flood_strike_reset_seconds=3600,
        )
        guardian = Guardian(settings, self.db)

        first_cycle_1 = guardian.record_message(
            chat_id=10,
            user_id=60,
            message_id=1,
            now=1000.0,
        )
        first_cycle_2 = guardian.record_message(
            chat_id=10,
            user_id=60,
            message_id=2,
            now=1001.0,
        )
        self.assertFalse(first_cycle_1.triggered)
        self.assertTrue(first_cycle_2.triggered)
        self.assertEqual(first_cycle_2.strike_count, 1)
        self.assertFalse(first_cycle_2.should_ban)

        second_cycle_1 = guardian.record_message(
            chat_id=10,
            user_id=60,
            message_id=3,
            now=1010.0,
        )
        second_cycle_2 = guardian.record_message(
            chat_id=10,
            user_id=60,
            message_id=4,
            now=1011.0,
        )
        self.assertFalse(second_cycle_1.triggered)
        self.assertTrue(second_cycle_2.triggered)
        self.assertEqual(second_cycle_2.strike_count, 2)
        self.assertTrue(second_cycle_2.should_ban)

    def test_expired_flood_strike_does_not_drive_later_ban(self) -> None:
        settings = replace(
            self.settings,
            flood_max_messages=2,
            flood_mute_levels=(1,),
            flood_ban_after_strikes=2,
            flood_strike_reset_seconds=60,
        )
        guardian = Guardian(settings, self.db)

        guardian.record_message(
            chat_id=11,
            user_id=61,
            message_id=1,
            now=2000.0,
        )
        first = guardian.record_message(
            chat_id=11,
            user_id=61,
            message_id=2,
            now=2001.0,
        )
        self.assertEqual(first.strike_count, 1)

        guardian.record_message(
            chat_id=11,
            user_id=61,
            message_id=3,
            now=2100.0,
        )
        later = guardian.record_message(
            chat_id=11,
            user_id=61,
            message_id=4,
            now=2101.0,
        )
        self.assertTrue(later.triggered)
        self.assertEqual(later.strike_count, 1)
        self.assertFalse(later.should_ban)

    def test_manual_warning_does_not_advance_flood_ban_counter(self) -> None:
        now = 3000.0
        self.db.add_strike(
            chat_id=10,
            user_id=40,
            reason="manual warning",
            severity="medium",
            source="admin",
            ttl_seconds=3600,
            now=now,
        )

        self.guardian.record_message(
            chat_id=10,
            user_id=40,
            message_id=1,
            now=now + 1,
        )
        self.guardian.record_message(
            chat_id=10,
            user_id=40,
            message_id=2,
            now=now + 2,
        )
        result = self.guardian.record_message(
            chat_id=10,
            user_id=40,
            message_id=3,
            now=now + 3,
        )

        self.assertTrue(result.triggered)
        self.assertEqual(result.strike_count, 1)

    def test_flood_deletion_scope_excludes_old_legitimate_messages(self) -> None:
        now = 12000.0
        self.db.record_recent_message(
            chat_id=10,
            user_id=50,
            message_id=1,
            created_at=now - 60,
        )

        self.guardian.record_message(
            chat_id=10,
            user_id=50,
            message_id=2,
            now=now,
        )
        self.guardian.record_message(
            chat_id=10,
            user_id=50,
            message_id=3,
            now=now + 1,
        )
        result = self.guardian.record_message(
            chat_id=10,
            user_id=50,
            message_id=4,
            now=now + 2,
        )

        self.assertTrue(result.triggered)
        self.assertEqual(result.message_ids, [2, 3, 4])
        self.assertNotIn(1, result.message_ids)

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
