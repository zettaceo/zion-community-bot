#!/usr/bin/env bash
set -euo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEM_PYTHON="/usr/bin/python3"
PYTHON="${ZION_VALIDATION_PYTHON:-$ROOT/.venv/bin/python}"

if [[ ! -x "$SYSTEM_PYTHON" ]]; then
  echo "Python de sistema ausente: $SYSTEM_PYTHON" >&2
  exit 1
fi
"$SYSTEM_PYTHON" -I "$ROOT/scripts/check-python-release-env.py"

PYCACHE_ROOT="$(mktemp -d /tmp/zion-validation-pycache.XXXXXX)"
chmod 700 "$PYCACHE_ROOT"
trap 'rm -rf -- "$PYCACHE_ROOT"' EXIT

# Never read/write repository-local __pycache__ during validation.
# All bytecode produced by compileall/imports/tests is isolated in /tmp and
# destroyed on exit, so ignored .pyc files cannot become release evidence.
export PYTHONPYCACHEPREFIX="$PYCACHE_ROOT"

if [[ -n "${ZION_VALIDATION_PYTHON:-}" && ! -x "$PYTHON" ]]; then
  echo "ZION_VALIDATION_PYTHON não é executável: $PYTHON" >&2
  exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON="$(command -v python3)"
  else
    echo "Python 3 não encontrado." >&2
    exit 1
  fi
fi

cd "$ROOT"

echo "[1/7] Compilando Python em cache temporário isolado..."
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
if /usr/bin/git ls-files | grep -E '(^|/)(\.env|zion\.db|zion\.db-wal|zion\.db-shm)$' >/dev/null; then
  echo "ERRO: arquivo sensível/runtime está versionado." >&2
  /usr/bin/git ls-files | grep -E '(^|/)(\.env|zion\.db|zion\.db-wal|zion\.db-shm)$' >&2 || true
  exit 1
fi

echo "[7/7] Executando secret scan..."
"$PYTHON" scripts/secret_scan.py

echo "ZION VALIDATION: OK"
