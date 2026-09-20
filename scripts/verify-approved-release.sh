#!/usr/bin/env bash
set -euo pipefail

ROOT="${ZION_PROD_ROOT:-/home/zetta/zion-community-bot}"
EXPECTED="${ZION_DEPLOY_COMMIT:-}"
REMOTE_BRANCH="${ZION_PRODUCTION_REMOTE_BRANCH:-zion-v1}"
APPROVED_REF="${ZION_APPROVED_REF:-origin/$REMOTE_BRANCH}"
EXPECTED_REPO="${ZION_EXPECTED_GITHUB_REPO:-zettaceo/zion-community-bot}"
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
if [[ "${ZION_GITHUB_GATES_PROVEN:-}" != "YES" ]]; then
  echo "ERRO: confirme os gates GitHub antes de verificar release aprovado." >&2
  exit 2
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "ERRO: runtime Python ausente: $PYTHON" >&2
  exit 2
fi

origin_url="$(git -C "$ROOT" remote get-url origin 2>/dev/null || true)"
case "$origin_url" in
  "https://github.com/$EXPECTED_REPO"|"https://github.com/$EXPECTED_REPO.git"|"git@github.com:$EXPECTED_REPO.git"|"ssh://git@github.com/$EXPECTED_REPO.git")
    ;;
  *)
    echo "ERRO: origin não aponta para o repositório GitHub esperado." >&2
    exit 2
    ;;
esac

if command -v timeout >/dev/null 2>&1; then
  remote_line="$(timeout 20 env GIT_TERMINAL_PROMPT=0 git -C "$ROOT" ls-remote --exit-code origin "refs/heads/$REMOTE_BRANCH" 2>/dev/null | head -n1 || true)"
else
  remote_line="$(env GIT_TERMINAL_PROMPT=0 git -C "$ROOT" ls-remote --exit-code origin "refs/heads/$REMOTE_BRANCH" 2>/dev/null | head -n1 || true)"
fi
remote_sha="${remote_line%%[[:space:]]*}"
if [[ "$remote_sha" != "$EXPECTED" ]]; then
  echo "ERRO: HEAD remoto ao vivo não corresponde a ZION_DEPLOY_COMMIT." >&2
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

ZION_RUNTIME_PYTHON="$PYTHON" \
ZION_PROD_ROOT="$ROOT" \
ZION_EXPECTED_COMMIT="$EXPECTED" \
ZION_APPROVED_REF="$APPROVED_REF" \
ZION_GITHUB_GATES_PROVEN=YES \
  bash "$candidate/scripts/predeploy-v11.sh"

echo
echo "APPROVED RELEASE VERIFICATION: OK"
echo "No production service was stopped/restarted."
echo "No production tracked file was modified."
