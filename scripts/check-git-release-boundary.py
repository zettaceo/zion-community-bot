from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def git(
    root: Path,
    *args: str,
    allow_no_match: bool = False,
) -> str:
    env = os.environ.copy()
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    allowed_codes = {0, 1} if allow_no_match else {0}
    if result.returncode not in allowed_codes:
        raise RuntimeError(
            "git boundary command failed: "
            + " ".join(args[:2])
        )
    return result.stdout.strip()


def reject_git_environment() -> None:
    dangerous = (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_REPLACE_REF_BASE",
        "GIT_CONFIG",
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_SYSTEM",
        "GIT_CONFIG_COUNT",
        "GIT_SSH",
        "GIT_SSH_COMMAND",
        "GIT_SSL_NO_VERIFY",
    )
    present = sorted(
        name for name in dangerous
        if os.environ.get(name) not in (None, "")
    )
    if present:
        raise RuntimeError(
            "release shell contains forbidden Git environment variables: "
            + ",".join(present)
        )


def validate(root: Path) -> None:
    reject_git_environment()

    if not root.is_dir():
        raise RuntimeError("release repository root is missing")

    inside = git(root, "rev-parse", "--is-inside-work-tree")
    if inside != "true":
        raise RuntimeError("release path is not a Git worktree")

    hooks_path = git(
        root,
        "config",
        "--show-origin",
        "--get-all",
        "core.hooksPath",
        allow_no_match=True,
    )
    if hooks_path:
        raise RuntimeError(
            "core.hooksPath is configured; release requires default hooks boundary"
        )

    default_hooks = Path(
        git(root, "rev-parse", "--git-path", "hooks")
    )
    if not default_hooks.is_absolute():
        default_hooks = root / default_hooks

    if default_hooks.exists():
        active = sorted(
            item.name
            for item in default_hooks.iterdir()
            if (
                item.is_file()
                and not item.name.endswith(".sample")
                and os.access(item, os.X_OK)
            )
        )
        if active:
            raise RuntimeError(
                "active local Git hooks are not allowed for release: "
                + ",".join(active)
            )

    replacements = git(root, "replace", "-l")
    if replacements:
        raise RuntimeError(
            "Git replace refs are not allowed for release"
        )

    grafts = Path(
        git(root, "rev-parse", "--git-path", "info/grafts")
    )
    if not grafts.is_absolute():
        grafts = root / grafts
    if grafts.is_file() and grafts.stat().st_size > 0:
        raise RuntimeError(
            "Git grafts are not allowed for release"
        )

    shallow = git(root, "rev-parse", "--is-shallow-repository")
    if shallow != "false":
        raise RuntimeError(
            "production release repository must not be shallow"
        )

    print(
        "git release boundary: OK | "
        "hooks=none replace_refs=none grafts=none shallow=false"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate local Git state for a ZION production release."
    )
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    validate(Path(args.root).expanduser().resolve())


if __name__ == "__main__":
    main()
