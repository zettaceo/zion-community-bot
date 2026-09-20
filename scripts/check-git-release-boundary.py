from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path, PurePosixPath


SAFE_IGNORED_TOP_LEVEL = frozenset(
    {
        ".venv",
        "venv",
        "env",
        "logs",
        "backups",
        ".pytest_cache",
        ".mypy_cache",
        "htmlcov",
        ".vscode",
        ".idea",
    }
)
IMPORTABLE_CODE_SUFFIXES = (".py", ".pyc", ".pyo", ".pyd", ".so")
GIT_EXECUTABLE = "/usr/bin/git"


def git(
    root: Path,
    *args: str,
    allow_no_match: bool = False,
) -> str:
    env = os.environ.copy()
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    result = subprocess.run(
        [GIT_EXECUTABLE, "-C", str(root), *args],
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
        "GIT_CONFIG_PARAMETERS",
        "GIT_CONFIG_COUNT",
        "GIT_INDEX_FILE",
        "GIT_NAMESPACE",
        "GIT_SSH",
        "GIT_SSH_COMMAND",
        "GIT_ASKPASS",
        "GIT_PROXY_COMMAND",
        "GIT_EXEC_PATH",
        "GIT_SSL_NO_VERIFY",
        "GIT_SSL_CAINFO",
        "GIT_SSL_CAPATH",
    )
    present = {
        name
        for name in dangerous
        if os.environ.get(name) not in (None, "")
    }
    present.update(
        name
        for name, value in os.environ.items()
        if (
            value not in (None, "")
            and (
                name.startswith("GIT_CONFIG_KEY_")
                or name.startswith("GIT_CONFIG_VALUE_")
            )
        )
    )
    present = sorted(present)
    if present:
        raise RuntimeError(
            "release shell contains forbidden Git environment variables: "
            + ",".join(present)
        )


def git_path(root: Path, relative: str) -> Path:
    path = Path(git(root, "rev-parse", "--git-path", relative))
    if not path.is_absolute():
        path = root / path
    return path


def active_metadata_rules(path: Path) -> list[str]:
    if not path.exists():
        return []
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(
            f"Git metadata path must be a regular file: {path}"
        )
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise RuntimeError(
            f"Git metadata file could not be read safely: {path}"
        ) from exc
    return [
        line
        for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    ]


def reject_local_ignore_and_attribute_overrides(root: Path) -> None:
    excludes = git_path(root, "info/exclude")
    if active_metadata_rules(excludes):
        raise RuntimeError(
            "local Git exclude rules are not allowed for release"
        )

    attributes = git_path(root, "info/attributes")
    if active_metadata_rules(attributes):
        raise RuntimeError(
            "local Git attribute rules are not allowed for release"
        )

    forbidden_config = (
        ("core.excludesFile", "core.excludesFile"),
        ("core.attributesFile", "core.attributesFile"),
        ("core.fsmonitor", "core.fsmonitor"),
        ("core.sshCommand", "core.sshCommand"),
        ("core.worktree", "core.worktree"),
    )
    for key, label in forbidden_config:
        configured = git(
            root,
            "config",
            "--show-origin",
            "--get-all",
            key,
            allow_no_match=True,
        )
        if configured:
            raise RuntimeError(
                f"{label} is configured; release requires a neutral Git boundary"
            )


def reject_ignored_importable_code(root: Path) -> None:
    ignored = git(
        root,
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "-z",
        allow_no_match=True,
    )
    suspicious: list[str] = []
    for raw in ignored.split("\0"):
        if not raw:
            continue
        path = PurePosixPath(raw)
        if not path.parts:
            continue
        if path.parts[0] in SAFE_IGNORED_TOP_LEVEL:
            continue
        lowered = raw.lower()
        if lowered.endswith(IMPORTABLE_CODE_SUFFIXES):
            suspicious.append(raw)

    if suspicious:
        preview = ",".join(sorted(suspicious)[:12])
        if len(suspicious) > 12:
            preview += f",...(+{len(suspicious) - 12})"
        raise RuntimeError(
            "ignored untracked importable code is not allowed for release: "
            + preview
        )


def reject_release_index_flags(root: Path) -> None:
    entries = git(
        root,
        "ls-files",
        "-v",
        "-z",
    )
    suspicious: list[str] = []
    for raw in entries.split("\0"):
        if not raw:
            continue
        if len(raw) < 3 or raw[1] != " ":
            raise RuntimeError(
                "unexpected git ls-files -v output while validating release index"
            )
        tag = raw[0]
        path = raw[2:]
        if tag == "S" or tag.islower():
            suspicious.append(f"{tag}:{path}")

    if suspicious:
        preview = ",".join(sorted(suspicious)[:12])
        if len(suspicious) > 12:
            preview += f",...(+{len(suspicious) - 12})"
        raise RuntimeError(
            "Git index contains assume-unchanged/skip-worktree entries; "
            "release worktree cannot prove exact tracked content: "
            + preview
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

    reject_local_ignore_and_attribute_overrides(root)

    url_rewrites = git(
        root,
        "config",
        "--show-origin",
        "--get-regexp",
        r"^url\..*\.insteadof$",
        allow_no_match=True,
    )
    if url_rewrites:
        raise RuntimeError(
            "Git url.*.insteadOf rewrite is not allowed for release"
        )

    uploadpack = git(
        root,
        "config",
        "--show-origin",
        "--get-all",
        "remote.origin.uploadpack",
        allow_no_match=True,
    )
    if uploadpack:
        raise RuntimeError(
            "remote.origin.uploadpack override is not allowed for release"
        )

    default_hooks = git_path(root, "hooks")
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

    grafts = git_path(root, "info/grafts")
    if grafts.is_file() and grafts.stat().st_size > 0:
        raise RuntimeError(
            "Git grafts are not allowed for release"
        )

    shallow = git(root, "rev-parse", "--is-shallow-repository")
    if shallow != "false":
        raise RuntimeError(
            "production release repository must not be shallow"
        )

    reject_release_index_flags(root)
    reject_ignored_importable_code(root)

    print(
        "git release boundary: OK | "
        "hooks=none replace_refs=none grafts=none shallow=false "
        "local_ignores=none index_flags=none ignored_importable_code=none"
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
