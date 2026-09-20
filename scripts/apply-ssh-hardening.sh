#!/usr/bin/env bash
set -euo pipefail

ROOT="${ZION_ROOT:-/home/zetta/zion-community-bot}"
EXPECTED_USER="${ZION_REMOTE_USER:-zetta}"
EXPECTED_GROUP="${ZION_REMOTE_GROUP:-$(id -gn "$EXPECTED_USER" 2>/dev/null || printf '%s' "$EXPECTED_USER")}"
SRC="$ROOT/ops/sshd/99-zion-remote.conf"
DST="/etc/ssh/sshd_config.d/99-zion-remote.conf"
SSH_DIR="${ZION_SSH_DIR:-$HOME/.ssh}"
AUTHORIZED_KEYS="${ZION_AUTHORIZED_KEYS:-$SSH_DIR/authorized_keys}"
STATE_DIR="${ZION_STATE_DIR:-/home/zetta/.local/state/zion-community-bot}"
BACKUP_DIR="$STATE_DIR/ssh-hardening-backups"

if [[ "${ZION_REMOTE_ACCESS_PROVEN:-}" != "YES" ]]; then
  echo "ERRO: defina ZION_REMOTE_ACCESS_PROVEN=YES somente após login por chave validado." >&2
  exit 2
fi

if [[ "$(id -un)" != "$EXPECTED_USER" ]]; then
  echo "ERRO: execute como $EXPECTED_USER, não como root." >&2
  exit 2
fi

if [[ ! -f "$SRC" || -L "$SRC" ]]; then
  echo "ERRO: template sshd ausente ou symlink: $SRC" >&2
  exit 2
fi

if ! command -v tailscale >/dev/null 2>&1; then
  echo "ERRO: Tailscale não está instalado." >&2
  exit 2
fi

tailscale_ip="$(tailscale ip -4 2>/dev/null | head -n1 || true)"
if [[ -z "$tailscale_ip" ]]; then
  echo "ERRO: Tailscale não possui IPv4 ativo." >&2
  exit 2
fi

python3 - "$tailscale_ip" <<'PY'
import ipaddress
import sys
address = ipaddress.ip_address(sys.argv[1])
if address not in ipaddress.ip_network("100.64.0.0/10"):
    raise SystemExit("Tailscale IPv4 fora de 100.64.0.0/10")
PY

if [[ -n "${SSH_CONNECTION:-}" ]]; then
  source_ip="${SSH_CONNECTION%% *}"
  python3 - "$source_ip" <<'PY'
import ipaddress
import sys
address = ipaddress.ip_address(sys.argv[1])
tailscale_v4 = ipaddress.ip_network("100.64.0.0/10")
tailscale_v6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")
if address not in tailscale_v4 and address not in tailscale_v6:
    raise SystemExit(
        "Sessão SSH atual não veio de um endereço Tailscale; abortando."
    )
PY
elif [[ "${ZION_PHYSICAL_CONSOLE:-}" != "YES" ]]; then
  echo "ERRO: sem sessão SSH Tailscale comprovada. Em console físico, defina ZION_PHYSICAL_CONSOLE=YES." >&2
  exit 2
fi

if [[ ! -d "$SSH_DIR" || -L "$SSH_DIR" ]]; then
  echo "ERRO: $SSH_DIR ausente ou symlink." >&2
  exit 2
fi
if [[ "$(stat -c '%a' "$SSH_DIR")" != "700" ]]; then
  echo "ERRO: $SSH_DIR deve ter modo 700." >&2
  exit 2
fi
if [[ "$(stat -c '%U' "$SSH_DIR")" != "$EXPECTED_USER" ]]; then
  echo "ERRO: $SSH_DIR deve pertencer a $EXPECTED_USER." >&2
  exit 2
fi

if [[ ! -f "$AUTHORIZED_KEYS" || -L "$AUTHORIZED_KEYS" ]]; then
  echo "ERRO: authorized_keys ausente ou symlink." >&2
  exit 2
