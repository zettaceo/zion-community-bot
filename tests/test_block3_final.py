from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from telegram.ext import ApplicationHandlerStop

from tests.helpers import make_settings
from tests.test_guardian_surface import FakeBot, FakeContext, make_update
from zion.telegram_app import (
    Runtime, command_idempotency_guard_handler, moderation_handler,
    telegram_entity_link_evidence,
)


class UniversalSecretSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / 'knowledge').mkdir()
        self.runtime = Runtime(make_settings(root))
        self.addCleanup(self.runtime.close)

    def check_hidden_secret(self, *, url, prefix_count=0, surface='entities', command=False):
        bot = FakeBot()
        context = FakeContext(self.runtime, bot)
        update = make_update(user_id=1, chat_type='private',
                             text='/status' if command else 'safe label')
        message = update.effective_message
        prefix = [SimpleNamespace(type='text_link', url=f'https://safe.example/{i}')
                  for i in range(prefix_count)]
        hidden = SimpleNamespace(type='text_link', url=url)
        message.entities = prefix
        if surface == 'entities':
            message.entities.append(hidden)
        elif surface == 'caption_entities':
            message.caption_entities = [hidden]
        else:
            button = SimpleNamespace(url=None, login_url=None, web_app=None)
            if surface == 'button':
                button.url = url
            else:
                setattr(button, surface, SimpleNamespace(url=url))
            message.reply_markup = SimpleNamespace(inline_keyboard=[[button]])
        with patch.object(self.runtime.db, 'claim_idempotency_key',
                          side_effect=AssertionError('secret must precede claim')) as claim:
            if command:
                with self.assertRaises(ApplicationHandlerStop):
                    asyncio.run(command_idempotency_guard_handler(update, context))
            else:
                asyncio.run(moderation_handler(update, context))
            claim.assert_not_called()
        self.assertEqual(bot.deleted, [(update.effective_chat.id, message.message_id)])
        self.assertEqual(bot.member_calls, 0)
        # Only IDs/classification may be persisted, never the hidden URL/value.
        dump = '\n'.join(self.runtime.db._conn.iterdump())
        self.assertNotIn('synthetic-credential-123456', dump)
        self.assertNotIn(url, dump)
        return message

    def test_private_secret_after_twenty_links_is_not_skipped(self):
        for surface in ('entities', 'caption_entities', 'button', 'login_url', 'web_app'):
            for command in (False, True):
                with self.subTest(surface=surface, command=command):
                    message = self.check_hidden_secret(
                        url='https://safe.example/?api_key=synthetic-credential-123456',
                        prefix_count=20, surface=surface, command=command)
                    _, reasons = telegram_entity_link_evidence(message)
                    self.assertIn('too-many-link-entities', reasons)

    def test_double_encoded_hidden_credential_is_detected_before_claim(self):
        self.check_hidden_secret(
            url='https://safe.example/?api%255Fkey%253Dsynthetic-credential-123456',
            command=True)

    def test_hidden_credential_after_policy_url_prefix_is_not_truncated(self):
        self.check_hidden_secret(
            url='https://safe.example/' + 'a' * 2100 + '?api_key=synthetic-credential-123456')

    def test_non_http_userinfo_credential_is_protected_in_private_chat(self):
        for scheme in ('ftp', 'custom'):
            with self.subTest(scheme=scheme):
                self.check_hidden_secret(
                    url=f'{scheme}://user:synthetic-credential-123456@safe.example/')

    def test_double_encoded_visible_url_credential_is_protected(self):
        bot = FakeBot()
        context = FakeContext(self.runtime, bot)
        update = make_update(user_id=2, chat_type='private', text=(
            'https://safe.example/?api%255Fkey%253Dsynthetic-credential-123456'))
        asyncio.run(moderation_handler(update, context))
        self.assertEqual(bot.deleted, [(123, 1)])

    def test_non_http_userinfo_is_redacted_in_logs(self):
        from zion.logging_safe import redact_secrets
        for scheme in ('ftp', 'custom'):
            text = f'{scheme}://user:synthetic-credential-123456@safe.example/'
            self.assertNotIn('synthetic-credential-123456', redact_secrets(text))
            self.assertIn('[REDACTED]', redact_secrets(text))
