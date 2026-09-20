#!/usr/bin/env bash
set -euo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

ROOT="/home/zetta/zion-community-bot"
SYSTEM_PYTHON="/usr/bin/python3"
EXPECTED_USER="zetta"
EXPECTED="${ZION_DEPLOY_COMMIT:-}"
REMOTE_BRANCH="zion-v1"
APPROVED_REF="origin/zion-v1"
EXPECTED_REPO="zettaceo/zion-community-bot"
LOCAL_PROD_BRANCH="zion-v1-prod"
RUNTIME_BASE="/home/zetta/.local/share/zion-community-bot/runtimes"
RUNTIME_DIR="$RUNTIME_BASE/$EXPECTED"
CURRENT_RUNTIME="$RUNTIME_BASE/current"
PYTHON="$CURRENT_RUNTIME/bin/python"
SRC="$ROOT/systemd/zion-dashboard.service"
DST="/etc/systemd/system/zion-dashboard.service"
BOT_UNIT="/etc/systemd/system/zion.service"
STATE_DIR="/home/zetta/.local/state/zion-community-bot"
DASHBOARD_STATE_DIR="$STATE_DIR/dashboard"
DB="$STATE_DIR/zion.db"
UNIT_WIFI_INTERFACE="wlx78bdbc575d1c"

if [[ "$(id -un)" != "$EXPECTED_USER" ]]; then
  echo "ERRO: execute como $EXPECTED_USER, não como root." >&2
  exit 2
fi
if [[ ! "$EXPECTED" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "ERRO: ZION_DEPLOY_COMMIT deve ser SHA Git completo de 40 caracteres." >&2
  exit 2
fi
if [[ "${ZION_GITHUB_GATES_PROVEN:-}" != "YES" ]]; then
  echo "ERRO: ZION_GITHUB_GATES_PROVEN=YES é obrigatório." >&2
  exit 2
fi
if [[ ! -x "$SYSTEM_PYTHON" ]]; then
  echo "ERRO: Python do sistema ausente: $SYSTEM_PYTHON" >&2
  exit 2
fi

cd "$ROOT"

echo "[1/8] Validando fronteira Git e SHA aprovado..."
"$SYSTEM_PYTHON" -I "$ROOT/scripts/check-git-release-boundary.py" \
  --root "$ROOT"

CURRENT_HEAD="$(GIT_NO_REPLACE_OBJECTS=1 /usr/bin/git rev-parse HEAD)"
CURRENT_BRANCH="$(GIT_NO_REPLACE_OBJECTS=1 /usr/bin/git symbolic-ref --quiet --short HEAD)"
APPROVED_SHA="$(GIT_NO_REPLACE_OBJECTS=1 /usr/bin/git rev-parse "$APPROVED_REF^{commit}")"
ORIGIN_URL="$(GIT_NO_REPLACE_OBJECTS=1 /usr/bin/git remote get-url origin)"
WORKTREE_STATUS="$(GIT_NO_REPLACE_OBJECTS=1 /usr/bin/git status --porcelain --untracked-files=all)"

if [[ "$CURRENT_HEAD" != "$EXPECTED" ]]; then
  echo "ERRO: HEAD de produção difere de ZION_DEPLOY_COMMIT." >&2
  exit 2
fi
if [[ "$CURRENT_BRANCH" != "$LOCAL_PROD_BRANCH" ]]; then
  echo "ERRO: branch local deve ser $LOCAL_PROD_BRANCH." >&2
  exit 2
fi
if [[ -n "$WORKTREE_STATUS" ]]; then
  echo "ERRO: worktree de produção não está limpo." >&2
  exit 2
fi
if [[ "$APPROVED_SHA" != "$EXPECTED" ]]; then
  echo "ERRO: $APPROVED_REF difere do SHA aprovado." >&2
  exit 2
fi

case "$ORIGIN_URL" in
  "https://github.com/$EXPECTED_REPO"|"https://github.com/$EXPECTED_REPO.git"|"git@github.com:$EXPECTED_REPO.git"|"ssh://git@github.com/$EXPECTED_REPO.git")
    ;;
  *)
    echo "ERRO: origin não aponta para $EXPECTED_REPO." >&2
    exit 2
    ;;
