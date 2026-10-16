# ZION Multi-Agent Command System - Implementation Plan

## Mission status

- Status: ACTIVE
- Development base: `origin/zion-v1.1-dev`
- Verified base SHA: `c88c3dd8947fa32168feddaa88dbfb870a1eed64`
- Work branch: `feature/zion-multi-agent-core`
- Production branch: `zion-v1` (no development is performed there)
- Baseline: 611/611 tests passed with the audited release runtime on 2026-10-15.

This document is the tracked execution authority for the multi-agent mission. An
item is DONE only when its implementation, relevant tests, documentation, and
validation evidence are complete.

Status markers:

- `[ ]` TODO
- `[~]` IN PROGRESS
- `[x]` DONE
- `[!]` BLOCKED

## Objective

Evolve the existing Telegram application into one coordinated ZION Multi-Agent
Core. ZION remains the only deterministic Guardian and orchestrator. MIMIR, EIR,
and FREYR receive bounded public speaking roles without moderation authority.
For every inbound message, the system produces either no conversational reply or
one reply from exactly one authorized identity.

## Reconciled repository state

| Ref | Verified SHA | State |
|---|---|---|
| `origin/main` | `d5db6a1c4308243a0bbb8d811e2ac8f0af408a0e` | CI #1322 SUCCESS |
| `origin/zion-v1` | `68e860c411ecf0e63305baa72c6ca66688d7832c` | CI #1326 SUCCESS; production line |
| `origin/zion-v1.1-dev` | `c88c3dd8947fa32168feddaa88dbfb870a1eed64` | CI #1325 SUCCESS; development authority |

`origin/zion-v1.1-dev` is an ancestor of `origin/zion-v1`. Their tracked content
is identical at reconciliation time; production contains one promotion commit.
The pre-existing local development branch was stale and is not used. The work
branch was created from the verified remote development SHA in an isolated
worktree.

## Preserved invariants

- Deterministic Guardian decisions remain outside Mistral.
- Only ZION has delete, strike, mute, ban, containment, and lockdown authority.
- Sensitive-content checks run before AI and before DM conversation handling.
- No network await occurs inside a SQLite transaction.
- Telegram delivery plus SQLite state is never described as exactly once.
- Secrets never enter Git, logs, SQLite, diagnostics, backups, prompts, or chat.
- SQLite/WAL integrity, process exclusivity, circuit breaker, token accounting,
  commit-pinned runtimes, rollback, and the existing host boundary remain intact.

## Target architecture

```text
Telegram updates
       |
       v
ZION Multi-Agent Core
       |
       +--> deterministic security and Guardian (ZION only)
       +--> DM access policy (before AI)
       +--> deterministic intent router, bounded AI fallback when needed
       +--> authority-filtered knowledge retrieval
       +--> durable speaker arbitration
       +--> one selected Telegram identity, or silence
```

The group has one intake authority. ZION receives and evaluates group updates.
MIMIR, EIR, and FREYR are outbound identities selected by the core; they do not
run competing group responders. Their private-update intake is isolated and
enforces the identity's DM policy before AI. A durable claim keyed by the source
chat and message/update identity is acquired before any external send. Retry and
uncertain-delivery handling fail closed against duplicate speakers.

## Initial identity and authority matrix

| Identity | Role | Group | DM | Moderation | Knowledge scope |
|---|---|---:|---|---|---|
| ZION | CCO / orchestrator | yes | creator only | full deterministic | community public |
| MIMIR | CTO | yes | closed | none | technical public/approved controlled |
| EIR | CXO / support | yes | public | none | support public |
| FREYR | CBO / partnerships | yes | public | none | business public/approved controlled |

## Decisions

1. Agent definitions are immutable registry data, not name-based conditionals.
2. Routing returns an intent and one candidate identity; arbitration owns the
   final speaking decision.
3. AI can help classify ambiguous benign intent, but cannot bypass authority,
   DM, knowledge, Guardian, or speaker policy.
4. Knowledge classification is enforced before context construction. Prompts are
   a second boundary, never the primary one.
5. Token storage extends the existing protected-store model with one explicitly
   bound token per identity and status-only diagnostics.
