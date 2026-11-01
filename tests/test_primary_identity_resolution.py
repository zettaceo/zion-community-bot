import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tests.helpers import make_settings
from tests.test_telegram_identity_store import TOKENS
from zion.agents import AgentId
from zion.secret_store import SecretStoreError
from zion.telegram_identity_store import TelegramIdentityStore
from zion.telegram_app import build_application


class PrimaryIdentityResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # Both the worktree and protected store are disposable and separate.
        self.worktree = self.root / 'worktree'
        self.worktree.mkdir()
        self.settings = replace(make_settings(self.worktree),
            telegram_token=TOKENS[AgentId.ZION],
            telegram_identity_secret_dir=self.root / 'private' / 'telegram-identities')
        self.store = TelegramIdentityStore(self.settings.telegram_identity_secret_dir)

    def test_absent_store_preserves_legacy_without_writing_anything(self):
        self.assertIs(self.settings.with_primary_telegram_identity(), self.settings)
        self.assertFalse(self.settings.telegram_identity_secret_dir.exists())
        self.assertNotIn(TOKENS[AgentId.ZION], repr(self.settings))

    def test_primary_application_and_runtime_use_protected_token_without_env_token(self):
        self.store.write_atomic(AgentId.ZION, TOKENS[AgentId.ZION])
        settings = replace(self.settings, telegram_token='')
        app = build_application(settings)
        try:
            self.assertEqual(app.bot.token, TOKENS[AgentId.ZION])
            self.assertEqual(app.bot_data['zion_runtime'].settings.telegram_token, app.bot.token)
            self.assertEqual(settings.telegram_token, '')
        finally:
            app.bot_data['zion_runtime'].close()

    def test_protected_identity_wins_over_legacy_but_unsafe_store_never_falls_back(self):
        self.store.write_atomic(AgentId.ZION, TOKENS[AgentId.ZION])
        settings = replace(self.settings, telegram_token=TOKENS[AgentId.EIR])
        self.assertEqual(settings.with_primary_telegram_identity().telegram_token, TOKENS[AgentId.ZION])
        (self.settings.telegram_identity_secret_dir / 'zion.token').chmod(0o644)
        with self.assertRaises(SecretStoreError):
            settings.with_primary_telegram_identity()

    def test_symlink_store_or_worktree_location_is_rejected(self):
        self.store.write_atomic(AgentId.ZION, TOKENS[AgentId.ZION])
        path = self.settings.telegram_identity_secret_dir / 'zion.token'
        original = path.with_suffix('.original')
        path.rename(original); path.symlink_to(original)
        with self.assertRaises(SecretStoreError):
            self.settings.with_primary_telegram_identity()
        inside = replace(self.settings, telegram_identity_secret_dir=self.worktree / 'secrets')
        with self.assertRaises(SecretStoreError):
            inside.with_primary_telegram_identity()
