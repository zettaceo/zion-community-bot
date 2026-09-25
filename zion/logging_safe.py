from __future__ import annotations

import logging
import os
import re
import stat
import threading
import unicodedata
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path


SECRET_ENV_MARKERS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "API_KEY",
    "PRIVATE_KEY",
    "ACCESS_KEY",
    "CLIENT_SECRET",
)

TELEGRAM_TOKEN_REGEX = re.compile(
    r"\d{6,}:[A-Za-z0-9_-]{20,}"
)

BEARER_REGEX = re.compile(
    r"(?i)(authorization\s*[:=]\s*bearer\s+)([^\s,;]+)"
)

BASIC_AUTH_URL_REGEX = re.compile(
    r"(?i)([a-z][a-z0-9+.-]*://[^/\s:@]+:)([^@\s/]+)(@)"
)

LABELED_CREDENTIAL_REGEX = re.compile(
    r"(?is)\b("
    r"api[ _-]?key|client[ _-]?secret|secret[ _-]?key|"
    r"access[ _-]?token|refresh[ _-]?token|auth[ _-]?token|"
    r"webhook[ _-]?secret|password|passwd|"
    r"telegram[ _-]?bot[ _-]?token|bot[ _-]?token"
    r")\b\s*[:=]\s*([^\s,;]{8,})"
)

SECRET_PARAMETER_REGEX = re.compile(
    r"(?i)"
    r"((?:token|api[_-]?key|secret|password|passwd|"
    r"access[_-]?key|client[_-]?secret)=)"
    r"([^&\s]+)"
)

PRIVATE_KEY_BLOCK_REGEX = re.compile(
    r"(?is)-----BEGIN [A-Z0-9 -]*PRIVATE KEY-----"
    r".*?"
    r"-----END [A-Z0-9 -]*PRIVATE KEY-----"
)

_RUNTIME_SECRET_VALUES: deque[str] = deque(maxlen=64)
_RUNTIME_SECRET_LOCK = threading.RLock()


def register_sensitive_value(value: object) -> None:
    text = str(value or "")
    if len(text) < 6:
        return
    with _RUNTIME_SECRET_LOCK:
        if text in _RUNTIME_SECRET_VALUES:
            return
        _RUNTIME_SECRET_VALUES.append(text)


INVISIBLE_SECURITY_CODEPOINTS = {
    0x200B,
    0x200C,
    0x200D,
    0x2060,
    0xFEFF,
}


def _normalize_security_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value))
    return "".join(
        char
        for char in text
        if ord(char) not in INVISIBLE_SECURITY_CODEPOINTS
    )


def _sensitive_values() -> list[str]:
    values = {
        value
        for name, value in os.environ.items()
        if value
        and len(value) >= 6
        and any(marker in name.upper() for marker in SECRET_ENV_MARKERS)
    }
    with _RUNTIME_SECRET_LOCK:
        values.update(_RUNTIME_SECRET_VALUES)
    return sorted(values, key=len, reverse=True)


def contains_high_confidence_credential(value: object) -> bool:
    text = _normalize_security_text(value)
    if TELEGRAM_TOKEN_REGEX.search(text):
        return True
    if BEARER_REGEX.search(text):
        return True
    if BASIC_AUTH_URL_REGEX.search(text):
        return True
    if LABELED_CREDENTIAL_REGEX.search(text):
        return True
    if PRIVATE_KEY_BLOCK_REGEX.search(text):
        return True
    return any(secret in text for secret in _sensitive_values())


def redact_secrets(value: object) -> str:
    text = _normalize_security_text(value)

    for secret in _sensitive_values():
        text = text.replace(secret, "[REDACTED]")

    text = TELEGRAM_TOKEN_REGEX.sub(
        "[REDACTED_TELEGRAM_TOKEN]",
        text,
    )
    text = BEARER_REGEX.sub(r"\1[REDACTED]", text)
    text = BASIC_AUTH_URL_REGEX.sub(
        r"\1[REDACTED]\3",
        text,
    )
    text = LABELED_CREDENTIAL_REGEX.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        text,
    )
    text = SECRET_PARAMETER_REGEX.sub(
        r"\1[REDACTED]",
        text,
    )
    text = PRIVATE_KEY_BLOCK_REGEX.sub(
        "[REDACTED_PRIVATE_KEY]",
        text,
    )
    return text


class PrivateRotatingFileHandler(RotatingFileHandler):
    def _secure_files(self) -> None:
        base = Path(self.baseFilename)
        for candidate in base.parent.glob(base.name + "*"):
            try:
                info = candidate.lstat()
                if not stat.S_ISREG(info.st_mode):
                    continue
                if info.st_nlink != 1:
                    continue
                os.chmod(candidate, 0o600)
            except OSError:
                pass

    def _open(self):
        flags = os.O_CREAT | os.O_WRONLY | os.O_APPEND
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC

        fd = os.open(self.baseFilename, flags, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise RuntimeError("ZION log target must be a regular file.")
            if info.st_nlink != 1:
                raise RuntimeError("ZION log target must not have hard links.")
            os.fchmod(fd, 0o600)
            stream = open(
                fd,
                mode=self.mode,
                encoding=self.encoding,
                errors=self.errors,
                closefd=True,
            )
            fd = -1
        finally:
            if fd >= 0:
                os.close(fd)

        self._secure_files()
        return stream

    def doRollover(self) -> None:
        super().doRollover()
        self._secure_files()


class SecretSafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_secrets(super().format(record))


def configure_logging(
    log_path: Path,
    level: int = logging.INFO,
    *,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if log_path.parent.is_symlink():
        raise RuntimeError("ZION log directory must not be a symlink.")
    try:
        info = log_path.lstat()
    except FileNotFoundError:
        info = None
    if info is not None:
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError("ZION log target must be a regular file.")
        if info.st_nlink != 1:
            raise RuntimeError("ZION log target must not have hard links.")

    formatter = SecretSafeFormatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    file_handler = PrivateRotatingFileHandler(
        log_path,
        maxBytes=max(1024 * 1024, int(max_bytes)),
        backupCount=max(1, int(backup_count)),
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler._secure_files()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logging.basicConfig(
        level=level,
        handlers=[file_handler, stream_handler],
        force=True,
    )

    for noisy in ("httpx", "httpcore", "telegram"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return logging.getLogger("zion")