6. Public group intake remains centralized. This avoids four independent
   consumers racing on the same message.
7. Existing operational commands remain available. The creator-only inline
   Control Center becomes the preferred administrative surface.

## Principal risks

| Risk | Control / gate |
|---|---|
| Duplicate replies during races, retries, callbacks, or edits | durable speaker claim, deterministic message key, concurrent and crash-boundary tests |
| Secondary identity receives group updates and competes | centralized group intake, group handlers disabled for secondary identities, topology tests |
| DM policy checked after AI | policy gate before session, retrieval, or provider call; negative provider-call assertions |
| Cross-agent or prompt-injection exfiltration | pre-retrieval classification/scope filter, deterministic confidentiality filter, adversarial tests |
| Token disclosure or unsafe filesystem state | 0700/0600, owner/link checks, atomic writes, runtime redaction, no DB/log values |
| Schema migration harms live DB | additive migration, disposable rehearsal, rollback and preservation tests |
| Historical APN/pitch facts become current truth | source manifest, page-level reconciliation, conflict register, HISTORICAL/EXCLUDED state |
| Telegram API/privacy assumptions are wrong | verify official Bot API and library lifecycle before transport implementation |
| Unprotected GitHub branches weaken promotion governance | do not claim PROVEN; require explicit evidence or documented waiver at release gate |
| Real bot tokens unavailable during development | finish store/runtime with fakes; mark only real provisioning and live acceptance blocked |

## Phase checklist

### PHASE 0 - Repository reconciliation

- [x] P00.01 Fetch remote refs and record exact authoritative heads.
  - Evidence: table above; GitHub CI #1322/#1325/#1326.
- [x] P00.02 Reconcile development and production history/content.
  - Evidence: development is the direct ancestor of production; no tracked content delta.
- [x] P00.03 Create isolated worktree and work branch from remote development SHA.
  - Evidence: `feature/zion-multi-agent-core` at `c88c3dd...`.
- [x] P00.04 Run the unmodified baseline suite with the audited runtime.
  - Evidence: 611 tests, PASS, 2026-10-15.
- [x] P00.05 Read mandatory architecture, security, operations, deployment, release, configuration, and lock documents.
- [x] P00.06 Inspect the current Telegram, Guardian, AI, knowledge, DB, health, dashboard, logging, secret, model, config, and process-lock surfaces.

### PHASE 1 - Architecture and threat model

- [x] P01.01 Document centralized intake and multi-identity send topology.
  - Evidence: `docs/MULTI-AGENT-ARCHITECTURE.md`.
- [x] P01.02 Verify Telegram Bot API privacy, update, callback, reply, DM, and multi-token constraints from primary sources.
  - Evidence: official references recorded in the architecture document; runtime uses python-telegram-bot 22.8.
- [x] P01.03 Define trust boundaries, abuse cases, failure states, and least privilege.
  - Evidence: architecture threat table and least-privilege deployment section.
- [x] P01.04 Record delivery semantics and recovery policy without exactly-once claims.
  - Evidence: claim-before-send and UNCERTAIN state contract in the architecture document.
- [x] P01.05 Add architecture and threat-model tests or contract assertions.
  - Evidence: immutable registry, DM matrix, routing authority, claim-key, replay,
    edit, uncertainty, concurrency, migration, and privacy contracts are executable.

### PHASE 2 - Agent registry

- [x] P02.01 Add immutable identity, role, DM, authority, and knowledge-scope models.
  - Evidence: `zion/agents.py` immutable profiles and enums.
- [x] P02.02 Add registry validation for unique IDs/usernames and safe defaults.
  - Evidence: one owner per speaking intent; only ZION can moderate; silence intents have no speaker.
- [x] P02.03 Add complete registry unit tests.
  - Evidence: `tests/test_agent_registry.py`, 10 focused tests PASS.

### PHASE 3 - Secure multi-token identity store

- [x] P03.01 Implement identity-bound protected token storage outside Git.
  - Evidence: `zion/telegram_identity_store.py`; fixed state path is outside the worktree.
