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

    def test_replayed_capture_is_blocked_after_runtime_restart(self):
        ctx = self.arm()
        self.rt.kimi_provisioning_client.validate_candidate = AsyncMock(side_effect=RuntimeError())
        self.capture(ctx)
        self.rt.close()
        self.rt = fixtures.Runtime(self.settings)
        ctx = FakeContext(self.rt)
        self.rt.kimi_provisioning_client.validate_candidate = AsyncMock()
        self.capture(ctx)
        self.rt.kimi_provisioning_client.validate_candidate.assert_not_awaited()
        self.assertNotIn(SECRET_A, '\n'.join(self.rt.db._conn.iterdump()))

    def test_first_candidate_after_restart_is_deleted_without_validation(self):
        self.arm()
        self.rt.close()
        self.rt = fixtures.Runtime(self.settings)
        ctx = FakeContext(self.rt)
        self.rt.kimi_provisioning_client.validate_candidate = AsyncMock()
        self.capture(ctx)
        self.assertIn((1001, 2), ctx.bot.deleted)
        self.rt.kimi_provisioning_client.validate_candidate.assert_not_awaited()
        self.assertEqual(self.rt.kimi_secret_store.status(), SecretStore.MISSING)
        self.assertIn('expirada', ctx.bot.sent[-1][1])
        self.assertNotIn(SECRET_A, '\n'.join(self.rt.db._conn.iterdump()))
        self.assertEqual(self.rt.db.get_setting('kimi_pending_capture:1001:1'), 'closed')
        # The consumed message is still blocked after its latch is closed.
        self.capture(ctx)
        # A distinct ordinary message is no longer swallowed.
        asyncio.run(kimi_secret_capture_handler(
            make_update(user_id=1, message_id=3, text='Olá'), ctx))

    def test_restart_requires_fresh_command_to_authorize_storage(self):
        self.arm()
        self.rt.close()
        self.rt = fixtures.Runtime(self.settings)
        ctx = self.arm()
        self.rt.kimi_provisioning_client.validate_candidate = AsyncMock()
        self.capture(ctx)
        self.rt.kimi_provisioning_client.validate_candidate.assert_awaited_once()
        self.assertEqual(self.rt.kimi_secret_store.read(), SECRET_A)

    def test_pending_write_failure_never_invites_secret_submission(self):
        ctx = FakeContext(self.rt)
        update = make_update(user_id=1)
        with patch.object(self.rt.db, 'set_setting', side_effect=RuntimeError(SECRET_A)):
            asyncio.run(set_kimi_key_command(update, ctx))
        self.assertFalse(self.rt.kimi_secret_captures)
        self.assertNotIn(SECRET_A, str(update.effective_message.replies))

    def test_latch_clear_failure_deletes_and_does_not_validate(self):
        ctx = self.arm()
        self.rt.kimi_provisioning_client.validate_candidate = AsyncMock()
        with patch.object(self.rt.db, 'set_setting', side_effect=RuntimeError()):
            self.capture(ctx)
        self.assertIn((1001, 2), ctx.bot.deleted)
        self.rt.kimi_provisioning_client.validate_candidate.assert_not_awaited()
        self.assertEqual(self.rt.db.get_setting('kimi_pending_capture:1001:1'), 'pending')

    def test_cancel_and_other_provider_clear_latch_durably(self):
        for command in (cancel_kimi_key_command, set_mistral_key_command):
            ctx = self.arm()
            asyncio.run(command(make_update(user_id=1), ctx))
            self.assertEqual(self.rt.db.get_setting('kimi_pending_capture:1001:1'), 'closed')
            self.assertFalse(self.rt.kimi_secret_captures)

    def test_marker_failure_blocks_provider_and_storage(self):
        ctx = self.arm()
        self.rt.kimi_provisioning_client.validate_candidate = AsyncMock()
        with patch.object(self.rt.db, 'claim_idempotency_key', side_effect=RuntimeError()):
            self.capture(ctx)
        self.rt.kimi_provisioning_client.validate_candidate.assert_not_awaited()
        self.assertEqual(self.rt.kimi_secret_store.status(), SecretStore.MISSING)
        self.assertIn((1001, 2), ctx.bot.deleted)

    def test_marker_expiration_does_not_extend_on_read(self):
        self.rt.db.claim_idempotency_key('synthetic-marker', ttl_seconds=60, now=100)
        self.assertTrue(self.rt.db.has_active_idempotency_key('synthetic-marker', now=159))
        self.assertFalse(self.rt.db.has_active_idempotency_key('synthetic-marker', now=160))

    def test_command_argument_deleted_before_durable_command_claim(self):
        ctx = FakeContext(self.rt)
        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(command_idempotency_guard_handler(make_update(user_id=1, text='/setkimikey '+SECRET_A), ctx))
        self.assertIn((1001, 1), ctx.bot.deleted)
        self.assertNotIn(SECRET_A, '\n'.join(self.rt.db._conn.iterdump()))
