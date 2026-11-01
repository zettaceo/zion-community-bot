"""Provider-bound local credentials. No environment-variable secret fallback."""
from __future__ import annotations

from enum import Enum
from pathlib import Path

from .secret_store import SecretStore


class ProviderId(str, Enum):
    MISTRAL = 'mistral'
    KIMI = 'kimi'


class ProviderSecretStore:
    """Fixed filenames backed by the already audited atomic SecretStore.

    The containing directory must already have a safe parent. Do not provision
    this directory in a repository, runtime or ordinary backup root.
    Existing Mistral credentials are not moved or read by this collection.
    """

    def __init__(self, directory: Path, *, expected_uid: int | None = None):
        self._stores = {provider: SecretStore(
            directory / (provider.value + '-api-key'), expected_uid=expected_uid)
            for provider in ProviderId}

    def for_provider(self, provider: ProviderId | str) -> SecretStore:
        # No user-controlled filename or URL can reach the filesystem.
        try:
            return self._stores[ProviderId(provider)]
        except (ValueError, KeyError, TypeError):
            raise ValueError('unknown provider identity') from None

    def statuses(self) -> dict[str, str]:
        return {provider.value: store.status() for provider, store in self._stores.items()}
