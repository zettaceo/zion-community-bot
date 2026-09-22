#!/usr/bin/env bash
set -euo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_USER="zetta"
EXPECTED_COMMIT="${ZION_EXPECTED_COMMIT:-}"

RULESET_SRC="$SCRIPT_ROOT/ops/nftables/zion-ssh-private.nft"
RUNTIME_SRC="$SCRIPT_ROOT/ops/nftables/zion-ssh-firewall-runtime.sh"
UNIT_SRC="$SCRIPT_ROOT/systemd/zion-ssh-firewall.service"

RULESET_DST="/etc/zion-community-bot/zion-ssh-private.nft"
RUNTIME_DST="/usr/local/sbin/zion-ssh-firewall-runtime"
UNIT_DST="/etc/systemd/system/zion-ssh-firewall.service"

SERVICE="zion-ssh-firewall.service"
BOT_SERVICE="zion.service"

if [[ "${ZION_FIREWALL_ROLLBACK_AUTHORIZED:-}" != "YES" ]]; then
  echo "ERRO: ZION_FIREWALL_ROLLBACK_AUTHORIZED=YES exige autorização explícita." >&2
  exit 2
fi

if [[ "$(id -un)" != "$EXPECTED_USER" ]]; then
  echo "ERRO: execute como $EXPECTED_USER, não como root." >&2
  exit 2
fi

if [[ ! "$EXPECTED_COMMIT" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "ERRO: ZION_EXPECTED_COMMIT deve ser o SHA revisado completo." >&2
  exit 2
fi

/usr/bin/python3 -I "$SCRIPT_ROOT/scripts/check-git-release-boundary.py" \
  --root "$SCRIPT_ROOT"

candidate_head="$(/usr/bin/git -C "$SCRIPT_ROOT" rev-parse HEAD)"
approved_sha="$(/usr/bin/git -C "$SCRIPT_ROOT" rev-parse origin/zion-v1.1-dev^{commit} 2>/dev/null || true)"
candidate_status="$(/usr/bin/git -C "$SCRIPT_ROOT" status --porcelain --untracked-files=all)"
if [[ "$candidate_head" != "$EXPECTED_COMMIT" || -n "$candidate_status" ]]; then
  echo "ERRO: rollback deve partir do candidate exato e limpo." >&2
  exit 2
fi
if [[ "$approved_sha" != "$EXPECTED_COMMIT" ]]; then
  echo "ERRO: origin/zion-v1.1-dev não aponta para o candidate do rollback." >&2
  exit 2
fi

if ! sudo -n /usr/bin/true 2>/dev/null; then
  echo "ERRO: sudo não autenticado; execute 'sudo -v' e tente novamente." >&2
  exit 2
fi

verify_exact_root_file() {
  local src="$1"
  local dst="$2"
  local expected_mode="$3"

  if [[ ! -f "$src" || -L "$src" ]]; then
    echo "ERRO: fonte revisada ausente ou symlink: $src" >&2
    exit 2
  fi
  if [[ ! -f "$dst" || -L "$dst" ]]; then
    echo "ERRO: destino firewall ausente ou não regular: $dst" >&2
    exit 2
  fi

  metadata="$(sudo /usr/bin/stat -c '%U:%G:%a:%h' "$dst")"
  if [[ "$metadata" != "root:root:$expected_mode:1" ]]; then
    echo "ERRO: destino firewall possui metadata inesperada: $dst" >&2
    exit 2
  fi

  if ! sudo /usr/bin/cmp -s "$src" "$dst"; then
    echo "ERRO: destino firewall diverge do candidate; não remover automaticamente: $dst" >&2
    exit 2
  fi
}

verify_exact_root_file "$RULESET_SRC" "$RULESET_DST" 644
verify_exact_root_file "$RUNTIME_SRC" "$RUNTIME_DST" 755
verify_exact_root_file "$UNIT_SRC" "$UNIT_DST" 644

if ! /usr/bin/systemctl is-active --quiet "$BOT_SERVICE"; then
  echo "ERRO: zion.service não está ativo; trate o incidente antes do rollback." >&2
  exit 2
fi

before_pid="$(/usr/bin/systemctl show "$BOT_SERVICE" -p MainPID --value)"
before_restarts="$(/usr/bin/systemctl show "$BOT_SERVICE" -p NRestarts --value)"

sudo /usr/bin/systemctl disable --now "$SERVICE"
sudo "$RUNTIME_DST" remove
sudo /usr/bin/rm -f "$UNIT_DST" "$RUNTIME_DST" "$RULESET_DST"
sudo /usr/bin/systemctl daemon-reload

if sudo /usr/sbin/nft list table inet zion_ssh_guard >/dev/null 2>&1; then
  echo "ERRO: tabela zion_ssh_guard permaneceu após rollback." >&2
  exit 1
fi

after_pid="$(/usr/bin/systemctl show "$BOT_SERVICE" -p MainPID --value)"
after_restarts="$(/usr/bin/systemctl show "$BOT_SERVICE" -p NRestarts --value)"
if [[ "$after_pid" != "$before_pid" || "$after_restarts" != "$before_restarts" ]]; then
  echo "ERRO: zion.service mudou durante rollback do firewall." >&2
  exit 1
fi

echo "Rollback do ZION SSH firewall concluído."
echo "A tabela dedicada e os três artefatos instalados foram removidos."
echo "Reavalie a causa antes de tentar nova aplicação."
