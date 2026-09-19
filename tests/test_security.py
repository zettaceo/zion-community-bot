from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from zion.ai_service import sanitize_for_ai
from zion.logging_safe import configure_logging, redact_secrets


class SecurityTests(unittest.TestCase):
    def test_log_file_permissions_are_private(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "zion.log"
            configure_logging(path)
            mode = stat.S_IMODE(path.stat().st_mode)
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
