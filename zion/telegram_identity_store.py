from __future__ import annotations

import re
import os
import stat
from pathlib import Path

from .agents import AgentId
from .secret_store import (
    SecretStore,
    SecretStoreError,
    SecretValidationError,
)


_TELEGRAM_TOKEN_REGEX = re.compile(
    r"^[0-9]{6,15}:[A-Za-z0-9_-]{20,128}$"
)


class TelegramIdentityStore:
    """Protected, identity-bound Telegram token collection.

    Secret values are returned only to the transport construction path. Public
    status methods expose CONFIGURED, MISSING, or UNSAFE and never include
    filenames or candidate material.
    """

    CONFIGURED = "CONFIGURED"
    MISSING = "MISSING"
    UNSAFE = "UNSAFE"

    _FILENAMES = {
        AgentId.ZION: "zion.token",
        AgentId.MIMIR: "mimir.token",
        AgentId.EIR: "eir.token",
        AgentId.FREYR: "freyr.token",
    }

    def __init__(
        self,
        directory: Path,
        *,
        expected_uid: int | None = None,
    ) -> None:
        self.directory = directory.expanduser()
        self.expected_uid = (
            os.getuid() if expected_uid is None else expected_uid
        )
        self._stores = {
            agent_id: SecretStore(
                self.directory / filename,
                expected_uid=self.expected_uid,
            )
            for agent_id, filename in self._FILENAMES.items()
        }

    def _parent_status(self) -> str:
        parent = self.directory.parent
        try:
            info = parent.lstat()
        except FileNotFoundError:
            return self.MISSING
        except OSError:
            return self.UNSAFE
        if not stat.S_ISDIR(info.st_mode):
            return self.UNSAFE
        if info.st_uid != self.expected_uid:
            return self.UNSAFE
        if stat.S_IMODE(info.st_mode) != 0o700:
            return self.UNSAFE
        try:
            if parent.resolve(strict=True) != parent.absolute():
                return self.UNSAFE
        except OSError:
            return self.UNSAFE
        return self.CONFIGURED

    def _ensure_parent(self) -> None:
        parent = self.directory.parent
        try:
            parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        except OSError as exc:
            raise SecretStoreError(
                "cannot create Telegram identity secret root"
            ) from exc
        if self._parent_status() != self.CONFIGURED:
            raise SecretStoreError(
                "Telegram identity secret root is unsafe"
            )

    @staticmethod
    def _agent_id(value: AgentId | str) -> AgentId:
        try:
            return (
                value
                if isinstance(value, AgentId)
                else AgentId(str(value).strip().lower())
            )
        except ValueError as exc:
            raise KeyError("unknown Telegram identity") from exc

    @staticmethod
    def _validate_token(value: str) -> str:
        try:
            normalized = SecretStore.normalize_candidate(value)
        except SecretValidationError as exc:
            raise SecretValidationError(
                "Telegram token failed structural validation"
            ) from exc
        if not _TELEGRAM_TOKEN_REGEX.fullmatch(normalized):
            raise SecretValidationError(
                "Telegram token failed structural validation"
            )
        return normalized

    def status(self, agent_id: AgentId | str) -> str:
        parent_status = self._parent_status()
        if parent_status == self.UNSAFE:
            return self.UNSAFE
        store = self._stores[self._agent_id(agent_id)]
        raw_status = store.status()
        if raw_status == SecretStore.MISSING:
            return self.MISSING
        if raw_status != SecretStore.PRIVATE:
            return self.UNSAFE
        try:
            value = store.read()
            if value is None:
                return self.MISSING
            self._validate_token(value)
        except (SecretStoreError, SecretValidationError):
            return self.UNSAFE
        return self.CONFIGURED

    def status_all(self) -> dict[AgentId, str]:
        return {
            agent_id: self.status(agent_id)
            for agent_id in AgentId
        }

    def read(self, agent_id: AgentId | str) -> str | None:
        store = self._stores[self._agent_id(agent_id)]
        value = store.read()
        if value is None:
            return None
        try:
            return self._validate_token(value)
        except SecretValidationError as exc:
            raise SecretStoreError(
                "Telegram identity payload is invalid"
            ) from exc

    def write_atomic(
        self,
        agent_id: AgentId | str,
        token: str,
    ) -> None:
        target_id = self._agent_id(agent_id)
        normalized = self._validate_token(token)
        self._ensure_parent()

        for other_id, store in self._stores.items():
            if other_id is target_id:
                continue
            try:
                existing = store.read()
            except SecretStoreError as exc:
                raise SecretStoreError(
                    "Telegram identity store contains an unsafe entry"
                ) from exc
            if existing is not None and existing == normalized:
                raise SecretValidationError(
                    "Telegram token is already assigned to another identity"
                )

        self._stores[target_id].write_atomic(normalized)

    def clear(self, agent_id: AgentId | str) -> bool:
        return self._stores[self._agent_id(agent_id)].clear()
