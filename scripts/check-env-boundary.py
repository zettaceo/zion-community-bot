from __future__ import annotations

import argparse
import os
import pwd
import re
import stat
from pathlib import Path


KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
MAX_ENV_BYTES = 256 * 1024


def _regular_private_file(
    path: Path,
    *,
    expected_owner: str,
) -> None:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("environment file must be a regular non-symlink file")

    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError("environment file must be regular")
    if info.st_nlink != 1:
        raise RuntimeError("environment file must not have hard links")

    mode = stat.S_IMODE(info.st_mode)
    if mode != 0o600:
        raise RuntimeError(
            f"environment file mode must be 0600; found {oct(mode)}"
        )

    try:
        owner = pwd.getpwuid(info.st_uid).pw_name
    except KeyError as exc:
        raise RuntimeError("environment file owner is unknown") from exc
    if owner != expected_owner:
        raise RuntimeError(
            "environment file owner mismatch: "
            f"expected={expected_owner} actual={owner}"
        )

    if info.st_size > MAX_ENV_BYTES:
        raise RuntimeError(
            f"environment file exceeds {MAX_ENV_BYTES} bytes"
        )


def _parse_assignment_keys(
    path: Path,
    *,
    label: str,
) -> list[str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise RuntimeError(
            f"{label} could not be read: {type(exc).__name__}"
        ) from exc

    if len(raw) > MAX_ENV_BYTES:
        raise RuntimeError(
            f"{label} exceeds {MAX_ENV_BYTES} bytes"
        )
    if b"\x00" in raw:
        raise RuntimeError(f"{label} contains NUL bytes")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(
            f"{label} is not valid UTF-8"
        ) from exc

    keys: list[str] = []
    seen: set[str] = set()

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            raise RuntimeError(
                f"{label} line {line_number}: export syntax is not allowed"
            )
        if "=" not in line:
            raise RuntimeError(
                f"{label} line {line_number}: invalid assignment"
            )

        key, _value = line.split("=", 1)
        key = key.strip()
        if not KEY_RE.fullmatch(key):
            raise RuntimeError(
                f"{label} line {line_number}: invalid key name"
            )
        if key in seen:
            raise RuntimeError(
                f"{label}: duplicate key {key}"
            )
        seen.add(key)
        keys.append(key)

    return keys


def allowed_keys(path: Path) -> frozenset[str]:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(
            "environment allowlist must be a regular versioned file"
        )
    keys = _parse_assignment_keys(path, label="environment allowlist")
    if not keys:
        raise RuntimeError("environment allowlist is empty")
    return frozenset(keys)


def validate_environment(
    env_path: Path,
    *,
    allowlist_path: Path,
    expected_owner: str,
) -> tuple[str, ...]:
    _regular_private_file(
        env_path,
        expected_owner=expected_owner,
    )
    allowed = allowed_keys(allowlist_path)
    configured = _parse_assignment_keys(
        env_path,
        label="production environment",
    )

    unknown = sorted(set(configured) - allowed)
    if unknown:
        # Key names are configuration metadata; values are never emitted.
        raise RuntimeError(
            "production environment contains non-allowlisted keys: "
            + ",".join(unknown)
        )

    return tuple(configured)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate ZION production .env metadata and key names "
            "without printing secret values."
        )
    )
    parser.add_argument("--env", required=True)
    parser.add_argument("--allowlist", required=True)
    parser.add_argument("--owner", default="zetta")
    args = parser.parse_args()

    configured = validate_environment(
        Path(args.env).expanduser(),
        allowlist_path=Path(args.allowlist).expanduser(),
        expected_owner=args.owner,
    )
    print(
        "environment boundary: OK | "
        f"configured_keys={len(configured)} | values=not-read-to-output"
    )


if __name__ == "__main__":
    main()
