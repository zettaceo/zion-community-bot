from __future__ import annotations

import asyncio
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx

from tests.helpers import make_settings
from zion.mistral import (
    MistralClient,
    MistralCredentialInvalid,
    MistralCredentialValidationUnavailable,
)
from zion.secret_store import SecretStore


OLD_SECRET = "synthetic-mistral-old-material-123456"
NEW_SECRET = "synthetic-mistral-new-material-654321"


class FakeResponse:
    def __init__(self, status_code: int, payload=None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        import json
        self.content = json.dumps(self._payload).encode('utf-8')

    def json(self):
        return self._payload


class FakeHTTPClient:
    def __init__(
        self,
        *,
        get_status: int = 200,
        get_error: Exception | None = None,
        post_payload=None,
    ) -> None:
        self.get_status = get_status
        self.get_error = get_error
        self.post_payload = post_payload or {
            "model": "synthetic-model",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
            },
        }
        self.auth_headers: list[str] = []
        self.get_urls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, *, headers):
        self.get_urls.append(str(url))
        self.auth_headers.append(headers["Authorization"])
        if self.get_error is not None:
            raise self.get_error
        return FakeResponse(self.get_status)

    async def post(self, url, *, headers, json):
        self.auth_headers.append(headers["Authorization"])
        return FakeResponse(200, self.post_payload)


class MistralSecretIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = replace(
            make_settings(self.root),
            ai_enabled=True,
        )
        self.settings.mistral_secret_path.parent.parent.mkdir(
            mode=0o700,
            exist_ok=True,
        )
        self.store = SecretStore(self.settings.mistral_secret_path)
        self.client = MistralClient(self.settings, self.store)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_missing_secret_keeps_provider_unconfigured(self) -> None:
        self.assertFalse(self.client.configured)

    def test_secret_appears_and_clears_without_restart(self) -> None:
        self.store.write_atomic(OLD_SECRET)
        self.assertTrue(self.client.configured)

        self.store.clear()
        self.assertFalse(self.client.configured)

    def test_next_provider_call_uses_rotated_secret(self) -> None:
        self.store.write_atomic(OLD_SECRET)
        first = FakeHTTPClient()
        with patch("zion.mistral.httpx.AsyncClient", return_value=first):
            asyncio.run(
                self.client._chat(
                    [{"role": "user", "content": "first"}],
                )
            )
        self.assertEqual(
            first.auth_headers,
            [f"Bearer {OLD_SECRET}"],
        )

        self.store.write_atomic(NEW_SECRET)
        second = FakeHTTPClient()
        with patch("zion.mistral.httpx.AsyncClient", return_value=second):
            asyncio.run(
                self.client._chat(
                    [{"role": "user", "content": "second"}],
                )
            )
        self.assertEqual(
            second.auth_headers,
            [f"Bearer {NEW_SECRET}"],
        )

    def test_official_models_endpoint_accepts_valid_key(self) -> None:
        fake = FakeHTTPClient(get_status=200)
        with patch(
            "zion.mistral.httpx.AsyncClient",
            return_value=fake,
        ) as client_factory:
            asyncio.run(self.client.validate_api_key(NEW_SECRET))

        self.assertEqual(
            fake.get_urls,
            ["https://api.mistral.ai/v1/models"],
        )
        self.assertEqual(fake.auth_headers, [f"Bearer {NEW_SECRET}"])
        self.assertFalse(
            client_factory.call_args.kwargs["follow_redirects"]
        )

    def test_401_rejects_candidate_without_writing_store(self) -> None:
        fake = FakeHTTPClient(get_status=401)
        with patch("zion.mistral.httpx.AsyncClient", return_value=fake):
            with self.assertRaises(MistralCredentialInvalid):
                asyncio.run(self.client.validate_api_key(NEW_SECRET))
        self.assertIsNone(self.store.read())

    def test_429_is_validation_unavailable_not_invalid(self) -> None:
        fake = FakeHTTPClient(get_status=429)
        with patch("zion.mistral.httpx.AsyncClient", return_value=fake):
            with self.assertRaises(MistralCredentialValidationUnavailable):
                asyncio.run(self.client.validate_api_key(NEW_SECRET))

    def test_provider_500_is_validation_unavailable(self) -> None:
        fake = FakeHTTPClient(get_status=500)
        with patch("zion.mistral.httpx.AsyncClient", return_value=fake):
            with self.assertRaises(MistralCredentialValidationUnavailable):
                asyncio.run(self.client.validate_api_key(NEW_SECRET))

    def test_network_timeout_is_validation_unavailable(self) -> None:
        fake = FakeHTTPClient(
            get_error=httpx.ReadTimeout("synthetic timeout")
        )
        with patch("zion.mistral.httpx.AsyncClient", return_value=fake):
            with self.assertRaises(MistralCredentialValidationUnavailable):
                asyncio.run(self.client.validate_api_key(NEW_SECRET))


if __name__ == "__main__":
    unittest.main()