fi
if [[ "$(stat -c '%h' "$AUTHORIZED_KEYS")" != "1" ]]; then
  echo "ERRO: authorized_keys hard-linked; abortando." >&2
  exit 2
fi
if [[ "$(stat -c '%a' "$AUTHORIZED_KEYS")" != "600" ]]; then
  echo "ERRO: authorized_keys deve ter modo 600." >&2
  exit 2
fi
if [[ "$(stat -c '%U' "$AUTHORIZED_KEYS")" != "$EXPECTED_USER" ]]; then
  echo "ERRO: authorized_keys deve pertencer a $EXPECTED_USER." >&2
  exit 2
fi
if ! grep -Eq '^[[:space:]]*(ssh-ed25519|sk-ssh-ed25519@openssh.com|ecdsa-sha2-nistp(256|384|521)|sk-ecdsa-sha2-nistp256@openssh.com|ssh-rsa)[[:space:]]+' "$AUTHORIZED_KEYS"; then
  echo "ERRO: nenhuma chave pública reconhecida em authorized_keys." >&2
  exit 2
fi

sudo /usr/bin/install -d -o "$EXPECTED_USER" -g "$EXPECTED_GROUP" -m 0700 "$STATE_DIR"
sudo /usr/bin/install -d -o "$EXPECTED_USER" -g "$EXPECTED_GROUP" -m 0700 "$BACKUP_DIR"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup=""
mutated=false

rollback() {
  if [[ "$mutated" != true ]]; then
    return
  fi
  echo "Falha após mutação; restaurando configuração SSH anterior..." >&2
  if [[ -n "$backup" && -f "$backup" ]]; then
    sudo /usr/bin/install -o root -g root -m 0644 "$backup" "$DST"
  else
    sudo /usr/bin/rm -f "$DST"
  fi
  sudo /usr/sbin/sshd -t
  sudo /usr/bin/systemctl reload ssh.service 2>/dev/null     || sudo /usr/bin/systemctl reload sshd.service 2>/dev/null     || true
}
trap rollback ERR

if [[ -f "$DST" ]]; then
  backup="$BACKUP_DIR/99-zion-remote.$stamp.conf"
  sudo /usr/bin/install     -o "$EXPECTED_USER"     -g "$EXPECTED_GROUP"     -m 0600     "$DST"     "$backup"
fi

sudo /usr/bin/install -o root -g root -m 0644 "$SRC" "$DST"
mutated=true

sudo /usr/sbin/sshd -t

sudo /usr/bin/systemctl reload ssh.service 2>/dev/null   || sudo /usr/bin/systemctl reload sshd.service

if ! /usr/bin/systemctl is-active --quiet ssh.service 2>/dev/null   && ! /usr/bin/systemctl is-active --quiet sshd.service 2>/dev/null; then
  echo "ERRO: serviço SSH não está ativo após reload." >&2
  exit 1
fi

effective="$(sudo /usr/sbin/sshd -T)"
declare -a required=(
  "passwordauthentication no"
  "kbdinteractiveauthentication no"
  "permitrootlogin no"
  "pubkeyauthentication yes"
  "authenticationmethods publickey"
  "permitemptypasswords no"
  "allowagentforwarding no"
  "allowtcpforwarding no"
  "x11forwarding no"
  "gatewayports no"
  "permittunnel no"
  "permituserenvironment no"
)
for item in "${required[@]}"; do
  if ! grep -Fqx "$item" <<<"$effective"; then
    echo "ERRO: sshd efetivo não contém '$item'." >&2
    exit 1
  fi
done

trap - ERR
mutated=false

echo "SSH hardening aplicado e validado com sshd -t."
if [[ -r /etc/ssh/ssh_host_ed25519_key.pub ]]; then
  echo "Fingerprint do host para conferir no segundo cliente:"
  ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
fi
echo "MANTENHA ESTA SESSÃO ABERTA."
echo "Abra uma segunda sessão via Tailscale e valide public-key auth antes de encerrar a sessão atual."
echo "Firewall/roteador não foram alterados por este script."
