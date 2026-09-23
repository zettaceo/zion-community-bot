from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "secret_scan.py"

spec = importlib.util.spec_from_file_location(
    "zion_secret_scan_script",
    SCRIPT,
)
if spec is None or spec.loader is None:
    raise RuntimeError("could not load secret_scan.py for tests")

module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SecretScanTests(unittest.TestCase):
    def test_binary_file_is_scanned_for_telegram_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.bin"
            token = (
                b"987654321:"
                b"AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
            )
            path.write_bytes(b"\x00\x01prefix" + token + b"suffix")

            findings = module.scan_file(path)
            self.assertTrue(
                any(
                    "Telegram bot token" in finding
                    for finding in findings
                )
            )

    def test_allowed_fake_token_does_not_fail_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.txt"
            token = next(iter(module.FAKE_TELEGRAM_TOKENS))
            path.write_bytes(token)

            self.assertEqual(module.scan_file(path), [])


if __name__ == "__main__":
    unittest.main()