- [x] P03.02 Enforce owner, 0700/0600, regular file, no symlink/hardlink, atomic durability, and fail-closed reads.
  - Evidence: wrapper reuses the audited atomic `SecretStore`; focused filesystem tests PASS.
- [x] P03.03 Register loaded tokens with runtime log redaction.
  - Evidence: formatter test proves loaded token material becomes `[REDACTED]`.
- [x] P03.04 Expose CONFIGURED/MISSING/UNSAFE only.
  - Evidence: value-blind status matrix test PASS.
- [~] P03.05 Prove tokens never enter logs, SQLite, diagnostics, backups, or repository files.
  - Evidence so far: log/status tests PASS; runtime diagnostics, DB, backup, and repository-wide checks remain.

### PHASE 4 - DM access policies

- [x] P04.01 Enforce ZION CREATOR_ONLY before AI/session/retrieval.
  - Evidence: the existing ZION private intake returns before session, retrieval,
    or provider access for every non-operator numeric ID.
- [~] P04.02 Enforce MIMIR CLOSED before AI/session/retrieval.
  - Evidence: deterministic policy and negative unit tests PASS; secondary
    transport wiring remains.
- [~] P04.03 Enable EIR PUBLIC support DM.
  - Evidence: deterministic policy PASS; secondary transport wiring remains.
- [~] P04.04 Enable FREYR PUBLIC business DM.
  - Evidence: deterministic policy PASS; secondary transport wiring remains.
- [~] P04.05 Add operator, ordinary-user, replay, and loop-prevention tests.
  - Evidence: operator/ordinary-user policy and ZION pre-AI negative tests PASS;
    multi-identity transport replay/loop tests remain.

### PHASE 5 - Intent routing

- [x] P05.01 Implement MODERATION/COMMUNITY/TECHNICAL/SUPPORT/PARTNERSHIP/UNRELATED/AMBIGUOUS taxonomy.
  - Evidence: `zion/router.py` returns registry-backed decisions for the full taxonomy.
- [~] P05.02 Add deterministic high-confidence routing and bounded AI fallback.
  - Evidence: deterministic routing is complete; bounded fallback remains.
- [x] P05.03 Preserve natural conversation and silence for irrelevant chatter.
  - Evidence: unrelated and addressed-but-ambiguous messages resolve to silence.
- [x] P05.04 Test mixed, ambiguous, injection, and adversarial intent.
  - Evidence: support/technical precedence, confidentiality, agent injection,
    ambiguity, moderation, and private-route cases PASS.

### PHASE 6 - Speaker arbitration

- [x] P06.01 Add durable, atomic speaker claim keyed by inbound message identity.
  - Evidence: schema v3 `speaker_claims` plus atomic `BEGIN IMMEDIATE` claim.
- [~] P06.02 Enforce zero-or-one external speaker and authorized handoff.
  - Evidence: registry authority and concurrent durable arbitration PASS; external
    Telegram send integration remains.
- [x] P06.03 Define retry, uncertain-send, callback, edit, replay, and expiration behavior.
  - Evidence: sent/uncertain states never replay; only `failed_safe` can retry;
    edits share the original key; callbacks use the update identity; stale claims
    are quarantined.
- [x] P06.04 Add concurrent connections/tasks and crash-boundary tests.
  - Evidence: two-connection race, stale crash recovery, replay, and error-state tests PASS.

### PHASE 7 - Telegram multi-identity transport

- [ ] P07.01 Implement one group intake and bounded secondary-DM intake.
- [ ] P07.02 Send through the selected identity without exposing its token.
- [ ] P07.03 Restrict secondary identities to minimum Telegram privileges.
- [ ] P07.04 Add lifecycle, offset, callback, error, and shutdown tests.

### PHASE 8 - ZION admin Control Center

- [ ] P08.01 Add creator-only inline main menu and required submenus.
- [ ] P08.02 Show agent status, policy, scope, health, activity, and routing telemetry.
- [ ] P08.03 Require explicit confirmation for dangerous actions.
- [ ] P08.04 Reject unauthorized, stale, replayed, and malformed callbacks.
- [ ] P08.05 Ensure no menu surface reveals secret values.

