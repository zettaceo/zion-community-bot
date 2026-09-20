from __future__ import annotations

import sqlite3
import sys
from importlib.metadata import PackageNotFoundError, distributions, version
from pathlib import Path


def parse_version(value: str) -> tuple[int, int, int]:
    parts: list[int] = []
    for chunk in value.split(".")[:3]:
        digits = ""
        for char in chunk:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits or 0))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)  # type: ignore[return-value]


def package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError as exc:
        raise RuntimeError(f"missing package: {name}") from exc


def canonical_distribution_name(value: str) -> str:
    return "-".join(
        chunk
        for chunk in value.lower().replace("_", "-").replace(".", "-").split("-")
        if chunk
    )


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise RuntimeError(message)


def runtime_lock() -> dict[str, str]:
    lock_path = Path(__file__).resolve().parent.parent / "requirements.lock"
    if not lock_path.is_file() or lock_path.is_symlink():
        raise RuntimeError("requirements.lock missing or symlinked")

    locked: dict[str, str] = {}
    for raw_line in lock_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        requirement = parts[0]
        hashes = parts[1:]
        if "==" not in requirement:
            raise RuntimeError(
                f"invalid requirements.lock entry: {line}"
            )
        name, expected = requirement.split("==", 1)
        name = name.strip()
        expected = expected.strip()
        if not name or not expected or name in locked:
            raise RuntimeError(
                f"invalid requirements.lock entry: {line}"
            )
        if not hashes:
            raise RuntimeError(
                f"requirements.lock entry missing SHA-256 hash: {name}"
            )
        for item in hashes:
            prefix = "--hash=sha256:"
            digest = item[len(prefix):] if item.startswith(prefix) else ""
            if (
                len(digest) != 64
                or any(char not in "0123456789abcdefABCDEF" for char in digest)
            ):
                raise RuntimeError(
                    f"invalid requirements.lock SHA-256 hash: {name}"
                )
        locked[name] = expected

    if not locked:
        raise RuntimeError("requirements.lock is empty")
    return locked


def verify_runtime_lock() -> dict[str, str]:
    locked = runtime_lock()
    locked_names = {
        canonical_distribution_name(name)
        for name in locked
    }

    for name, expected in locked.items():
        actual = package_version(name)
        require(
            actual == expected,
            (
                "runtime package differs from audited lock: "
                f"{name} expected={expected} actual={actual}"
            ),
        )

    bootstrap_allowed = {"pip", "setuptools", "wheel"}
    installed: set[str] = set()
    for dist in distributions():
        raw_name = str(dist.metadata.get("Name") or "").strip()
        if not raw_name:
            raise RuntimeError(
                "installed distribution without a canonical name"
            )
        installed.add(canonical_distribution_name(raw_name))

    unexpected = sorted(
        installed - locked_names - bootstrap_allowed
    )
    require(
        not unexpected,
        (
            "runtime contains distributions outside audited lock: "
            + ",".join(unexpected)
        ),
    )
    return locked


def main() -> None:
    locked = verify_runtime_lock()

    python_version = sys.version_info[:3]
    require(
        python_version[:2] == (3, 12),
        (
            "audited ZION v1.1 runtime requires Python 3.12.x; "
            f"found {sys.version.split()[0]}"
        ),
    )

    ptb_raw = package_version("python-telegram-bot")
    dotenv_raw = package_version("python-dotenv")
    httpx_raw = package_version("httpx")
    idna_raw = package_version("idna")

    ptb = parse_version(ptb_raw)
    dotenv = parse_version(dotenv_raw)
    httpx = parse_version(httpx_raw)
    idna = parse_version(idna_raw)

    require(
        21 <= ptb[0] < 23,
        f"python-telegram-bot must be >=21,<23; found {ptb_raw}",
    )
    require(
        dotenv[0] == 1,
        f"python-dotenv must be >=1,<2; found {dotenv_raw}",
    )
    require(
        httpx[0] == 0 and httpx >= (0, 27, 0),
        f"httpx must be >=0.27,<1; found {httpx_raw}",
    )
    require(
        idna[0] == 3,
        f"idna must be >=3,<4; found {idna_raw}",
    )

    sqlite_version = parse_version(sqlite3.sqlite_version)
    require(
        sqlite_version >= (3, 24, 0),
        (
            "SQLite >=3.24 required for UPSERT support; "
            f"found {sqlite3.sqlite_version}"
        ),
    )

    print(
        "runtime compatibility: OK | "
        f"python={sys.version.split()[0]} | "
        f"ptb={ptb_raw} | dotenv={dotenv_raw} | "
        f"httpx={httpx_raw} | idna={idna_raw} | "
        f"sqlite={sqlite3.sqlite_version} | "
        f"locked_packages={len(locked)}"
    )


if __name__ == "__main__":
    main()