esac

if command -v timeout >/dev/null 2>&1; then
  REMOTE_LINE="$(
    timeout 20 env GIT_TERMINAL_PROMPT=0 \
      /usr/bin/git ls-remote --exit-code origin "refs/heads/$REMOTE_BRANCH" \
      2>/dev/null | head -n1 || true
  )"
else
  REMOTE_LINE="$(
    env GIT_TERMINAL_PROMPT=0 \
      /usr/bin/git ls-remote --exit-code origin "refs/heads/$REMOTE_BRANCH" \
      2>/dev/null | head -n1 || true
  )"
fi
REMOTE_SHA="${REMOTE_LINE%%[[:space:]]*}"
if [[ "$REMOTE_SHA" != "$EXPECTED" ]]; then
  echo "ERRO: origin/$REMOTE_BRANCH ao vivo não coincide com SHA aprovado." >&2
  exit 2
fi

echo "[2/8] Validando runtime do mesmo SHA..."
if [[ ! -L "$CURRENT_RUNTIME" ]]; then
  echo "ERRO: runtime/current deve ser symlink." >&2
  exit 2
fi
CURRENT_RUNTIME_REAL="$(readlink -f -- "$CURRENT_RUNTIME" || true)"
RUNTIME_DIR_REAL="$(readlink -f -- "$RUNTIME_DIR" || true)"
if [[ -z "$CURRENT_RUNTIME_REAL" || "$CURRENT_RUNTIME_REAL" != "$RUNTIME_DIR_REAL" ]]; then
  echo "ERRO: runtime/current não aponta para runtime do SHA aprovado." >&2
  exit 2
fi
if [[ ! -f "$RUNTIME_DIR/release-sha.txt" ]] \
  || [[ "$(tr -d '\r\n' < "$RUNTIME_DIR/release-sha.txt")" != "$EXPECTED" ]]; then
  echo "ERRO: identidade do runtime não coincide com SHA aprovado." >&2
  exit 2
fi
if [[ ! -x "$PYTHON" ]]; then
  echo "ERRO: runtime Python ausente: $PYTHON" >&2
  exit 2
fi
"$PYTHON" "$ROOT/scripts/check-runtime.py"

echo "[3/8] Validando bot v1.1 ativo e estado..."
if [[ ! -f "$BOT_UNIT" || -L "$BOT_UNIT" ]]; then
  echo "ERRO: unit instalada do bot ausente ou symlink." >&2
  exit 2
fi
if ! grep -Fq "ZION_DB_PATH=$DB" "$BOT_UNIT"; then
  echo "ERRO: bot instalado ainda não usa o layout de estado v1.1." >&2
  exit 2
fi
if ! grep -Fq "$CURRENT_RUNTIME/bin/python" "$BOT_UNIT"; then
  echo "ERRO: bot instalado não usa runtime/current aprovado." >&2
  exit 2
fi
if ! /usr/bin/systemctl is-active --quiet zion.service; then
  echo "ERRO: zion.service deve estar ativo antes do bootstrap do dashboard." >&2
  exit 2
fi
if [[ ! -f "$DB" || -L "$DB" ]]; then
  echo "ERRO: $DB deve ser arquivo regular não-symlink." >&2
  exit 2
fi
if [[ "$(stat -c '%h' "$DB")" != "1" ]]; then
  echo "ERRO: $DB não pode possuir hard links." >&2
  exit 2
fi
if [[ -e "$DASHBOARD_STATE_DIR" || -L "$DASHBOARD_STATE_DIR" ]]; then
  if [[ -L "$DASHBOARD_STATE_DIR" || ! -d "$DASHBOARD_STATE_DIR" ]]; then
    echo "ERRO: dashboard state dir existente deve ser diretório regular." >&2
    exit 2
  fi
  DASHBOARD_STATE_REAL="$(readlink -f -- "$DASHBOARD_STATE_DIR" 2>/dev/null || true)"
  if [[ "$DASHBOARD_STATE_REAL" != "$DASHBOARD_STATE_DIR" ]]; then
    echo "ERRO: dashboard state dir resolve por alias/symlink." >&2
    exit 2
  fi
  if [[ "$(stat -c '%U' "$DASHBOARD_STATE_DIR")" != "$EXPECTED_USER" ]] \
    || [[ "$(stat -c '%a' "$DASHBOARD_STATE_DIR")" != "700" ]]; then
    echo "ERRO: dashboard state dir deve ser 0700 e pertencer a $EXPECTED_USER." >&2
    exit 2
  fi
