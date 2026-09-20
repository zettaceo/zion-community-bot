#!/usr/bin/env bash
set -euo pipefail

ROOT="${ZION_PROD_ROOT:-/home/zetta/zion-community-bot}"
EXPECTED="${ZION_DEPLOY_COMMIT:-}"
APPROVED_REF="${ZION_APPROVED_REF:-origin/zion-v1}"
PYTHON="${ZION_RUNTIME_PYTHON:-$ROOT/.venv/bin/python}"
EXPECTED_USER="${ZION_REMOTE_USER:-zetta}"

if [[ ! "$EXPECTED" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "ERRO: ZION_DEPLOY_COMMIT deve ser um SHA completo de 40 caracteres." >&2
  exit 2
fi

if [[ "$(id -un)" != "$EXPECTED_USER" ]]; then
  echo "ERRO: execute como $EXPECTED_USER." >&2
  exit 2
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "ERRO: runtime Python ausente: $PYTHON" >&2
  exit 2
fi

approved_sha="$(git -C "$ROOT" rev-parse "$APPROVED_REF^{commit}" 2>/dev/null || true)"
if [[ "$approved_sha" != "$EXPECTED" ]]; then
  echo "ERRO: $APPROVED_REF=$approved_sha, esperado=$EXPECTED." >&2
  echo "Execute git fetch explicitamente e revise o novo SHA antes de tentar novamente." >&2
  exit 2
fi

if ! git -C "$ROOT" cat-file -e "$EXPECTED^{commit}" 2>/dev/null; then
  echo "ERRO: commit aprovado não existe no repositório local." >&2
  exit 2
fi

tmp_root="$(mktemp -d /tmp/zion-approved-release.XXXXXX)"
chmod 700 "$tmp_root"
candidate="$tmp_root/candidate"
worktree_added=false

cleanup() {
  if [[ "$worktree_added" == true ]]; then
    git -C "$ROOT" worktree remove --force "$candidate" >/dev/null 2>&1 || true
  fi
  rm -rf "$tmp_root"
}
trap cleanup EXIT

git -C "$ROOT" worktree add --detach "$candidate" "$EXPECTED" >/dev/null
worktree_added=true

echo "Approved release candidate: $EXPECTED"
echo "Temporary candidate worktree: created"
echo "Production service remains running during verification."

ZION_RUNTIME_PYTHON="$PYTHON" ZION_PROD_ROOT="$ROOT" ZION_EXPECTED_COMMIT="$EXPECTED" ZION_APPROVED_REF="$APPROVED_REF" bash "$candidate/scripts/predeploy-v11.sh"

echo
echo "APPROVED RELEASE VERIFICATION: OK"
echo "No production service was stopped/restarted."
echo "No production tracked file was modified."
