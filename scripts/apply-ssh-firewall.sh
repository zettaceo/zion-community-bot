#!/usr/bin/env bash
set -euo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_USER="zetta"

RULESET_SRC="$SCRIPT_ROOT/ops/nftables/zion-ssh-private.nft"
RUNTIME_SRC="$SCRIPT_ROOT/ops/nftables/zion-ssh-firewall-runtime.sh"
UNIT_SRC="$SCRIPT_ROOT/systemd/zion-ssh-firewall.service"

CONFIG_DIR="/etc/zion-community-bot"
RULESET_DST="$CONFIG_DIR/zion-ssh-private.nft"
RUNTIME_DST="/usr/local/sbin/zion-ssh-firewall-runtime"
UNIT_DST="/etc/systemd/system/zion-ssh-firewall.service"

BACKUP_PARENT="/var/lib/zion-community-bot"
BACKUP_DIR="$BACKUP_PARENT/firewall-backups"
SERVICE="zion-ssh-firewall.service"
BOT_SERVICE="zion.service"

if [[ "${ZION_FIREWALL_CHANGE_AUTHORIZED:-}" != "YES" ]]; then
  echo "ERRO: ZION_FIREWALL_CHANGE_AUTHORIZED=YES exige autorização explícita." >&2
  exit 2
fi
if [[ "${ZION_REMOTE_ACCESS_PROVEN:-}" != "YES" ]]; then
  echo "ERRO: ZION_REMOTE_ACCESS_PROVEN=YES exige acesso SSH Tailscale por chave já provado." >&2
  exit 2
fi
if [[ "${ZION_SECOND_SSH_PROVEN:-}" != "YES" ]]; then
  echo "ERRO: ZION_SECOND_SSH_PROVEN=YES exige segunda sessão independente já provada." >&2
  exit 2
fi

if [[ "$(id -un)" != "$EXPECTED_USER" ]]; then
  echo "ERRO: execute como $EXPECTED_USER, não como root." >&2
  exit 2
fi

for path in "$RULESET_SRC" "$RUNTIME_SRC" "$UNIT_SRC"; do
  if [[ ! -f "$path" || -L "$path" ]]; then
    echo "ERRO: artefato firewall ausente ou symlink: $path" >&2
    exit 2
  fi
done

if ! command -v tailscale >/dev/null 2>&1 || [[ ! -d /sys/class/net/tailscale0 ]]; then
  echo "ERRO: Tailscale/tailscale0 não está pronto." >&2
  exit 2
fi
if [[ ! -x /usr/sbin/nft ]]; then
  echo "ERRO: /usr/sbin/nft ausente." >&2
  exit 2
fi
if ! /usr/bin/systemctl is-active --quiet "$BOT_SERVICE"; then
  echo "ERRO: zion.service não está ativo; trate o incidente antes do firewall." >&2
  exit 2
fi

if ! sudo -n /usr/bin/true 2>/dev/null; then
  echo "ERRO: sudo não autenticado; execute 'sudo -v' e tente novamente." >&2
  exit 2
fi

source_ip=""
if [[ -n "${SSH_CONNECTION:-}" ]]; then
  source_ip="${SSH_CONNECTION%% *}"
elif [[ "${ZION_PHYSICAL_CONSOLE:-}" == "YES" && -n "${ZION_TAILSCALE_CLIENT_IP:-}" ]]; then
  source_ip="$ZION_TAILSCALE_CLIENT_IP"
else
  echo "ERRO: use uma sessão SSH via Tailscale ou informe o cliente Tailscale no console físico." >&2
  exit 2
fi

/usr/bin/python3 -I - "$source_ip" <<'PY'
import ipaddress
import sys

address = ipaddress.ip_address(sys.argv[1])
allowed = (
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("fd7a:115c:a1e0::/48"),
)
if not any(address in network for network in allowed):
    raise SystemExit("cliente administrativo não pertence ao espaço Tailscale")
PY

before_pid="$(/usr/bin/systemctl show "$BOT_SERVICE" -p MainPID --value)"
before_restarts="$(/usr/bin/systemctl show "$BOT_SERVICE" -p NRestarts --value)"

if [[ -e "$CONFIG_DIR" || -L "$CONFIG_DIR" ]]; then
  if [[ ! -d "$CONFIG_DIR" || -L "$CONFIG_DIR" ]]; then
    echo "ERRO: $CONFIG_DIR deve ser diretório real." >&2
    exit 2
  fi
  config_meta="$(sudo /usr/bin/stat -c '%U:%G:%a' "$CONFIG_DIR")"
  if [[ "$config_meta" != "root:root:755" ]]; then
    echo "ERRO: $CONFIG_DIR deve ser root:root 0755." >&2
    exit 2
  fi
