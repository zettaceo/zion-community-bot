#!/usr/bin/env bash
set -u

echo "ZION REMOTE ACCESS PREFLIGHT"
echo "============================"

echo
echo "[1] Tailscale"
if command -v tailscale >/dev/null 2>&1; then
  echo "tailscale: installed"
  tailscale ip -4 2>/dev/null | sed 's/^/tailscale_ipv4: /' || true
else
  echo "tailscale: NOT_INSTALLED"
fi

echo
echo "[2] OpenSSH server"
if command -v sshd >/dev/null 2>&1; then
  echo "sshd: installed"
  if command -v systemctl >/dev/null 2>&1; then
    systemctl is-active ssh.service 2>/dev/null || \
      systemctl is-active sshd.service 2>/dev/null || true
  fi
else
  echo "sshd: NOT_INSTALLED"
fi

echo
echo "[3] SSH permissions"
if [ -d "$HOME/.ssh" ]; then
  stat -c '%a %n' "$HOME/.ssh" 2>/dev/null || true
else
  echo "$HOME/.ssh: NOT_FOUND"
fi
if [ -f "$HOME/.ssh/authorized_keys" ]; then
  stat -c '%a %n' "$HOME/.ssh/authorized_keys" 2>/dev/null || true
else
  echo "authorized_keys: NOT_FOUND"
fi

echo
echo "[4] ZION service"
if command -v systemctl >/dev/null 2>&1; then
  systemctl show zion.service \
    -p ActiveState \
    -p SubState \
    -p MainPID \
    -p NRestarts 2>/dev/null || true
fi

echo
echo "No configuration was changed."
