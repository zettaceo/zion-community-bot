from __future__ import annotations

import logging
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from zion.ai_service import sanitize_for_ai
from zion.health import _private_file
from zion.logging_safe import (
    PrivateRotatingFileHandler,
    SecretSafeFormatter,
    configure_logging,
    contains_high_confidence_credential,
    redact_secrets,
    register_sensitive_value,
)


class SecurityTests(unittest.TestCase):
    def test_log_file_permissions_are_private(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "zion.log"
            configure_logging(path)
            mode = stat.S_IMODE(path.stat().st_mode)
            self.assertEqual(mode, 0o600)

    def test_symlinked_log_target_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.log"
            target.write_text("do not follow", encoding="utf-8")
            link = root / "zion.log"
            link.symlink_to(target)

            with self.assertRaises(RuntimeError):
                configure_logging(link)

    def test_hardlinked_log_target_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.log"
            target.write_text("outside", encoding="utf-8")
            link = root / "zion.log"
            link.hardlink_to(target)

            with self.assertRaisesRegex(RuntimeError, "hard links"):
                configure_logging(link)

            self.assertEqual(
                target.read_text(encoding="utf-8"),
                "outside",
            )

    def test_sensitive_file_health_rejects_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            regular = root / "regular"
            regular.write_text("ok", encoding="utf-8")
            regular.chmod(0o600)
            self.assertTrue(_private_file(regular))

            symlink = root / "symlink"
            symlink.symlink_to(regular)
            self.assertFalse(_private_file(symlink))

            hardlink = root / "hardlink"
            hardlink.hardlink_to(regular)
            self.assertFalse(_private_file(regular))
            self.assertFalse(_private_file(hardlink))

    def test_rotated_log_files_remain_private(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rotate.log"
            handler = PrivateRotatingFileHandler(
                path,
                maxBytes=128,
                backupCount=2,
                encoding="utf-8",
            )
            handler.setFormatter(
                SecretSafeFormatter("%(levelname)s %(message)s")
            )
            logger = logging.getLogger(
                f"zion-test-rotation-{id(handler)}"
            )
            logger.setLevel(logging.INFO)
            logger.propagate = False
            logger.handlers = [handler]

            try:
                for index in range(20):
                    logger.info(
                        "line-%s-%s",
                        index,
                        "x" * 40,
                    )
            finally:
                handler.close()
                logger.handlers = []

            rotated = list(path.parent.glob("rotate.log*"))
            self.assertGreaterEqual(len(rotated), 2)
            for candidate in rotated:
                mode = stat.S_IMODE(candidate.stat().st_mode)
                self.assertEqual(mode, 0o600)

    def test_telegram_token_redacted(self) -> None:
        fake = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
        result = redact_secrets(
            "POST https://api.telegram.org/bot"
            + fake
            + "/getUpdates"
        )
        self.assertNotIn(fake, result)
        self.assertIn("[REDACTED_TELEGRAM_TOKEN]", result)

    def test_labeled_password_is_redacted_from_logs(self) -> None:
        secret = "example-password-123456"
        value = redact_secrets(
            f"password: {secret}"
        )
        self.assertNotIn(secret, value)
        self.assertIn("[REDACTED]", value)

    def test_bearer_redacted(self) -> None:
        result = redact_secrets(
            "Authorization: Bearer fake-secret-value-123"
        )
        self.assertNotIn("fake-secret-value-123", result)

    def test_ai_input_credential_redacted(self) -> None:
        result = sanitize_for_ai(
            "api_key=super-secret-user-key-123456"
        )
        self.assertNotIn(
            "super-secret-user-key-123456",
            result,
        )
        self.assertIn("[REDACTED]", result)

    def test_wallet_secret_redacted_before_ai(self) -> None:
        text = (
            "seed phrase: alpha beta gamma delta epsilon zeta "
            "eta theta iota kappa lambda mu"
        )
        result = sanitize_for_ai(text)
        self.assertNotIn("alpha beta gamma", result)
        self.assertIn("[REDACTED_WALLET_SECRET]", result)

    def test_labeled_api_key_is_high_confidence_credential(self) -> None:
        self.assertTrue(
            contains_high_confidence_credential(
                "API key: example-secret-value-123456"
            )
        )

    def test_crypto_token_parameter_is_not_treated_as_credential(self) -> None:
        self.assertFalse(
            contains_high_confidence_credential(
                "token=USDC"
            )
        )

    def test_bearer_is_high_confidence_credential(self) -> None:
        self.assertTrue(
            contains_high_confidence_credential(
                "Authorization: Bearer example-secret-value-123"
            )
        )


    def test_private_key_block_is_high_confidence_and_redacted(self) -> None:
        begin = "-----BEGIN " + "OPENSSH PRIVATE" + " KEY-----"
        end = "-----END " + "OPENSSH PRIVATE" + " KEY-----"
        value = (
            begin + "\n"
            "example-private-material-not-real\n"
            + end
        )
        self.assertTrue(contains_high_confidence_credential(value))
        redacted = redact_secrets(value)
        self.assertNotIn("example-private-material-not-real", redacted)
        self.assertIn("[REDACTED_PRIVATE_KEY]", redacted)

    def test_basic_auth_url_is_detected_and_redacted(self) -> None:
        value = "https://alice:super-secret-password@example.com/path"
        self.assertTrue(
            contains_high_confidence_credential(value)
        )
        redacted = redact_secrets(value)
        self.assertNotIn("super-secret-password", redacted)
        self.assertIn("alice:[REDACTED]@", redacted)

    def test_zero_width_obfuscated_api_key_is_detected(self) -> None:
        value = (
            "api\u200b key: "
            "example-secret-value-123456"
        )
        self.assertTrue(
            contains_high_confidence_credential(value)
        )
        redacted = redact_secrets(value)
        self.assertNotIn(
            "example-secret-value-123456",
            redacted,
        )

    def test_access_token_label_is_high_confidence(self) -> None:
        self.assertTrue(
            contains_high_confidence_credential(
                "access token: example-access-token-123456"
            )
        )

    def test_fullwidth_credential_label_is_normalized(self) -> None:
        value = (
            "ＡＰＩ ｋｅｙ： "
            "example-secret-value-123456"
        )
        self.assertTrue(
            contains_high_confidence_credential(value)
        )
        self.assertNotIn(
            "example-secret-value-123456",
            redact_secrets(value),
        )

    def test_runtime_registered_secret_is_redacted_without_env(self) -> None:
        secret = "synthetic-runtime-mistral-material-123456"
        register_sensitive_value(secret)

        result = redact_secrets(f"provider credential={secret}")

        self.assertNotIn(secret, result)
        self.assertIn("[REDACTED]", result)

    def test_environment_secret_redacted(self) -> None:
        with patch.dict(
            os.environ,
            {"MISTRAL_API_KEY": "mistral-test-secret-123456"},
        ):
            result = redact_secrets(
                "value=mistral-test-secret-123456"
            )
        self.assertNotIn("mistral-test-secret-123456", result)


if __name__ == "__main__":
    unittest.main()
