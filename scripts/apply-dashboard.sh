#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/zetta/zion-community-bot"
SRC="$ROOT/systemd/zion-dashboard.service"
DST="/etc/systemd/system/zion-dashboard.service"

cd "$ROOT"
bash scripts/validate.sh

sudo /usr/bin/install   -o root   -g root   -m 0644   "$SRC"   "$DST"

sudo /usr/bin/systemctl daemon-reload
sudo /usr/bin/systemctl enable --now zion-dashboard.service

sudo /usr/bin/systemctl status   zion-dashboard.service   --no-pager   --full

echo
echo "Dashboard local: http://127.0.0.1:8765/"
