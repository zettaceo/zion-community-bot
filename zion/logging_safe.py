from __future__ import annotations

import logging
import os
import re
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


def redact_secrets(value: object) -> str:
    text = str(value)

    for secret in _sensitive_values():
        text = text.replace(secret, "[REDACTED]")

    text = TELEGRAM_TOKEN_REGEX.sub(
        "[REDACTED_TELEGRAM_TOKEN]",
        text,
    )
    text = BEARER_REGEX.sub(r"\1[REDACTED]", text)
    text = SECRET_PARAMETER_REGEX.sub(
        r"\1[REDACTED]",
        text,
    )
    return text


class SecretSafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_secrets(super().format(record))


def configure_logging(log_path: Path, level: int = logging.INFO) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)

    formatter = SecretSafeFormatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(formatter)

    try:
        os.chmod(log_path, 0o600)
    except OSError:
        pass

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
