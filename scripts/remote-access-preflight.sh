#!/usr/bin/env bash
set -uo pipefail

REPORT_ONLY=false
if [[ "${1:-}" == "--report-only" ]]; then
  REPORT_ONLY=true
elif [[ -n "${1:-}" ]]; then
  echo "usage: $0 [--report-only]" >&2
  exit 64
fi

if [[ "$REPORT_ONLY" == true ]]; then
  EXPECTED_USER="${ZION_REMOTE_USER:-zetta}"
  SSH_DIR="${ZION_SSH_DIR:-$HOME/.ssh}"
  AUTHORIZED_KEYS="${ZION_AUTHORIZED_KEYS:-$SSH_DIR/authorized_keys}"
  SSHD_DROPIN="${ZION_SSHD_DROPIN:-/etc/ssh/sshd_config.d/00-zion-remote.conf}"
else
  EXPECTED_USER="zetta"
  SSH_DIR="/home/zetta/.ssh"
  AUTHORIZED_KEYS="/home/zetta/.ssh/authorized_keys"
  SSHD_DROPIN="/etc/ssh/sshd_config.d/00-zion-remote.conf"
fi

failures=0
warnings=0

pass() {
  printf 'PASS: %s\n' "$1"
}

warn() {
  warnings=$((warnings + 1))
  printf 'WARN: %s\n' "$1"
}

fail() {
  failures=$((failures + 1))
  printf 'FAIL: %s\n' "$1"
}

mode_of() {
  stat -c '%a' "$1" 2>/dev/null || printf 'unknown'
}

owner_of() {
  stat -c '%U' "$1" 2>/dev/null || printf 'unknown'
}

is_regular_single_link() {
  [[ -f "$1" && ! -L "$1" ]] || return 1
  [[ "$(stat -c '%h' "$1" 2>/dev/null || printf '0')" == "1" ]]
}

echo "ZION REMOTE ACCESS PREFLIGHT"
echo "============================"
echo "mode=$([[ "$REPORT_ONLY" == true ]] && echo report-only || echo strict)"
echo

echo "[1/7] Tailscale"
if ! command -v tailscale >/dev/null 2>&1; then
  fail "tailscale not installed"
else
  tailscale_ip="$(tailscale ip -4 2>/dev/null | head -n1 || true)"
  if [[ -z "$tailscale_ip" ]]; then
    fail "Tailscale has no active IPv4 address"
  elif python3 - "$tailscale_ip" <<'PY' >/dev/null 2>&1
import ipaddress
import sys
address = ipaddress.ip_address(sys.argv[1])
network = ipaddress.ip_network("100.64.0.0/10")
raise SystemExit(0 if address in network else 1)
PY
  then
    pass "Tailscale IPv4 is active in CGNAT range"
  else
    fail "reported Tailscale IPv4 is outside 100.64.0.0/10"
  fi

  if [[ -d /sys/class/net/tailscale0 ]]; then
    pass "tailscale0 interface present"
  else
    warn "tailscale0 interface not visible"
  fi
fi

client_ip=""
if [[ -n "${SSH_CONNECTION:-}" ]]; then
  client_ip="${SSH_CONNECTION%% *}"
elif [[ -n "${ZION_TAILSCALE_CLIENT_IP:-}" ]]; then
  client_ip="$ZION_TAILSCALE_CLIENT_IP"
fi

if [[ -n "$client_ip" ]]; then
  if python3 - "$client_ip" <<'PY' >/dev/null 2>&1
import ipaddress
import sys
address = ipaddress.ip_address(sys.argv[1])
v4 = ipaddress.ip_network("100.64.0.0/10")
v6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")
raise SystemExit(0 if address in v4 or address in v6 else 1)
PY
  then
    pass "SSH client context is a Tailscale address"
  else
    fail "SSH client context is outside Tailscale address space"
    client_ip=""
  fi
elif [[ "$REPORT_ONLY" == true ]]; then
  warn "no current Tailscale SSH client context available"
else
  fail "strict mode requires SSH_CONNECTION or ZION_TAILSCALE_CLIENT_IP"
fi

echo
echo "[2/7] OpenSSH server"
if ! command -v sshd >/dev/null 2>&1; then
  fail "sshd not installed"
else
  pass "sshd installed"

  if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-active --quiet ssh.service 2>/dev/null       || systemctl is-active --quiet sshd.service 2>/dev/null; then
      pass "SSH service active"
    else
      fail "SSH service not active"
    fi
  else
    warn "systemctl unavailable; SSH service state not verified"
  fi
fi

echo
echo "[3/7] SSH key directory"
if [[ ! -d "$SSH_DIR" || -L "$SSH_DIR" ]]; then
  fail "$SSH_DIR missing or symlinked"
else
  ssh_mode="$(mode_of "$SSH_DIR")"
  ssh_owner="$(owner_of "$SSH_DIR")"
  if [[ "$ssh_mode" == "700" ]]; then
    pass "$SSH_DIR mode=700"
  else
    fail "$SSH_DIR mode=$ssh_mode (expected 700)"
  fi
  if [[ "$ssh_owner" == "$EXPECTED_USER" ]]; then
    pass "$SSH_DIR owner=$EXPECTED_USER"
  else
    fail "$SSH_DIR owner=$ssh_owner (expected $EXPECTED_USER)"
  fi
fi

if ! is_regular_single_link "$AUTHORIZED_KEYS"; then
  fail "$AUTHORIZED_KEYS missing, symlinked or hard-linked"
