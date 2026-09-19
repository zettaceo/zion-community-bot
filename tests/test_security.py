from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from zion.ai_service import sanitize_for_ai
from zion.logging_safe import redact_secrets


class SecurityTests(unittest.TestCase):
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
