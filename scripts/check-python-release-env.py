from __future__ import annotations

import os


def main() -> None:
    forbidden = sorted(
        name
        for name in os.environ
        if name.startswith("PYTHON")
    )
    if forbidden:
        raise RuntimeError(
            "release shell contains forbidden Python environment variables: "
            + ",".join(forbidden)
        )

    print("python release environment: OK | python_env=clean")


if __name__ == "__main__":
    main()