else
  key_mode="$(mode_of "$AUTHORIZED_KEYS")"
  key_owner="$(owner_of "$AUTHORIZED_KEYS")"
  if [[ "$key_mode" == "600" ]]; then
    pass "authorized_keys mode=600"
  else
    fail "authorized_keys mode=$key_mode (expected 600)"
  fi
  if [[ "$key_owner" == "$EXPECTED_USER" ]]; then
    pass "authorized_keys owner=$EXPECTED_USER"
  else
    fail "authorized_keys owner=$key_owner (expected $EXPECTED_USER)"
  fi
  if grep -Eq '^[[:space:]]*(ssh-ed25519|sk-ssh-ed25519@openssh.com|ecdsa-sha2-nistp(256|384|521)|sk-ecdsa-sha2-nistp256@openssh.com|ssh-rsa)[[:space:]]+' "$AUTHORIZED_KEYS"; then
    pass "authorized_keys contains at least one public key"
  else
    fail "authorized_keys contains no recognized public key"
  fi
fi

echo
echo "[4/7] ZION sshd hardening"
if ! is_regular_single_link "$SSHD_DROPIN"; then
  fail "$SSHD_DROPIN missing, symlinked or hard-linked"
else
  dropin_mode="$(mode_of "$SSHD_DROPIN")"
  dropin_owner="$(owner_of "$SSHD_DROPIN")"
  [[ "$dropin_mode" == "644" ]] \
    && pass "ZION sshd drop-in mode=644" \
    || fail "ZION sshd drop-in mode=$dropin_mode (expected 644)"
  [[ "$dropin_owner" == "root" ]] \
    && pass "ZION sshd drop-in owner=root" \
    || fail "ZION sshd drop-in owner=$dropin_owner (expected root)"
fi

if command -v sshd >/dev/null 2>&1; then
  effective=""
  if [[ -n "$client_ip" && -n "${tailscale_ip:-}" ]]; then
    context="user=$EXPECTED_USER,host=zion-server,addr=$client_ip,laddr=$tailscale_ip,lport=22"
    effective="$(sshd -T -C "$context" 2>/dev/null || true)"
    if [[ -z "$effective" ]] && command -v sudo >/dev/null 2>&1; then
      effective="$(sudo -n "$(command -v sshd)" -T -C "$context" 2>/dev/null || true)"
    fi
  fi

  if [[ -z "$effective" ]]; then
    if [[ "$REPORT_ONLY" == true ]]; then
      warn "effective user/address-specific sshd configuration could not be proven"
    else
      fail "effective user/address-specific sshd configuration could not be proven; run sudo -v and retry"
    fi
  else
    declare -a required=(
      "passwordauthentication no"
      "kbdinteractiveauthentication no"
      "permitrootlogin no"
      "pubkeyauthentication yes"
      "authenticationmethods publickey"
      "permitemptypasswords no"
      "strictmodes yes"
      "allowtcpforwarding no"
      "allowstreamlocalforwarding no"
      "allowagentforwarding no"
      "x11forwarding no"
      "gatewayports no"
      "permittunnel no"
      "permituserenvironment no"
      "maxauthtries 3"
      "maxsessions 4"
      "logingracetime 30"
      "loglevel VERBOSE"
    )
    for item in "${required[@]}"; do
      if grep -Fqx "$item" <<<"$effective"; then
        pass "sshd $item"
      else
        fail "effective sshd missing: $item"
      fi
    done

    if grep -Eq "^authorizedkeysfile .*\.ssh/authorized_keys( |$)" <<<"$effective"; then
      pass "sshd AuthorizedKeysFile includes .ssh/authorized_keys"
    else
      fail "effective sshd AuthorizedKeysFile does not include .ssh/authorized_keys"
    fi

    if grep -Eq "^allowusers( .*)? $EXPECTED_USER( |$)|^allowusers $EXPECTED_USER$" <<<"$effective"; then
      pass "sshd AllowUsers includes $EXPECTED_USER"
    else
      fail "effective AllowUsers does not prove access for $EXPECTED_USER"
    fi
  fi
fi

echo
echo "[5/7] SSH host identity"
host_pub="/etc/ssh/ssh_host_ed25519_key.pub"
if [[ -r "$host_pub" ]] && command -v ssh-keygen >/dev/null 2>&1; then
  fingerprint="$(ssh-keygen -lf "$host_pub" 2>/dev/null | awk '{print $2}' || true)"
  if [[ -n "$fingerprint" ]]; then
    pass "ED25519 host fingerprint available for out-of-band verification: $fingerprint"
  else
    fail "could not calculate ED25519 host fingerprint"
  fi
else
  fail "ED25519 host public key/fingerprint unavailable"
fi

echo
echo "[6/7] Listening surface"
if command -v ss >/dev/null 2>&1; then
  listeners="$(ss -ltn 2>/dev/null | awk 'NR>1 {print $4}' | grep -E '(^|:)22$' || true)"
  if [[ -z "$listeners" ]]; then
    fail "no TCP/22 listener detected"
  else
    pass "TCP/22 listener detected"
    if grep -Eq '(^0\.0\.0\.0:22$|^\*:22$|^\[::\]:22$|^:::22$)' <<<"$listeners"; then
      warn "sshd listens on wildcard addresses; firewall/router policy must restrict exposure"
    fi
  fi
else
  warn "ss command unavailable; listener scope not verified"
fi

echo
echo "[7/7] Non-verifiable external controls"
warn "router/NAT TCP/22 forwarding cannot be proven from this host"
warn "Tailnet ACL/device-approval policy must be verified in Tailscale administration"
warn "a second independent SSH session must be tested before closing the bootstrap session"

echo
echo "Summary: failures=$failures warnings=$warnings"
echo "No configuration was changed."

if [[ "$REPORT_ONLY" == true ]]; then
  exit 0
fi

if (( failures > 0 )); then
  exit 2
fi

exit 0
