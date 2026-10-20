# Primary Telegram identity — prepared transition

The primary Application and its shared Runtime resolve ZION's token through the
existing `TelegramIdentityStore` before constructing transports. A configured
protected ZION identity takes precedence over legacy configuration. An unsafe,
symlinked or in-worktree identity store blocks startup instead of falling back.
Only an absent protected identity permits the legacy token during transition.
Settings representations omit the token value.

The configuration preflight in `apply-zion-v1.sh` and `predeploy-v11.sh` uses the
same resolver. A release can therefore run with the primary token present only
in the protected store, while `.env` still contains non-secret configuration.
Secondary identity deduplication sees the resolved primary token.

This change performs no migration. It does not read or provision real tokens in
development, edit `.env`, change Telegram identities or restart the service.
The real primary identity transition belongs to the separately approved release:
verify the intended ZION identity, provision it through the protected operator
workflow, then remove the legacy value only after exact identity verification
and rollback preparation. Never print a token or put it in a command argument,
report, ordinary backup or Git. Rollback must explicitly account for which token
source the previous runtime supports; do not silently remove its only source.

A successful local test proves resolution behavior, not live credential
validity or permission in the Telegram group.