### PHASE 9 - Knowledge classification

- [ ] P09.01 Add PUBLIC/CONTROLLED/INTERNAL/SECRET metadata and source identity.
- [ ] P09.02 Filter by agent scope and context before model context is built.
- [ ] P09.03 Add freshness/status/version and source-aware internal provenance.
- [ ] P09.04 Fail closed on missing/invalid classification.
- [ ] P09.05 Add per-agent retrieval and leakage tests.

### PHASE 10 - Knowledge reconciliation

- [~] P10.01 Locate and authenticate the current Technical Paper source.
  - Evidence: a six-page prototype PDF was found locally; the specified 83-page route source still requires authoritative location/reconciliation.
- [x] P10.02 Locate the current 21-page APN PDF.
  - Evidence: `/home/zetta/Documentos/Z-SWAP-Apresentacao-21-Slides.pdf`, 21 pages.
- [ ] P10.03 Visually and textually inspect all relevant pages of both current sources.
- [ ] P10.04 Distinguish the current APN from historical `docs/PITCH-DECK.md`.
- [ ] P10.05 Create `docs/apn/Z-SWAP-APN-SOURCE.md` from verified content only.
- [ ] P10.06 Classify every APN and Technical Paper section.
- [ ] P10.07 Reconcile conflicts against current executable/public facts and record decisions.
- [ ] P10.08 Create `knowledge/MANIFEST.md` with authority, status, version, and allowed agents.
- [ ] P10.09 Test retrieval filters and cross-agent/injection leakage.

### PHASE 11 - MIMIR CTO

- [ ] P11.01 Add grounded technical identity prompt and public technical scope.
- [ ] P11.02 Reject internal implementation, security, infrastructure, and unpublished facts.
- [ ] P11.03 Test depth, uncertainty, roadmap boundaries, and closed DM.

### PHASE 12 - EIR CXO

- [ ] P12.01 Add support identity, support triage, and public DM flow.
- [ ] P12.02 Prevent requests for seed, private key, password, API secret, token, or 2FA.
- [ ] P12.03 Test question/problem/bug/account/human escalation classes.

### PHASE 13 - FREYR CBO

- [ ] P13.01 Add institutional/partnership identity and public DM flow.
- [ ] P13.02 Add data-minimized partnership qualification and operator summary.
- [ ] P13.03 Define and test retention, privacy, and audit behavior if persistence is used.

### PHASE 14 - Cross-agent handoff

- [ ] P14.01 Implement invisible, bounded rerouting before external response.
- [ ] P14.02 Prove handoff preserves single-speaker and authority boundaries.
- [ ] P14.03 Test technical/support/business loops and ambiguity.

### PHASE 15 - Confidentiality and prompt-injection hardening

- [ ] P15.01 Apply deterministic internal-information and credential boundary to every agent.
- [ ] P15.02 Test founder/admin impersonation and system-prompt/source requests.
- [ ] P15.03 Test cross-agent oracle and controlled/internal/secret exfiltration.
- [ ] P15.04 Test document reproduction/copyright-safe behavior.

### PHASE 16 - Persistence, privacy, and retention

- [~] P16.01 Add the minimum schema required for durable arbitration/telemetry/leads.
  - Evidence: durable arbitration schema is complete; later telemetry/lead needs
    remain subject to data-minimization review.
- [x] P16.02 Add atomic migrations and pre-upgrade compatibility tests.
  - Evidence: schema 2 to 3 migration preserves prior data and rolls back on failure.
- [x] P16.03 Minimize stored user content and define retention/pruning.
  - Evidence: claims contain identifiers/status metadata only, never message text;
    terminal rows have bounded pruning.
- [x] P16.04 Prove no transaction spans a network await.
  - Evidence: claim/complete are separate synchronous DB operations; transport is
    structurally outside the transaction boundary.

### PHASE 17 - Observability, health, and diagnostics

- [ ] P17.01 Add per-identity status without secret values.
- [ ] P17.02 Add routing, arbitration, silence, handoff, and failure telemetry.
- [ ] P17.03 Extend `/status`, `/health`, `/diagnostics`, `/aistatus`, dashboard, and menu coherently.
- [ ] P17.04 Add safe-log and degraded-state tests.

