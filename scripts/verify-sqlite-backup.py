#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from zion.db import SUPPORTED_SCHEMA_VERSION, ZionDB


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a ZION SQLite backup without modifying it."
        )
    )
    parser.add_argument("database", type=Path)
    parser.add_argument(
        "--sha256",
        dest="expected_sha256",
        help="Expected lowercase/uppercase SHA-256 hex digest.",
    )
    args = parser.parse_args()

    path = args.database.expanduser()
    if not path.is_file():
        print(f"ERROR: backup not found: {path}", file=sys.stderr)
        return 2
    if path.is_symlink():
        print("ERROR: backup path must not be a symlink", file=sys.stderr)
        return 2

    actual_sha256 = sha256_file(path)
    if (
        args.expected_sha256
        and actual_sha256.lower()
        != args.expected_sha256.strip().lower()
    ):
        print(
            "ERROR: SHA-256 mismatch",
            file=sys.stderr,
        )
        return 3

    db = ZionDB(path, readonly=True)
    try:
        verification = db.verify_integrity(full=True)
        schema_version = db.schema_version()
    finally:
        db.close()

    if not verification["ok"]:
        print(
            f"ERROR: SQLite verification failed: {verification}",
            file=sys.stderr,
        )
        return 4

    if schema_version > SUPPORTED_SCHEMA_VERSION:
        print(
            "ERROR: backup schema is newer than this verifier: "
            f"backup=v{schema_version} "
            f"supported=v{SUPPORTED_SCHEMA_VERSION}",
            file=sys.stderr,
        )
        return 5

    print("ZION SQLITE BACKUP: OK")
    print(f"path={path}")
    print(f"sha256={actual_sha256}")
    print(f"size_bytes={path.stat().st_size}")
    print(f"schema_version={schema_version}")
    print("integrity_check=OK")
    print("foreign_key_check=OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
