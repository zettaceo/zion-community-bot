#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
PROD_ROOT="/home/zetta/zion-community-bot"
PROD_DB="$PROD_ROOT/zion.db"
SERVICE="zion.service"

TMP_ROOT="$(mktemp -d /tmp/zion-v11-predeploy.XXXXXX)"
chmod 700 "$TMP_ROOT"
trap 'rm -rf "$TMP_ROOT"' EXIT

echo "ZION v1.1 PRE-DEPLOY — READ-ONLY PRODUCTION CHECK"
echo "================================================="

echo
echo "[1/7] Branch/commit..."
cd "$ROOT"
git status --short --branch
HEAD_SHA="$(git rev-parse HEAD)"
echo "candidate_head=$HEAD_SHA"

echo
echo "[2/7] Virtualenv..."
if [[ ! -x "$PYTHON" ]]; then
  echo "ERRO: $PYTHON não existe." >&2
  exit 1
fi
echo "python=$PYTHON"

echo
echo "[3/7] Full repository validation..."
bash "$ROOT/scripts/validate.sh"

echo
echo "[4/7] Candidate systemd unit..."
/usr/bin/systemd-analyze verify "$ROOT/systemd/zion.service"
echo "systemd_unit=OK"

echo
echo "[5/7] Current production service (no change)..."
/usr/bin/systemctl show "$SERVICE" \
  -p ActiveState \
  -p SubState \
  -p MainPID \
  -p NRestarts \
  -p ExecMainStartTimestamp

echo
echo "[6/7] Production SQLite backup to disposable /tmp copy..."
if [[ ! -f "$PROD_DB" ]]; then
  echo "ERRO: banco de produção não encontrado em $PROD_DB" >&2
  exit 1
fi

COPY_DB="$TMP_ROOT/zion-copy.db"

"$PYTHON" - <<PY
import sqlite3
from pathlib import Path

source = Path("$PROD_DB")
target = Path("$COPY_DB")

src = sqlite3.connect(
    source.resolve().as_uri() + "?mode=ro",
    uri=True,
    timeout=5,
)
dst = sqlite3.connect(str(target))
try:
    before = src.execute("PRAGMA quick_check").fetchone()
    before_result = str(before[0]) if before else "no_result"
    if before_result.lower() != "ok":
        raise RuntimeError(
            f"production quick_check failed: {before_result}"
        )

    src.backup(dst)

    copied = dst.execute("PRAGMA quick_check").fetchone()
    copied_result = str(copied[0]) if copied else "no_result"
    if copied_result.lower() != "ok":
        raise RuntimeError(
            f"backup quick_check failed: {copied_result}"
        )

    tables = dst.execute(
        "SELECT COUNT(*) FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchone()[0]
finally:
    dst.close()
    src.close()

print(f"production_quick_check={before_result}")
print(f"backup_quick_check={copied_result}")
print(f"backup_user_tables={tables}")
PY

echo
echo "[7/7] Applying candidate schema ONLY to disposable copy..."
"$PYTHON" - <<PY
from pathlib import Path

from zion.db import ZionDB

path = Path("$COPY_DB")
db = ZionDB(path)
try:
    db.initialize()

    integrity_ok, integrity_result = db.integrity_check()
    if not integrity_ok:
        raise RuntimeError(
            f"candidate migration quick_check failed: {integrity_result}"
        )

    pragmas = db.runtime_pragmas()
    if pragmas["journal_mode"] != "wal":
        raise RuntimeError(
            f"candidate journal_mode={pragmas['journal_mode']}"
        )
    if int(pragmas["foreign_keys"]) != 1:
        raise RuntimeError("candidate foreign_keys disabled")

    print(f"candidate_schema_version={db.schema_version()}")
    print(f"candidate_quick_check={integrity_result}")
    print(f"candidate_journal_mode={pragmas['journal_mode']}")
    print(f"candidate_foreign_keys={pragmas['foreign_keys']}")
    print(f"candidate_db_size_bytes={db.file_size_bytes()}")
finally:
    db.close()
PY

echo
echo "PRE-DEPLOY: OK"
echo "Nenhum serviço foi parado/reiniciado."
echo "Nenhum arquivo de produção foi modificado por este script."
