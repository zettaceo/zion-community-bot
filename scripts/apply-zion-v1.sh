#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/zetta/zion-community-bot"
PYTHON="$ROOT/.venv/bin/python"
SERVICE_SRC="$ROOT/systemd/zion.service"
SERVICE_DST="/etc/systemd/system/zion.service"
BACKUP_DIR="$ROOT/backups"

cd "$ROOT"

echo "[1/9] Conferindo ambiente virtual..."
if [[ ! -x "$PYTHON" ]]; then
  echo "ERRO: $PYTHON não existe." >&2
  exit 1
fi

echo "[2/9] Conferindo dependências sem alterar o ambiente..."
"$PYTHON" - <<'PY'
import httpx
import telegram
from dotenv import load_dotenv
print("dependencies: OK")
PY

echo "[3/9] Validando código, testes, shell e segredos..."
bash "$ROOT/scripts/validate.sh"

echo "[4/9] Conferindo arquivo systemd autoritativo..."
if [[ ! -f "$SERVICE_SRC" ]]; then
  echo "ERRO: $SERVICE_SRC não existe." >&2
  exit 1
fi
/usr/bin/systemd-analyze verify "$SERVICE_SRC"

echo "[5/9] Parando ZION somente após validação completa..."
sudo /usr/bin/systemctl stop zion.service

echo "[6/9] Criando backup local antes da migração..."
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BACKUP_DIR/$STAMP"
mkdir -p "$DEST"
chmod 700 "$DEST"

if [[ -f "$ROOT/zion_state.json" ]]; then
  cp -a "$ROOT/zion_state.json" "$DEST/zion_state.json"
fi

if [[ -f "$ROOT/zion.db" ]]; then
  "$PYTHON" - <<PY
import sqlite3
from pathlib import Path

source = Path("$ROOT/zion.db")
target = Path("$DEST/zion.db")

src = sqlite3.connect(str(source))
dst = sqlite3.connect(str(target))
try:
    src.backup(dst)
finally:
    dst.close()
    src.close()

print(f"sqlite backup: {target}")
PY
fi

echo "[7/9] Inicializando/migrando banco local..."
"$PYTHON" - <<'PY'
from zion.config import Settings
from zion.db import ZionDB
from zion.migrate import migrate_legacy_guardian_state

settings = Settings.from_env()
db = ZionDB(settings.db_path)
db.initialize()
migrate_legacy_guardian_state(db, settings.legacy_state_path)
assert db.ping()
print(f"database: OK ({settings.db_path})")
db.close()
PY

echo "[8/9] Instalando unit autoritativa e iniciando ZION..."
sudo /usr/bin/install   -o root   -g root   -m 0644   "$SERVICE_SRC"   "$SERVICE_DST"

sudo /usr/bin/systemctl daemon-reload
sudo /usr/bin/systemctl enable zion.service >/dev/null
sudo /usr/bin/systemctl start zion.service

sleep 3

echo "[9/9] Estado final..."
sudo /usr/bin/systemctl status zion.service --no-pager --full
echo
/usr/bin/systemctl show zion.service   -p NRestarts   -p ActiveState   -p SubState   -p ExecMainStartTimestamp

if ! /usr/bin/systemctl is-active --quiet zion.service; then
  echo "ERRO: zion.service não ficou ativo." >&2
  exit 1
fi

echo
echo "Deploy modular concluído."
echo "Backup pré-migração: $DEST"
echo "Teste /status e, como admin, /health e /aistatus no Telegram."
