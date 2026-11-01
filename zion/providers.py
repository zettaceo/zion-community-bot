"""Explicit completion boundary for offline evaluation and future runtime wiring.

No provider is activated by importing this module. Runtime continues to use its
current Mistral path until price, privacy and quality acceptance is complete.
No model may execute tools or choose moderation actions through this boundary.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from .secret_store import SecretStore, SecretStoreError


class ProviderError(RuntimeError):
    """A fixed error code only: never response bodies, headers or input text."""


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cached_input_tokens: int = 0


class CompletionProvider(Protocol):
    @property
    def configured(self) -> bool: ...

    async def complete(self, messages: list[dict[str, str]], *, max_tokens: int) -> Completion: ...


class MistralCompletionProvider:
    """Uses the existing provider's pacing, fixed endpoint and protected store."""
    def __init__(self, client):
        self.client = client

    @property
    def configured(self) -> bool:
        return self.client.configured

    async def complete(self, messages: list[dict[str, str]], *, max_tokens: int) -> Completion:
        result = await self.client._chat(messages, max_tokens=max_tokens)
        return Completion(result.text, result.model, result.input_tokens,
                          result.output_tokens, result.latency_ms)


class KimiCompletionProvider:
    """Text-only, no tools, no hidden-reasoning export, no automatic retry.

    A timeout/5xx is an uncertain charge: callers must reserve before sending
    and retain that reservation on failure. Automatic fallback is not safe here.
    Numeric prices and live eligibility are deliberately not inferred.
    """
    CHAT_URL = 'https://api.moonshot.ai/v1/chat/completions'
    MODELS_URL = 'https://api.moonshot.ai/v1/models'
    MODELS = frozenset({'kimi-k2.6', 'kimi-k3'})
    RESPONSE_LIMIT = 1024 * 1024

    def __init__(self, store: SecretStore, *, model: str,
                 transport: httpx.AsyncBaseTransport | None = None):
        if model not in self.MODELS:
            raise ValueError('unreviewed Kimi model')
        self.store = store
        self.model = model
        self._transport = transport

    @property
    def configured(self) -> bool:
        return self.store.status() == SecretStore.PRIVATE

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=httpx.Timeout(45.0), follow_redirects=False,
                                 trust_env=False, transport=self._transport)

    @staticmethod
    def _status(status: int) -> None:
        if status == 200:
            return
        if status in (401, 403):
            raise ProviderError('credential_rejected')
        if status == 429:
            raise ProviderError('rate_limited')
        if 300 <= status < 400:
            raise ProviderError('redirect_rejected')
        raise ProviderError('provider_unavailable')

    async def validate_candidate(self, candidate: str) -> None:
        try:
            candidate = SecretStore.normalize_candidate(candidate)
            async with self._client() as client:
                async with client.stream('GET', self.MODELS_URL,
                                         headers={'Authorization': 'Bearer ' + candidate}) as response:
                    self._status(response.status_code)
        except (httpx.HTTPError, SecretStoreError):
            raise ProviderError('credential_validation_unavailable') from None

    async def complete(self, messages: list[dict[str, str]], *, max_tokens: int) -> Completion:
        if type(max_tokens) is not int or not 1 <= max_tokens <= 4096:
            raise ValueError('invalid completion limit')
        if not 1 <= len(messages) <= 16 or any(
            set(m) != {'role', 'content'} or m['role'] not in {'system', 'user', 'assistant'}
            or not isinstance(m['content'], str) for m in messages
        ):
            raise ValueError('invalid completion messages')
        if sum(len(m['content'].encode('utf-8')) for m in messages) > 48000:
            raise ValueError('completion input exceeds bound')
        try:
            credential = self.store.read()
            if not credential:
                raise ProviderError('credential_missing')
        except SecretStoreError:
            raise ProviderError('credential_unsafe') from None
        payload = {'model': self.model, 'messages': messages, 'max_tokens': max_tokens,
                   'stream': False}
        if self.model == 'kimi-k2.6':
            payload['thinking'] = {'type': 'disabled'}
        else:
            payload['reasoning_effort'] = 'low'
        started = time.monotonic()
        try:
            async with self._client() as client:
                async with client.stream('POST', self.CHAT_URL, json=payload,
                                         headers={'Authorization': 'Bearer ' + credential}) as response:
                    self._status(response.status_code)
                    body = bytearray()
                    async for part in response.aiter_bytes():
                        body.extend(part)
                        if len(body) > self.RESPONSE_LIMIT:
                            raise ProviderError('response_too_large')
            data = json.loads(body)
            choices = data['choices']
            if len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
                raise ProviderError('incomplete_response')
            message = choices[0]['message']
            if message.get('tool_calls') or message.get('function_call'):
                raise ProviderError('tool_call_rejected')
            text = message['content']
            usage = data['usage']
            prompt, completion = usage['prompt_tokens'], usage['completion_tokens']
            cached = usage.get('prompt_tokens_details', {}).get('cached_tokens',
                               usage.get('cached_tokens', 0))
            if any(type(n) is not int or n < 0 for n in (prompt, completion, cached)):
                raise ProviderError('invalid_usage')
            if cached > prompt or completion > max_tokens or prompt > 60000:
                raise ProviderError('invalid_usage')
            if not isinstance(text, str) or not text.strip() or len(text) > 32000:
                raise ProviderError('invalid_content')
            if data.get('model') != self.model:
                raise ProviderError('model_mismatch')
            return Completion(text, self.model, prompt, completion,
                              int((time.monotonic() - started) * 1000), cached)
        except (httpx.HTTPError, UnicodeError, ValueError, KeyError, TypeError, IndexError):
            raise ProviderError('invalid_or_unavailable_response') from None
