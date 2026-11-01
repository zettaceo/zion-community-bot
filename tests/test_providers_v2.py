from __future__ import annotations

import asyncio
import json
import os
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from zion.provider_secrets import ProviderSecretStore
from zion.providers import KimiCompletionProvider, ProviderError
from zion.secret_store import SecretStore, SecretStoreError


class ProviderSecretsTests(unittest.TestCase):
    def test_separate_provider_atomic_rotation_and_minimal_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            stores = ProviderSecretStore(Path(tmp) / 'secrets')
            kimi, mistral = stores.for_provider('kimi'), stores.for_provider('mistral')
            old, new, other = [secrets.token_urlsafe(32) for _ in range(3)]
            kimi.write_atomic(old); mistral.write_atomic(other)
            kimi.write_atomic(new)
            self.assertEqual(kimi.read(), new)
            self.assertEqual(mistral.read(), other)
            self.assertEqual(stores.statuses(), {'mistral': 'PRIVATE', 'kimi': 'PRIVATE'})
            self.assertEqual(kimi.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(kimi.directory.stat().st_mode & 0o777, 0o700)
            with self.assertRaises(SecretStoreError):
                kimi.write_atomic('bad')
            self.assertEqual(kimi.read(), new)
            with self.assertRaises(ValueError):
                stores.for_provider('../../outside')

    def test_provider_store_rejects_symlink_hardlink_mode_and_wrong_owner(self):
        for attack in ('symlink', 'hardlink', 'mode', 'owner', 'directory'):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); stores = ProviderSecretStore(root / 'secrets')
                store = stores.for_provider('kimi'); store.write_atomic(secrets.token_urlsafe(32))
                if attack == 'symlink':
                    moved = root / 'moved'; store.path.rename(moved); store.path.symlink_to(moved)
                elif attack == 'hardlink':
                    os.link(store.path, root / 'alias')
                elif attack == 'mode':
                    store.path.chmod(0o644)
                elif attack == 'owner':
                    store = ProviderSecretStore(root / 'secrets', expected_uid=os.getuid()+1).for_provider('kimi')
                else:
                    store.directory.chmod(0o755)
                self.assertEqual(store.status(), SecretStore.UNSAFE)
                with self.assertRaises(SecretStoreError):
                    store.read()

    def test_rotation_rolls_back_after_sync_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ProviderSecretStore(Path(tmp) / 'secrets').for_provider('kimi')
            original = secrets.token_urlsafe(32); store.write_atomic(original)
            sync = store._fsync_directory; calls = 0
            def fail_once():
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise SecretStoreError('test storage failure')
                sync()
            with patch.object(store, '_fsync_directory', side_effect=fail_once):
                with self.assertRaises(SecretStoreError):
                    store.write_atomic(secrets.token_urlsafe(32))
            self.assertEqual(store.read(), original)


class KimiTransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = ProviderSecretStore(Path(self.temp.name) / 'secrets').for_provider('kimi')
        self.candidate = secrets.token_urlsafe(32)
        self.store.write_atomic(self.candidate)

    def response(self):
        return {'model': 'kimi-k2.6', 'choices': [{'finish_reason': 'stop', 'message': {
            'content': 'Resposta pública.', 'reasoning_content': 'NEVER_RETURN_REASONING'}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'cached_tokens': 3}}

    async def test_official_endpoint_parameters_and_reasoning_not_returned(self):
        calls = []
        async def respond(request):
            calls.append(request)
            return httpx.Response(200, json=self.response())
        client = KimiCompletionProvider(self.store, model='kimi-k2.6', transport=httpx.MockTransport(respond))
        result = await client.complete([{'role': 'user', 'content': 'Pergunta sintética'}], max_tokens=128)
        self.assertEqual(str(calls[0].url), client.CHAT_URL)
        data = json.loads(calls[0].content)
        self.assertEqual(data['thinking'], {'type': 'disabled'})
        self.assertNotIn('temperature', data)
        self.assertNotIn('tools', data)
        self.assertNotIn('NEVER_RETURN_REASONING', repr(result))
        self.assertNotIn(self.candidate, repr(result))
        self.assertEqual(result.cached_input_tokens, 3)
        self.assertEqual(len(calls), 1)

    async def test_http_failures_never_echo_provider_body_or_retry(self):
        for code in (302, 400, 401, 403, 429, 500, 503):
            with self.subTest(code=code):
                calls = []
                async def respond(request):
                    calls.append(request)
                    return httpx.Response(code, text=self.candidate, headers={'Location': 'https://attacker.invalid'})
                client = KimiCompletionProvider(self.store, model='kimi-k3', transport=httpx.MockTransport(respond))
                with self.assertRaises(ProviderError) as error:
                    await client.complete([{'role': 'user', 'content': 'synthetic'}], max_tokens=20)
                self.assertNotIn(self.candidate, str(error.exception))
                self.assertEqual(len(calls), 1)

    async def test_rejects_missing_usage_tool_calls_truncation_model_drift(self):
        for fault in ('usage', 'tool', 'truncated', 'model', 'negative', 'boolean', 'over_limit'):
            with self.subTest(fault=fault):
                data = self.response()
                if fault == 'usage': del data['usage']
                if fault == 'tool': data['choices'][0]['message']['tool_calls'] = [{'name': 'delete'}]
                if fault == 'truncated': data['choices'][0]['finish_reason'] = 'length'
                if fault == 'model': data['model'] = 'unreviewed'
                if fault == 'negative': data['usage']['prompt_tokens'] = -1
                if fault == 'boolean': data['usage']['prompt_tokens'] = True
                if fault == 'over_limit': data['usage']['completion_tokens'] = 129
                client = KimiCompletionProvider(self.store, model='kimi-k2.6',
                    transport=httpx.MockTransport(lambda request: httpx.Response(200, json=data)))
                with self.assertRaises(ProviderError):
                    await client.complete([{'role': 'user', 'content': 'synthetic'}], max_tokens=128)

    async def test_bad_input_does_not_send_or_read_secret(self):
        client = KimiCompletionProvider(self.store, model='kimi-k2.6',
            transport=httpx.MockTransport(lambda request: self.fail('network attempted')))
        with patch.object(self.store, 'read', side_effect=AssertionError('credential read')):
            with self.assertRaises(ValueError):
                await client.complete([{'role': 'tool', 'content': 'x'}], max_tokens=128)
            with self.assertRaises(ValueError):
                await client.complete([{'role': 'user', 'content': 'x'*48001}], max_tokens=128)
            with self.assertRaises(ValueError):
                await client.complete([{'role': 'user', 'content': 'x'}], max_tokens=0)

    async def test_timeout_and_oversized_response_are_sanitized(self):
        async def timeout(request):
            raise httpx.ReadTimeout(self.candidate)
        for handler in (timeout, lambda request: httpx.Response(200, content=b'x'*(1024*1024+1))):
            client = KimiCompletionProvider(self.store, model='kimi-k2.6', transport=httpx.MockTransport(handler))
            with self.assertRaises(ProviderError) as error:
                await client.complete([{'role': 'user', 'content': 'synthetic'}], max_tokens=128)
            self.assertNotIn(self.candidate, str(error.exception))
