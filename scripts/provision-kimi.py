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
from zion.providers import KimiCompletionProvider


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
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            candidate = getpass.getpass('Chave Kimi [entrada oculta]: ')
        # Metadata-only authentication probe; this does not select a live model.
        client = KimiCompletionProvider(store, model='kimi-k2.6')
        asyncio.run(client.validate_candidate(candidate))
        store.write_atomic(candidate)
        candidate = ''
        print('PROVISIONING_RESULT=PASS provider=kimi status=PRIVATE runtime_activation=NO')
        return 0
    except (KeyboardInterrupt, EOFError):
        print('\nPROVISIONING_RESULT=CANCELLED')
        return 1
    except Exception:
        # Do not print provider errors, tracebacks, candidate, path or response.
        print('PROVISIONING_RESULT=FAIL reason=validation_or_storage')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
