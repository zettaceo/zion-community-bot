#!/usr/bin/env bash
set -uo pipefail

REPORT_ONLY=false
if [[ "${1:-}" == "--report-only" ]]; then
  REPORT_ONLY=true
elif [[ -n "${1:-}" ]]; then
  echo "usage: $0 [--report-only]" >&2
  exit 64
fi

if [[ "$REPORT_ONLY" == true ]]; then
  ROOT="${ZION_PROD_ROOT:-/home/zetta/zion-community-bot}"
  EXPECTED_USER="${ZION_REMOTE_USER:-zetta}"
else
  ROOT="/home/zetta/zion-community-bot"
  EXPECTED_USER="zetta"
fi
EXPECTED="${ZION_DEPLOY_COMMIT:-}"
REMOTE_BRANCH="zion-v1"
APPROVED_REF="origin/zion-v1"
EXPECTED_REPO="zettaceo/zion-community-bot"
LOCAL_PROD_BRANCH="zion-v1-prod"
ENV_FILE="$ROOT/.env"

failures=0
warnings=0

pass() { printf 'PASS: %s\n' "$1"; }
warn() { warnings=$((warnings + 1)); printf 'WARN: %s\n' "$1"; }
fail() { failures=$((failures + 1)); printf 'FAIL: %s\n' "$1"; }

echo "ZION DEPLOYMENT PREFLIGHT"
echo "========================="
echo "This script is read-only for production runtime state."
echo

if [[ ! "$EXPECTED" =~ ^[0-9a-fA-F]{40}$ ]]; then
  fail "ZION_DEPLOY_COMMIT must be one full 40-character commit SHA"
fi

if [[ ! -d "$ROOT/.git" && ! -f "$ROOT/.git" ]]; then
  fail "production Git worktree not found at $ROOT"
else
  current_head="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
  current_branch="$(git -C "$ROOT" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  approved_sha="$(git -C "$ROOT" rev-parse "$APPROVED_REF^{commit}" 2>/dev/null || true)"
  origin_url="$(git -C "$ROOT" remote get-url origin 2>/dev/null || true)"

  case "$origin_url" in
    "https://github.com/$EXPECTED_REPO"|"https://github.com/$EXPECTED_REPO.git"|"git@github.com:$EXPECTED_REPO.git"|"ssh://git@github.com/$EXPECTED_REPO.git")
      pass "origin points to expected GitHub repository"
      ;;
    *)
      fail "origin does not point to the expected GitHub repository"
      ;;
  esac

  if command -v timeout >/dev/null 2>&1; then
    remote_line="$(timeout 20 env GIT_TERMINAL_PROMPT=0 git -C "$ROOT" ls-remote --exit-code origin "refs/heads/$REMOTE_BRANCH" 2>/dev/null | head -n1 || true)"
  else
    remote_line="$(env GIT_TERMINAL_PROMPT=0 git -C "$ROOT" ls-remote --exit-code origin "refs/heads/$REMOTE_BRANCH" 2>/dev/null | head -n1 || true)"
  fi
  remote_sha="${remote_line%%[[:space:]]*}"
  if [[ -n "$EXPECTED" && "$remote_sha" == "$EXPECTED" ]]; then
    pass "live origin/$REMOTE_BRANCH exactly matches approved commit"
  else
    fail "live origin/$REMOTE_BRANCH could not be proven equal to ZION_DEPLOY_COMMIT"
  fi

  if [[ -n "$EXPECTED" && "$approved_sha" == "$EXPECTED" ]]; then
    pass "$APPROVED_REF exactly matches approved commit"
  else
    fail "$APPROVED_REF does not exactly match ZION_DEPLOY_COMMIT"
  fi

  if [[ "$current_branch" == "$LOCAL_PROD_BRANCH" ]]; then
    pass "local production branch is $LOCAL_PROD_BRANCH"
  else
    fail "current branch=$current_branch (expected $LOCAL_PROD_BRANCH)"
  fi

  if git -C "$ROOT" diff --quiet     && git -C "$ROOT" diff --cached --quiet; then
    pass "tracked production worktree is clean"
  else
    fail "tracked production worktree has local changes"
  fi

  if [[ -n "$EXPECTED" && -n "$current_head" ]]     && git -C "$ROOT" merge-base --is-ancestor "$current_head" "$EXPECTED" 2>/dev/null; then
    pass "approved commit is a fast-forward descendant of current production"
  else
    fail "approved commit is not a proven fast-forward descendant"
  fi
