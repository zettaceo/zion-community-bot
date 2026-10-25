#!/usr/bin/env python3
"""Interactive local provisioning only; never accept credentials as arguments."""
from __future__ import annotations

import asyncio
import getpass
import logging
import os
from pathlib import Path
import stat
import sys
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from zion.provider_secrets import ProviderSecretStore
from zion.providers import KimiCompletionProvider, ProviderError
from zion.secret_store import SecretStore, SecretStoreError, SecretValidationError


def _fail(reason: str) -> int:
    # Only fixed stage codes may cross the terminal boundary.
    print(f'PROVISIONING_RESULT=FAIL reason={reason}')
    return 1


def main() -> int:
    if len(sys.argv) != 1 or not sys.stdin.isatty() or not sys.stderr.isatty():
        print('PROVISIONING_RESULT=FAIL reason=interactive_terminal_required')
        return 1
    logging.disable(logging.CRITICAL)
    root = Path.home() / '.local/state/zion-community-bot/secrets'
    try:
        info = root.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700
                or root.resolve(strict=True) != root.absolute()):
            raise ValueError('unsafe root')
        store = ProviderSecretStore(root / 'providers').for_provider('kimi')
    except Exception:
        return _fail('unsafe_secret_root')

    candidate = ''
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            candidate = getpass.getpass('Chave Kimi [entrada oculta]: ')
        try:
            candidate = SecretStore.normalize_candidate(candidate)
        except SecretValidationError:
            return _fail('input_invalid')

        # A metadata-only authentication probe must succeed before storage.
        client = KimiCompletionProvider(store, model='kimi-k2.6')
        try:
            asyncio.run(client.validate_candidate(candidate))
        except ProviderError as exc:
            reason = str(exc)
            if reason not in {
                'credential_rejected', 'rate_limited', 'redirect_rejected',
                'provider_unavailable', 'credential_validation_unavailable',
            }:
                reason = 'provider_probe_unavailable'
            return _fail(reason)
        except Exception:
            return _fail('provider_probe_unavailable')

        try:
            store.write_atomic(candidate)
            if store.status() != SecretStore.PRIVATE:
                return _fail('storage_unavailable')
        except (SecretStoreError, OSError):
            return _fail('storage_unavailable')
        print('PROVISIONING_RESULT=PASS provider=kimi status=PRIVATE runtime_activation=NO')
        return 0
    except (KeyboardInterrupt, EOFError):
        print('\nPROVISIONING_RESULT=CANCELLED')
        return 1
    except Exception:
        return _fail('local_unavailable')
    finally:
        candidate = ''


if __name__ == '__main__':
    raise SystemExit(main())
