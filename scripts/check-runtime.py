from __future__ import annotations

import sqlite3
import sys
from importlib.metadata import PackageNotFoundError, version


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


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    python_version = sys.version_info[:3]
    require(
        python_version >= (3, 10, 0),
        f"Python >=3.10 required; found {sys.version.split()[0]}",
    )

    ptb_raw = package_version("python-telegram-bot")
    dotenv_raw = package_version("python-dotenv")
    httpx_raw = package_version("httpx")

    ptb = parse_version(ptb_raw)
    dotenv = parse_version(dotenv_raw)
    httpx = parse_version(httpx_raw)

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
        f"httpx={httpx_raw} | sqlite={sqlite3.sqlite_version}"
    )


if __name__ == "__main__":
    main()
