#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROD_ROOT="/home/zetta/zion-community-bot"
SYSTEM_PYTHON="/usr/bin/python3"
EXPECTED_USER="zetta"
EXPECTED="${ZION_DEPLOY_COMMIT:-}"

RUNTIME_PARENT="/home/zetta/.local/share/zion-community-bot"
RUNTIME_BASE="$RUNTIME_PARENT/runtimes"
RUNTIME_DIR="$RUNTIME_BASE/$EXPECTED"
CURRENT_LINK="$RUNTIME_BASE/current"
LEGACY_RUNTIME="$PROD_ROOT/.venv"

if [[ "$(id -un)" != "$EXPECTED_USER" ]]; then
  echo "ERRO: execute como $EXPECTED_USER." >&2
  exit 2
fi

if [[ ! "$EXPECTED" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "ERRO: ZION_DEPLOY_COMMIT deve ser SHA completo." >&2
  exit 2
fi

if [[ ! -x "$SYSTEM_PYTHON" ]]; then
  echo "ERRO: $SYSTEM_PYTHON ausente." >&2
  exit 2
fi

"$SYSTEM_PYTHON" - <<'PY'
import sys
if sys.version_info[:2] != (3, 12):
    raise SystemExit(
        "Python de bootstrap deve ser 3.12.x; "
        f"encontrado={sys.version.split()[0]}"
    )
PY

"$SYSTEM_PYTHON" -I "$ROOT/scripts/check-git-release-boundary.py"   --root "$ROOT"

HEAD_SHA="$(GIT_NO_REPLACE_OBJECTS=1 git -C "$ROOT" rev-parse HEAD)"
if [[ "$HEAD_SHA" != "$EXPECTED" ]]; then
  echo "ERRO: worktree de runtime não corresponde ao SHA aprovado." >&2
  exit 2
fi

STATUS="$(git -C "$ROOT" status --porcelain --untracked-files=all)"
if [[ -n "$STATUS" ]]; then
  echo "ERRO: candidate worktree contaminada." >&2
  exit 2
fi

if [[ -e "$ROOT/.env" || -L "$ROOT/.env" ]]; then
  echo "ERRO: candidate worktree não pode conter .env local." >&2
  exit 2
fi

if [[ -L "$RUNTIME_PARENT" || -L "$RUNTIME_BASE" ]]; then
  echo "ERRO: fronteira de runtime não pode usar diretório symlink." >&2
  exit 2
fi

mkdir -p "$RUNTIME_BASE"
chmod 700 "$RUNTIME_PARENT" "$RUNTIME_BASE"

for path in "$RUNTIME_PARENT" "$RUNTIME_BASE"; do
  real="$(readlink -f -- "$path" 2>/dev/null || true)"
  if [[ "$real" != "$path" ]]; then
    echo "ERRO: caminho de runtime resolve por alias/symlink: $path -> $real" >&2
    exit 2
  fi
  if [[ "$(stat -c '%U' "$path")" != "$EXPECTED_USER" ]]; then
    echo "ERRO: $path deve pertencer a $EXPECTED_USER." >&2
    exit 2
  fi
done

validate_runtime() {
  local python="$1"
  "$python" "$ROOT/scripts/check-runtime.py"
  "$python" -m pip check
}

validate_previous_runtime_target() {
  local target="$1"

  if [[ "$target" == "$LEGACY_RUNTIME" ]]; then
    if [[ ! -x "$target/bin/python" ]]; then
      echo "ERRO: runtime legado inválido." >&2
      return 1
    fi
    return 0
  fi

  case "$target" in
    "$RUNTIME_BASE"/*) ;;
    *)
      echo "ERRO: runtime/current anterior aponta fora da fronteira aprovada." >&2
      return 1
      ;;
  esac

  local name
  name="$(basename "$target")"
  if [[ ! "$name" =~ ^[0-9a-fA-F]{40}$ ]]; then
    echo "ERRO: runtime anterior não possui identidade SHA." >&2
    return 1
  fi
  if [[ ! -f "$target/release-sha.txt" ]] \
    || [[ "$(cat "$target/release-sha.txt" 2>/dev/null || true)" != "$name" ]] \
    || [[ ! -x "$target/bin/python" ]]; then
    echo "ERRO: runtime anterior possui identidade inválida." >&2
    return 1
  fi
  validate_runtime "$target/bin/python"
}

if [[ -e "$CURRENT_LINK" || -L "$CURRENT_LINK" ]]; then
  if [[ ! -L "$CURRENT_LINK" ]]; then
    echo "ERRO: runtime/current deve ser symlink." >&2
    exit 2
  fi
  CURRENT_TARGET="$(readlink -f -- "$CURRENT_LINK" 2>/dev/null || true)"
  validate_previous_runtime_target "$CURRENT_TARGET"
else
  if [[ ! -x "$LEGACY_RUNTIME/bin/python" ]]; then
    echo "ERRO: runtime legado ausente; não é possível bootstrap seguro." >&2
    exit 2
  fi
  ln -s "$LEGACY_RUNTIME" "$CURRENT_LINK"
  CURRENT_TARGET="$LEGACY_RUNTIME"
fi

if [[ -e "$RUNTIME_DIR" || -L "$RUNTIME_DIR" ]]; then
  if [[ -L "$RUNTIME_DIR" || ! -d "$RUNTIME_DIR" ]]; then
    echo "ERRO: runtime candidato existente não é diretório regular." >&2
    exit 2
  fi
  if [[ ! -x "$RUNTIME_DIR/bin/python" ]]; then
    echo "ERRO: runtime candidato existente não possui Python." >&2
    exit 2
  fi
  if [[ ! -f "$RUNTIME_DIR/release-sha.txt" ]]     || [[ "$(cat "$RUNTIME_DIR/release-sha.txt")" != "$EXPECTED" ]]; then
    echo "ERRO: runtime candidato existente possui identidade inválida." >&2
    exit 2
  fi
  validate_runtime "$RUNTIME_DIR/bin/python"
  if find "$RUNTIME_DIR" \( -type f -o -type d \) -perm /0222 -print -quit \
    | grep -q .; then
    echo "ERRO: runtime candidato existente contém caminho gravável." >&2
    exit 2
  fi
  echo "release runtime: OK (reused) | sha=$EXPECTED"
  echo "runtime_path=$RUNTIME_DIR"
  echo "current_runtime_before=$CURRENT_TARGET"
  exit 0
fi

TMP_RUNTIME="$RUNTIME_BASE/.runtime-$EXPECTED.$BASHPID"
cleanup() {
  if [[ -n "${TMP_RUNTIME:-}" && -d "$TMP_RUNTIME" ]]; then
    rm -rf "$TMP_RUNTIME"
  fi
}
trap cleanup EXIT

"$SYSTEM_PYTHON" -m venv "$TMP_RUNTIME"
"$TMP_RUNTIME/bin/python" -m pip --isolated install \
  --disable-pip-version-check \
  --no-input \
  --no-deps \
  --only-binary=:all: \
  --index-url https://pypi.org/simple \
  -r "$ROOT/requirements.lock"

validate_runtime "$TMP_RUNTIME/bin/python"

printf '%s\n' "$EXPECTED" > "$TMP_RUNTIME/release-sha.txt"
sha256sum "$ROOT/requirements.lock" \
  | awk '{print $1}' > "$TMP_RUNTIME/requirements-lock.sha256"
chmod 0444 \
  "$TMP_RUNTIME/release-sha.txt" \
  "$TMP_RUNTIME/requirements-lock.sha256"

chmod -R a-w "$TMP_RUNTIME"

mv "$TMP_RUNTIME" "$RUNTIME_DIR"
TMP_RUNTIME=""

validate_runtime "$RUNTIME_DIR/bin/python"
if find "$RUNTIME_DIR" \( -type f -o -type d \) -perm /0222 -print -quit \
  | grep -q .; then
  echo "ERRO: runtime publicado contém caminho gravável." >&2
  exit 2
fi

echo "release runtime: OK (created) | sha=$EXPECTED"
echo "runtime_path=$RUNTIME_DIR"
echo "current_runtime_before=$CURRENT_TARGET"
echo "runtime/current was NOT switched to the candidate."
