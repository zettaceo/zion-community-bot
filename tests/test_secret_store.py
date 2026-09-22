from __future__ import annotations

import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from zion.secret_store import (
    SecretStore,
    SecretStoreError,
    SecretValidationError,
)


SYNTHETIC_SECRET = "synthetic-mistral-key-material-123456"


class SecretStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.path = self.root / "secrets" / "mistral-api-key"
        self.store = SecretStore(self.path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_atomic_write_creates_private_directory_and_file(self) -> None:
        self.store.write_atomic(SYNTHETIC_SECRET)

        self.assertEqual(self.store.read(), SYNTHETIC_SECRET)
        self.assertEqual(self.store.status(), SecretStore.PRIVATE)
        self.assertEqual(
            stat.S_IMODE(self.path.parent.stat().st_mode),
            0o700,
        )
        self.assertEqual(
            stat.S_IMODE(self.path.stat().st_mode),
            0o600,
        )
        self.assertEqual(self.path.stat().st_nlink, 1)
        self.assertEqual(self.path.stat().st_uid, os.getuid())

    def test_rotation_replaces_secret_atomically(self) -> None:
        replacement = "synthetic-mistral-rotated-material-654321"
        self.store.write_atomic(SYNTHETIC_SECRET)
        self.store.write_atomic(replacement)

        self.assertEqual(self.store.read(), replacement)
        self.assertEqual(self.store.status(), SecretStore.PRIVATE)

    def test_invalid_candidate_preserves_existing_secret(self) -> None:
        self.store.write_atomic(SYNTHETIC_SECRET)

        with self.assertRaises(SecretValidationError):
            self.store.write_atomic("short")

        self.assertEqual(self.store.read(), SYNTHETIC_SECRET)

    def test_internal_whitespace_is_rejected(self) -> None:
        with self.assertRaises(SecretValidationError):
            self.store.write_atomic(
                "synthetic-mistral key-material-123456"
            )

    def test_trailing_newline_is_normalized_only_in_memory(self) -> None:
        self.store.write_atomic(SYNTHETIC_SECRET + "\n")
        self.assertEqual(self.store.read(), SYNTHETIC_SECRET)
        self.assertEqual(
            self.path.read_bytes(),
            SYNTHETIC_SECRET.encode("utf-8"),
        )

    def test_oversized_candidate_is_rejected(self) -> None:
        with self.assertRaises(SecretValidationError):
            self.store.write_atomic(
                "x" * (SecretStore.MAX_SECRET_BYTES + 1)
            )

    def test_dangling_symlink_secret_directory_is_unsafe(self) -> None:
        dangling = self.root / "missing-target"
        self.path.parent.symlink_to(dangling, target_is_directory=True)

        self.assertEqual(self.store.status(), SecretStore.UNSAFE)
        with self.assertRaises(SecretStoreError):
            self.store.read()
        with self.assertRaises(SecretStoreError):
            self.store.clear()

    def test_post_publish_failure_restores_previous_secret(self) -> None:
        replacement = "synthetic-mistral-new-material-987654"
        self.store.write_atomic(SYNTHETIC_SECRET)

        original_fsync = self.store._fsync_directory
        calls = {"count": 0}

        def fail_once() -> None:
            calls["count"] += 1
            if calls["count"] == 1:
                raise SecretStoreError("synthetic directory fsync failure")
            original_fsync()

        with patch.object(
            self.store,
            "_fsync_directory",
            side_effect=fail_once,
        ):
            with self.assertRaises(SecretStoreError):
                self.store.write_atomic(replacement)

        self.assertEqual(self.store.read(), SYNTHETIC_SECRET)
        self.assertEqual(self.store.status(), SecretStore.PRIVATE)

    def test_first_publish_failure_leaves_secret_missing(self) -> None:
        original_fsync = self.store._fsync_directory
        calls = {"count": 0}

        def fail_once() -> None:
            calls["count"] += 1
            if calls["count"] == 1:
                raise SecretStoreError("synthetic directory fsync failure")
            original_fsync()

        with patch.object(
            self.store,
            "_fsync_directory",
            side_effect=fail_once,
        ):
            with self.assertRaises(SecretStoreError):
                self.store.write_atomic(SYNTHETIC_SECRET)

        self.assertEqual(self.store.status(), SecretStore.MISSING)
        self.assertIsNone(self.store.read())

    def test_clear_durability_failure_restores_previous_secret(self) -> None:
        self.store.write_atomic(SYNTHETIC_SECRET)

        original_fsync = self.store._fsync_directory
        calls = {"count": 0}

        def fail_once() -> None:
            calls["count"] += 1
            if calls["count"] == 1:
                raise SecretStoreError("synthetic clear fsync failure")
            original_fsync()

        with patch.object(
            self.store,
            "_fsync_directory",
            side_effect=fail_once,
        ):
            with self.assertRaises(SecretStoreError):
                self.store.clear()

        self.assertEqual(self.store.read(), SYNTHETIC_SECRET)
        self.assertEqual(self.store.status(), SecretStore.PRIVATE)

    def test_symlink_destination_is_rejected(self) -> None:
        self.path.parent.mkdir(mode=0o700)
        target = self.root / "other-secret"
        target.write_text(SYNTHETIC_SECRET, encoding="utf-8")
        target.chmod(0o600)
        self.path.symlink_to(target)

        self.assertEqual(self.store.status(), SecretStore.UNSAFE)
        with self.assertRaises(SecretStoreError):
            self.store.write_atomic(SYNTHETIC_SECRET)

    def test_hardlinked_secret_is_rejected(self) -> None:
        self.store.write_atomic(SYNTHETIC_SECRET)
        alias = self.root / "secret-alias"
        os.link(self.path, alias)

        self.assertEqual(self.store.status(), SecretStore.UNSAFE)
        with self.assertRaises(SecretStoreError):
            self.store.read()

    def test_world_readable_secret_is_unsafe(self) -> None:
        self.store.write_atomic(SYNTHETIC_SECRET)
        self.path.chmod(0o644)

        self.assertEqual(self.store.status(), SecretStore.UNSAFE)
        with self.assertRaises(SecretStoreError):
            self.store.read()

    def test_world_accessible_secret_directory_is_unsafe(self) -> None:
        self.store.write_atomic(SYNTHETIC_SECRET)
        self.path.parent.chmod(0o755)

        self.assertEqual(self.store.status(), SecretStore.UNSAFE)
        with self.assertRaises(SecretStoreError):
            self.store.read()

    def test_replace_failure_preserves_old_secret_and_cleans_temp(self) -> None:
        self.store.write_atomic(SYNTHETIC_SECRET)
        replacement = "synthetic-mistral-new-material-987654"

        with patch(
            "zion.secret_store.os.replace",
            side_effect=OSError("synthetic replace failure"),
        ):
            with self.assertRaises(OSError):
                self.store.write_atomic(replacement)

        self.assertEqual(self.store.read(), SYNTHETIC_SECRET)
        leftovers = list(
            self.path.parent.glob(".mistral-api-key.tmp-*")
        )
        self.assertEqual(leftovers, [])

    def test_clear_removes_only_valid_secret(self) -> None:
        self.store.write_atomic(SYNTHETIC_SECRET)
        self.assertTrue(self.store.clear())
        self.assertEqual(self.store.status(), SecretStore.MISSING)
        self.assertIsNone(self.store.read())
        self.assertFalse(self.store.clear())


if __name__ == "__main__":
    unittest.main()
