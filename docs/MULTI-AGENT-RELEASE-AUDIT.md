# ZION Multi-Agent Command System - Release Audit

Date: 2026-10-16  
Scope: development candidate based on `zion-v1.1-dev`  
Status: development validation passed; integration, production, Acer, and live
Telegram acceptance remain evidence gates.

This report separates repository evidence from external state. It does not
claim that the candidate is deployed or that real secondary identities are
configured.

## Architecture

ZION owns the only group update intake, deterministic Guardian, speaker
arbitration, creator Control Center, and operator notification channel. MIMIR,
EIR, and FREYR have token-specific transports for authorized replies and their
own private-inbox policy. Secondary group polling discards group updates; they
never become parallel moderation or intake authorities.

The group path is:

```text
Telegram group update
  -> ZION deterministic secret/Guardian/link/flood policy
  -> deterministic intent routing
  -> bounded advisory intent fallback only when routing is ambiguous
  -> one durable final-speaker claim
  -> one token-specific send
  -> terminal sent / failed-safe / uncertain state
```

The model can return only an allowlisted conversational intent. It cannot
select moderation, tokens, arbitrary identities, or punitive actions.

## Agent and authority matrix

| Agent | Role | Group intent | DM | Moderation |
|---|---|---|---|---|
| ZION | CCO / Guardian / orchestrator | community, moderation | creator only | full deterministic |
| MIMIR | CTO | technical | closed | none |
| EIR | CXO / support | support | public | none |
| FREYR | CBO / partnerships | partnership | public | none |

Every speaking intent has one registry owner. Unrelated and ambiguous intents
have no speaker. Handoffs are invisible, occur before the external send, and
are bounded to one hop.

## Knowledge matrix

| Agent | Allowed scopes | Explicitly excluded |
|---|---|---|
| ZION | community public and approved shared public sources | controlled technical, internal, secret |
| MIMIR | technical public and controlled public projection | internal implementation, infrastructure, secret |
| EIR | support public and approved shared public sources | controlled technical/business, internal, secret |
| FREYR | business public, business controlled, approved shared public sources | controlled technical, internal, secret |

The manifest rejects missing, malformed, historical, superseded, excluded,
INTERNAL, and SECRET sources before model context is built. Source provenance
remains internal and public answers do not expose file, repository, path, or
commit details.

## Privacy and persistence

The protected identity store is outside Git and `.env`, with owner-only
directories/files, regular-file and single-link checks, atomic publication,
identity binding, duplicate-token rejection, and runtime log redaction.

SQLite schema changes are additive:

- schema 3: durable `speaker_claims` for one-speaker arbitration;
- schema 4: minimized `routing_events` for content-free telemetry.

Routing telemetry stores a hashed route key, bounded agent/intent/outcome
labels, handoff and fallback flags, status, and timestamps. It has no message,
prompt, contact, username, user ID, or chat ID column. FREYR lead content is not
persisted; only count/status audit metadata is stored. Terminal routing and
speaker rows are pruned on the existing idempotency-retention cadence.

Migration tests prove schema 2 to 4 compatibility and preservation of existing
data. The real Acer database still requires a verified backup and disposable
copy rehearsal before cutover.

## Workflows

EIR applies deterministic triage for question, usage problem, user error,
possible incident, possible bug, account issue, and human request. Sensitive
classes receive a human-review boundary in both group and DM. No support flow
asks for a seed phrase, private key, password, token, API secret, or 2FA code.

FREYR accepts only labelled, bounded qualification fields, requires
company/project plus contact plus proposal/objective/integration, and routes a
minimized summary to the creator through the primary ZION identity. Contract,
commercial, exclusivity, equity, commission, and binding-timing decisions stay
human. A group partnership response directs qualification to FREYR's private
inbox without requesting sensitive data publicly.

## Files changed from the reconciled development base

```text
ZION-MASTER-PLAN.md
docs/CHAT-HANDOFF.md
docs/DEPLOYMENT-MODEL.md
docs/MULTI-AGENT-ARCHITECTURE.md
docs/MULTI-AGENT-IMPLEMENTATION-PLAN.md
docs/MULTI-AGENT-RELEASE-AUDIT.md
docs/OPERATIONS.md
docs/POLICIES.md
docs/SECURITY.md
docs/apn/Z-SWAP-APN-SOURCE.md
docs/technical-paper/Z-SWAP-TECHNICAL-PAPER-SOURCE.md
knowledge/MANIFEST.md
knowledge/README.md
knowledge/z-swap-plans.md
knowledge/zswap-apn.md
knowledge/zswap-features.md
knowledge/zswap-status.md
knowledge/zswap-technical-public.md
tests/helpers.py
tests/test_agent_registry.py
tests/test_ai.py
tests/test_application.py
tests/test_block2_failures.py
tests/test_control_center.py
tests/test_conversation.py
tests/test_dm_policy.py
tests/test_guardian_surface.py
tests/test_health.py
tests/test_knowledge.py
tests/test_mistral_boundaries.py
tests/test_multi_agent_router.py
tests/test_multi_agent_transport.py
tests/test_speaker_arbitration.py
tests/test_telegram_identity_store.py
tests/test_transaction_atomicity.py
tests/test_v11.py
zion/agents.py
zion/ai_service.py
zion/config.py
zion/db.py
zion/dm_policy.py
zion/health.py
zion/knowledge.py
zion/mistral.py
zion/models.py
zion/multi_agent_transport.py
zion/router.py
zion/speaker.py
zion/telegram_app.py
zion/telegram_identity_store.py
```

