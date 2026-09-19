from __future__ import annotations

import logging
import os
import re
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

LABELED_CREDENTIAL_REGEX = re.compile(
    r"(?is)\b("
    r"api[ _-]?key|client[ _-]?secret|password|passwd|"
    r"telegram[ _-]?bot[ _-]?token|bot[ _-]?token"
    r")\b\s*[:=]\s*([^\s,;]{8,})"
)

SECRET_PARAMETER_REGEX = re.compile(
    r"(?i)"
    r"((?:token|api[_-]?key|secret|password|passwd|"
    r"access[_-]?key|client[_-]?secret)=)"
    r"([^&\s]+)"
)


def _sensitive_values() -> list[str]:
    values = {
        value
        for name, value in os.environ.items()
        if value
        and len(value) >= 6
        and any(marker in name.upper() for marker in SECRET_ENV_MARKERS)
    }
    return sorted(values, key=len, reverse=True)


def contains_high_confidence_credential(value: object) -> bool:
    text = str(value)
    if TELEGRAM_TOKEN_REGEX.search(text):
        return True
    if BEARER_REGEX.search(text):
        return True
    if LABELED_CREDENTIAL_REGEX.search(text):
        return True
    return any(secret in text for secret in _sensitive_values())


def redact_secrets(value: object) -> str:
    text = str(value)

    for secret in _sensitive_values():
        text = text.replace(secret, "[REDACTED]")

    text = TELEGRAM_TOKEN_REGEX.sub(
        "[REDACTED_TELEGRAM_TOKEN]",
        text,
    )
    text = BEARER_REGEX.sub(r"\1[REDACTED]", text)
    text = LABELED_CREDENTIAL_REGEX.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        text,
    )
    text = SECRET_PARAMETER_REGEX.sub(
        r"\1[REDACTED]",
        text,
    )
    return text


class PrivateRotatingFileHandler(RotatingFileHandler):
    def _secure_files(self) -> None:
        base = Path(self.baseFilename)
        for candidate in base.parent.glob(base.name + "*"):
            try:
                if candidate.is_symlink():
                    continue
                if candidate.is_file():
                    os.chmod(candidate, 0o600)
            except OSError:
                pass

    def _open(self):
        stream = super()._open()
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
    if log_path.is_symlink():
        raise RuntimeError("ZION log path must not be a symlink.")

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
