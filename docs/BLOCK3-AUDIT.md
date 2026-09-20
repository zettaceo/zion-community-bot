# Block 3 audit — reconciled

Authoritative base: `zion-v1.1-dev` at
`d4cda026e0b9099d18af73d73322d876b7dc8e57`.

Canonical review branch: `audit/block3-reconciled` (Draft PR #6).

This branch reconciles both parallel Block 3 audit lines:

- PR #4 / `zion-v1.1-block3-guardian`
- PR #5 / `audit/block3-guardian-telegram`

Neither source branch is authoritative by itself. The reconciled branch keeps the
current Block 2 merge base and ports only evidence-backed hardening from both
lines.

## Reconciled controls

- Community-only moderation stops at the private-chat boundary, while secret and
  credential protection remains universal.
- Positive cached Telegram admin privilege is revalidated before privileged
  chat-local commands; negative cache entries remain bounded anti-amplification
  protection.
- Runtime admin and rate-limit caches are TTL-pruned.
- Link handling uses IDNA2008/UTS46 non-transitional normalization, rejects
  invisible hostname obfuscation, records unsupported schemes separately, and
  fails closed on unparseable or excessive Telegram link entities.
- Hidden URLs from text links, captions, inline-keyboard URL buttons,
  `login_url`, and `web_app` participate in link and secret inspection.
- Percent-encoded hidden URL credentials are decoded for detection without
  persisting the raw credential.
- Unicode/NFKC-obfuscated credential labels, HTTP basic-auth credentials,
  labeled Base58/byte-array wallet keys, mnemonic-like material, and PEM/OpenSSH
  private-key blocks are covered by deterministic protection.
- Command secret protection executes before the persistent command
  idempotency claim. This keeps deletion retriable if the process crashes before
  the normal command pipeline, while functional command side effects remain
  at-most-once.
- Ordinary moderation updates and join-service updates have persistent
  idempotency keys, preventing duplicate punitive/onboarding side effects from
  Telegram redelivery.
- Flood deletion is limited to the triggering time window. Flood containment and
  the incident are persisted before Telegram enforcement; the external result is
  recorded afterward.
- Manual mute/ban/unban persist intent before the external Telegram call.
- Raid onboarding is batch-safe. Join persistence, raid counting, and the local
  ELEVATED transition are committed atomically before network notifications.
- Domain policy changes and other operator policy mutations keep audit records in
  the same SQLite transaction as the local mutation.
- Operator-facing user-controlled text is sanitized against control/newline/bidi
  display spoofing.
- A command privilege-matrix regression locks the intended public/admin/operator
  boundaries.

## Conflict resolutions

Two parallel implementations handled IDNA differently. The automated branch
rejected `faß.de` because Python's legacy built-in IDNA codec may collapse it to
`fass.de`. The reconciled branch instead uses the external `idna` package with
UTS46 and `transitional=False`, so `faß.de` becomes the distinct
`xn--fa-hia.de` and cannot alias an ASCII allowlist.

Unsupported or malformed clickable targets are represented in
`LinkDecision.unsupported_schemes` rather than as a synthetic domain string.
This keeps domain policy evidence separate from parser/scheme evidence while
remaining fail-closed.

The source PR #5 CI failure was not a product failure: its synthetic OpenSSH key
fixture contained a literal PEM begin marker and was correctly rejected by the
repository secret scanner. The fixture is now assembled at runtime; the scanner
itself was not weakened.

A post-reconciliation review found one additional crash-ordering gap: command
update IDs were claimed before universal secret deletion. A crash between those
steps could suppress Telegram redelivery while leaving a credential visible. The
secret preflight now runs before the durable claim; the regression test proves
the claim is not attempted for a secret-bearing command.

## Validation

The first fully reconciled candidate completed GitHub CI with:

- 262 tests
- failures=0
- errors=0
- secret scan: OK
- ZION validation: OK

Automated test-name comparison found no source-PR regressions missing from the
reconciled suite. Two old IDNA test names were intentionally replaced because the
non-transitional IDNA2008 implementation makes the old “reject sharp-s” behavior
obsolete while preserving the security invariant.

## Residual boundary

Telegram effects and SQLite commits are not a distributed transaction. No network
`await` is placed inside a SQLite transaction to pretend otherwise. Intent can
be persisted before an external effect and outcome can be recorded afterward,
but a crash in between remains an explicit unknown-outcome boundary.

Real Telegram verification is still required for supergroup permission semantics,
admin-role changes during cache TTL, actual media/entity/update shapes, concurrent
update delivery, and crash timing around external effects. Production, the Acer,
the live SQLite database, `.env`, systemd, network configuration, and deployment
are outside this GitHub-only Block 3 audit.
