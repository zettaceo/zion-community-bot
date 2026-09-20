from __future__ import annotations

import ast
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from telegram.constants import ChatMemberStatus
from telegram.ext import ApplicationHandlerStop

from tests.helpers import make_settings
from tests import test_guardian_surface as surface_tests
from tests.test_guardian_surface import (
    FakeBot, FakeContext, make_update,
)
from tests.test_raid_guardian import update_for, member
from zion.models import FloodDecision, OperatingState
from zion import telegram_app as app


class FinalGuardianReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'knowledge').mkdir()
        self.runtime = app.Runtime(make_settings(self.root))
        self.addCleanup(lambda: self.runtime.close())

    def test_failed_flood_mute_is_not_announced_as_success(self):
        bot = FakeBot()
        bot.restrict_chat_member = AsyncMock(side_effect=RuntimeError('simulated API failure'))
        context = FakeContext(self.runtime, bot)
        update = make_update(user_id=2, chat_type='supergroup', text='flood')
        self.runtime.db.set_containment(-100123, 2, 9999999999, 'flood')
        asyncio.run(app._enforce_flood(update, context, FloodDecision(
            triggered=True, strike_count=1, mute_seconds=60)))
        notice = bot.sent[-1][1]
        self.assertNotIn('silenciado por', notice)
        self.assertIn('falhou', notice)
        self.assertGreater(self.runtime.db.containment_until(-100123, 2), 0)
        action = self.runtime.db._conn.execute('SELECT success FROM actions').fetchone()
        self.assertEqual(action[0], 0)

    def test_ama_open_confirmation_cannot_inject_admin_fields(self):
        bot = FakeBot()
        context = FakeContext(self.runtime, bot)
        title = 'Topic\nID: forged\u202eADMIN'
        context.args = [title]
        update = make_update(user_id=1, chat_type='supergroup', text='/amaopen topic')
        asyncio.run(app.ama_open_command(update, context))
        reply = update.effective_message.replies[0]
        self.assertNotIn('\nID: forged', reply)
        self.assertNotIn('\u202e', reply)
        self.assertEqual(self.runtime.db.active_ama(-100123)['title'], title)

    def test_private_messages_skip_all_community_controls_in_every_state(self):
        bot = FakeBot()
        context = FakeContext(self.runtime, bot)
        self.runtime.db.set_containment(123, 2, 9999999999, 'test')
        for state in (OperatingState.NORMAL, OperatingState.ELEVATED,
                      OperatingState.ATTACK, OperatingState.LOCKDOWN):
            self.runtime.db.set_operating_state(state)
            for handler in (app.command_guard_handler, app.moderation_handler):
                with self.subTest(state=state, handler=handler.__name__):
                    update = make_update(user_id=2, chat_type='private',
                                         text='/ask https://untrusted.example/' )
                    with patch.object(self.runtime.guardian, 'record_message', side_effect=AssertionError), \
                         patch.object(self.runtime.guardian, 'containment_remaining', side_effect=AssertionError), \
                         patch.object(self.runtime.guardian, 'evaluate_links', side_effect=AssertionError):
                        asyncio.run(handler(update, context))
        self.assertEqual(bot.deleted + bot.banned + bot.restricted, [])
        self.assertEqual(bot.member_calls, 0)

    def test_private_secret_matrix_still_deletes_before_exemptions(self):
        secrets = [
            'API key: synthetic-credential-123456',
            'Authorization: Bearer synthetic-credential-123456',
            'password: synthetic-credential-123456',
            'access_token=synthetic-credential-123456',
            'seed phrase:\n' + ' '.join(['example'] * 12),
            'private key: ' + 'a' * 64,
            'private key: ' + '3' * 88,
            'private key: [' + ','.join(['7'] * 64) + ']',
            '-----BEGIN ' + 'OPENSSH PRIVATE KEY-----\nexample\n-----END ' + 'OPENSSH PRIVATE KEY-----',
            'ＡＰＩ ｋｅｙ: synthetic-credential-123456',
            'api\u200b_key=synthetic-credential-123456',
        ]
        self.runtime.db.set_operating_state(OperatingState.LOCKDOWN)
        for i, secret in enumerate(secrets, start=100):
            with self.subTest(case=i):
                bot = FakeBot()
                context = FakeContext(self.runtime, bot)
                update = make_update(user_id=1, chat_type='private', text=secret, message_id=i)
                asyncio.run(app.moderation_handler(update, context))
                self.assertEqual(bot.deleted, [(123, i)])
                self.assertEqual(bot.member_calls, 0)
                self.assertNotIn(secret, '\n'.join(self.runtime.db._conn.iterdump()))

    def test_all_global_commands_reject_group_admin(self):
        bot = FakeBot(ChatMemberStatus.ADMINISTRATOR)
        context = FakeContext(self.runtime, bot)
        for name in surface_tests.CommandAuthorizationContractTests.OPERATOR_ONLY:
            with self.subTest(command=name):
                update = make_update(user_id=2, chat_type='supergroup', text='/status')
                asyncio.run(getattr(app, name)(update, context))
                self.assertIn('operadores explícitos', update.effective_message.replies[0])
        self.assertEqual(bot.member_calls, 0)

    def test_admin_membership_failure_does_not_use_positive_cache(self):
        bot = FakeBot(ChatMemberStatus.ADMINISTRATOR)
        context = FakeContext(self.runtime, bot)
        update = make_update(user_id=2, chat_type='supergroup', text='/ban')
        self.assertTrue(asyncio.run(app.is_admin(update, context)))
        bot.get_chat_member = AsyncMock(side_effect=RuntimeError('membership unavailable'))
        self.assertFalse(asyncio.run(app.require_admin(update, context)))
        bot.get_chat_member.assert_awaited_once()

    def test_secret_delete_retries_after_preclaim_audit_failure(self):
        bot = FakeBot()
        context = FakeContext(self.runtime, bot)
        update = make_update(user_id=1, chat_type='private',
                             text='/status API key: synthetic-credential-123456')
        with patch.object(self.runtime.db, 'create_incident', side_effect=RuntimeError('crash')), \
             patch.object(self.runtime.db, 'claim_idempotency_key', side_effect=AssertionError) as claim:
            with self.assertRaises(RuntimeError):
                asyncio.run(app.command_idempotency_guard_handler(update, context))
            claim.assert_not_called()
        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(app.command_idempotency_guard_handler(update, context))
        self.assertEqual(bot.deleted, [(123, 1), (123, 1)])
        self.assertEqual(self.runtime.db._conn.execute('SELECT COUNT(*) FROM idempotency_keys').fetchone()[0], 0)

    def test_normal_command_claim_survives_runtime_restart(self):
        update = make_update(user_id=1, chat_type='private', text='/status')
        context = FakeContext(self.runtime, FakeBot())
        asyncio.run(app.command_idempotency_guard_handler(update, context))
        self.runtime.close()
        self.runtime = app.Runtime(make_settings(self.root))
        context = FakeContext(self.runtime, FakeBot())
        with self.assertRaises(ApplicationHandlerStop):
            asyncio.run(app.command_idempotency_guard_handler(update, context))

    def test_join_atomic_failure_is_retriable_without_onboarding(self):
        bot = FakeBot()
        context = FakeContext(self.runtime, bot)
        update = update_for(*[member(i) for i in range(10, 18)])
        with patch.object(self.runtime.db, 'record_action', side_effect=RuntimeError('audit failure')):
            asyncio.run(app.welcome_handler(update, context))
        self.assertEqual(update.effective_message.replies, [])
        self.assertEqual(bot.sent, [])
        self.assertEqual(self.runtime.db.count_user_events(chat_id=-100500, event_type='joined', since=0), 0)
        self.assertEqual(self.runtime.db.get_operating_state(), OperatingState.NORMAL)
        asyncio.run(app.welcome_handler(update, context))
        self.assertEqual(self.runtime.db.get_operating_state(), OperatingState.ELEVATED)
        self.assertEqual(len(update.effective_message.replies), 1)

    def test_ban_failure_falls_back_to_mute_with_local_containment(self):
        bot = FakeBot()
        bot.ban_chat_member = AsyncMock(side_effect=RuntimeError('ban unavailable'))
        context = FakeContext(self.runtime, bot)
        update = make_update(user_id=2, chat_type='supergroup', text='flood')
        asyncio.run(app._enforce_flood(update, context, FloodDecision(
            triggered=True, should_ban=True, strike_count=4, mute_seconds=60)))
        self.assertEqual(bot.restricted, [(-100123, 2)])
        self.assertGreater(self.runtime.db.containment_until(-100123, 2), 0)
        results = [tuple(row) for row in self.runtime.db._conn.execute(
            'SELECT action_type,success FROM actions ORDER BY created_at')]
        self.assertEqual(results, [('ban', 0), ('mute', 1)])

    def test_no_sqlite_transaction_contains_await_in_any_runtime_module(self):
        for path in (Path(__file__).resolve().parents[1] / 'zion').glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, (ast.With, ast.AsyncWith)) and any(
                    isinstance(item.context_expr, ast.Call)
                    and isinstance(item.context_expr.func, ast.Attribute)
                    and item.context_expr.func.attr in ('transaction', '_transaction_locked')
                    for item in node.items
                ):
                    self.assertFalse(any(isinstance(child, ast.Await) for child in ast.walk(node)),
                                     f'{path.name}:{node.lineno}')
