#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/zetta/zion-community-bot"
PYTHON="$ROOT/.venv/bin/python"
BOT="$ROOT/bot.py"
SERVICE_SRC="$ROOT/systemd/zion.service"
SERVICE_DST="/etc/systemd/system/zion.service"

echo "[1/5] Validando sintaxe do ZION..."
"$PYTHON" -m py_compile "$BOT"

echo "[2/5] Instalando arquivo systemd autoritativo..."
sudo /usr/bin/install   -o root   -g root   -m 0644   "$SERVICE_SRC"   "$SERVICE_DST"

echo "[3/5] Recarregando systemd..."
sudo /usr/bin/systemctl daemon-reload

echo "[4/5] Habilitando e reiniciando ZION..."
sudo /usr/bin/systemctl enable zion.service >/dev/null
sudo /usr/bin/systemctl restart zion.service

echo "[5/5] Estado atual:"
sudo /usr/bin/systemctl status zion.service --no-pager --full
