#!/usr/bin/env bash
set -uo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

REPORT_ONLY=false
if [[ "${1:-}" == "--report-only" ]]; then
  REPORT_ONLY=true
elif [[ -n "${1:-}" ]]; then
  echo "usage: $0 [--report-only]" >&2
  exit 64
fi

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEM_PYTHON="/usr/bin/python3"

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
RUNTIME_BASE="/home/zetta/.local/share/zion-community-bot/runtimes"
RUNTIME_DIR="$RUNTIME_BASE/$EXPECTED"
CURRENT_RUNTIME="$RUNTIME_BASE/current"

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

candidate_head="$(/usr/bin/git -C "$SCRIPT_ROOT" rev-parse HEAD 2>/dev/null || true)"
if [[ -n "$EXPECTED" && "$candidate_head" == "$EXPECTED" ]]; then
  pass "preflight code itself is pinned to the approved candidate SHA"
else
  fail "preflight script worktree HEAD does not equal ZION_DEPLOY_COMMIT"
fi
candidate_status="$(/usr/bin/git -C "$SCRIPT_ROOT" status --porcelain --untracked-files=all 2>/dev/null || true)"
if [[ -z "$candidate_status" ]]; then
  pass "candidate gate worktree is clean including non-ignored untracked files"
else
  fail "candidate gate worktree contains tracked/untracked changes"
fi

if [[ -e "$SCRIPT_ROOT/.env" || -L "$SCRIPT_ROOT/.env" ]]; then
  fail "candidate worktree must not contain an ignored .env"
else
  pass "candidate worktree has no local .env"
fi

if [[ -x "$SYSTEM_PYTHON" ]] \
  && "$SYSTEM_PYTHON" -I "$SCRIPT_ROOT/scripts/check-git-release-boundary.py" \
    --root "$SCRIPT_ROOT" >/dev/null; then
  pass "candidate local Git boundary is clean"
else
  fail "candidate local Git boundary validation failed"
fi

PYTHON_ENV_CLEAN=false
if [[ -x "$SYSTEM_PYTHON" ]] \
  && "$SYSTEM_PYTHON" -I "$SCRIPT_ROOT/scripts/check-python-release-env.py" \
    >/dev/null; then
  PYTHON_ENV_CLEAN=true
  pass "release Python environment is clean"
else
  fail "release shell contains forbidden PYTHON* environment variables"
fi

if [[ ! -d "$ROOT/.git" && ! -f "$ROOT/.git" ]]; then
  fail "production Git worktree not found at $ROOT"
else
  if [[ -x "$SYSTEM_PYTHON" ]] \
    && "$SYSTEM_PYTHON" -I "$SCRIPT_ROOT/scripts/check-git-release-boundary.py" \
      --root "$ROOT" >/dev/null; then
    pass "production local Git boundary is clean"
  else
    fail "production local Git boundary validation failed"
  fi

  current_head="$(/usr/bin/git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
  current_branch="$(/usr/bin/git -C "$ROOT" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  approved_sha="$(/usr/bin/git -C "$ROOT" rev-parse "$APPROVED_REF^{commit}" 2>/dev/null || true)"
  origin_url="$(/usr/bin/git -C "$ROOT" remote get-url origin 2>/dev/null || true)"

  case "$origin_url" in
    "https://github.com/$EXPECTED_REPO"|"https://github.com/$EXPECTED_REPO.git"|"git@github.com:$EXPECTED_REPO.git"|"ssh://git@github.com/$EXPECTED_REPO.git")
      pass "origin points to expected GitHub repository"
      ;;
    *)
      fail "origin does not point to the expected GitHub repository"
      ;;
  esac

  if command -v timeout >/dev/null 2>&1; then
    remote_line="$(timeout 20 env GIT_TERMINAL_PROMPT=0 /usr/bin/git -C "$ROOT" ls-remote --exit-code origin "refs/heads/$REMOTE_BRANCH" 2>/dev/null | head -n1 || true)"
  else
    remote_line="$(env GIT_TERMINAL_PROMPT=0 /usr/bin/git -C "$ROOT" ls-remote --exit-code origin "refs/heads/$REMOTE_BRANCH" 2>/dev/null | head -n1 || true)"
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

  production_status="$(/usr/bin/git -C "$ROOT" status --porcelain --untracked-files=all 2>/dev/null || true)"
  if [[ -z "$production_status" ]]; then
    pass "production worktree is clean including non-ignored untracked files"
  else
    fail "production worktree has tracked/untracked changes"
  fi

  if [[ -n "$EXPECTED" && -n "$current_head" ]]     && /usr/bin/git -C "$ROOT" merge-base --is-ancestor "$current_head" "$EXPECTED" 2>/dev/null; then
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

