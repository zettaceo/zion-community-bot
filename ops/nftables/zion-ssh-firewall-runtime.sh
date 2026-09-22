#!/usr/bin/env bash
set -euo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

TABLE_FAMILY="inet"
TABLE_NAME="zion_ssh_guard"
RULESET="/etc/zion-community-bot/zion-ssh-private.nft"
NFT="/usr/sbin/nft"

if [[ ! -x "$NFT" ]]; then
  echo "ERRO: nft ausente em $NFT." >&2
  exit 2
fi

table_exists() {
  "$NFT" list table "$TABLE_FAMILY" "$TABLE_NAME" >/dev/null 2>&1
}

validate_loaded_table() {
  local rendered
  rendered="$("$NFT" list table "$TABLE_FAMILY" "$TABLE_NAME")"

  grep -Fq 'iifname "lo" tcp dport 22 accept' <<<"$rendered"     || return 1
  grep -Fq 'iifname "tailscale0" tcp dport 22 accept' <<<"$rendered"     || return 1
  grep -Eq 'tcp dport 22 counter packets [0-9]+ bytes [0-9]+ drop' <<<"$rendered"     || return 1
}

case "${1:-apply}" in
  apply)
    if [[ ! -f "$RULESET" || -L "$RULESET" ]]; then
      echo "ERRO: ruleset ZION ausente ou symlink." >&2
      exit 2
    fi

    if table_exists; then
      if validate_loaded_table; then
        exit 0
      fi
      echo "ERRO: tabela $TABLE_NAME já existe com conteúdo inesperado." >&2
      exit 2
    fi

    "$NFT" -f "$RULESET"
    if ! validate_loaded_table; then
      "$NFT" delete table "$TABLE_FAMILY" "$TABLE_NAME" >/dev/null 2>&1 || true
      echo "ERRO: tabela SSH ZION carregada com contrato inesperado." >&2
      exit 2
    fi
    ;;

  check)
    if ! table_exists || ! validate_loaded_table; then
      echo "ERRO: guard SSH ZION ausente ou divergente." >&2
      exit 2
    fi
    ;;

  remove)
    if table_exists; then
      "$NFT" delete table "$TABLE_FAMILY" "$TABLE_NAME"
    fi
    ;;

  *)
    echo "usage: $0 [apply|check|remove]" >&2
    exit 64
    ;;
esac
