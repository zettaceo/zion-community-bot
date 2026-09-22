from __future__ import annotations

import os
import stat
import threading
import uuid
from pathlib import Path


class SecretStoreError(RuntimeError):
    """Secret-store boundary failure without secret material."""


class SecretValidationError(SecretStoreError):
    """Candidate secret failed local structural validation."""


class SecretStore:
    MISSING = "MISSING"
    PRIVATE = "PRIVATE"
    UNSAFE = "UNSAFE"

    MIN_SECRET_BYTES = 16
    MAX_SECRET_BYTES = 4096

    def __init__(self, path: Path, *, expected_uid: int | None = None):
        self.path = path.expanduser()
        self.directory = self.path.parent
        self.expected_uid = os.getuid() if expected_uid is None else expected_uid
        self._lock = threading.Lock()

    @staticmethod
    def normalize_candidate(value: str) -> str:
        if not isinstance(value, str):
            raise SecretValidationError("secret candidate must be text")

        normalized = value.strip()
        encoded = normalized.encode("utf-8", errors="strict")

        if not normalized:
            raise SecretValidationError("secret candidate is empty")
        if len(encoded) < SecretStore.MIN_SECRET_BYTES:
            raise SecretValidationError("secret candidate is too short")
        if len(encoded) > SecretStore.MAX_SECRET_BYTES:
            raise SecretValidationError("secret candidate is too long")
        if any(char.isspace() for char in normalized):
            raise SecretValidationError(
                "secret candidate contains whitespace"
            )
        if any(ord(char) < 33 or ord(char) == 127 for char in normalized):
            raise SecretValidationError(
                "secret candidate contains control characters"
            )

        return normalized

    def _directory_entry_exists(self) -> bool:
        try:
            self.directory.lstat()
        except FileNotFoundError:
            return False
        except OSError:
            # Metadata uncertainty is unsafe, never equivalent to missing.
            return True
        return True

    def _validate_directory(self) -> None:
        try:
            info = self.directory.lstat()
        except FileNotFoundError as exc:
            raise SecretStoreError("secret directory is missing") from exc
        except OSError as exc:
            raise SecretStoreError("secret directory metadata unavailable") from exc

        mode = stat.S_IMODE(info.st_mode)
        if not stat.S_ISDIR(info.st_mode):
            raise SecretStoreError("secret directory is not a directory")
        if info.st_uid != self.expected_uid:
            raise SecretStoreError("secret directory owner is invalid")
        if mode != 0o700:
            raise SecretStoreError("secret directory mode is invalid")
        try:
            resolved = self.directory.resolve(strict=True)
        except OSError as exc:
            raise SecretStoreError(
                "secret directory canonical path unavailable"
            ) from exc
        if resolved != self.directory.absolute():
            raise SecretStoreError(
                "secret directory resolves through a symlink or alias"
            )

    def _ensure_directory(self) -> None:
        try:
            self.directory.mkdir(mode=0o700, exist_ok=True)
        except OSError as exc:
            raise SecretStoreError("cannot create secret directory") from exc
        self._validate_directory()

    def _validate_file_stat(self, info: os.stat_result) -> None:
        if not stat.S_ISREG(info.st_mode):
            raise SecretStoreError("secret path is not a regular file")
        if info.st_nlink != 1:
            raise SecretStoreError("secret file has multiple hard links")
        if info.st_uid != self.expected_uid:
            raise SecretStoreError("secret file owner is invalid")
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise SecretStoreError("secret file mode is invalid")

    def _validate_existing_path(self) -> None:
        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise SecretStoreError("secret file metadata unavailable") from exc

        if stat.S_ISLNK(info.st_mode):
            raise SecretStoreError("secret path is a symlink")
        self._validate_file_stat(info)

    def status(self) -> str:
        try:
            self._validate_directory()
        except SecretStoreError:
            if not self._directory_entry_exists():
                return self.MISSING
            return self.UNSAFE

        try:
            info = self.path.lstat()
        except FileNotFoundError:
            return self.MISSING
        except OSError:
            return self.UNSAFE

        try:
            if stat.S_ISLNK(info.st_mode):
                raise SecretStoreError("secret path is a symlink")
            self._validate_file_stat(info)
            # A structurally invalid payload is unsafe, not merely missing.
            value = self.read()
            if value is None:
                return self.MISSING
        except (SecretStoreError, SecretValidationError, UnicodeError):
            return self.UNSAFE
        return self.PRIVATE

    def read(self) -> str | None:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        try:
            self._validate_directory()
        except SecretStoreError:
            if not self._directory_entry_exists():
                return None
            raise

        try:
            fd = os.open(self.path, flags)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise SecretStoreError("cannot open secret file") from exc

        try:
            info = os.fstat(fd)
            self._validate_file_stat(info)
            data = os.read(fd, self.MAX_SECRET_BYTES + 2)
            if len(data) > self.MAX_SECRET_BYTES + 1:
                raise SecretStoreError("secret file exceeds size limit")
        finally:
            os.close(fd)

        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SecretStoreError("secret file is not valid UTF-8") from exc

        try:
            return self.normalize_candidate(text)
        except SecretValidationError as exc:
            raise SecretStoreError("secret file payload is invalid") from exc

    def _fsync_directory(self) -> None:
        flags = os.O_RDONLY
        if hasattr(os, "O_DIRECTORY"):
            flags |= os.O_DIRECTORY
        try:
            fd = os.open(self.directory, flags)
        except OSError as exc:
            raise SecretStoreError("cannot open secret directory") from exc
        try:
            os.fsync(fd)
        except OSError as exc:
            raise SecretStoreError("cannot fsync secret directory") from exc
        finally:
            os.close(fd)

    def _write_private_temp(
        self,
        payload: bytes,
        *,
        label: str,
    ) -> Path:
        tmp = self.directory / (
            "." + self.path.name + f".{label}-" + uuid.uuid4().hex
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        fd: int | None = None
        try:
            fd = os.open(tmp, flags, 0o600)
            info = os.fstat(fd)
            self._validate_file_stat(info)

            offset = 0
            while offset < len(payload):
                written = os.write(fd, payload[offset:])
                if written <= 0:
                    raise SecretStoreError("short secret write")
                offset += written
            os.fsync(fd)
            os.close(fd)
            fd = None

            tmp_info = tmp.lstat()
            self._validate_file_stat(tmp_info)
            return tmp
        except BaseException:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass
            raise

    def _restore_previous_after_publish_failure(
        self,
        previous: str | None,
    ) -> None:
        if previous is None:
            self._validate_existing_path()
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            self._fsync_directory()
            return

        rollback_tmp = self._write_private_temp(
            previous.encode("utf-8"),
            label="rollback",
        )
        try:
            os.replace(rollback_tmp, self.path)
            self._fsync_directory()
            if self.read() != previous:
                raise SecretStoreError(
                    "secret rollback verification failed"
                )
        finally:
            try:
                rollback_tmp.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass

    def write_atomic(self, value: str) -> None:
        normalized = self.normalize_candidate(value)
        payload = normalized.encode("utf-8")

        with self._lock:
            self._ensure_directory()
            self._validate_existing_path()
            previous = self.read()

            tmp = self._write_private_temp(payload, label="tmp")
            published = False
            try:
                self._validate_existing_path()
                os.replace(tmp, self.path)
                published = True
                try:
                    self._fsync_directory()
                    if self.read() != normalized:
                        raise SecretStoreError(
                            "published secret verification failed"
                        )
                except BaseException as publish_exc:
                    try:
                        self._restore_previous_after_publish_failure(
                            previous
                        )
                    except BaseException as rollback_exc:
                        raise SecretStoreError(
                            "secret publication failed and rollback "
                            "could not be confirmed"
                        ) from rollback_exc
                    raise SecretStoreError(
                        "secret publication failed; previous state restored"
                    ) from publish_exc
            finally:
                if not published:
                    try:
                        tmp.unlink()
                    except FileNotFoundError:
                        pass
                    except OSError:
                        pass

    def clear(self) -> bool:
        with self._lock:
            try:
                self._validate_directory()
            except SecretStoreError:
                if not self._directory_entry_exists():
                    return False
                raise

            try:
                self._validate_existing_path()
                self.path.lstat()
            except FileNotFoundError:
                return False

            previous = self.read()
            if previous is None:
                return False

            try:
                self.path.unlink()
            except OSError as exc:
                raise SecretStoreError("cannot remove secret file") from exc

            try:
                self._fsync_directory()
            except BaseException as clear_exc:
                try:
                    rollback_tmp = self._write_private_temp(
                        previous.encode("utf-8"),
                        label="clear-rollback",
                    )
                    try:
                        os.replace(rollback_tmp, self.path)
                        self._fsync_directory()
                        if self.read() != previous:
                            raise SecretStoreError(
                                "secret clear rollback verification failed"
                            )
                    finally:
                        try:
                            rollback_tmp.unlink()
                        except FileNotFoundError:
                            pass
                        except OSError:
                            pass
                except BaseException as rollback_exc:
                    raise SecretStoreError(
                        "secret clear failed and rollback "
                        "could not be confirmed"
                    ) from rollback_exc
                raise SecretStoreError(
                    "secret clear durability failed; previous state restored"
                ) from clear_exc

            return True
