#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/zetta/zion-community-bot"
SYSTEM_PYTHON="/usr/bin/python3"
SERVICE_SRC="$ROOT/systemd/zion.service"
SERVICE_DST="/etc/systemd/system/zion.service"
BACKUP_DIR="/home/zetta/.local/share/zion-community-bot/deploy-backups"
STATE_DIR="/home/zetta/.local/state/zion-community-bot"
RUNTIME_BASE="/home/zetta/.local/share/zion-community-bot/runtimes"
CURRENT_RUNTIME="$RUNTIME_BASE/current"
EXPECTED_USER="zetta"
EXPECTED_COMMIT="${ZION_EXPECTED_COMMIT:-}"
RUNTIME_DIR="$RUNTIME_BASE/$EXPECTED_COMMIT"
PYTHON="$RUNTIME_DIR/bin/python"
TARGET_DB="$STATE_DIR/zion.db"
TARGET_LEGACY="$STATE_DIR/zion_state.json"
TARGET_LOG="$STATE_DIR/zion.log"
TARGET_LOCK="$STATE_DIR/runtime.lock"
APPROVED_REF="origin/zion-v1"
EXPECTED_REPO="zettaceo/zion-community-bot"
PREVIOUS_COMMIT="${ZION_PREVIOUS_COMMIT:-}"
LOCAL_PROD_BRANCH="zion-v1-prod"

if [[ "$(id -un)" != "$EXPECTED_USER" ]]; then
  echo "ERRO: execute o deploy como $EXPECTED_USER." >&2
  exit 1
fi
if [[ ! -x "$SYSTEM_PYTHON" ]]; then
  echo "ERRO: $SYSTEM_PYTHON ausente." >&2
  exit 1
fi
"$SYSTEM_PYTHON" -I "$ROOT/scripts/check-git-release-boundary.py" \
  --root "$ROOT"

cd "$ROOT"

echo "[1/15] Conferindo runtime candidato por SHA..."
if [[ ! -d "$RUNTIME_DIR" || -L "$RUNTIME_DIR" || ! -x "$PYTHON" ]]; then
  echo "ERRO: runtime candidato inválido: $RUNTIME_DIR" >&2
  exit 1
fi
if [[ ! -f "$RUNTIME_DIR/release-sha.txt" ]] \
  || [[ "$(cat "$RUNTIME_DIR/release-sha.txt" 2>/dev/null || true)" != "$EXPECTED_COMMIT" ]]; then
  echo "ERRO: identidade do runtime candidato não corresponde ao release." >&2
  exit 1
fi
if [[ ! -L "$CURRENT_RUNTIME" ]]; then
  echo "ERRO: runtime/current não existe como symlink." >&2
  exit 1
fi
PREVIOUS_RUNTIME_TARGET="$(readlink -f -- "$CURRENT_RUNTIME" 2>/dev/null || true)"
if [[ ! -x "$PREVIOUS_RUNTIME_TARGET/bin/python" ]]; then
  echo "ERRO: runtime/current anterior é inválido." >&2
  exit 1
fi
"$PYTHON" "$ROOT/scripts/check-runtime.py"
"$PYTHON" -m pip check

echo "[2/15] Conferindo worktree e commit..."
CURRENT_BRANCH="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
if [[ "$CURRENT_BRANCH" != "$LOCAL_PROD_BRANCH" ]]; then
  echo "ERRO: branch local=$CURRENT_BRANCH; esperado=$LOCAL_PROD_BRANCH." >&2
  exit 1
fi
WORKTREE_STATUS="$(git status --porcelain --untracked-files=all)"
if [[ -n "$WORKTREE_STATUS" ]]; then
  echo "ERRO: worktree possui alterações rastreadas ou arquivos não versionados." >&2
  exit 1
fi

CURRENT_HEAD="$(git rev-parse HEAD)"
echo "HEAD=$CURRENT_HEAD"

if [[ ! "$EXPECTED_COMMIT" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "ERRO: ZION_EXPECTED_COMMIT é obrigatório e deve ser SHA completo." >&2
  exit 1
fi
if [[ "$CURRENT_HEAD" != "$EXPECTED_COMMIT" ]]; then
  echo "ERRO: HEAD diferente de ZION_EXPECTED_COMMIT." >&2
  exit 1
fi

if [[ "${ZION_GITHUB_GATES_PROVEN:-}" != "YES" ]]; then
  echo "ERRO: ZION_GITHUB_GATES_PROVEN=YES é obrigatório após verificar proteção/CI no GitHub." >&2
  exit 1
fi

ORIGIN_URL="$(git remote get-url origin 2>/dev/null || true)"
case "$ORIGIN_URL" in
  "https://github.com/$EXPECTED_REPO"|"https://github.com/$EXPECTED_REPO.git"|"git@github.com:$EXPECTED_REPO.git"|"ssh://git@github.com/$EXPECTED_REPO.git")
    ;;
  *)
    echo "ERRO: origin não aponta para o repositório GitHub esperado." >&2
    exit 1
    ;;
