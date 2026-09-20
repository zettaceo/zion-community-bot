#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEM_PYTHON="/usr/bin/python3"
PROD_ROOT="/home/zetta/zion-community-bot"
PROD_ENV="$PROD_ROOT/.env"
SERVICE="zion.service"
INSTALLED_SERVICE="/etc/systemd/system/zion.service"
STATE_DIR="/home/zetta/.local/state/zion-community-bot"
STATE_DB="$STATE_DIR/zion.db"
EXPECTED_COMMIT="${ZION_EXPECTED_COMMIT:-}"
APPROVED_REF="origin/zion-v1"
RUNTIME_BASE="/home/zetta/.local/share/zion-community-bot/runtimes"
PYTHON="${ZION_RUNTIME_PYTHON:-$RUNTIME_BASE/$EXPECTED_COMMIT/bin/python}"

TMP_ROOT="$(mktemp -d /tmp/zion-v11-predeploy.XXXXXX)"
chmod 700 "$TMP_ROOT"
trap 'rm -rf "$TMP_ROOT"' EXIT

echo "ZION v1.1 PRE-DEPLOY — READ-ONLY PRODUCTION CHECK"
echo "================================================="

echo
echo "[1/8] Approved branch/commit..."
if [[ ! -x "$SYSTEM_PYTHON" ]]; then
  echo "ERRO: $SYSTEM_PYTHON ausente." >&2
  exit 1
fi
"$SYSTEM_PYTHON" -I "$ROOT/scripts/check-git-release-boundary.py" \
  --root "$ROOT"
"$SYSTEM_PYTHON" -I "$ROOT/scripts/check-git-release-boundary.py" \
  --root "$PROD_ROOT"

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
CANDIDATE_STATUS="$(git status --porcelain --untracked-files=all)"
if [[ -n "$CANDIDATE_STATUS" ]]; then
  echo "ERRO: candidate worktree possui alterações rastreadas ou arquivos não versionados." >&2
  exit 1
fi
if [[ -e "$ROOT/.env" || -L "$ROOT/.env" ]]; then
  echo "ERRO: candidate worktree não pode conter .env local ignorado." >&2
  exit 1
fi

echo "candidate_head=$HEAD_SHA"
echo "approved_ref=$APPROVED_REF"
echo "approved_sha=$APPROVED_SHA"

echo
echo "[2/8] Staged release runtime..."
if [[ ! -x "$PYTHON" ]]; then
  echo "ERRO: runtime candidato ausente: $PYTHON" >&2
  exit 1
fi
if [[ ! -f "$RUNTIME_BASE/$EXPECTED_COMMIT/release-sha.txt" ]] \
  || [[ "$(cat "$RUNTIME_BASE/$EXPECTED_COMMIT/release-sha.txt")" != "$EXPECTED_COMMIT" ]]; then
  echo "ERRO: identidade do runtime candidato inválida." >&2
  exit 1
fi
"$PYTHON" "$ROOT/scripts/check-runtime.py"
"$PYTHON" -m pip check

echo
echo "[3/8] Full repository validation..."
ZION_VALIDATION_PYTHON="$PYTHON" bash "$ROOT/scripts/validate.sh"

echo
echo "[4/8] Candidate systemd units..."
/usr/bin/systemd-analyze verify "$ROOT/systemd/zion.service"

DASHBOARD_LOAD_STATE="$(
  /usr/bin/systemctl show zion-dashboard.service \
    -p LoadState --value 2>/dev/null || true
)"
if [[ -n "$DASHBOARD_LOAD_STATE" && "$DASHBOARD_LOAD_STATE" != "not-found" ]]; then
  /usr/bin/systemd-analyze verify "$ROOT/systemd/zion-dashboard.service"
  echo "dashboard_systemd_unit=OK"
fi
echo "systemd_unit=OK"

PROD_SERVICE_STATE_LAYOUT=false
if [[ -f "$INSTALLED_SERVICE" ]] \
  && grep -Fq "ZION_DB_PATH=$STATE_DB" "$INSTALLED_SERVICE"; then
  PROD_SERVICE_STATE_LAYOUT=true
