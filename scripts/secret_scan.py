#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


TELEGRAM_TOKEN = re.compile(
    rb"(?<![A-Za-z0-9_])\d{6,}:[A-Za-z0-9_-]{20,}"
)

FAKE_TELEGRAM_TOKENS = {
    b"123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
}

PEM_PRIVATE_KEY = re.compile(
    rb"-----BEGIN "
    rb"(?:RSA |EC |OPENSSH )?"
    rb"PRIVATE"
    rb" KEY-----"
)

HIGH_RISK_PREFIXES = (
    b"gh" + b"p_",
    b"github" + b"_pat_",
    b"AK" + b"IA",
)

ENV_SECRET_ASSIGNMENT = re.compile(
    rb"(?m)^(TELEGRAM_BOT_TOKEN|MISTRAL_API_KEY)=(.+)$"
)

ALLOWED_ENV_VALUES = {
    b"",
    b"<local secret>",
    b"<secret>",
    b"REPLACE_ME",
}


def tracked_files() -> list[Path]:
    raw = subprocess.check_output(
        ["git", "ls-files", "-z"],
    )
    return [
        Path(item.decode("utf-8"))
        for item in raw.split(b"\0")
        if item
    ]


def scan_file(path: Path) -> list[str]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        return [f"{path}: não foi possível ler: {exc}"]

    if b"\0" in data:
        return []

    findings: list[str] = []

    for match in TELEGRAM_TOKEN.finditer(data):
        token = match.group(0)
        if token not in FAKE_TELEGRAM_TOKENS:
            findings.append(
                f"{path}: possível Telegram bot token"
            )

    if PEM_PRIVATE_KEY.search(data):
        findings.append(
            f"{path}: possível chave privada PEM"
        )

    for prefix in HIGH_RISK_PREFIXES:
        if prefix in data:
            findings.append(
                f"{path}: possível segredo com prefixo {prefix.decode('ascii')}"
            )

    for match in ENV_SECRET_ASSIGNMENT.finditer(data):
        value = match.group(2).strip()
        if value not in ALLOWED_ENV_VALUES:
            findings.append(
                f"{path}: atribuição não vazia para "
                f"{match.group(1).decode('ascii')}"
            )

    return findings


def main() -> int:
    findings: list[str] = []

    for path in tracked_files():
        findings.extend(scan_file(path))

    if findings:
        print("SECRET SCAN: FALHOU", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1

    print("SECRET SCAN: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