if [[ -x "$SYSTEM_PYTHON" ]] \
  && "$SYSTEM_PYTHON" -I "$SCRIPT_ROOT/scripts/check-env-boundary.py" \
    --env "$ENV_FILE" \
    --allowlist "$SCRIPT_ROOT/.env.example" \
    --owner "$EXPECTED_USER" >/dev/null; then
  pass "production .env metadata and key allowlist are valid"
else
  fail "production .env boundary validation failed"
fi

if command -v systemctl >/dev/null 2>&1; then
  if systemctl is-active --quiet zion.service 2>/dev/null; then
    pass "zion.service is currently active"
  elif [[ "$REPORT_ONLY" == true ]]; then
    warn "zion.service is not active"
  else
    fail "zion.service is not active; treat existing outage before release"
  fi

  runner_units="$(systemctl list-unit-files --type=service --no-legend 2>/dev/null     | awk '{print $1}'     | grep -E '^actions\.runner\.' || true)"
  if [[ -n "$runner_units" ]]; then
    fail "GitHub Actions self-hosted runner service detected on production host"
  else
    pass "no actions.runner.* service detected"
  fi
else
  if [[ "$REPORT_ONLY" == true ]]; then
    warn "systemctl unavailable"
  else
    fail "systemctl unavailable"
  fi
fi

if command -v pgrep >/dev/null 2>&1   && pgrep -af 'Runner\.Listener|runsvc\.sh' >/dev/null 2>&1; then
  fail "GitHub Actions runner process detected on production host"
else
  pass "no GitHub Actions runner process detected"
fi

if [[ -x "$SCRIPT_ROOT/scripts/remote-access-preflight.sh" ]]; then
  if "$SCRIPT_ROOT/scripts/remote-access-preflight.sh" >/dev/null 2>&1; then
    pass "candidate remote-access preflight passes"
  else
    fail "candidate remote-access preflight does not pass"
  fi
else
  fail "candidate remote-access-preflight.sh missing or not executable"
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

if [[ -L "$CURRENT_RUNTIME" ]] \
  && [[ -x "$(readlink -f -- "$CURRENT_RUNTIME" 2>/dev/null || true)/bin/python" ]]; then
  pass "runtime/current points to an executable runtime"
else
  fail "runtime/current is missing or invalid"
fi

if [[ "$PYTHON_ENV_CLEAN" != true ]]; then
  fail "staged candidate runtime validation skipped because Python environment is contaminated"
elif [[ -d "$RUNTIME_DIR" && ! -L "$RUNTIME_DIR" ]] \
  && [[ -x "$RUNTIME_DIR/bin/python" ]] \
  && [[ -f "$RUNTIME_DIR/release-sha.txt" ]] \
  && [[ "$(cat "$RUNTIME_DIR/release-sha.txt" 2>/dev/null || true)" == "$EXPECTED" ]]; then
  if "$RUNTIME_DIR/bin/python" "$SCRIPT_ROOT/scripts/check-runtime.py" >/dev/null \
    && "$RUNTIME_DIR/bin/python" -m pip check >/dev/null; then
    pass "staged candidate runtime matches audited release lock"
  else
    fail "staged candidate runtime validation failed"
  fi
else
  fail "staged candidate runtime is missing or has wrong identity"
fi

if [[ -x "$SCRIPT_ROOT/scripts/predeploy-v11.sh" ]]; then
  pass "candidate predeploy verifier present in approved worktree"
else
  fail "candidate predeploy verifier missing from approved worktree"
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
