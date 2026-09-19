#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON="$(command -v python3)"
  else
    echo "Python 3 não encontrado." >&2
    exit 1
  fi
fi

cd "$ROOT"

echo "[1/7] Compilando Python..."
"$PYTHON" -m compileall -q bot.py zion tests scripts

echo "[2/7] Conferindo compatibilidade do runtime..."
"$PYTHON" scripts/check-runtime.py

echo "[3/7] Testando imports..."
"$PYTHON" - <<'PY'
import httpx
import telegram
from dotenv import load_dotenv
import zion
from zion.telegram_app import build_application

print("imports: OK")
PY

echo "[4/7] Rodando unit tests..."
"$PYTHON" -m unittest discover -s tests -v

echo "[5/7] Validando shell scripts..."
for script in scripts/*.sh; do
  /usr/bin/bash -n "$script"
done

echo "[6/7] Verificando arquivos sensíveis versionados..."
if git ls-files | grep -E '(^|/)(\.env|zion\.db|zion\.db-wal|zion\.db-shm)$' >/dev/null; then
  echo "ERRO: arquivo sensível/runtime está versionado." >&2
  git ls-files | grep -E '(^|/)(\.env|zion\.db|zion\.db-wal|zion\.db-shm)$' >&2 || true
  exit 1
fi

echo "[7/7] Executando secret scan..."
"$PYTHON" scripts/secret_scan.py

echo "ZION VALIDATION: OK"
