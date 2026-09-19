#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/zetta/zion-community-bot"
PYTHON="$ROOT/.venv/bin/python"
SERVICE_SRC="$ROOT/systemd/zion.service"
SERVICE_DST="/etc/systemd/system/zion.service"
BACKUP_DIR="$ROOT/backups"

cd "$ROOT"

echo "[1/11] Conferindo ambiente virtual..."
if [[ ! -x "$PYTHON" ]]; then
  echo "ERRO: $PYTHON não existe." >&2
  exit 1
fi

echo "[2/11] Conferindo worktree e commit..."
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERRO: existem alterações rastreadas não commitadas." >&2
  exit 1
fi

CURRENT_HEAD="$(git rev-parse HEAD)"
echo "HEAD=$CURRENT_HEAD"

if [[ -n "${ZION_EXPECTED_COMMIT:-}" ]] \
  && [[ "$CURRENT_HEAD" != "$ZION_EXPECTED_COMMIT" ]]; then
  echo "ERRO: HEAD diferente de ZION_EXPECTED_COMMIT." >&2
  exit 1
fi

echo "[3/11] Conferindo dependências sem alterar o ambiente..."
"$PYTHON" - <<'PY'
import httpx
import telegram
from dotenv import load_dotenv
print("dependencies: OK")
PY

echo "[4/11] Validando código, testes, shell e segredos..."
bash "$ROOT/scripts/validate.sh"

echo "[5/11] Conferindo arquivo systemd autoritativo..."
if [[ ! -f "$SERVICE_SRC" ]]; then
  echo "ERRO: $SERVICE_SRC não existe." >&2
  exit 1
fi
/usr/bin/systemd-analyze verify "$SERVICE_SRC"

echo "[6/11] Criando backup local antes de parar ZION..."
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BACKUP_DIR/$STAMP"
mkdir -p "$DEST"
chmod 700 "$DEST"

printf '%s\n' "$CURRENT_HEAD" > "$DEST/git-head.txt"
chmod 600 "$DEST/git-head.txt"

if [[ -f "$ROOT/.env" ]]; then
  cp -a "$ROOT/.env" "$DEST/.env"
  chmod 600 "$DEST/.env"
fi

if [[ -f "$ROOT/zion_state.json" ]]; then
  cp -a "$ROOT/zion_state.json" "$DEST/zion_state.json"
  chmod 600 "$DEST/zion_state.json"
fi

if [[ -f "$ROOT/zion.db" ]]; then
  "$PYTHON" - <<PY
import os
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

os.chmod(target, 0o600)
print(f"sqlite backup: {target}")
PY
fi

echo "[7/11] Parando ZION somente após validação e backup..."
sudo /usr/bin/systemctl stop zion.service

echo "[8/11] Inicializando/migrando banco local..."
"$PYTHON" - <<'PY'
from zion.config import Settings
from zion.db import ZionDB
from zion.migrate import migrate_legacy_guardian_state

settings = Settings.from_env()
db = ZionDB(settings.db_path)
try:
    db.initialize()
    migrate_legacy_guardian_state(db, settings.legacy_state_path)
    if not db.ping():
        raise RuntimeError("database ping failed")
    integrity_ok, integrity_result = db.integrity_check()
    if not integrity_ok:
        raise RuntimeError(
            f"SQLite quick_check failed: {integrity_result}"
        )
    print(
        f"database: OK ({settings.db_path}) | "
        f"quick_check={integrity_result}"
    )
finally:
    db.close()
PY

echo "[9/11] Instalando unit autoritativa..."
sudo /usr/bin/install \
  -o root \
  -g root \
  -m 0644 \
  "$SERVICE_SRC" \
  "$SERVICE_DST"

sudo /usr/bin/systemctl daemon-reload
sudo /usr/bin/systemctl enable zion.service >/dev/null

echo "[10/11] Iniciando ZION..."
sudo /usr/bin/systemctl start zion.service

for _ in $(seq 1 20); do
  if /usr/bin/systemctl is-active --quiet zion.service; then
    break
  fi
  sleep 1
done

echo "[11/11] Estado final..."
sudo /usr/bin/systemctl status zion.service --no-pager --full
echo
/usr/bin/systemctl show zion.service \
  -p NRestarts \
  -p ActiveState \
  -p SubState \
  -p ExecMainStartTimestamp

if ! /usr/bin/systemctl is-active --quiet zion.service; then
  echo "ERRO: zion.service não ficou ativo." >&2
  echo "Backup pré-deploy: $DEST" >&2
  exit 1
fi

echo
echo "Deploy modular concluído."
echo "Commit implantado: $CURRENT_HEAD"
echo "Backup pré-deploy: $DEST"
echo "Teste /status e, como operador, /health, /diagnostics e /aistatus."
