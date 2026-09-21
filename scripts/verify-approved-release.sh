#!/usr/bin/env bash
set -euo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="/home/zetta/zion-community-bot"
SYSTEM_PYTHON="/usr/bin/python3"
EXPECTED="${ZION_DEPLOY_COMMIT:-}"
RELEASE_SOURCE="${ZION_RELEASE_SOURCE:-production}"
case "$RELEASE_SOURCE" in
  candidate)
    REMOTE_BRANCH="zion-v1.1-dev"
    APPROVED_REF="origin/zion-v1.1-dev"
    ;;
  production)
    REMOTE_BRANCH="zion-v1"
    APPROVED_REF="origin/zion-v1"
    ;;
  *)
    echo "ERRO: ZION_RELEASE_SOURCE deve ser candidate ou production." >&2
    exit 64
    ;;
esac
EXPECTED_REPO="zettaceo/zion-community-bot"
RUNTIME_BASE="/home/zetta/.local/share/zion-community-bot/runtimes"
PYTHON="$RUNTIME_BASE/$EXPECTED/bin/python"
EXPECTED_USER="zetta"
SAFE_GIT_SSH_COMMAND="/usr/bin/ssh -F /dev/null -o BatchMode=yes -o StrictHostKeyChecking=yes -o ProxyCommand=none -o ProxyJump=none -o PermitLocalCommand=no"

if [[ ! "$EXPECTED" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "ERRO: ZION_DEPLOY_COMMIT deve ser um SHA completo de 40 caracteres." >&2
  exit 2
fi

if [[ "$(id -un)" != "$EXPECTED_USER" ]]; then
  echo "ERRO: execute como $EXPECTED_USER." >&2
  exit 2
fi
if [[ ! -x "$SYSTEM_PYTHON" ]]; then
  echo "ERRO: $SYSTEM_PYTHON ausente." >&2
  exit 2
fi
"$SYSTEM_PYTHON" -I "$SCRIPT_ROOT/scripts/check-git-release-boundary.py" \
  --root "$ROOT"
"$SYSTEM_PYTHON" -I "$SCRIPT_ROOT/scripts/check-python-release-env.py"
if [[ "${ZION_GITHUB_GATES_PROVEN:-}" != "YES" ]]; then
  echo "ERRO: confirme os gates GitHub antes de verificar release aprovado." >&2
  exit 2
fi

if [[ ! -x "$PYTHON" ]] \
  || [[ ! -f "$RUNTIME_BASE/$EXPECTED/release-sha.txt" ]] \
  || [[ "$(cat "$RUNTIME_BASE/$EXPECTED/release-sha.txt" 2>/dev/null || true)" != "$EXPECTED" ]]; then
  echo "ERRO: runtime candidato por SHA ausente ou inválido." >&2
  exit 2
fi

origin_url="$(/usr/bin/git -C "$ROOT" remote get-url origin 2>/dev/null || true)"
case "$origin_url" in
  "https://github.com/$EXPECTED_REPO"|"https://github.com/$EXPECTED_REPO.git"|"git@github.com:$EXPECTED_REPO.git"|"ssh://git@github.com/$EXPECTED_REPO.git")
    ;;
  *)
    echo "ERRO: origin não aponta para o repositório GitHub esperado." >&2
    exit 2
    ;;
esac

if command -v timeout >/dev/null 2>&1; then
  remote_line="$(timeout 20 env GIT_TERMINAL_PROMPT=0 /usr/bin/git -c "core.sshCommand=$SAFE_GIT_SSH_COMMAND" -c ssh.variant=ssh -C "$ROOT" ls-remote --exit-code origin "refs/heads/$REMOTE_BRANCH" 2>/dev/null | head -n1 || true)"
else
  remote_line="$(env GIT_TERMINAL_PROMPT=0 /usr/bin/git -c "core.sshCommand=$SAFE_GIT_SSH_COMMAND" -c ssh.variant=ssh -C "$ROOT" ls-remote --exit-code origin "refs/heads/$REMOTE_BRANCH" 2>/dev/null | head -n1 || true)"
fi
remote_sha="${remote_line%%[[:space:]]*}"
if [[ "$remote_sha" != "$EXPECTED" ]]; then
  echo "ERRO: HEAD remoto ao vivo não corresponde a ZION_DEPLOY_COMMIT." >&2
  exit 2
fi

approved_sha="$(/usr/bin/git -C "$ROOT" rev-parse "$APPROVED_REF^{commit}" 2>/dev/null || true)"
if [[ "$approved_sha" != "$EXPECTED" ]]; then
  echo "ERRO: $APPROVED_REF=$approved_sha, esperado=$EXPECTED." >&2
  echo "Execute /usr/bin/git fetch explicitamente e revise o novo SHA antes de tentar novamente." >&2
  exit 2
fi

if ! /usr/bin/git -C "$ROOT" cat-file -e "$EXPECTED^{commit}" 2>/dev/null; then
  echo "ERRO: commit aprovado não existe no repositório local." >&2
  exit 2
fi

tmp_root="$(mktemp -d /tmp/zion-approved-release.XXXXXX)"
chmod 700 "$tmp_root"
candidate="$tmp_root/candidate"
worktree_added=false

cleanup() {
  if [[ "$worktree_added" == true ]]; then
    /usr/bin/git -C "$ROOT" worktree remove --force "$candidate" >/dev/null 2>&1 || true
  fi
  rm -rf "$tmp_root"
}
trap cleanup EXIT

GIT_NO_REPLACE_OBJECTS=1 \
/usr/bin/git -c core.hooksPath=/dev/null -C "$ROOT" \
  worktree add --detach "$candidate" "$EXPECTED" >/dev/null
worktree_added=true

echo "Approved release source: $RELEASE_SOURCE"
echo "Approved release candidate: $EXPECTED"
echo "Temporary candidate worktree: created"
echo "Production service remains running during verification."

ZION_EXPECTED_COMMIT="$EXPECTED" \
ZION_RELEASE_SOURCE="$RELEASE_SOURCE" \
ZION_GITHUB_GATES_PROVEN=YES \
  bash "$candidate/scripts/predeploy-v11.sh"

echo
echo "APPROVED RELEASE VERIFICATION: OK"
echo "No production service was stopped/restarted."
echo "No production tracked file was modified."
