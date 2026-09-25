#!/usr/bin/env bash
set -euo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

github_proven="${ZION_GITHUB_GATES_PROVEN:-}"
github_waived="${ZION_GITHUB_GATES_WAIVED:-}"
remote_proven="${ZION_REMOTE_NETWORK_PROVEN:-}"
remote_waived="${ZION_REMOTE_NETWORK_WAIVED:-}"
initial_waiver="${ZION_INITIAL_GO_LIVE_WAIVER:-}"
waiver_reason="${ZION_EXTERNAL_WAIVER_REASON:-}"

fail() {
  printf 'ERRO: %s\n' "$1" >&2
  exit 2
}

validate_pair() {
  local gate="$1"
  local proven="$2"
  local waived="$3"

  if [[ "$proven" == "YES" && "$waived" == "YES" ]]; then
    fail "$gate não pode estar simultaneamente PROVEN e WAIVED."
  fi

  if [[ "$proven" != "YES" && "$waived" != "YES" ]]; then
    fail "$gate exige PROVEN=YES ou WAIVED=YES."
  fi
}

validate_pair "GitHub governance" "$github_proven" "$github_waived"
validate_pair "Remote network control-plane" "$remote_proven" "$remote_waived"

waiver_used=false
if [[ "$github_waived" == "YES" || "$remote_waived" == "YES" ]]; then
  waiver_used=true
fi

if [[ "$waiver_used" == true ]]; then
  if [[ "$initial_waiver" != "YES" ]]; then
    fail "waiver externo exige ZION_INITIAL_GO_LIVE_WAIVER=YES."
  fi
  if [[ -z "$waiver_reason" ]]; then
    fail "waiver externo exige ZION_EXTERNAL_WAIVER_REASON não vazio."
  fi
  if [[ "$waiver_reason" == *$'\n'* || "$waiver_reason" == *$'\r'* ]]; then
    fail "ZION_EXTERNAL_WAIVER_REASON deve ser uma única linha."
  fi
  if (( ${#waiver_reason} > 160 )); then
    fail "ZION_EXTERNAL_WAIVER_REASON excede 160 caracteres."
  fi
else
  if [[ -n "$github_waived" || -n "$remote_waived" || -n "$initial_waiver" || -n "$waiver_reason" ]]; then
    fail "variáveis de waiver devem permanecer vazias quando todos os gates são PROVEN."
  fi
fi

if [[ "$github_proven" == "YES" ]]; then
  echo "github_governance=PROVEN"
else
  echo "github_governance=WAIVED"
fi

if [[ "$remote_proven" == "YES" ]]; then
  echo "remote_network=PROVEN"
else
  echo "remote_network=WAIVED"
fi

if [[ "$waiver_used" == true ]]; then
  echo "external_waiver=ACTIVE"
  echo "external_waiver_reason_present=YES"
else
  echo "external_waiver=NONE"
fi
