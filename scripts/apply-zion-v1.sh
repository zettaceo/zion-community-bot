#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/zetta/zion-community-bot"
PYTHON="$ROOT/.venv/bin/python"
SERVICE_SRC="$ROOT/systemd/zion.service"
SERVICE_DST="/etc/systemd/system/zion.service"
BACKUP_DIR="$ROOT/backups"
STATE_DIR="/home/zetta/.local/state/zion-community-bot"

cd "$ROOT"

echo "[1/12] Conferindo ambiente virtual..."
if [[ ! -x "$PYTHON" ]]; then
  echo "ERRO: $PYTHON não existe." >&2
  exit 1
fi

echo "[2/12] Conferindo worktree e commit..."
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

echo "[3/12] Conferindo dependências sem alterar o ambiente..."
"$PYTHON" - <<'PY'
import httpx
import telegram
from dotenv import load_dotenv
print("dependencies: OK")
PY

echo "[4/12] Validando código, testes, shell e segredos..."
bash "$ROOT/scripts/validate.sh"

echo "[5/12] Conferindo arquivo systemd autoritativo..."
if [[ ! -f "$SERVICE_SRC" ]]; then
  echo "ERRO: $SERVICE_SRC não existe." >&2
  exit 1
fi
/usr/bin/systemd-analyze verify "$SERVICE_SRC"

echo "[6/12] Preparando diretório privado de estado compartilhado..."
sudo /usr/bin/install \
  -d \
  -o zetta \
  -g zetta \
  -m 0700 \
  "$STATE_DIR"

echo "[7/12] Criando e verificando backup local antes de parar ZION..."
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

if [[ -f "$SERVICE_DST" ]]; then
  cp -a "$SERVICE_DST" "$DEST/zion.service.installed"
  chmod 600 "$DEST/zion.service.installed"
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
    row = dst.execute("PRAGMA quick_check").fetchone()
    result = str(row[0]) if row else "no_result"
    if result.lower() != "ok":
        raise RuntimeError(
            f"backup SQLite quick_check failed: {result}"
        )
finally:
    dst.close()
    src.close()

os.chmod(target, 0o600)
print(f"sqlite backup: OK ({target})")
PY
fi

echo "[8/12] Parando ZION somente após validação e backup..."
sudo /usr/bin/systemctl stop zion.service

if /usr/bin/systemctl is-active --quiet zion.service; then
  echo "ERRO: zion.service permaneceu ativo após stop." >&2
  exit 1
fi

echo "[9/12] Inicializando/migrando banco local..."
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
    pragmas = db.runtime_pragmas()
    if pragmas["journal_mode"] != "wal":
        raise RuntimeError(
            f"SQLite journal_mode inesperado: {pragmas['journal_mode']}"
        )
    if int(pragmas["foreign_keys"]) != 1:
        raise RuntimeError("SQLite foreign_keys está desativado")
    print(
        f"database: OK ({settings.db_path}) | "
        f"schema=v{db.schema_version()} | "
        f"quick_check={integrity_result}"
    )
finally:
    db.close()
PY

echo "[10/12] Instalando unit autoritativa..."
sudo /usr/bin/install \
  -o root \
  -g root \
  -m 0644 \
  "$SERVICE_SRC" \
  "$SERVICE_DST"

sudo /usr/bin/systemctl daemon-reload
sudo /usr/bin/systemctl enable zion.service >/dev/null

echo "[11/12] Iniciando ZION..."
sudo /usr/bin/systemctl start zion.service

for _ in $(seq 1 20); do
  if /usr/bin/systemctl is-active --quiet zion.service; then
    break
  fi
  sleep 1
done

echo "[12/12] Estado final..."
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
echo "Backup pré-deploy verificado: $DEST"
echo "Teste /status e, como operador, /health, /diagnostics, /jobs e /aistatus."
