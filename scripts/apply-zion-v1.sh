#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/zetta/zion-community-bot"
PYTHON="$ROOT/.venv/bin/python"

cd "$ROOT"

echo "[1/7] Conferindo ambiente virtual..."
if [[ ! -x "$PYTHON" ]]; then
  echo "ERRO: $PYTHON não existe." >&2
  exit 1
fi

echo "[2/7] Conferindo dependências sem alterar o ambiente..."
"$PYTHON" - <<'PY'
import httpx
import telegram
from dotenv import load_dotenv
print("dependencies: OK")
PY

echo "[3/7] Validando código, testes e segredos..."
bash "$ROOT/scripts/validate.sh"

echo "[4/7] Inicializando/migrando banco local..."
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

echo "[5/7] Parando ZION apenas após validação completa..."
sudo /usr/bin/systemctl stop zion.service

echo "[6/7] Recarregando systemd e iniciando ZION modular..."
sudo /usr/bin/systemctl daemon-reload
sudo /usr/bin/systemctl start zion.service

sleep 2

echo "[7/7] Estado final..."
sudo /usr/bin/systemctl status zion.service --no-pager --full
echo
/usr/bin/systemctl show zion.service   -p NRestarts   -p ActiveState   -p SubState   -p ExecMainStartTimestamp

echo
echo "Deploy modular concluído. Teste /status, /health e /aistatus no Telegram."
