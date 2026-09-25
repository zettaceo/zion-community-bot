#!/usr/bin/env bash
set -euo pipefail

echo "ERRO: scripts/apply-systemd.sh é legado e está desabilitado no release v1.1." >&2
echo "Use o fluxo controlado por SHA em docs/DEPLOYMENT-MODEL.md e scripts/apply-zion-v1.sh." >&2
exit 64
