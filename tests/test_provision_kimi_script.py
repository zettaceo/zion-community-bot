"""Exercise interactive provisioning stages with synthetic values only."""
from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from zion.providers import ProviderError
from zion.provider_secrets import ProviderSecretStore
from zion.secret_store import SecretStore


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/provision-kimi.py'
spec = importlib.util.spec_from_file_location('provision_kimi_script_test', SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)
SYNTHETIC = 'synthetic-test-only-key-9876543210'


class ProvisionKimiScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.secret_root = self.home / '.local/state/zion-community-bot/secrets'
        self.secret_root.mkdir(parents=True, mode=0o700)
        self.store = ProviderSecretStore(self.secret_root / 'providers').for_provider('kimi')

    def run_script(self, candidate: str, validation_error: Exception | None = None):
        probes = []

        class Client:
            def __init__(self, store, *, model):
                assert model == 'kimi-k2.6'

            async def validate_candidate(self, secret):
                probes.append(True)
                if validation_error:
                    raise validation_error
                self_assert = secret == SYNTHETIC
                if not self_assert:
                    raise AssertionError('unexpected candidate in test')

        output = io.StringIO()
        with patch.object(module.sys, 'argv', ['provision-kimi.py']), \
             patch.object(module.sys, 'stdin', SimpleNamespace(isatty=lambda: True)), \
             patch.object(module.sys, 'stderr', SimpleNamespace(isatty=lambda: True)), \
             patch.object(module.Path, 'home', return_value=self.home), \
             patch.object(module.getpass, 'getpass', return_value=candidate), \
             patch.object(module, 'KimiCompletionProvider', Client), \
             patch.object(module.logging, 'disable'), redirect_stdout(output):
            result = module.main()
        self.assertNotIn(candidate, output.getvalue())
        return result, output.getvalue().strip(), len(probes)

    def test_malformed_candidate_is_rejected_before_network_or_storage(self):
        result, output, probes = self.run_script('short')
        self.assertEqual((result, output, probes),
            (1, 'PROVISIONING_RESULT=FAIL reason=input_invalid', 0))
        self.assertEqual(self.store.status(), SecretStore.MISSING)

    def test_rejected_credential_reports_stage_without_storing_candidate(self):
        result, output, probes = self.run_script(
            SYNTHETIC, ProviderError('credential_rejected'))
        self.assertEqual((result, output, probes),
            (1, 'PROVISIONING_RESULT=FAIL reason=credential_rejected', 1))
        self.assertEqual(self.store.status(), SecretStore.MISSING)

    def test_rate_limit_and_transport_failure_have_distinct_fixed_codes(self):
        for error, expected in ((ProviderError('rate_limited'), 'rate_limited'),
                                (ProviderError('credential_validation_unavailable'),
                                 'credential_validation_unavailable')):
            with self.subTest(expected=expected):
                result, output, probes = self.run_script(SYNTHETIC, error)
                self.assertEqual((result, output, probes),
                    (1, f'PROVISIONING_RESULT=FAIL reason={expected}', 1))
                self.assertEqual(self.store.status(), SecretStore.MISSING)

    def test_valid_candidate_creates_private_store_without_runtime_activation(self):
        result, output, probes = self.run_script(SYNTHETIC)
        self.assertEqual((result, output, probes),
            (0, 'PROVISIONING_RESULT=PASS provider=kimi status=PRIVATE runtime_activation=NO', 1))
        self.assertEqual(self.store.status(), SecretStore.PRIVATE)
        self.assertEqual((self.secret_root / 'providers').stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)