fi
echo "production_state_layout=$PROD_SERVICE_STATE_LAYOUT"

echo
echo "[5/8] Production config + candidate knowledge readiness (read-only)..."
"$PYTHON" "$ROOT/scripts/check-env-boundary.py" \
  --env "$PROD_ENV" \
  --allowlist "$ROOT/.env.example" \
  --owner zetta

PROD_ENV="$PROD_ENV" \
PROD_ROOT="$PROD_ROOT" \
CANDIDATE_ROOT="$ROOT" \
PROD_SERVICE_STATE_LAYOUT="$PROD_SERVICE_STATE_LAYOUT" \
STATE_DIR="$STATE_DIR" \
"$PYTHON" - <<'PY'
import os
import stat
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(os.environ["PROD_ENV"])
prod_root = Path(os.environ["PROD_ROOT"]).resolve()
candidate_root = Path(os.environ["CANDIDATE_ROOT"]).resolve()

if not env_path.is_file() or env_path.is_symlink():
    raise RuntimeError("production .env absent or symlinked")

info = env_path.stat()
mode = stat.S_IMODE(info.st_mode)
if mode & 0o077:
    raise RuntimeError(
        f"production .env permissions too broad: {oct(mode)}"
    )
if env_path.owner() != "zetta":
    raise RuntimeError(
        f"production .env owner must be zetta: {env_path.owner()}"
    )
if info.st_nlink != 1:
    raise RuntimeError("production .env must not have hard links")

load_dotenv(env_path, override=True)

# Settings is imported from the detached candidate worktree.
# Model the *currently installed* production unit, not merely .env defaults.
state_dir = Path(os.environ["STATE_DIR"]).resolve()
if os.environ["PROD_SERVICE_STATE_LAYOUT"] == "true":
    os.environ["ZION_DB_PATH"] = str(state_dir / "zion.db")
    os.environ["ZION_STATE_FILE"] = str(state_dir / "zion_state.json")
    os.environ["ZION_LOG_PATH"] = str(state_dir / "zion.log")
    os.environ["ZION_RUNTIME_LOCK_PATH"] = str(state_dir / "runtime.lock")
else:
    os.environ.setdefault("ZION_DB_PATH", str(prod_root / "zion.db"))
    os.environ.setdefault(
        "ZION_STATE_FILE",
        str(prod_root / "zion_state.json"),
    )
    os.environ.setdefault("ZION_LOG_PATH", str(prod_root / "zion.log"))

os.environ.setdefault(
    "ZION_KNOWLEDGE_DIR",
    str(prod_root / "knowledge"),
)

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

configured_knowledge = settings.knowledge_dir.resolve(strict=False)
default_prod_knowledge = (prod_root / "knowledge").resolve(strict=False)
if configured_knowledge == default_prod_knowledge:
    knowledge_path = candidate_root / "knowledge"
else:
    knowledge_path = configured_knowledge

knowledge = KnowledgeBase(knowledge_path)
if not knowledge.chunks:
    raise RuntimeError("candidate/effective knowledge base empty")
if knowledge.load_errors:
    raise RuntimeError(
        "candidate/effective knowledge errors: "
        + ",".join(knowledge.load_errors)
    )

print(
    "production config: OK | "
    f"operators={len(settings.admin_user_ids)} | "
    f"ai_enabled={settings.ai_enabled} | "
    f"db_path={settings.db_path} | "
    f"knowledge_source={knowledge_path} | "
    f"knowledge_chunks={len(knowledge.chunks)}"
)
PY

echo
echo "[6/8] Current production service + dashboard alignment (no change)..."
if ! /usr/bin/systemctl is-active --quiet "$SERVICE"; then
  echo "ERRO: produção atual não está ativa; trate como incidente antes do release." >&2
  exit 1
fi
/usr/bin/systemctl show "$SERVICE" \
  -p ActiveState \
  -p SubState \
  -p MainPID \
  -p NRestarts \
  -p ExecMainStartTimestamp

