#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/zetta/zion-community-bot"

SCRIPT_SRC="$ROOT/scripts/wifi-guardian.sh"
SCRIPT_DST="/usr/local/sbin/zion-wifi-guardian"

SERVICE_SRC="$ROOT/systemd/zion-wifi-guardian.service"
SERVICE_DST="/etc/systemd/system/zion-wifi-guardian.service"

TIMER_SRC="$ROOT/systemd/zion-wifi-guardian.timer"
TIMER_DST="/etc/systemd/system/zion-wifi-guardian.timer"

echo "[1/6] Validando script do Wi-Fi Guardian..."
/usr/bin/bash -n "$SCRIPT_SRC"

echo "[2/6] Instalando script..."
sudo /usr/bin/install \
  -o root \
  -g root \
  -m 0755 \
  "$SCRIPT_SRC" \
  "$SCRIPT_DST"

echo "[3/6] Instalando unidades systemd..."
sudo /usr/bin/install \
  -o root \
  -g root \
  -m 0644 \
  "$SERVICE_SRC" \
  "$SERVICE_DST"

sudo /usr/bin/install \
  -o root \
  -g root \
  -m 0644 \
  "$TIMER_SRC" \
  "$TIMER_DST"

echo "[4/6] Recarregando systemd..."
sudo /usr/bin/systemctl daemon-reload

echo "[5/6] Habilitando timer e executando teste inicial..."
sudo /usr/bin/systemctl enable --now zion-wifi-guardian.timer >/dev/null
sudo /usr/bin/systemctl start zion-wifi-guardian.service

echo "[6/6] Estado atual:"
sudo /usr/bin/systemctl status zion-wifi-guardian.timer --no-pager --full
echo
sudo /usr/bin/systemctl show zion-wifi-guardian.service \
  -p Result \
  -p ExecMainStatus \
  -p ActiveState \
  -p SubState
echo
sudo /usr/bin/journalctl \
  -u zion-wifi-guardian.service \
  -n 10 \
  --no-pager
