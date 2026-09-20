#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/zetta/zion-community-bot"
PYTHON="/home/zetta/.local/share/zion-community-bot/runtimes/current/bin/python"
SRC="$ROOT/systemd/zion-dashboard.service"
DST="/etc/systemd/system/zion-dashboard.service"
STATE_DIR="/home/zetta/.local/state/zion-community-bot"
DB="$STATE_DIR/zion.db"
UNIT_WIFI_INTERFACE="wlx78bdbc575d1c"

cd "$ROOT"

echo "[1/6] Validando repositório..."
bash scripts/validate.sh

echo "[2/6] Conferindo pré-requisitos..."
if [[ ! -f "$SRC" ]]; then
  echo "ERRO: $SRC não existe." >&2
  exit 1
fi
if [[ ! -x "$PYTHON" ]]; then
  echo "ERRO: runtime Python ausente: $PYTHON" >&2
  exit 1
fi

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

if [[ ! -f "$DB" ]]; then
  echo "ERRO: $DB não existe. O dashboard é read-only e não cria banco." >&2
  exit 1
fi
/usr/bin/systemd-analyze verify "$SRC"

echo "[3/6] Preparando diretório privado de logs..."
sudo /usr/bin/install \
  -d \
  -o zetta \
  -g zetta \
  -m 0700 \
  "$STATE_DIR"

echo "[4/6] Instalando unit do dashboard..."
sudo /usr/bin/install \
  -o root \
  -g root \
  -m 0644 \
  "$SRC" \
  "$DST"
sudo /usr/bin/systemctl daemon-reload

echo "[5/6] Iniciando dashboard..."
sudo /usr/bin/systemctl enable --now zion-dashboard.service

echo "[6/6] Estado final..."
sudo /usr/bin/systemctl status \
  zion-dashboard.service \
  --no-pager \
  --full

if ! /usr/bin/systemctl is-active --quiet zion-dashboard.service; then
  echo "ERRO: zion-dashboard.service não ficou ativo." >&2
  exit 1
fi

echo
echo "Dashboard local read-only: http://127.0.0.1:8765/"