PROD_DB_PATH="$(
  PROD_ENV="$PROD_ENV" \
  PROD_ROOT="$PROD_ROOT" \
  PROD_SERVICE_STATE_LAYOUT="$PROD_SERVICE_STATE_LAYOUT" \
  STATE_DIR="$STATE_DIR" \
  "$PYTHON" - <<'PY'
import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(os.environ["PROD_ENV"])
prod_root = Path(os.environ["PROD_ROOT"]).resolve()
state_dir = Path(os.environ["STATE_DIR"]).resolve()
load_dotenv(env_path, override=True)
if os.environ["PROD_SERVICE_STATE_LAYOUT"] == "true":
    os.environ["ZION_DB_PATH"] = str(state_dir / "zion.db")
else:
    os.environ.setdefault("ZION_DB_PATH", str(prod_root / "zion.db"))

from zion.config import Settings
print(Settings.from_env().db_path.expanduser().resolve(strict=False))
PY
)"

DASHBOARD_LOAD_STATE="$(
  /usr/bin/systemctl show zion-dashboard.service \
    -p LoadState --value 2>/dev/null || true
)"
if [[ -n "$DASHBOARD_LOAD_STATE" && "$DASHBOARD_LOAD_STATE" != "not-found" ]]; then
  DASHBOARD_ENV="$(
    /usr/bin/systemctl show zion-dashboard.service \
      -p Environment --value 2>/dev/null || true
  )"
  DASHBOARD_DB_PATH="$(
    printf '%s\n' "$DASHBOARD_ENV" \
      | tr ' ' '\n' \
      | sed -n 's/^ZION_DASHBOARD_DB_PATH=//p' \
      | head -n1
  )"
  if [[ -z "$DASHBOARD_DB_PATH" ]]; then
    echo "ERRO: dashboard instalado sem ZION_DASHBOARD_DB_PATH explícito." >&2
    exit 1
  fi
  DASHBOARD_DB_PATH="$(
    P="$DASHBOARD_DB_PATH" \
      "$PYTHON" -c 'import os, pathlib; print(pathlib.Path(os.environ["P"]).expanduser().resolve(strict=False))'
  )"
  if [[ "$DASHBOARD_DB_PATH" != "$PROD_DB_PATH" ]]; then
    echo "ERRO: dashboard aponta para DB diferente do bot." >&2
    echo "bot_db=$PROD_DB_PATH" >&2
    echo "dashboard_db=$DASHBOARD_DB_PATH" >&2
    exit 1
  fi
  echo "dashboard_db_alignment=OK | db=$PROD_DB_PATH"
fi

echo
echo "[7/8] Production SQLite backup to disposable /tmp copy..."
COPY_DB="$TMP_ROOT/zion-copy.db"
COPY_LEGACY="$TMP_ROOT/zion_state.json"

PROD_ENV="$PROD_ENV" \
PROD_ROOT="$PROD_ROOT" \
PROD_SERVICE_STATE_LAYOUT="$PROD_SERVICE_STATE_LAYOUT" \
STATE_DIR="$STATE_DIR" \
COPY_DB="$COPY_DB" \
COPY_LEGACY="$COPY_LEGACY" \
"$PYTHON" - <<'PY'
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(os.environ["PROD_ENV"])
prod_root = Path(os.environ["PROD_ROOT"]).resolve()
state_dir = Path(os.environ["STATE_DIR"]).resolve()
load_dotenv(env_path, override=True)
if os.environ["PROD_SERVICE_STATE_LAYOUT"] == "true":
    os.environ["ZION_DB_PATH"] = str(state_dir / "zion.db")
    os.environ["ZION_STATE_FILE"] = str(state_dir / "zion_state.json")
else:
    os.environ.setdefault("ZION_DB_PATH", str(prod_root / "zion.db"))
    os.environ.setdefault(
        "ZION_STATE_FILE",
        str(prod_root / "zion_state.json"),
    )

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
