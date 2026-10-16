from __future__ import annotations

import logging
import os
import tempfile
import unittest
from pathlib import Path

from tests.helpers import make_settings
from zion.agents import AgentId
from zion.db import ZionDB
from zion.health import HealthService
from zion.logging_safe import SecretSafeFormatter
from zion.secret_store import SecretStoreError, SecretValidationError
from zion.telegram_identity_store import TelegramIdentityStore


TOKENS = {
    AgentId.ZION: "100000001" + ":ZionSyntheticTokenMaterial_123456789",
    AgentId.MIMIR: "100000002" + ":MimirSyntheticTokenMaterial_12345678",
    AgentId.EIR: "100000003" + ":EirSyntheticTokenMaterial_1234567890",
    AgentId.FREYR: "100000004" + ":FreyrSyntheticTokenMaterial_12345678",
}


class TelegramIdentityStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / "state" / "telegram-identities"
        self.store = TelegramIdentityStore(self.directory)

    def test_atomic_write_binds_private_file_to_identity(self) -> None:
        self.store.write_atomic(AgentId.MIMIR, TOKENS[AgentId.MIMIR])

        self.assertEqual(
            self.store.status(AgentId.MIMIR),
            TelegramIdentityStore.CONFIGURED,
        )
        self.assertEqual(
            self.store.read(AgentId.MIMIR),
            TOKENS[AgentId.MIMIR],
        )
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        token_path = self.directory / "mimir.token"
        self.assertEqual(token_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(token_path.stat().st_nlink, 1)

    def test_status_all_never_contains_secret_values(self) -> None:
        self.store.write_atomic(AgentId.EIR, TOKENS[AgentId.EIR])
        status = self.store.status_all()

        self.assertEqual(status[AgentId.EIR], "CONFIGURED")
        self.assertEqual(status[AgentId.ZION], "MISSING")
        rendered = repr(status)
        for token in TOKENS.values():
            self.assertNotIn(token, rendered)

    def test_token_is_registered_for_safe_log_redaction(self) -> None:
        token = TOKENS[AgentId.FREYR]
        self.store.write_atomic(AgentId.FREYR, token)
        formatter = SecretSafeFormatter("%(message)s")
        record = logging.LogRecord(
            "test",
            logging.INFO,
            __file__,
            1,
            "transport failed for %s",
            (token,),
            None,
        )

        rendered = formatter.format(record)

        self.assertNotIn(token, rendered)
        self.assertIn("[REDACTED]", rendered)

    def test_token_never_propagates_to_sqlite_backup_or_diagnostics(self) -> None:
        settings = make_settings(self.root)
        store = TelegramIdentityStore(settings.telegram_identity_secret_dir)
        token = TOKENS[AgentId.MIMIR]
        store.write_atomic(AgentId.MIMIR, token)
        database = ZionDB(settings.db_path)
        database.initialize()
        self.addCleanup(database.close)

        health = HealthService(
            settings,
            database,
            telegram_identity_store=store,
        )
        self.assertNotIn(token, repr(health.snapshot().details))
        self.assertNotIn(token, "\n".join(database._conn.iterdump()))

        backup_path = self.root / "verified-backup.db"
        database.backup_to(backup_path)
        self.assertNotIn(token.encode("utf-8"), backup_path.read_bytes())
        for sidecar_suffix in ("-wal", "-shm"):
            sidecar = Path(str(settings.db_path) + sidecar_suffix)
            if sidecar.exists():
                self.assertNotIn(token.encode("utf-8"), sidecar.read_bytes())

    def test_invalid_token_is_rejected_without_echo(self) -> None:
        candidate = "not-a-valid-private-token-material"
        with self.assertRaises(SecretValidationError) as raised:
            self.store.write_atomic(AgentId.ZION, candidate)
        self.assertNotIn(candidate, str(raised.exception))
        self.assertEqual(
            self.store.status(AgentId.ZION),
            TelegramIdentityStore.MISSING,
        )

    def test_same_token_cannot_be_assigned_twice(self) -> None:
        token = TOKENS[AgentId.ZION]
        self.store.write_atomic(AgentId.ZION, token)

        with self.assertRaisesRegex(
            SecretValidationError,
            "already assigned",
        ):
            self.store.write_atomic(AgentId.MIMIR, token)

        self.assertEqual(
            self.store.status(AgentId.MIMIR),
            TelegramIdentityStore.MISSING,
        )

    def test_symlinked_directory_is_unsafe_and_write_fails_closed(self) -> None:
        real = self.root / "real"
        real.mkdir(mode=0o700)
        self.directory.parent.mkdir(mode=0o700)
        self.directory.symlink_to(real, target_is_directory=True)

        self.assertEqual(
            self.store.status(AgentId.ZION),
            TelegramIdentityStore.UNSAFE,
        )
        with self.assertRaises(SecretStoreError):
            self.store.write_atomic(AgentId.ZION, TOKENS[AgentId.ZION])

    def test_hardlinked_identity_file_is_unsafe(self) -> None:
        self.store.write_atomic(AgentId.ZION, TOKENS[AgentId.ZION])
        os.link(
            self.directory / "zion.token",
            self.root / "stolen-link",
        )

        self.assertEqual(
            self.store.status(AgentId.ZION),
            TelegramIdentityStore.UNSAFE,
        )
        with self.assertRaises(SecretStoreError):
            self.store.read(AgentId.ZION)

    def test_world_accessible_directory_is_unsafe(self) -> None:
        self.store.write_atomic(AgentId.EIR, TOKENS[AgentId.EIR])
        self.directory.chmod(0o755)

        self.assertEqual(
            self.store.status(AgentId.EIR),
            TelegramIdentityStore.UNSAFE,
        )
        with self.assertRaises(SecretStoreError):
            self.store.read(AgentId.EIR)

    def test_unknown_identity_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            self.store.status("thor")

    def test_clear_is_identity_scoped(self) -> None:
        self.store.write_atomic(AgentId.EIR, TOKENS[AgentId.EIR])
        self.store.write_atomic(AgentId.FREYR, TOKENS[AgentId.FREYR])

        self.assertTrue(self.store.clear(AgentId.EIR))
        self.assertIsNone(self.store.read(AgentId.EIR))
        self.assertEqual(
            self.store.read(AgentId.FREYR),
            TOKENS[AgentId.FREYR],
        )


if __name__ == "__main__":
    unittest.main()