fi

echo "[4/8] Validando código, unit e configuração..."
if [[ ! -f "$SRC" || -L "$SRC" ]]; then
  echo "ERRO: $SRC ausente ou symlink." >&2
  exit 2
fi
if [[ -e "$DST" || -L "$DST" ]]; then
  echo "ERRO: dashboard já está instalado; atualizações devem passar pelo release controlado principal." >&2
  exit 2
fi

ZION_VALIDATION_PYTHON="$PYTHON" bash "$ROOT/scripts/validate.sh"
/usr/bin/systemd-analyze verify "$SRC"

"$PYTHON" - <<'PY'
from zion.config import Settings

settings = Settings.from_env()
if settings.wifi_interface != "wlx78bdbc575d1c":
    raise RuntimeError(
        "zion-dashboard.service Wi-Fi interface diverge from bot config: "
        f"bot={settings.wifi_interface} "
        "dashboard=wlx78bdbc575d1c"
    )
PY

echo "[5/8] Revalidando inputs imediatamente antes do sudo..."
"$SYSTEM_PYTHON" -I "$ROOT/scripts/check-git-release-boundary.py" \
  --root "$ROOT"
if [[ "$(GIT_NO_REPLACE_OBJECTS=1 /usr/bin/git rev-parse HEAD)" != "$EXPECTED" ]]; then
  echo "ERRO: HEAD mudou durante o bootstrap do dashboard." >&2
  exit 2
fi
if [[ -n "$(GIT_NO_REPLACE_OBJECTS=1 /usr/bin/git status --porcelain --untracked-files=all)" ]]; then
  echo "ERRO: worktree mudou durante o bootstrap do dashboard." >&2
  exit 2
fi
if [[ "$(readlink -f -- "$CURRENT_RUNTIME" || true)" != "$RUNTIME_DIR_REAL" ]]; then
  echo "ERRO: runtime/current mudou durante o bootstrap do dashboard." >&2
  exit 2
fi

mutated=false
created_dashboard_state=false
rollback() {
  if [[ "$mutated" == true ]]; then
    echo "Falha após mutação; removendo bootstrap incompleto do dashboard..." >&2
    sudo /usr/bin/systemctl disable --now zion-dashboard.service >/dev/null 2>&1 || true
    sudo /usr/bin/rm -f "$DST"
    sudo /usr/bin/systemctl daemon-reload || true
  fi
  if [[ "$created_dashboard_state" == true ]]; then
    /usr/bin/rm -rf -- "$DASHBOARD_STATE_DIR"
  fi
}
trap rollback ERR

echo "[6/8] Preparando estado mínimo e instalando unit aprovada..."
if [[ ! -d "$DASHBOARD_STATE_DIR" ]]; then
  /usr/bin/install -d -m 0700 "$DASHBOARD_STATE_DIR"
  created_dashboard_state=true
fi
sudo /usr/bin/install \
  -o root \
  -g root \
  -m 0644 \
  "$SRC" \
  "$DST"
mutated=true
sudo /usr/bin/systemctl daemon-reload

echo "[7/8] Habilitando dashboard local..."
sudo /usr/bin/systemctl enable --now zion-dashboard.service

echo "[8/8] Verificando estado final..."
if ! /usr/bin/systemctl is-active --quiet zion-dashboard.service; then
  echo "ERRO: zion-dashboard.service não ficou ativo." >&2
  exit 1
fi
sudo /usr/bin/systemctl status \
  zion-dashboard.service \
  --no-pager \
  --full

trap - ERR
mutated=false

echo
echo "Dashboard local read-only: http://127.0.0.1:8765/"
