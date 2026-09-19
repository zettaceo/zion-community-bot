#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
PROD_ROOT="/home/zetta/zion-community-bot"
PROD_DB="$PROD_ROOT/zion.db"
PROD_ENV="$PROD_ROOT/.env"
PROD_LEGACY="$PROD_ROOT/zion_state.json"
SERVICE="zion.service"

TMP_ROOT="$(mktemp -d /tmp/zion-v11-predeploy.XXXXXX)"
chmod 700 "$TMP_ROOT"
trap 'rm -rf "$TMP_ROOT"' EXIT

echo "ZION v1.1 PRE-DEPLOY — READ-ONLY PRODUCTION CHECK"
echo "================================================="

echo
echo "[1/8] Branch/commit..."
cd "$ROOT"
git status --short --branch
HEAD_SHA="$(git rev-parse HEAD)"
echo "candidate_head=$HEAD_SHA"

echo
echo "[2/8] Virtualenv..."
if [[ ! -x "$PYTHON" ]]; then
  echo "ERRO: $PYTHON não existe." >&2
  exit 1
fi
"$PYTHON" "$ROOT/scripts/check-runtime.py"

echo
echo "[3/8] Full repository validation..."
bash "$ROOT/scripts/validate.sh"

echo
echo "[4/8] Candidate systemd unit..."
/usr/bin/systemd-analyze verify "$ROOT/systemd/zion.service"
echo "systemd_unit=OK"

echo
echo "[5/8] Production config readiness (read-only)..."
PROD_ENV="$PROD_ENV" "$PYTHON" - <<'PY'
import os
import stat
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(os.environ["PROD_ENV"])
if not env_path.is_file() or env_path.is_symlink():
    raise RuntimeError("production .env absent or symlinked")

mode = stat.S_IMODE(env_path.stat().st_mode)
if mode & 0o077:
    raise RuntimeError(
        f"production .env permissions too broad: {oct(mode)}"
    )

load_dotenv(env_path, override=True)

from zion.config import Settings
from zion.knowledge import KnowledgeBase
from zion.mistral import MistralClient

settings = Settings.from_env()

if not settings.telegram_token:
    raise RuntimeError("TELEGRAM_BOT_TOKEN missing")
if not settings.admin_user_ids:
    raise RuntimeError("ZION_ADMIN_USER_IDS empty")

if settings.ai_enabled and not MistralClient(settings).configured:
    raise RuntimeError(
        "AI enabled without complete official Mistral configuration"
    )

knowledge = KnowledgeBase(settings.knowledge_dir)
if not knowledge.chunks:
    raise RuntimeError("candidate knowledge base empty")
if knowledge.load_errors:
    raise RuntimeError(
        "candidate knowledge errors: "
        + ",".join(knowledge.load_errors)
    )

print(
    "production config: OK | "
    f"operators={len(settings.admin_user_ids)} | "
    f"ai_enabled={settings.ai_enabled} | "
    f"candidate_knowledge_chunks={len(knowledge.chunks)}"
)
PY

echo
echo "[6/8] Current production service (no change)..."
/usr/bin/systemctl show "$SERVICE" \
  -p ActiveState \
  -p SubState \
  -p MainPID \
  -p NRestarts \
  -p ExecMainStartTimestamp

echo
echo "[7/8] Production SQLite backup to disposable /tmp copy..."
if [[ ! -f "$PROD_DB" ]]; then
  echo "ERRO: banco de produção não encontrado em $PROD_DB" >&2
  exit 1
fi

COPY_DB="$TMP_ROOT/zion-copy.db"
COPY_LEGACY="$TMP_ROOT/zion_state.json"

if [[ -f "$PROD_LEGACY" ]]; then
  cp -a "$PROD_LEGACY" "$COPY_LEGACY"
  chmod 600 "$COPY_LEGACY"
fi

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
echo "[8/8] Applying candidate migrations ONLY to disposable copy..."
"$PYTHON" - <<PY
from pathlib import Path

from zion.db import ZionDB
from zion.migrate import migrate_legacy_guardian_state

db_path = Path("$COPY_DB")
legacy_path = Path("$COPY_LEGACY")

db = ZionDB(db_path)
try:
    db.initialize()
    migrate_legacy_guardian_state(db, legacy_path)

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