esac

APPROVED_SHA="$(git rev-parse "$APPROVED_REF^{commit}" 2>/dev/null || true)"
if [[ -z "$APPROVED_SHA" ]] || ! git merge-base --is-ancestor "$EXPECTED_COMMIT" "$APPROVED_REF" 2>/dev/null; then
  echo "ERRO: ZION_EXPECTED_COMMIT não pertence ao histórico local aprovado de $APPROVED_REF." >&2
  exit 1
fi

if [[ ! "$PREVIOUS_COMMIT" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "ERRO: ZION_PREVIOUS_COMMIT é obrigatório e deve ser SHA completo." >&2
  exit 1
fi
if [[ "$PREVIOUS_COMMIT" == "$CURRENT_HEAD" ]]; then
  echo "ERRO: ZION_PREVIOUS_COMMIT não pode ser igual ao release atual." >&2
  exit 1
fi
if ! git cat-file -e "$PREVIOUS_COMMIT^{commit}" 2>/dev/null; then
  echo "ERRO: ZION_PREVIOUS_COMMIT não existe localmente." >&2
  exit 1
fi
if ! git merge-base --is-ancestor "$PREVIOUS_COMMIT" "$CURRENT_HEAD"; then
  echo "ERRO: ZION_PREVIOUS_COMMIT não é ancestral do release atual." >&2
  exit 1
fi

echo "[3/15] Reconfirmando runtime auditado..."
"$PYTHON" "$ROOT/scripts/check-runtime.py"
"$PYTHON" -m pip check

echo "[4/15] Validando código, testes, shell e segredos..."
ZION_VALIDATION_PYTHON="$PYTHON" bash "$ROOT/scripts/validate.sh"

echo "[5/15] Conferindo arquivo systemd autoritativo..."
if [[ ! -f "$SERVICE_SRC" ]]; then
  echo "ERRO: $SERVICE_SRC não existe." >&2
  exit 1
fi
/usr/bin/systemd-analyze verify "$SERVICE_SRC"

echo "[6/15] Validando configuração e conhecimento ANTES do stop..."
"$PYTHON" "$ROOT/scripts/check-env-boundary.py" \
  --env "$ROOT/.env" \
  --allowlist "$ROOT/.env.example" \
  --owner zetta

"$PYTHON" - <<'PY'
import stat
from pathlib import Path

from zion.config import Settings
from zion.knowledge import KnowledgeBase
from zion.mistral import MistralClient

settings = Settings.from_env()
env_path = settings.root_dir / ".env"

if not env_path.is_file() or env_path.is_symlink():
    raise RuntimeError(".env ausente ou symlink")

info = env_path.stat()
mode = stat.S_IMODE(info.st_mode)
if mode & 0o077:
    raise RuntimeError(
        f".env possui permissões excessivas: {oct(mode)}"
    )
if env_path.owner() != "zetta":
    raise RuntimeError(
        f".env deve pertencer a zetta: {env_path.owner()}"
    )
if info.st_nlink != 1:
    raise RuntimeError(
        ".env não pode possuir hard links"
    )

if not settings.telegram_token:
    raise RuntimeError("TELEGRAM_BOT_TOKEN ausente")

issues = settings.configuration_issues()
if issues:
    raise RuntimeError(
        "configuration issues: " + ",".join(issues)
    )

if settings.ai_enabled and not MistralClient(settings).configured:
    raise RuntimeError(
        "IA habilitada sem configuração Mistral oficial completa"
    )

knowledge = KnowledgeBase(settings.knowledge_dir)
if not knowledge.chunks:
    raise RuntimeError("knowledge base vazia")
if knowledge.load_errors:
    raise RuntimeError(
        "knowledge load errors: " + ",".join(knowledge.load_errors)
    )

root = settings.root_dir.resolve()
state = (
    Path.home()
    / ".local"
    / "state"
    / "zion-community-bot"
).resolve()

def under(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(parent)
        return True
    except ValueError:
        return False

if not (
    under(settings.db_path, root)
    or under(settings.db_path, state)
):
    raise RuntimeError(
        "ZION_DB_PATH fora das áreas graváveis do sandbox systemd"
    )

if not (
    under(settings.log_path, root)
    or under(settings.log_path, state)
):
    raise RuntimeError(
        "ZION_LOG_PATH fora das áreas graváveis do sandbox systemd"
    )

if not under(settings.runtime_lock_path, state):
    raise RuntimeError(
        "ZION_RUNTIME_LOCK_PATH fora do state dir compartilhado"
    )

print(
    "config readiness: OK | "
    f"operators={len(settings.admin_user_ids)} | "
    f"knowledge_chunks={len(knowledge.chunks)} | "
    f"ai_enabled={settings.ai_enabled}"
)
PY

echo "[7/15] Preparando diretório privado de estado compartilhado..."
sudo /usr/bin/install \
  -d \
  -o zetta \
  -g zetta \
  -m 0700 \
  "$STATE_DIR"

echo "[8/15] Criando e verificando backup antes de parar ZION..."
if [[ -L "$BACKUP_DIR" ]]; then
  echo "ERRO: diretório de backup não pode ser symlink." >&2
  exit 1
fi
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
BACKUP_REAL="$(readlink -f -- "$BACKUP_DIR" 2>/dev/null || true)"
if [[ "$BACKUP_REAL" != "$BACKUP_DIR" ]]; then
  echo "ERRO: caminho de backup resolve por symlink/alias: $BACKUP_REAL" >&2
  exit 1
fi
if [[ "$(stat -c '%U' "$BACKUP_DIR")" != "$EXPECTED_USER" ]]; then
  echo "ERRO: diretório de backup deve pertencer a $EXPECTED_USER." >&2
  exit 1
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$BASHPID"
DEST="$BACKUP_DIR/$STAMP"
mkdir "$DEST"
chmod 700 "$DEST"

printf '%s\n' "$CURRENT_HEAD" > "$DEST/git-head.txt"
printf '%s\n' "$APPROVED_REF" > "$DEST/approved-ref.txt"
printf '%s\n' "$APPROVED_SHA" > "$DEST/approved-sha.txt"
printf '%s\n' "$PREVIOUS_COMMIT" > "$DEST/rollback-head.txt"
printf '%s\n' "$PREVIOUS_RUNTIME_TARGET" > "$DEST/runtime-before.txt"
printf '%s\n' "$RUNTIME_DIR" > "$DEST/runtime-candidate.txt"
git status --short --branch > "$DEST/git-status.txt"
stat -c 'mode=%a owner=%U group=%G' "$ROOT/.env" > "$DEST/env-metadata.txt"
sha256sum "$ROOT/.env" > "$DEST/env.sha256"
chmod 600 \
  "$DEST/git-head.txt" \
  "$DEST/approved-ref.txt" \
  "$DEST/approved-sha.txt" \
  "$DEST/rollback-head.txt" \
  "$DEST/runtime-before.txt" \
  "$DEST/runtime-candidate.txt" \
  "$DEST/git-status.txt" \
  "$DEST/env-metadata.txt" \
  "$DEST/env.sha256"

if [[ -f "$SERVICE_DST" ]]; then
  cp -a "$SERVICE_DST" "$DEST/zion.service.installed"
  chmod 600 "$DEST/zion.service.installed"
fi

DEST="$DEST" "$PYTHON" - <<'PY'
import os
import shutil
from pathlib import Path

from zion.config import Settings
from zion.db import ZION_APPLICATION_ID, ZionDB

settings = Settings.from_env()
dest = Path(os.environ["DEST"])

if settings.legacy_state_path.is_file():
    target = dest / "zion_state.json"
    shutil.copy2(settings.legacy_state_path, target)
    os.chmod(target, 0o600)

source = settings.db_path
if source.is_file():
    target = dest / "zion.db"
    db = ZionDB(source, readonly=True)
    try:
        metadata = db.backup_to(target)
    finally:
        db.close()

    manifest = dest / "zion.db.sha256"
    manifest.write_text(
        f"{metadata['sha256']}  zion.db\n",
        encoding="ascii",
    )
    os.chmod(manifest, 0o600)

    print(
        "sqlite backup: VERIFIED | "
        f"schema=v{metadata['schema_version']} | "
        f"bytes={metadata['size_bytes']} | "
        f"sha256={metadata['sha256']}"
    )
else:
    print("sqlite backup: source database not present yet")
PY

echo "[9/15] Parando ZION somente após todos os gates e backup..."
sudo /usr/bin/systemctl stop zion.service

if /usr/bin/systemctl is-active --quiet zion.service; then
  echo "ERRO: zion.service permaneceu ativo após stop." >&2
  exit 1
fi

echo "[10/15] Trocando runtime/current atomicamente..."
TMP_CURRENT="$RUNTIME_BASE/.current-$BASHPID"
rm -f "$TMP_CURRENT"
ln -s "$RUNTIME_DIR" "$TMP_CURRENT"
mv -Tf "$TMP_CURRENT" "$CURRENT_RUNTIME"
if [[ "$(readlink -f -- "$CURRENT_RUNTIME" 2>/dev/null || true)" != "$RUNTIME_DIR" ]]; then
  echo "ERRO: runtime/current não aponta para o release candidato." >&2
  exit 1
fi

echo "[11/15] Relocando estado mutável e migrando SQLite..."
ZION_TARGET_DB="$TARGET_DB" \
ZION_TARGET_LEGACY="$TARGET_LEGACY" \
ZION_TARGET_LOG="$TARGET_LOG" \
ZION_TARGET_LOCK="$TARGET_LOCK" \
"$PYTHON" - <<'PY'
import os
import shutil
from pathlib import Path

from zion.config import Settings
from zion.db import ZION_APPLICATION_ID, ZionDB
from zion.migrate import migrate_legacy_guardian_state

settings = Settings.from_env()
source_db = settings.db_path.expanduser().resolve(strict=False)
source_legacy = settings.legacy_state_path.expanduser().resolve(strict=False)

target_db = Path(os.environ["ZION_TARGET_DB"]).resolve(strict=False)
target_legacy = Path(os.environ["ZION_TARGET_LEGACY"]).resolve(strict=False)

target_db.parent.mkdir(parents=True, exist_ok=True)
os.chmod(target_db.parent, 0o700)

if source_db != target_db:
    if target_db.exists():
        raise RuntimeError(
            f"target database already exists during relocation: {target_db}"
        )
    if not source_db.is_file():
        raise RuntimeError(
            f"source production database missing: {source_db}"
        )
    source = ZionDB(source_db, readonly=True)
    try:
        verification = source.verify_integrity(full=True)
        if not verification["ok"]:
            raise RuntimeError(
                f"source database integrity failed: {verification}"
            )
        source.backup_to(target_db)
    finally:
        source.close()

if source_legacy != target_legacy and source_legacy.is_file():
    if target_legacy.exists():
        raise RuntimeError(
            f"target legacy state already exists: {target_legacy}"
        )
    shutil.copy2(source_legacy, target_legacy)
    os.chmod(target_legacy, 0o600)

db = ZionDB(target_db)
try:
    db.initialize()
    migrate_legacy_guardian_state(
        db,
        target_legacy,
    )

    if not db.ping():
        raise RuntimeError("database ping failed")

    verification = db.verify_integrity(full=True)
    if not verification["ok"]:
        raise RuntimeError(
            "SQLite verification failed after migration: "
            f"{verification}"
        )

    pragmas = db.runtime_pragmas()
    if pragmas["journal_mode"] != "wal":
        raise RuntimeError(
            f"SQLite journal_mode inesperado: {pragmas['journal_mode']}"
        )
    if int(pragmas["foreign_keys"]) != 1:
        raise RuntimeError("SQLite foreign_keys está desativado")
    if int(pragmas["synchronous"]) != 2:
        raise RuntimeError(
            f"SQLite synchronous não está FULL: "
            f"{pragmas['synchronous']}"
        )
    if int(pragmas["trusted_schema"]) != 0:
        raise RuntimeError("SQLite trusted_schema não está OFF")
    if int(pragmas["application_id"]) != ZION_APPLICATION_ID:
        raise RuntimeError(
            "SQLite application_id não corresponde ao ZION"
        )

    print(
        f"database: OK ({target_db}) | "
        f"schema=v{db.schema_version()} | "
        "integrity=OK | foreign_keys=OK | synchronous=FULL"
    )
finally:
    db.close()
PY

echo "[12/15] Instalando unit autoritativa..."
sudo /usr/bin/install \
  -o root \
  -g root \
  -m 0644 \
  "$SERVICE_SRC" \
  "$SERVICE_DST"

sudo /usr/bin/systemctl daemon-reload
sudo /usr/bin/systemctl enable zion.service >/dev/null

echo "[13/15] Iniciando ZION..."
sudo /usr/bin/systemctl start zion.service

for _ in $(seq 1 20); do
  if /usr/bin/systemctl is-active --quiet zion.service; then
    break
  fi
  sleep 1
done

echo "[14/15] Estado final..."
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

echo "[15/15] Confirmando runtime e state efetivos..."
if [[ "$(readlink -f -- "$CURRENT_RUNTIME")" != "$RUNTIME_DIR" ]]; then
  echo "ERRO: runtime/current divergiu após start." >&2
  exit 1
fi
if [[ ! -f "$TARGET_DB" ]]; then
  echo "ERRO: banco efetivo não existe no state dir." >&2
  exit 1
fi

echo
echo "Deploy modular concluído."
echo "Commit implantado: $CURRENT_HEAD"
echo "Backup pré-deploy verificado: $DEST"
echo "A .env NÃO foi duplicada no backup; somente metadados/hash foram salvos."
echo "Teste /status e, como operador, /health, /diagnostics, /jobs e /aistatus."