fi

if [[ "$(id -un)" == "$EXPECTED_USER" ]]; then
  pass "operator user=$EXPECTED_USER"
else
  fail "operator user must be $EXPECTED_USER"
fi

if [[ -f "$ENV_FILE" && ! -L "$ENV_FILE" ]]; then
  env_mode="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || true)"
  env_owner="$(stat -c '%U' "$ENV_FILE" 2>/dev/null || true)"
  [[ "$env_mode" == "600" ]] && pass ".env mode=600" || fail ".env mode=$env_mode"
  [[ "$env_owner" == "$EXPECTED_USER" ]] && pass ".env owner=$EXPECTED_USER" || fail ".env owner=$env_owner"
else
  fail ".env missing or symlinked"
fi

if command -v systemctl >/dev/null 2>&1; then
  if systemctl is-active --quiet zion.service 2>/dev/null; then
    pass "zion.service is currently active"
  else
    warn "zion.service is not active"
  fi

  runner_units="$(systemctl list-unit-files --type=service --no-legend 2>/dev/null     | awk '{print $1}'     | grep -E '^actions\.runner\.' || true)"
  if [[ -n "$runner_units" ]]; then
    fail "GitHub Actions self-hosted runner service detected on production host"
  else
    pass "no actions.runner.* service detected"
  fi
else
  warn "systemctl unavailable"
fi

if command -v pgrep >/dev/null 2>&1   && pgrep -af 'Runner\.Listener|runsvc\.sh' >/dev/null 2>&1; then
  fail "GitHub Actions runner process detected on production host"
else
  pass "no GitHub Actions runner process detected"
fi

if [[ -x "$ROOT/scripts/remote-access-preflight.sh" ]]; then
  if "$ROOT/scripts/remote-access-preflight.sh" >/dev/null 2>&1; then
    pass "remote-access preflight passes"
  else
    fail "remote-access preflight does not pass"
  fi
else
  fail "remote-access-preflight.sh missing or not executable"
fi

if [[ "${ZION_GITHUB_GATES_PROVEN:-}" == "YES" ]]; then
  pass "GitHub production branch/ruleset gate explicitly confirmed"
else
  fail "set ZION_GITHUB_GATES_PROVEN=YES only after verifying zion-v1 protection and required CI"
fi

if [[ "${ZION_REMOTE_NETWORK_PROVEN:-}" == "YES" ]]; then
  pass "router/Tailnet exposure controls explicitly confirmed"
else
  fail "set ZION_REMOTE_NETWORK_PROVEN=YES only after verifying no public TCP/22 forward and Tailnet policy"
fi

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  pass "production virtualenv Python present"
else
  fail "production virtualenv Python missing"
fi

if [[ -x "$ROOT/scripts/predeploy-v11.sh" ]]; then
  pass "candidate predeploy verifier present"
else
  fail "candidate predeploy verifier missing"
fi

echo
echo "External controls are explicit attestations:"
echo "- ZION_GITHUB_GATES_PROVEN=YES: zion-v1 protection + required CI verified."
echo "- ZION_REMOTE_NETWORK_PROVEN=YES: no public TCP/22 forward + Tailnet policy verified."
echo "- The host cannot independently prove those control-plane settings."

echo
echo "Summary: failures=$failures warnings=$warnings"
echo "No service was stopped/restarted."
echo "No production file was modified."

if [[ "$REPORT_ONLY" == true ]]; then
  exit 0
fi
if (( failures > 0 )); then
  exit 2
fi
exit 0