### PHASE 18 - Adversarial test matrix

- [ ] P18.01 Routing, mixed intent, unrelated chatter, and ambiguity.
- [ ] P18.02 Concurrent messages, duplicate updates, edits, callbacks, retries, and uncertain sends.
- [ ] P18.03 DM authority and non-operator access.
- [ ] P18.04 Secret-store filesystem attacks and secret propagation.
- [ ] P18.05 Knowledge/injection/cross-agent exfiltration.
- [ ] P18.06 Guardian/flood/link/secret behavior through centralized intake.

### PHASE 19 - Full regression

- [ ] P19.01 Run focused new tests.
- [ ] P19.02 Run all Guardian/moderation/security/persistence tests.
- [ ] P19.03 Run the complete suite with zero removed/weakened tests.
- [ ] P19.04 Run secret scan and normal repository validation.

### PHASE 20 - Documentation reconciliation

- [ ] P20.01 Update architecture, policies, security, operations, configuration, and deployment docs.
- [ ] P20.02 Document Telegram topology and provisioning procedure without token values.
- [ ] P20.03 Update `docs/CHAT-HANDOFF.md`.
- [ ] P20.04 Reconcile plan evidence and remove stale claims.

### PHASE 21 - Development release audit

- [ ] P21.01 Create `docs/MULTI-AGENT-RELEASE-AUDIT.md`.
- [ ] P21.02 Verify clean tree, exact SHA, CI, migrations, runtime, rollback, and all evidence.
- [ ] P21.03 Review the full diff for authority/security/knowledge regressions.
- [ ] P21.04 Open PR to `zion-v1.1-dev`, obtain green CI/review, and merge.

### PHASE 22 - Production promotion

- [ ] P22.01 Open production PR from audited development to `zion-v1`.
- [ ] P22.02 Verify the exact production merge SHA and rerun release verification.
- [ ] P22.03 Prepare exact runtime, disposable DB rehearsal, preflight, and rollback evidence.
- [ ] P22.04 Stop on any failed gate; never deploy a dev/arbitrary SHA.

### PHASE 23 - Acer deployment and acceptance

- [ ] P23.01 Provision real secondary tokens locally into the completed protected store.
- [ ] P23.02 Validate bot identities without logging tokens and add bots with minimum privilege.
- [ ] P23.03 Execute controlled cutover and verify host/service/DB/store/runtime state.
- [ ] P23.04 Execute all 17 group/DM acceptance cases.
- [ ] P23.05 Prove one message has at most one speaker and Guardian remains authoritative.
- [ ] P23.06 Verify rollback readiness and complete final audit evidence.

## Immediate implementation sequence

1. Finish Phase 1 using official Telegram behavior and a repository threat model.
2. Implement the formal agent registry (Phase 2) as the first code change.
3. Implement the identity token store and its filesystem/redaction test matrix.
4. Add DM policy and durable arbitration before enabling multi-token transport.
5. Add routing/knowledge/agents, then Control Center and observability.
6. Reconcile APN/Technical Paper independently of runtime work; never index an
   unclassified source.
7. Only after all development gates, use PR-based promotion and exact-SHA deploy.

## Evidence log

| Date | Evidence | Result |
|---|---|---|
| 2026-10-15 | Remote refs and ancestry/content comparison | reconciled |
| 2026-10-15 | GitHub runs #1322, #1325, #1326 | SUCCESS |
| 2026-10-15 | Audited-runtime full baseline | 611/611 PASS |
| 2026-10-15 | APN `pdfinfo` | 21 pages |
| 2026-10-15 | Technical prototype `pdfinfo` | 6 pages; not accepted as the described 83-page route source |
| 2026-10-15 | Registry and protected identity-store focused tests | 20/20 PASS |
| 2026-10-15 | Full suite after first implementation increment | 631/631 PASS |
| 2026-10-15 | DM, deterministic routing, durable arbitration, and schema v3 tests | focused PASS |
| 2026-10-15 | Full suite after second implementation increment | 656/656 PASS |
