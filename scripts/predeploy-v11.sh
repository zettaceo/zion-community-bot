#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ZION_RUNTIME_PYTHON:-$ROOT/.venv/bin/python}"
PROD_ROOT="${ZION_PROD_ROOT:-/home/zetta/zion-community-bot}"
PROD_ENV="$PROD_ROOT/.env"
SERVICE="${ZION_SERVICE:-zion.service}"
EXPECTED_COMMIT="${ZION_EXPECTED_COMMIT:-}"
APPROVED_REF="origin/zion-v1"

TMP_ROOT="$(mktemp -d /tmp/zion-v11-predeploy.XXXXXX)"
chmod 700 "$TMP_ROOT"
trap 'rm -rf "$TMP_ROOT"' EXIT

echo "ZION v1.1 PRE-DEPLOY — READ-ONLY PRODUCTION CHECK"
echo "================================================="

echo
echo "[1/8] Approved branch/commit..."
cd "$ROOT"
git status --short --branch
HEAD_SHA="$(git rev-parse HEAD)"

if [[ ! "$EXPECTED_COMMIT" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "ERRO: ZION_EXPECTED_COMMIT deve ser um SHA completo de 40 caracteres." >&2
  exit 1
fi

APPROVED_SHA="$(git rev-parse "$APPROVED_REF^{commit}" 2>/dev/null || true)"
if [[ "$HEAD_SHA" != "$EXPECTED_COMMIT" ]]; then
  echo "ERRO: candidate HEAD diferente de ZION_EXPECTED_COMMIT." >&2
  exit 1
fi
if [[ "$APPROVED_SHA" != "$EXPECTED_COMMIT" ]]; then
  echo "ERRO: $APPROVED_REF não aponta exatamente para o commit aprovado." >&2
  exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERRO: candidate worktree possui alterações rastreadas." >&2
  exit 1
fi

echo "candidate_head=$HEAD_SHA"
echo "approved_ref=$APPROVED_REF"
echo "approved_sha=$APPROVED_SHA"

echo
echo "[2/8] Virtualenv..."
if [[ ! -x "$PYTHON" ]]; then
  echo "ERRO: $PYTHON não existe." >&2
  exit 1
fi
"$PYTHON" "$ROOT/scripts/check-runtime.py"

echo
echo "[3/8] Full repository validation..."
ZION_VALIDATION_PYTHON="$PYTHON" bash "$ROOT/scripts/validate.sh"

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
if env_path.owner() != "zetta":
    raise RuntimeError(
        f"production .env owner must be zetta: {env_path.owner()}"
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
COPY_DB="$TMP_ROOT/zion-copy.db"
COPY_LEGACY="$TMP_ROOT/zion_state.json"

PROD_ENV="$PROD_ENV" \
COPY_DB="$COPY_DB" \
COPY_LEGACY="$COPY_LEGACY" \
"$PYTHON" - <<'PY'
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(os.environ["PROD_ENV"])
load_dotenv(env_path, override=True)

from zion.config import Settings
from zion.db import ZION_APPLICATION_ID, ZionDB

settings = Settings.from_env()
source = settings.db_path
target = Path(os.environ["COPY_DB"])
legacy_target = Path(os.environ["COPY_LEGACY"])

if not source.is_file():
    raise RuntimeError(
        f"production database not found at {source}"
    )

if settings.legacy_state_path.is_file():
    shutil.copy2(settings.legacy_state_path, legacy_target)
    os.chmod(legacy_target, 0o600)

db = ZionDB(source, readonly=True)
try:
    verification = db.verify_integrity(full=True)
    if not verification["ok"]:
        raise RuntimeError(
            "production SQLite verification failed: "
            f"{verification}"
        )
    metadata = db.backup_to(target)
finally:
    db.close()

print("production_integrity=OK")
print("production_foreign_keys=OK")
print(f"backup_schema_version={metadata['schema_version']}")
print(f"backup_size_bytes={metadata['size_bytes']}")
print(f"backup_sha256={metadata['sha256']}")
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

    verification = db.verify_integrity(full=True)
    if not verification["ok"]:
        raise RuntimeError(
            "candidate migration verification failed: "
            f"{verification}"
        )

    pragmas = db.runtime_pragmas()
    if pragmas["journal_mode"] != "wal":
        raise RuntimeError(
            f"candidate journal_mode={pragmas['journal_mode']}"
        )
    if int(pragmas["foreign_keys"]) != 1:
        raise RuntimeError("candidate foreign_keys disabled")
    if int(pragmas["synchronous"]) != 2:
        raise RuntimeError(
            f"candidate synchronous={pragmas['synchronous']}"
        )
    if int(pragmas["trusted_schema"]) != 0:
        raise RuntimeError("candidate trusted_schema is not OFF")
    if int(pragmas["application_id"]) != ZION_APPLICATION_ID:
        raise RuntimeError("candidate application_id is not ZION")

    print(f"candidate_schema_version={db.schema_version()}")
    print("candidate_integrity=OK")
    print("candidate_foreign_keys=OK")
    print(f"candidate_journal_mode={pragmas['journal_mode']}")
    print(f"candidate_synchronous={pragmas['synchronous']}")
    print(f"candidate_trusted_schema={pragmas['trusted_schema']}")
    print(f"candidate_application_id={pragmas['application_id']}")
    print(f"candidate_db_size_bytes={db.file_size_bytes()}")
finally:
    db.close()
PY

echo
echo "PRE-DEPLOY: OK"
echo "Nenhum serviço foi parado/reiniciado."
echo "Nenhum arquivo de produção foi modificado por este script."