No systemd unit, SSH, firewall, Tailscale, router, or dependency-lock change is
part of this candidate.

## Validation evidence

The final local development validation used the audited current release
runtime:

- Python: 3.12.3;
- locked distributions: 9;
- runtime compatibility: PASS;
- imports: PASS;
- focused routing/workflow/conversation matrix: 60/60 PASS;
- Guardian/moderation/security matrix: 163/163 PASS;
- persistence/release matrix: 104/104 PASS;
- complete suite: 714/714 PASS;
- shell checks: PASS;
- sensitive-file boundary: PASS;
- secret scan: OK;
- ZION validation: OK.

No test was removed or relaxed for this release.

## Adversarial security review

| Boundary | Evidence | Result |
|---|---|---|
| privilege escalation | immutable registry; only ZION owns moderation intent | PASS |
| secondary punitive authority | no moderation tools or authority in secondary profiles | PASS |
| token leakage | log, diagnostics, SQLite, backup, WAL/SHM, repository negative tests | PASS |
| knowledge leakage | manifest fail-closed classification and per-agent retrieval tests | PASS |
| prompt injection | direct, founder/admin, cross-agent, percent/base64 encoded cases | PASS |
| document exfiltration | full APN/Technical Paper reproduction is refused with summary offer | PASS |
| multi-speaker race | concurrent SQLite claims, duplicate/edit/callback/retry tests | PASS |
| DM bypass | creator-only/closed/public policy before retrieval/provider | PASS |
| callback authorization | operator, nonce, expiry, replay, malformed action tests | PASS |
| persistence minimization | no message/contact/user/chat fields in routing telemetry | PASS |
| transaction boundary | structural test proves no network await inside DB transaction | PASS |
| degraded delivery | failed-safe/uncertain paths do not create a second speaker or ghost context | PASS |
| Guardian regression | abuse, flood, link, secret, containment matrices remain green | PASS |

Repository findings discovered and resolved during the final pass:

1. synthetic Telegram test values looked like real credentials to the secret
   scanner; fixtures were kept synthetic while removing repository-literal
   secret-shaped strings, and the scan was rerun successfully;
2. a failed multi-agent send could populate local conversation memory as if it
   had been delivered; memory now advances only after confirmed delivery;
3. EIR's deterministic sensitive-case boundary covered DM but not group
   support; the same triage and human-review warning now applies to both.

Unresolved repository findings:

- CRITICAL: none;
- HIGH: none;
- MEDIUM: none;
- LOW: the existing SIGKILL process-lock test emits Python `ResourceWarning`
  notices for synthetic subprocess pipes while still closing the functional
  lock boundary and passing. It does not affect the production runtime or
  release result.

## Git, CI, release, and deployment identity

- reconciled development base:
  `c88c3dd8947fa32168feddaa88dbfb870a1eed64`;
- feature branch: `feature/zion-multi-agent-core`;
- audited implementation candidate SHA:
  `2dc52ee40179218d2115e680a14f22bcae65f4f9`;
- audit/report commit: documentation-only descendant of that candidate;
- integrated implementation `zion-v1.1-dev` SHA:
  `1e639f063497fd7528b58193610fa9dda181c2d0` (PR #59);
- development CI: ZION CI #1328, run `38981413006`, job
  `117242891135`, SUCCESS on the exact integrated implementation SHA;
- production `zion-v1` SHA: pending production PR;
- Acer deployed SHA/runtime: pending controlled cutover.

These fields must be updated from real GitHub and Acer evidence. A green local
suite is not a substitute for exact-SHA CI, release verification, or live
acceptance.

## Remaining gates

1. Open and merge a production PR into `zion-v1` only after all release gates.
2. Revalidate the exact production merge SHA and prepare its immutable runtime.
3. Rehearse schema 4 on a disposable verified copy of the Acer database.
4. Provision real secondary tokens locally on the Acer without chat/history
   exposure; validate identity while revealing only safe status.
5. Configure MIMIR, EIR, and FREYR with minimum Telegram privileges.
6. Execute the controlled cutover and all 17 live group/DM acceptance cases.
7. Prove service, database, stores, one-speaker behavior, Guardian authority,
    logs, and rollback readiness after deployment.

Until those gates are measured, production and live multi-agent acceptance are
PENDING rather than PASS.