fi

check_existing_exact() {
  local src="$1"
  local dst="$2"
  if [[ ! -e "$dst" && ! -L "$dst" ]]; then
    return 1
  fi
  if [[ ! -f "$dst" || -L "$dst" ]]; then
    echo "ERRO: destino existente não é arquivo regular: $dst" >&2
    exit 2
  fi
  if ! sudo /usr/bin/cmp -s "$src" "$dst"; then
    echo "ERRO: destino existente diverge do candidato revisado: $dst" >&2
    exit 2
  fi
  return 0
}

existing=0
check_existing_exact "$RULESET_SRC" "$RULESET_DST" && existing=$((existing + 1))
check_existing_exact "$RUNTIME_SRC" "$RUNTIME_DST" && existing=$((existing + 1))
check_existing_exact "$UNIT_SRC" "$UNIT_DST" && existing=$((existing + 1))

if (( existing != 0 && existing != 3 )); then
  echo "ERRO: instalação firewall parcial; revisão manual necessária." >&2
  exit 2
fi

fresh=false
if (( existing == 0 )); then
  fresh=true
fi

sudo /usr/bin/install -d -o root -g root -m 0755 "$BACKUP_PARENT"
sudo /usr/bin/install -d -o root -g root -m 0700 "$BACKUP_DIR"

if [[ "$(sudo /usr/bin/stat -c '%U:%G:%a' "$BACKUP_DIR")" != "root:root:700" ]]; then
  echo "ERRO: backup firewall deve ser root:root 0700." >&2
  exit 2
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
evidence="$BACKUP_DIR/nft-before.$stamp.$BASHPID.txt"
sudo /usr/sbin/nft list ruleset | sudo /usr/bin/tee "$evidence" >/dev/null
sudo /usr/bin/chown root:root "$evidence"
sudo /usr/bin/chmod 0600 "$evidence"

mutated=false
rollback() {
  if [[ "$mutated" != true ]]; then
    return
  fi
  echo "Falha após mutação; removendo somente o guard SSH ZION recém-instalado..." >&2
  sudo /usr/bin/systemctl disable --now "$SERVICE" >/dev/null 2>&1 || true
  sudo /usr/local/sbin/zion-ssh-firewall-runtime remove >/dev/null 2>&1 || true
  if [[ "$fresh" == true ]]; then
    sudo /usr/bin/rm -f "$UNIT_DST" "$RUNTIME_DST" "$RULESET_DST"
    sudo /usr/bin/systemctl daemon-reload >/dev/null 2>&1 || true
  fi
}
trap rollback ERR

if [[ "$fresh" == true ]]; then
  sudo /usr/bin/install -d -o root -g root -m 0755 "$CONFIG_DIR"
  sudo /usr/bin/install -o root -g root -m 0644 "$RULESET_SRC" "$RULESET_DST"
  sudo /usr/bin/install -o root -g root -m 0755 "$RUNTIME_SRC" "$RUNTIME_DST"
  sudo /usr/bin/install -o root -g root -m 0644 "$UNIT_SRC" "$UNIT_DST"
fi

mutated=true

sudo /usr/bin/systemctl daemon-reload
sudo /usr/bin/systemctl enable --now "$SERVICE"
sudo /usr/local/sbin/zion-ssh-firewall-runtime check

if ! /usr/bin/systemctl is-active --quiet "$SERVICE"; then
  echo "ERRO: $SERVICE não está ativo." >&2
  exit 1
fi
if ! /usr/bin/systemctl is-enabled --quiet "$SERVICE"; then
  echo "ERRO: $SERVICE não está habilitado." >&2
  exit 1
fi

after_pid="$(/usr/bin/systemctl show "$BOT_SERVICE" -p MainPID --value)"
after_restarts="$(/usr/bin/systemctl show "$BOT_SERVICE" -p NRestarts --value)"
if [[ "$after_pid" != "$before_pid" || "$after_restarts" != "$before_restarts" ]]; then
  echo "ERRO: zion.service mudou durante a aplicação do firewall." >&2
  exit 1
fi

trap - ERR
mutated=false

echo "ZION SSH firewall guard aplicado."
echo "Somente TCP/22 foi alterado:"
echo "- loopback: permitido"
echo "- tailscale0: permitido"
echo "- demais interfaces IPv4/IPv6: DROP"
echo "Nenhum outro tráfego foi alterado."
echo "MANTENHA AS SESSÕES ATUAIS ABERTAS."
echo "Abra uma TERCEIRA sessão SSH via Tailscale e prove Accepted publickey antes de encerrar recovery."
echo "evidence=$evidence"
