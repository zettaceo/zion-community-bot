#!/usr/bin/env bash
set -euo pipefail

ROOT="${ZION_PROD_ROOT:-/home/zetta/zion-community-bot}"
PYTHON="$ROOT/.venv/bin/python"
SERVICE_SRC="$ROOT/systemd/zion.service"
SERVICE_DST="/etc/systemd/system/zion.service"
BACKUP_DIR="$ROOT/backups"
STATE_DIR="/home/zetta/.local/state/zion-community-bot"
EXPECTED_COMMIT="${ZION_EXPECTED_COMMIT:-}"
REMOTE_BRANCH="zion-v1"
APPROVED_REF="origin/zion-v1"
EXPECTED_REPO="zettaceo/zion-community-bot"
PREVIOUS_COMMIT="${ZION_PREVIOUS_COMMIT:-}"
LOCAL_PROD_BRANCH="zion-v1-prod"

cd "$ROOT"

echo "[1/13] Conferindo ambiente virtual..."
if [[ ! -x "$PYTHON" ]]; then
  echo "ERRO: $PYTHON não existe." >&2
  exit 1
fi

echo "[2/13] Conferindo worktree e commit..."
CURRENT_BRANCH="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
if [[ "$CURRENT_BRANCH" != "$LOCAL_PROD_BRANCH" ]]; then
  echo "ERRO: branch local=$CURRENT_BRANCH; esperado=$LOCAL_PROD_BRANCH." >&2
  exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "ERRO: existem alterações rastreadas não commitadas." >&2
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

if command -v timeout >/dev/null 2>&1; then
  REMOTE_LINE="$(timeout 20 env GIT_TERMINAL_PROMPT=0 git ls-remote --exit-code origin "refs/heads/$REMOTE_BRANCH" 2>/dev/null | head -n1 || true)"
else
  REMOTE_LINE="$(env GIT_TERMINAL_PROMPT=0 git ls-remote --exit-code origin "refs/heads/$REMOTE_BRANCH" 2>/dev/null | head -n1 || true)"
fi
REMOTE_SHA="${REMOTE_LINE%%[[:space:]]*}"
if [[ "$REMOTE_SHA" != "$EXPECTED_COMMIT" ]]; then
  echo "ERRO: HEAD remoto ao vivo de $REMOTE_BRANCH não corresponde ao commit esperado." >&2
  exit 1
fi

APPROVED_SHA="$(git rev-parse "$APPROVED_REF^{commit}" 2>/dev/null || true)"
if [[ "$APPROVED_SHA" != "$EXPECTED_COMMIT" ]]; then
  echo "ERRO: $APPROVED_REF não aponta para ZION_EXPECTED_COMMIT." >&2
  exit 1
fi

if [[ -n "$PREVIOUS_COMMIT" ]]; then
  if [[ ! "$PREVIOUS_COMMIT" =~ ^[0-9a-fA-F]{40}$ ]]; then
    echo "ERRO: ZION_PREVIOUS_COMMIT inválido." >&2
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
fi

echo "[3/13] Conferindo compatibilidade do runtime..."
"$PYTHON" "$ROOT/scripts/check-runtime.py"

echo "[4/13] Validando código, testes, shell e segredos..."
bash "$ROOT/scripts/validate.sh"

echo "[5/13] Conferindo arquivo systemd autoritativo..."
if [[ ! -f "$SERVICE_SRC" ]]; then
  echo "ERRO: $SERVICE_SRC não existe." >&2
  exit 1
fi
/usr/bin/systemd-analyze verify "$SERVICE_SRC"

echo "[6/13] Validando configuração e conhecimento ANTES do stop..."
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

mode = stat.S_IMODE(env_path.stat().st_mode)
if mode & 0o077:
    raise RuntimeError(
        f".env possui permissões excessivas: {oct(mode)}"
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

echo "[7/13] Preparando diretório privado de estado compartilhado..."
sudo /usr/bin/install \
  -d \
  -o zetta \
  -g zetta \
  -m 0700 \
  "$STATE_DIR"

echo "[8/13] Criando e verificando backup antes de parar ZION..."
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BACKUP_DIR/$STAMP"
mkdir -p "$DEST"
chmod 700 "$DEST"

printf '%s\n' "$CURRENT_HEAD" > "$DEST/git-head.txt"
printf '%s\n' "$APPROVED_REF" > "$DEST/approved-ref.txt"
printf '%s\n' "$APPROVED_SHA" > "$DEST/approved-sha.txt"
if [[ -n "$PREVIOUS_COMMIT" ]]; then
  printf '%s\n' "$PREVIOUS_COMMIT" > "$DEST/rollback-head.txt"
fi
git status --short --branch > "$DEST/git-status.txt"
stat -c 'mode=%a owner=%U group=%G' "$ROOT/.env" > "$DEST/env-metadata.txt"
sha256sum "$ROOT/.env" > "$DEST/env.sha256"
chmod 600 \
  "$DEST/git-head.txt" \
  "$DEST/approved-ref.txt" \
  "$DEST/approved-sha.txt" \
  "$DEST/git-status.txt" \
  "$DEST/env-metadata.txt" \
  "$DEST/env.sha256"
if [[ -f "$DEST/rollback-head.txt" ]]; then
  chmod 600 "$DEST/rollback-head.txt"
fi

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

echo "[9/13] Parando ZION somente após todos os gates e backup..."
sudo /usr/bin/systemctl stop zion.service

if /usr/bin/systemctl is-active --quiet zion.service; then
  echo "ERRO: zion.service permaneceu ativo após stop." >&2
  exit 1
fi

echo "[10/13] Inicializando/migrando banco local..."
"$PYTHON" - <<'PY'
from zion.config import Settings
from zion.db import ZionDB
from zion.migrate import migrate_legacy_guardian_state

settings = Settings.from_env()
db = ZionDB(settings.db_path)
try:
    db.initialize()
    migrate_legacy_guardian_state(
        db,
        settings.legacy_state_path,
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
        f"database: OK ({settings.db_path}) | "
        f"schema=v{db.schema_version()} | "
        "integrity=OK | foreign_keys=OK | synchronous=FULL"
    )
finally:
    db.close()
PY

echo "[11/13] Instalando unit autoritativa..."
sudo /usr/bin/install \
  -o root \
  -g root \
  -m 0644 \
  "$SERVICE_SRC" \
  "$SERVICE_DST"

sudo /usr/bin/systemctl daemon-reload
sudo /usr/bin/systemctl enable zion.service >/dev/null

echo "[12/13] Iniciando ZION..."
sudo /usr/bin/systemctl start zion.service

for _ in $(seq 1 20); do
  if /usr/bin/systemctl is-active --quiet zion.service; then
    break
  fi
  sleep 1
done

echo "[13/13] Estado final..."
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
echo "A .env NÃO foi duplicada no backup; somente metadados/hash foram salvos."
echo "Teste /status e, como operador, /health, /diagnostics, /jobs e /aistatus."
