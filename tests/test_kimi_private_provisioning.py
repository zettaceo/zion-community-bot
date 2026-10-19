import asyncio
import time
import unittest
from unittest.mock import AsyncMock, patch
from telegram.ext import ApplicationHandlerStop
from tests import test_mistral_private_provisioning as fixtures
from tests.test_mistral_private_provisioning import (
    FakeContext, FakeBot, make_update, SECRET_A, SECRET_B)
from zion.kimi_provisioning import (set_kimi_key_command, kimi_secret_capture_handler,
                                  cancel_kimi_key_command, kimi_status_command)
from zion.secret_store import SecretStore
from zion.telegram_app import set_mistral_key_command, command_idempotency_guard_handler


class KimiProvisioningTests(unittest.TestCase):
    def setUp(self):
        fixtures.MistralPrivateProvisioningTests.setUp(self)
        self.settings.mistral_secret_path.parent.mkdir(mode=0o700, exist_ok=True)

    tearDown = fixtures.MistralPrivateProvisioningTests.tearDown

    def arm(self):
        ctx = FakeContext(self.rt)
        asyncio.run(set_kimi_key_command(make_update(user_id=1), ctx))
        return ctx

    def capture(self, ctx, text=SECRET_A):
        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(kimi_secret_capture_handler(make_update(user_id=1, message_id=2, text=text), ctx))

    def test_deletes_before_validation_and_persists_without_activation_or_secret_audit(self):
        ctx = self.arm()
        async def validate(candidate):
            self.assertIn((1001, 2), ctx.bot.deleted)
            self.assertEqual(self.rt.kimi_secret_store.status(), SecretStore.MISSING)
        self.rt.kimi_provisioning_client.validate_candidate = AsyncMock(side_effect=validate)
        self.capture(ctx)
        self.assertEqual(self.rt.kimi_secret_store.read(), SECRET_A)
        self.assertNotIn(SECRET_A, '\n'.join(self.rt.db._conn.iterdump()))
        self.assertNotIn(SECRET_A, str(ctx.bot.sent))
        self.assertIn('Ativação nas conversas: NÃO', ctx.bot.sent[-1][1])
        self.assertEqual(self.rt.secret_store.status(), SecretStore.MISSING)

    def test_delete_failure_prevents_validation_and_write(self):
        ctx = self.arm(); ctx.bot = FakeBot(delete_ok=False)
        self.rt.kimi_provisioning_client.validate_candidate = AsyncMock()
        self.capture(ctx)
        self.rt.kimi_provisioning_client.validate_candidate.assert_not_awaited()
        self.assertEqual(self.rt.kimi_secret_store.status(), SecretStore.MISSING)

    def test_private_explicit_operator_only(self):
        for user, chat_type in ((2, 'private'), (1, 'supergroup')):
            asyncio.run(set_kimi_key_command(make_update(user_id=user, chat_type=chat_type), FakeContext(self.rt)))
        self.assertFalse(self.rt.kimi_secret_captures)

    def test_expired_capture_is_deleted_not_sent_to_normal_pipeline(self):
        ctx = self.arm(); self.rt.kimi_secret_captures[(1001, 1)] = time.monotonic()-1
        self.rt.kimi_provisioning_client.validate_candidate = AsyncMock()
        self.capture(ctx)
        self.assertIn((1001, 2), ctx.bot.deleted)
        self.rt.kimi_provisioning_client.validate_candidate.assert_not_awaited()

    def test_validation_failure_preserves_previous_key_and_hides_exception(self):
        self.rt.kimi_secret_store.write_atomic(SECRET_B)
        ctx = self.arm()
        self.rt.kimi_provisioning_client.validate_candidate = AsyncMock(side_effect=RuntimeError(SECRET_A))
        self.capture(ctx)
        self.assertEqual(self.rt.kimi_secret_store.read(), SECRET_B)
        self.assertNotIn(SECRET_A, str(ctx.bot.sent))

    def test_audit_failure_rolls_back_rotation(self):
        self.rt.kimi_secret_store.write_atomic(SECRET_B)
        ctx = self.arm(); self.rt.kimi_provisioning_client.validate_candidate = AsyncMock()
        with patch('zion.kimi_provisioning._audit', side_effect=RuntimeError()):
            self.capture(ctx)
        self.assertEqual(self.rt.kimi_secret_store.read(), SECRET_B)

    def test_mutually_exclusive_capture_and_cancel(self):
        ctx = self.arm()
        asyncio.run(set_mistral_key_command(make_update(user_id=1), ctx))
        self.assertFalse(self.rt.kimi_secret_captures)
        asyncio.run(set_kimi_key_command(make_update(user_id=1), ctx))
        self.assertFalse(self.rt.mistral_secret_captures)
        asyncio.run(cancel_kimi_key_command(make_update(user_id=1), ctx))
        self.assertFalse(self.rt.kimi_secret_captures)

    def test_command_argument_deleted_before_durable_command_claim(self):
        ctx = FakeContext(self.rt)
        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(command_idempotency_guard_handler(make_update(user_id=1, text='/setkimikey '+SECRET_A), ctx))
        self.assertIn((1001, 1), ctx.bot.deleted)
        self.assertNotIn(SECRET_A, '\n'.join(self.rt.db._conn.iterdump()))
