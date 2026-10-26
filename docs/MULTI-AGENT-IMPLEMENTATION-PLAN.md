# Cognitive Architecture v2 — current execution checkpoint

Date: 2026-10-26. Status: IN PROGRESS, not production accepted.
This section supersedes older current-state labels below; the prior mission's
checklists remain historical evidence, not proof of v2 completion.

## Measured identity and environment

- main: `d5db6a1c4308243a0bbb8d811e2ac8f0af408a0e`; CI run 36140123319 SUCCESS.
- development: `57a10444422373271fbd602acc083199346b5031`; CI run 39163089575 SUCCESS.
- production: `472a4b3f0ce73a8635d400c0073701013c357b92`; CI run 39163164036 SUCCESS.
- Production is four history commits ahead of development, with identical tracked content.
- Working branch: `codex/multi-agent-cognitive-v2` at `/home/zetta/.codex/worktrees/zion-cognitive-v2`.
- The operator explicitly authorized an isolated worktree on the Acer after the
  mission's section 64 host restriction was raised. Production checkout is not
  a development directory.
- Read-only host check on 2026-10-26: service active/running, NRestarts 0;
  current runtime and production checkout resolve to the production SHA above.
  No restart/deploy in this increment.
- Open unrelated PR #11 remains untouched. Recent related merged PRs: #59–65.
- Rulesets and production protection endpoints returned HTTP 403 (account plan
  restriction). Governance is NOT PROVEN. Prior waivers are not silently renewed.
- Fresh local baseline: 724 tests PASS, SECRET SCAN OK, ZION VALIDATION OK.
  Log: `/tmp/zion-cognitive-v2-baseline.log`. This is base evidence, not v2 evidence.

## Existing architecture and gaps

One ZION group intake already selects bounded identities; registry, DM gates,
protected secondary identity store, durable speaker arbitration, minimized
routing telemetry, Control Center and agent-filtered Knowledge already exist.
Mistral-specific Settings/client/accounting remain the current provider path.
Kimi registration and bounded synthetic evaluations have been measured, but no
full comparative benchmark, production model choice or activation is claimed.

The user-reported endpoint-to-swap contamination was reproduced for five
explicit topic-switch variants. Existing follow-up heuristics accepted `E...`
before checking the new subject. The exact unprefixed swap question passed the
baseline fixture; the real Telegram failure is not claimed reproduced verbatim.

The Z-SWAP source repo is now `/home/zetta/swap-z-app`; fetched main is
`986ae759c1c76fe23967a8e61489d986b2bb9a51`. Its public source of truth and fee
implementation supersede the bot's old claim that Solana platform fees are
universally disabled. `tier/types.ts`, `founders-commercial-truth.ts`,
`chains.ts` and `founders-public/facts.ts` are unchanged from the prior snapshot.
This comparison does not prove deployment/runtime availability of all app features.

## Production authorization boundary — latest operator instruction

Prepare and finish the implementation and available validations first. Deliver
an evidence-backed final report for operator review. Production merge and deploy
require a NEW explicit approval after that report. Prior statements permitting
production work do not authorize bypassing this latest boundary. Until then,
work remains in the isolated development branch/draft PR.

## Revised delivery sequence authorized by operator

The earlier plan expected Kimi registration after publication through ZION DM.
The operator subsequently chose and completed hidden local terminal provisioning
on 2026-10-25. Metadata-only validation passed; the credential remains private
and Kimi is not active in Telegram. Release planning still distinguishes:

1. Infrastructure/conversation release with Mistral retained and protected Kimi
   registration present. It still needs ordinary code, CI, security, release and
   controlled cutover checks; this change of sequence does not waive those gates.
2. Synthetic/public A/B evaluation and account policy review. Bounded Kimi
   evaluations have exposed unresolved quality failures; registration is not
   provider acceptance. Kimi remains inactive until the independent gates pass.
3. Real Telegram acceptance, which cannot be inferred from unit tests or smoke.

Never label deferred Kimi benchmarks PASS or the entire v2 mission complete.

## v2 phase tracking (mission sections 63–73)

- [~] 00 Reconciliation: mandatory documents reviewed; remote identities/CI and
  fresh baseline measured. Older deployment labels need continued reconciliation.
- [~] 01 Threat model and architecture: preserve existing boundaries; extend for
  provider data handling, cost admission, context isolation and output validation.
- [~] 02 Registry/authority: expanded intents and existing deterministic authority implemented; final v2 acceptance pending.
- [~] 03 Telegram store: protected primary-token resolution and matching release
  preflight implemented; actual primary-token migration deferred to approved cutover.
- [~] 04 Bounded provider protocol and Kimi adapter implemented/tested; host-owned runtime selection and approval expiry implemented. No candidate is activated.
- [~] 05 Provider-aware protected store and private DM provisioner implemented;
  pending Kimi capture survives restart as interception-only metadata, with fresh
  authorization required for storage. The operator also provisioned a Kimi
  credential through hidden local terminal input; private registration does not
  activate the runtime provider.
- [~] 06 DM enforcement: identity/private-channel paths reviewed; deterministic denial-before-AI and
  v2 native delivery regressions retained. Real Telegram acceptance pending.
- [~] 07 Bounded reviewed aliases and confidence tiers implemented; wider evaluation pending.
- [~] 08 Expanded intents, stable DB delivery families and noisy-language handler regressions pass.
- [~] 09 Context isolation: first bounded topic-label increment implemented; six
  switch pairs, including five baseline failures, now pass. Structured user/issue
  state, fixed fragment slots, bounded whole-turn history and a 24-turn adversarial
  regression are implemented. Live acceptance remains pending.
- [~] 10 Speaker arbitration: v2 duplicate-intake test exercises native two-request generation and proves one external speaker with usage counted once. Live concurrency acceptance remains pending.
- [~] 11 Identity transport: official Bot API/FAQ rechecked 2026-10-25 and local transport boundary
  reviewed. Actual Telegram configuration/delivery acceptance remains pending.
- [~] 12 Control Center: private provider/model token usage, optional estimated currency accounting and credential-versus-activation views implemented. Currency caps are not imposed without a reviewed host policy.
- [~] 13 Knowledge classification: pre-generation classification/expiry/agent boundaries reviewed with DM
  policy: only the explicit MIMIR technical projection is CONTROLLED-accessible;
  raw paper excluded and alternate-provider/tool context PUBLIC-only. Broader live
  source certification remains pending.
- [~] 14 APN/paper: canonical APN and final 83-page controlled paper identified;
  all 83 pages visually classified in `technical-paper/Z-SWAP-83-PAGE-REVIEW.md`.
  Routing and portfolio contradictions reconciled against the exact application
  snapshot; broader live source certification remains pending. Raw controlled
  material is not indexed.
- [~] 15 Manifest/freshness: plans snapshot updated after current source/code check;
  schema-2 snapshot/expiry/supersession enforcement implemented. Existing sources
  explicitly remain snapshot_only; no fresh runtime verification is fabricated.
- [~] 16 PUBLIC knowledge registry now wired to native Mistral function transport: one validated batch, bounded outputs, no second tool round and no arbitrary operations. Kimi remains text-only.
- [~] 17 Host-owned model-selection policy implemented: complexity/evidence/scope and valid quality/privacy/pricing approvals required, plus configured currency admission. Candidate quality acceptance remains pending.
- [~] 18 Fixed response-mode planner integrated into shared provider prompt; live quality acceptance pending.
- [~] 19 ZION executive response policy implemented; live competitive quality still FAIL/PENDING.
- [~] 20 MIMIR mechanism/evidence policy implemented; live response acceptance still pending.
- [~] 21 EIR diagnosis/claim boundaries implemented; observed cost hallucination now guarded, live retest pending.
- [~] 22 FREYR objection planning and business retrieval corrected; live pricing-context retest pending.
- [~] 23 Structured handoff implemented: fixed labels, no generated transcript transfer, no authority grant and no other-user issue transfer. Existing one-hop delivery bound is preserved.
- [~] 24 Confidentiality: shared AIService output boundary tested across all four
  identities with 24 malicious/unsupported outputs, plus rejection-to-safe-answer
  recovery. Rejected content is absent from SQLite and usage remains accounted.
  This is deterministic simulated-provider evidence, not live model acceptance.
- [~] 25 Injection: preserve existing controls; expanded source/provider matrix pending.
- [~] 26 Deterministic output guard implemented; not a complete factuality or confidentiality proof.
- [~] 27 Mistral timeout/bounded 429 retry/circuit preserved; every HTTP attempt
  now has durable admission. Cross-provider fallback remains blocked by acceptance.
- [~] 28 Isolated monetary evaluation ledger and integrated runtime provider/model
  token reservations implemented. Optional runtime currency caps, dated prices, frozen-rate settlement and bounded model selection are implemented. Real candidate activation remains blocked by acceptance.
- [~] 29 Versioned 108-case synthetic dataset (18 categories), generation evaluator and human-review gate implemented.
- [!] 30 Live A/B benchmark: store, dated official prices, credential, bounded
  spend and synthetic/PUBLIC-only inputs supported small Mistral/Kimi trials.
  The full comparable benchmark, human review and provider decision remain open.
- [~] 31 Four versioned 12-turn generation scenarios and bounded actual-answer
  history implemented; stop on provider/guard/repetition failure, per-turn durable
  evidence and mandatory human review. Simulated-provider regression passes;
  the latest bounded K3 debate stopped at turn 1 on `missing_feature_status`;
  other scenarios and runtime routing/tools/Telegram acceptance remain pending.
  See `COGNITIVE-V2-CONVERSATION-EVALUATION.md`.
- [~] 32 Full regression: committed candidate `9926cc9` passed 893/893.
  The later local comparison-context refinement passed 895/895, SECRET SCAN OK
  and ZION VALIDATION OK (`zion-v2-comparison-local-validation.log`). It still
  needs an exact-SHA CI after commit. The baseline was 724/724.
- [~] 33 Documentation: this checkpoint and cognitive routing contract added.
- [~] 34 Draft PR #66 open against development. Exact-SHA CI passed at
  `9926cc959033b8d2d857fda077eab50779f55075` (run 40298660922).
  Subsequent commits need their own exact-SHA checks and final v2 release audit.
- [!] 35 Production promotion: requires NEW user approval after the final report,
  plus release/security gates. Kimi activation separately blocked.
- [ ] 36 Exact production SHA revalidation.
- [ ] 37 Controlled Acer cutover.
- [!] 38 Real Telegram acceptance: requires messages from a real human/test account;
  sending with a bot is not a substitute. New v2 behavior is not deployed.

## Tools, policy and source checkpoint — 2026-10-20

- Native Mistral tools, host-approved selection, optional monetary admission and
  structured handoff are implemented; see `COGNITIVE-V2-GENERATION-POLICY.md`.
- Baseline composition still supplies no candidate approvals, alternative adapters
  or monetary policy. Kimi registration does not create any of them. Promotion
  and actual model/cap activation require the separate acceptance gates.
- Final combined validation on 2026-10-21: 847 tests PASS, SECRET SCAN OK,
  ZION VALIDATION OK (`zion-v2-final-policy-validation.log`). Focused transport/
  policy/store suite: 27 PASS. An earlier 845-test run had one fixture error: the
  synthetic HTTP response omitted `content`, required by the new body-size guard.
  The fixture now supplies serialized content; the guard and assertions remain.
  The final run includes two additional response-bound/retry-accounting tests.
- Exact paper hash/page count reacquired, with fresh visual matrices 76–78 review.
  Corrected the CoW-as-quote-source conflation in all three affected knowledge
  sections using source `986ae759` and retained all classifications/qualifiers.
  Removed repo/SHA prose from the loaded public status chunk; provenance remains
  in manifest metadata. The subsequent 2026-10-21 review classified all 83 pages;
  see the page ledger for source conflicts and remaining runtime boundaries.
- Existing live failures remain open. No further paid calls were made merely to
  obtain green output. The generation-only evaluator is not acceptance for the
  new native tool path; controlled live tests still need to exercise that path.

## Private capture and shared output checkpoint — 2026-10-20

- Restart before the first Kimi candidate now preserves an interception-only
  latch. The candidate is deleted/refused, never validated or sent to AI; a fresh
  command is required to authorize storage. Explicit cancellation and switching
  to Mistral clear the latch durably. Failure to persist/read/clear it fails closed.
- Focused private provisioning: 34 tests PASS. Full suite at that source state:
  815 PASS, SECRET SCAN OK, ZION VALIDATION OK.
- Additional output matrix: six rejected output classes for each of four agents,
  with untrusted founder authorization in conversation context; eight sequential
  rejected/safe responses verify recovery without poisoning the circuit. Focused
  AI suite: 31 PASS. No network, live token or production state used.
- Evidence: `zion-v2-capture-restart-validation.log` under the persistent worktrees
  directory. Final combined regression: **817 tests PASS**, SECRET SCAN OK,
  ZION VALIDATION OK, in `zion-v2-capture-output-validation.log`.
- The earlier real Mistral quality failures remain open in
  `docs/COGNITIVE-V2-QUALITY-FINDINGS.md`. These controls do not certify factuality.

## Recovery checkpoint — 2026-10-19

The temporary worktree disappeared between turns. Both committed checkpoints
survived. Uncommitted source edits were recovered from recorded file-writing
commands into the persistent worktree above; no operational/provisioning commands
were replayed. Fresh full validation: **754/754 PASS**, SECRET SCAN OK,
ZION VALIDATION OK. Evidence outside repo:
`/home/zetta/.codex/worktrees/zion-cognitive-recovery-validation.log`.

The second increment includes ephemeral user/thread fragment slots, shared A/B
prompt construction, public-only candidate-provider context, and fail-closed
output handling. It does not constitute complete cognitive architecture v2.
No schema, production service, production checkout, token or release ref changed.
The former `/tmp` evidence files are historical references and may no longer exist.

The final PT-BR 83-page paper was initially reviewed at pages 2, 22, 77, 78;
all 83 pages were subsequently visually classified on 2026-10-21. It is CONTROLLED, not blanket public authority.
See the source inventory addendum; broad feature/runtime reconciliation remains
pending. Do not index the raw PDF or promote unverified features.

## Conversation hardening and smoke review — 2026-10-19

- Full regression after private provider panel, explicit risk-caveat handling,
  private-route filtering and long-context regression: 773/773 PASS; secret
  scan and normal validation OK. Evidence: `zion-v2-hardening-validation.log`
  under `/home/zetta/.codex/worktrees/`.
- A 24-turn topic-switch test initially hit the fixture's real four-requests/minute
  cap at turn five. The fixture now advances both wall/monotonic clocks by 31s;
  neither AI pacing nor Guardian thresholds were disabled. It passes including
  a final founder-identity claim requesting private endpoints/API key.
- Mistral smoke evidence `20261019T231516206919Z-ministral-8b-2512.jsonl`
  completed five generation cases, all marked REVIEW_REQUIRED automatically.
  Assistant review found an unsupported transaction-safety guarantee in v2-001.
  Therefore this is NOT accepted. A regression now rejects that exact expression
  while allowing explicit denials of such guarantees. The private response guard
  is still not a complete factuality proof. Cumulative estimated evaluation cost
  at that checkpoint: 2,942 micro-USD, not an invoice or account balance.
- Full regression after this safety-guarantee fix: 773/773 PASS, secret scan and
  validation OK (`zion-v2-smoke-finding-validation.log`).
- Kimi evaluation remains deferred by operator choice. The isolated stronger
  Mistral smoke returned HTTP 403 on the first case and stopped. It is NOT
  EXECUTED for quality; the reason for provider refusal is not independently
  known. Evidence: `20261019T231750801923Z-mistral-large-2512.jsonl` in the same
  private evaluation directory. Cumulative reserved-or-spent estimate is 10,090
  micro-USD; the rejected request reservation was retained, not claimed billed.
- Current full validation including stronger-candidate price accounting:
  **774/774 PASS**, SECRET SCAN OK, ZION VALIDATION OK. Evidence:
  `/home/zetta/.codex/worktrees/zion-v2-large-validation.log`.
  No production, configuration, key or runtime switch occurred.

## Executive quality checkpoint — 2026-10-20

- Competitive objection planning and role instructions implemented; the exact
  mission objection is now included alongside seven additional synthetic cases.
  Original 100 evaluation cases preserved. Selection supports bounded exact IDs.
- Initial four-case live round failed human/automated review. Retrieval and
  evaluator continuation issues were fixed, and observed unsupported output
  received regression guards. The exact retest stopped at the first case because
  an unapproved market-service reference was blocked. Remaining three cases were
  NOT EXECUTED in that retest, not PASS.
- Full local regression: 810 tests PASS, SECRET SCAN OK, ZION VALIDATION OK.
  Live quality is still FAILED/PENDING. See
  `docs/COGNITIVE-V2-QUALITY-FINDINGS.md` for evidence and limitations, and
  `docs/EXECUTIVE-ARGUMENTATION.md` for the response contract.
- Kimi remains unactivated. No production configuration, service or token changed.

## Runtime budgets and primary identity — 2026-10-20

- Every runtime Mistral HTTP attempt now reserves tokens durably before I/O,
  including retries and route/classification calls. Shared/provider/model caps
  use the existing daily token policy, without changing production configuration.
- Unknown results retain the reservation across timeout, cancellation and restart.
  Successful usage settles once; overrun/corruption fails closed. No prompts or
  identities are stored in this ledger; SQLite schema is unchanged.
- Private Control Center shows charged/reserved totals and reports unavailable
  accounting explicitly. This is not a currency invoice. No Kimi activation,
  model upgrade or automatic fallback occurred.
- Budget checkpoint: 801 tests PASS, SECRET SCAN OK, ZION VALIDATION OK.
  Evidence: `/home/zetta/.codex/worktrees/zion-v2-runtime-budget-final-validation.log`.
- Primary Telegram resolution now supports the protected store in both startup
  and release preflight. Unsafe storage blocks fallback; absent storage preserves
  legacy behavior until an approved migration. No real token was read/moved.
  Focused identity/application/config validation: 20 tests PASS.
- Details: `docs/PROVIDER-RUNTIME-BUDGET.md` and
  `docs/PRIMARY-TELEGRAM-IDENTITY.md`. Full combined validation: 805 tests
  PASS, SECRET SCAN OK, ZION VALIDATION OK. Evidence:
  `/home/zetta/.codex/worktrees/zion-v2-budget-identity-validation.log`.

## Knowledge freshness enforcement — 2026-10-20

- Manifest schema 2 carries source ID/title/type, snapshot date, authority,
  reciprocal supersession, freshness, expiry and notes. Schema 1 remains readable
  for legacy fixtures with the previous status semantics.
- DRAFT and UNVERIFIED are explicitly excluded; a CURRENT source cannot also be
  superseded. Unknown, conflicting, duplicate or cyclic links reject the manifest.
- Expiry is checked on every retrieval in UTC, including after the reload date.
  Existing approved projections are labelled snapshot_only, not freshly verified.
- Focused retrieval/freshness tests: 42 PASS. Full validation: 787 tests PASS,
  SECRET SCAN OK, ZION VALIDATION OK. Evidence:
  `/home/zetta/.codex/worktrees/zion-v2-freshness-validation.log`. This does not semantically reconcile contradictory claims in
  different current documents; those still require source review.

## Structured state and replay hardening — 2026-10-19

- Structured ephemeral summaries track only bounded topic/agent/entity labels,
  unverified open issue and objection state. Whole exchanges replace arbitrary
  character slicing. A different participant cannot inherit another user's issue.
- Monetary claims absent from approved context are rejected by currency/amount.
  This does not certify attribution to the correct plan or network.
- Full validation of these changes: 779 tests PASS, SECRET SCAN OK, ZION
  VALIDATION OK (`zion-structured-state-validation.log`).
- A regression reproduced Kimi capture re-entry after failed validation and a
  runtime restart: the capture handler returned without stopping dispatch.
  A minimized message-identity marker now blocks replays within the configured
  idempotency retention window. No candidate/hash is stored in that marker;
  schema unchanged. Metadata is persisted before deletion/provider validation
  so a crash does not discard the replay boundary. DB failures stop dispatch.
  Full regression: 782 tests PASS, SECRET SCAN OK, ZION VALIDATION OK;
  evidence: `/home/zetta/.codex/worktrees/zion-v2-replay-validation.log`.
  The focused restart regression passes. This is not a guarantee about arbitrary
  unsolicited keys or credentials first sent after an expired/lost capture arm.
- Production remains untouched and requires approval after the final report.

## Kimi private-chat provisioning — 2026-10-19

Operator-selected input channel: private ZION DM. Implemented explicit-operator
capture, delete-before-validation, bounded TTL, cancellation, metadata-only
status/audit, rollback on audit failure, and mutually exclusive Mistral capture.
No automatic provider activation. Full validation: **771/771 PASS**, SECRET SCAN
OK, ZION VALIDATION OK. Focused provisioning/application tests: 13 PASS.
Evidence: `/home/zetta/.codex/worktrees/zion-kimi-dm-validation.log`.
Production delivery is pending an approved release containing these handlers;
do not invite the operator to paste a credential into the running older bot.

## Tools/planner checkpoint — 2026-10-19

Fresh full validation after local knowledge operations, response planning,
contextual `cm` recovery and provider-output persistence regression:
**763/763 PASS**, SECRET SCAN OK, ZION VALIDATION OK.
Evidence: `/home/zetta/.codex/worktrees/zion-cognitive-tools-planner-validation.log`.
Focused tools/evaluation/language: 14 PASS. Planner/boundaries/acceptance: 18 PASS.
The service was independently read as active/running with NRestarts=0, still at
production `472a4b3f0ce73a8635d400c0073701013c357b92`; no cutover occurred.

## Live baseline smoke — 2026-10-19

A generation-only synthetic/public smoke on `ministral-8b-2512` stopped after
case `v2-031` returned `AUTOMATED_FAIL`, reason `absolute_safety`. Case `v2-001`
is `REVIEW_REQUIRED`, not accepted. The rejected answer was withheld from the
evidence by design, so the exact phrasing and potential guard false-positive
cannot be inferred from the retained record. No automatic retry or weakened
rule was used. Two provider calls; estimated cost 770 micro-USD (USD 0.00077).
Evidence:
`/home/zetta/.local/state/zion-community-bot/evaluations/cognitive-v2/20261019T161009625327Z-ministral-8b-2512.jsonl`.
No full benchmark or winner declaration. Remaining smoke cases were NOT EXECUTED.

## Increment evidence and limitations

- Focused: 84 tests PASS (`/tmp/zion-cognitive-v2-focused.log`).
- Baseline failure: `/tmp/zion-context-v2-before.log`, five failing switch variants.
- New code is a bounded lexical topic discriminator, NOT complete semantic routing.
- No DB/schema, Guardian, authority, dependencies, services or real secrets changed.
- First increment used no paid provider requests; see the subsequent smoke evidence above.
- First increment implementation commit: `1c0cff7ae5c318eb96c3d67a747e1c29eb9dc4b9`.
  Local full validation 727/727 PASS; no new remote CI or production acceptance yet.

---

# Historical implementation plan (v1 multi-agent mission)

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
- [x] P03.05 Prove tokens never enter logs, SQLite, diagnostics, backups, or repository files.
  - Evidence: protected-store values are redacted from logs and absent from
    safe status, health/diagnostics, SQLite dumps, verified backups, WAL/SHM,
    and tracked repository content; secret scan PASS.

### PHASE 4 - DM access policies

- [x] P04.01 Enforce ZION CREATOR_ONLY before AI/session/retrieval.
  - Evidence: the existing ZION private intake returns before session, retrieval,
    or provider access for every non-operator numeric ID.
- [x] P04.02 Enforce MIMIR CLOSED before AI/session/retrieval.
  - Evidence: the secondary private handler rejects MIMIR before content,
    idempotency, retrieval, or provider access; negative test PASS.
- [x] P04.03 Enable EIR PUBLIC support DM.
  - Evidence: private intake preserves the EIR identity through retrieval and
    provider prompt; duplicate update is suppressed.
- [x] P04.04 Enable FREYR PUBLIC business DM.
  - Evidence: private intake preserves the FREYR identity through retrieval and
    provider prompt; duplicate update is suppressed.
- [x] P04.05 Add operator, ordinary-user, replay, and loop-prevention tests.
  - Evidence: ZION creator boundary, MIMIR closed DM, EIR/FREYR public DM,
    duplicate update suppression, and secondary group discard tests PASS.

### PHASE 5 - Intent routing

- [x] P05.01 Implement MODERATION/COMMUNITY/TECHNICAL/SUPPORT/PARTNERSHIP/UNRELATED/AMBIGUOUS taxonomy.
  - Evidence: `zion/router.py` returns registry-backed decisions for the full taxonomy.
- [x] P05.02 Add deterministic high-confidence routing and bounded AI fallback.
  - Evidence: deterministic routing runs first; Mistral can return only an
    allowlisted benign intent, confidence below 0.80 fails closed, and
    moderation is impossible through the fallback interface.
- [x] P05.03 Preserve natural conversation and silence for irrelevant chatter.
  - Evidence: unrelated and addressed-but-ambiguous messages resolve to silence.
- [x] P05.04 Test mixed, ambiguous, injection, and adversarial intent.
  - Evidence: support/technical precedence, confidentiality, agent injection,
    ambiguity, moderation, and private-route cases PASS.

### PHASE 6 - Speaker arbitration

- [x] P06.01 Add durable, atomic speaker claim keyed by inbound message identity.
  - Evidence: schema v3 `speaker_claims` plus atomic `BEGIN IMMEDIATE` claim.
- [x] P06.02 Enforce zero-or-one external speaker and authorized handoff.
  - Evidence: registry authority, concurrent durable arbitration, token-specific
    external send, sent-state completion, and duplicate-update suppression PASS.
- [x] P06.03 Define retry, uncertain-send, callback, edit, replay, and expiration behavior.
  - Evidence: sent/uncertain states never replay; only `failed_safe` can retry;
    edits share the original key; callbacks use the update identity; stale claims
    are quarantined.
- [x] P06.04 Add concurrent connections/tasks and crash-boundary tests.
  - Evidence: two-connection race, stale crash recovery, replay, and error-state tests PASS.

### PHASE 7 - Telegram multi-identity transport

- [x] P07.01 Implement one group intake and bounded secondary-DM intake.
  - Evidence: ZION owns group intake; secondary applications discard non-private
    updates and apply each identity's DM policy before AI.
- [x] P07.02 Send through the selected identity without exposing its token.
  - Evidence: `MultiAgentTransport` selects the protected token-specific client;
    safe statuses and timeout/failure-state tests PASS.
- [!] P07.03 Restrict secondary identities to minimum Telegram privileges.
  - Evidence: code grants no moderation authority and ignores secondary group
    intake. Live BotFather/group privilege configuration requires the real bot
    identities and remains blocked until Phase 23 acceptance on the Acer.
- [x] P07.04 Add lifecycle, offset, callback, error, and shutdown tests.
  - Evidence: per-token polling startup, pending-update discard, callback/edit
    claim identity, group discard, safe/uncertain errors, and reverse lifecycle
    shutdown tests PASS.

### PHASE 8 - ZION admin Control Center

- [x] P08.01 Add creator-only inline main menu and required submenus.
  - Evidence: all required top-level areas and per-agent/routing detail views
    have authorized inline callbacks.
- [x] P08.02 Show agent status, policy, scope, health, activity, and routing telemetry.
  - Evidence: per-agent runtime/store/DM/scope/moderation/routed/sent/failure/
    last-success data and aggregate routing telemetry render without secrets.
- [x] P08.03 Require explicit confirmation for dangerous actions.
  - Evidence: LOCKDOWN requires a separate one-time confirmation session.
- [x] P08.04 Reject unauthorized, stale, replayed, and malformed callbacks.
  - Evidence: authorization, nonce expiry, action allowlist, and one-time
    confirmation tests PASS.
- [x] P08.05 Ensure no menu surface reveals secret values.
  - Evidence: menu renders safe status only; secret-value negative test PASS.

### PHASE 9 - Knowledge classification

- [x] P09.01 Add PUBLIC/CONTROLLED/INTERNAL/SECRET metadata and source identity.
- [x] P09.02 Filter by agent scope and context before model context is built.
- [x] P09.03 Add freshness/status/version and source-aware internal provenance.
- [x] P09.04 Fail closed on missing/invalid classification.
- [x] P09.05 Add per-agent retrieval and leakage tests.
  - Evidence: machine-readable manifest, agent-aware retrieval, current-status
    filter, invalid/unclassified fail-closed behavior, and INTERNAL/SECRET
    exclusion tests PASS.

### PHASE 10 - Knowledge reconciliation

- [x] P10.01 Locate and authenticate the current Technical Paper source.
  - Evidence: the named `technical-paper/01-PAGE-BY-PAGE-ROUTE.md` is absent
    from fetched Git history, local search and accessible Drive search. The
    current Drive master project, README and 67-section content plan dated
    2026-10-14 were authenticated and transcribed without inventing the absent
    route file.
- [x] P10.02 Locate the current 21-page APN PDF.
  - Evidence: final v2 PDF SHA-256 `f11814ff...a8b5c4d`, 21 pages, plus its
    matching authorized textual source and assembly QA.
- [x] P10.03 Visually and textually inspect all relevant pages of both current sources.
  - Evidence: all 21 APN pages visually reviewed; authorized 21-page text and
    all 67 Technical Paper plan sections reviewed.
- [x] P10.04 Distinguish the current APN from historical `docs/PITCH-DECK.md`.
  - Evidence: canonical APN source marks the old Solana/Colosseum deck
    HISTORICAL / EXCLUDED.
- [x] P10.05 Create `docs/apn/Z-SWAP-APN-SOURCE.md` from verified content only.
- [x] P10.06 Classify every APN and Technical Paper section.
  - Evidence: APN page groups and all 67 paper sections are classified;
    technical raw sources remain outside retrieval.
- [x] P10.07 Reconcile conflicts against current executable/public facts and record decisions.
  - Evidence: reconciliation used Z-SWAP `origin/main` `166fd5be...` and its
    public source of truth. Superseded Founder prices/supply/version-3 clause
    were removed; Autopilot is now IMPLEMENTED_DISABLED; Portfolio/Orders are
    PARTIAL.
- [x] P10.08 Create `knowledge/MANIFEST.md` with authority, status, version, and allowed agents.
- [x] P10.09 Test retrieval filters and cross-agent/injection leakage.
  - Evidence: APN projection is available to institutional roles; the
    CONTROLLED technical projection is retrievable by MIMIR and excluded from
    ZION. INTERNAL/SECRET/non-current sources still fail closed.

### PHASE 11 - MIMIR CTO

- [x] P11.01 Add grounded technical identity prompt and public technical scope.
- [x] P11.02 Reject internal implementation, security, infrastructure, and unpublished facts.
- [x] P11.03 Test depth, uncertainty, roadmap boundaries, and closed DM.
  - Evidence: reconciled public Technical Paper projections, identity,
    confidentiality, unknown-agent, completeness, status-boundary, uncertainty,
    and closed-DM tests PASS.

### PHASE 12 - EIR CXO

- [x] P12.01 Add support identity, support triage, and public DM flow.
- [x] P12.02 Prevent requests for seed, private key, password, API secret, token, or 2FA.
- [x] P12.03 Test question/problem/bug/account/human escalation classes.
  - Evidence: deterministic triage covers question, usage problem, user error,
    possible incident, possible bug, account, and human; sensitive classes
    require human review.

### PHASE 13 - FREYR CBO

- [x] P13.01 Add institutional/partnership identity and public DM flow.
- [x] P13.02 Add data-minimized partnership qualification and operator summary.
  - Evidence: only labelled fields are accepted; minimum required groups are
    enforced; the summary is delivered through the primary ZION bot.
- [x] P13.03 Define and test retention, privacy, and audit behavior if persistence is used.
  - Evidence: lead content is not persisted; audit stores only field/delivery
    counts and decision status; SQLite dump negative tests PASS.

### PHASE 14 - Cross-agent handoff

- [x] P14.01 Implement invisible, bounded rerouting before external response.
  - Evidence: one-hop handoff is computed before claim/send; the addressed
    identity emits no acknowledgement.
- [x] P14.02 Prove handoff preserves single-speaker and authority boundaries.
  - Evidence: the durable final-speaker claim and transport capture prove one
    authorized external identity.
- [x] P14.03 Test technical/support/business loops and ambiguity.
  - Evidence: EIR-to-MIMIR, FREYR-to-EIR, MIMIR-to-FREYR, multi-address
    ambiguity, and handoff_count<=1 tests PASS.

### PHASE 15 - Confidentiality and prompt-injection hardening

- [x] P15.01 Apply deterministic internal-information and credential boundary to every agent.
- [x] P15.02 Test founder/admin impersonation and system-prompt/source requests.
- [x] P15.03 Test cross-agent oracle and controlled/internal/secret exfiltration.
- [x] P15.04 Test document reproduction/copyright-safe behavior.
  - Evidence: whole APN/Technical Paper reproduction receives a bounded summary
    offer; the provider prompt independently prohibits whole-document output.

### PHASE 16 - Persistence, privacy, and retention

- [x] P16.01 Add the minimum schema required for durable arbitration/telemetry/leads.
  - Evidence: schema v4 adds content-free routing telemetry; no lead table is
    created because FREYR intentionally does not persist lead content.
- [x] P16.02 Add atomic migrations and pre-upgrade compatibility tests.
  - Evidence: schema 2 to 4 migration preserves prior data; v3 to v4 is
    additive; migration rollback and future-schema tests remain green.
- [x] P16.03 Minimize stored user content and define retention/pruning.
  - Evidence: claims and routing telemetry exclude message/contact/user/chat
    content; lead data is not stored; terminal rows have bounded housekeeping.
- [x] P16.04 Prove no transaction spans a network await.
  - Evidence: claim/complete are separate synchronous DB operations; transport is
    structurally outside the transaction boundary.

### PHASE 17 - Observability, health, and diagnostics

- [x] P17.01 Add per-identity status without secret values.
- [x] P17.02 Add routing, arbitration, silence, handoff, and failure telemetry.
  - Evidence: schema-v4 aggregates cover routed/sent/send failure, silence,
    ambiguity, handoff, denied DM, routing failure, and last success.
- [x] P17.03 Extend `/status`, `/health`, `/diagnostics`, `/aistatus`, dashboard, and menu coherently.
  - Evidence: status/health remain compatible; diagnostics, AI status, and the
    creator Control Center expose value-blind multi-agent state and routing.
- [x] P17.04 Add safe-log and degraded-state tests.
  - Evidence: protected-store log redaction, UNSAFE health, missing/disabled,
    duplicate-token, unavailable primary/secondary transport, failed-safe and
    uncertain delivery, no ghost conversation context, and safe recovery tests PASS.

### PHASE 18 - Adversarial test matrix

- [x] P18.01 Routing, mixed intent, unrelated chatter, and ambiguity.
- [x] P18.02 Concurrent messages, duplicate updates, edits, callbacks, retries, and uncertain sends.
- [x] P18.03 DM authority and non-operator access.
- [x] P18.04 Secret-store filesystem attacks and secret propagation.
- [x] P18.05 Knowledge/injection/cross-agent exfiltration.
- [x] P18.06 Guardian/flood/link/secret behavior through centralized intake.
  - Evidence: focused routing/workflow/conversation matrix 60/60 PASS;
    Guardian/moderation/security matrix 163/163 PASS; persistence/release matrix
    104/104 PASS; complete suite PASS.

### PHASE 19 - Full regression

- [x] P19.01 Run focused new tests.
- [x] P19.02 Run all Guardian/moderation/security/persistence tests.
- [x] P19.03 Run the complete suite with zero removed/weakened tests.
- [x] P19.04 Run secret scan and normal repository validation.
  - Evidence: audited Python 3.12 runtime, 9 locked packages, imports PASS,
    714/714 tests PASS, shell checks PASS, sensitive-file boundary PASS,
    `SECRET SCAN: OK`, `ZION VALIDATION: OK` on 2026-10-16.

### PHASE 20 - Documentation reconciliation

- [x] P20.01 Update architecture, policies, security, operations, configuration, and deployment docs.
  - Evidence: master plan, architecture, policy, security, operations, and
    deployment contracts describe the implemented boundaries.
- [x] P20.02 Document Telegram topology and provisioning procedure without token values.
  - Evidence: architecture/deployment docs define centralized intake, secondary
    privacy/minimum privilege, protected local provisioning, and value-blind verification.
- [x] P20.03 Update `docs/CHAT-HANDOFF.md`.
  - Evidence: dated development handoff records implementation and separates
    pending release/live gates.
- [x] P20.04 Reconcile plan evidence and remove stale claims.
  - Evidence: implementation statuses and evidence log reconciled after the
    714-test full validation; live-only gates remain explicitly blocked/pending.

### PHASE 21 - Development release audit

- [x] P21.01 Create `docs/MULTI-AGENT-RELEASE-AUDIT.md`.
  - Evidence: adversarial boundary, validation, migration, file, matrix, finding,
    and pending external-gate evidence is recorded without production claims.
- [x] P21.02 Verify clean tree, exact SHA, CI, migrations, runtime, rollback, and all evidence.
  - Evidence: implementation candidate
    `2dc52ee40179218d2115e680a14f22bcae65f4f9`, clean worktree, migration and
    rollback tests, 714-test local validation, and exact integrated SHA
    `1e639f063497fd7528b58193610fa9dda181c2d0` with ZION CI #1328 SUCCESS.
    Exact production runtime/rehearsal remains Phase 22 rather than dev evidence.
- [x] P21.03 Review the full diff for authority/security/knowledge regressions.
  - Evidence: full 49-file base-to-candidate delta reviewed; no unresolved
    CRITICAL/HIGH/MEDIUM repository finding; one non-runtime LOW warning recorded.
- [x] P21.04 Open PR to `zion-v1.1-dev`, obtain green CI/review, and merge.
  - Evidence: PR #59 merged as
    `1e639f063497fd7528b58193610fa9dda181c2d0`; PR CI run `38981339446`
    and integrated push CI #1328 run `38981413006` both SUCCESS.

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
| 2026-10-16 | Identity prompts, knowledge firewall, transport, DM, Control Center, and safe health focused suite | 112/112 PASS |
| 2026-10-16 | Full suite after third implementation increment | 678/678 PASS |
| 2026-10-16 | APN/Technical Paper source discovery, classification and public-truth reconciliation | complete; absent named route explicitly recorded |
| 2026-10-16 | Reconciled knowledge/Mistral focused suite | 45/45 PASS |
| 2026-10-16 | Full suite after fourth implementation increment | 682/682 PASS |
| 2026-10-16 | Bounded fallback, one-hop handoff, EIR/FREYR workflows, schema v4 telemetry and Control Center | focused 60/60 PASS; degraded/security/persistence matrices PASS |
| 2026-10-16 | Final development validation before release audit | runtime/imports/shell PASS; 714/714 tests; SECRET SCAN OK; ZION VALIDATION OK |
| 2026-10-16 | PR #59 and exact integrated development SHA `1e639f0634...` | PR CI and ZION CI #1328 SUCCESS |

## Final acceptance forward-fix — 2026-10-18

Production baseline: `24b069afc38099e464742bfa9e3cf0d03d4721b4`.
Development base: `3d053e87010a95ed239b0ce57e15fbaae7666fc0`.

- [x] Reproduce short swap and developer-interface routing gaps without history.
- [x] Recognize singular/plural swap, bridge, orders, routing, liquidity and
  developer vocabulary in both the admission gate and deterministic router.
- [x] Assert exactly one MIMIR delivery for all acceptance phrases through the
  ordinary-message handler; no command or prior conversation required.
- [x] Fail closed for interface discovery before retrieval/provider/history.
  No developer interface is explicitly approved in the current public corpus.
  MIMIR explains the boundary and asks for the intended use case. Publishing an
  interface later requires a reviewed public authority contract; this change
  does not infer approval from a URL or generic technical document.
- [x] Add provider-contract regressions against best-price guarantees, universal
  smart-contract execution claims, and categorical platform safety claims.
- [x] Full regression: 724/724 PASS; runtime/imports/shell PASS;
  SECRET SCAN OK; ZION VALIDATION OK. Focused routing/conversation: 64 PASS.
- [ ] Repeat both exact failed messages in a controlled Telegram acceptance
  environment; inspect actual MIMIR answers and one-speaker behavior.
- [ ] Only after both real cases pass, consider a separately approved promotion.

Quality tests assert the prompt contract; they do not certify every possible
provider-generated response. Live answer quality acceptance remains required.
The production service and release refs are not changed by this forward-fix.

## Visual source and long-conversation checkpoint — 2026-10-21

All 83 controlled paper pages are visually classified in the new ledger.
Generic swap descriptions now match the selected-source routing contract.
Portfolio unknown values / partial totals are reconciled against exact source
`986ae759`, not assumed from a PDF or claimed as new live production proof.
Knowledge/tool regressions: 48 PASS; source-only full validation: 849 PASS,
SECRET SCAN OK, ZION VALIDATION OK (`zion-v2-paper-validation.log`).

The subsequent multi-turn evaluation harness adds four 12-turn synthetic scenarios
and real prior-answer continuity with bounded history. Focused harness regression:
11 PASS (`zion-v2-conversations-tests.log`), using simulated providers only.
No paid calls, real provider acceptance, production changes or Kimi activation.
Final combined validation: 854 tests PASS, SECRET SCAN OK, ZION VALIDATION OK
(`zion-v2-source-conversations-validation.log`). Result and unchanged branch base
rechecked on 2026-10-25. Exact-SHA CI is recorded in the draft PR after commit.

## Boundary audit and native evaluation — 2026-10-25

See `COGNITIVE-V2-BOUNDARY-REVIEW.md`. The official Telegram contract and local
identity/DM/source/provider boundaries were reviewed without changing production.
Native Mistral evaluation now invokes the real bounded tool-generation path and
reserves estimated cost before each request; no implicit retry or double outer
reservation. Its synthetic tests do not certify real model quality or Telegram.

One bounded text-generation retest of the original four failing cases was made
after tightening commercial grounding and verifying only the baseline price.
v2-101 still failed `unapproved_market_service_claim`; the other three cases
were not executed. No blocked response was retained. The current baseline is
NOT quality-accepted; see the exact evidence and accounting in the findings doc.

Native smoke v2-001 completed one HTTP request, no tool call selected. Review
FAILED on an execution guarantee missed by the earlier output guard; a new
regression now blocks the exact claim and preserves explicit caveats. No real
second tool round or improved live answer is claimed. Both current live findings
remain acceptance blockers. Remote main/development/production identities were
rechecked on 2026-10-25 and match the measured hashes above.

Validation for this increment: native evaluation/transport harness 25 PASS;
identity/DM/transport/delivery suite 49 PASS; output guarantee/native suite
11 PASS. Final combined suite: 860 PASS, SECRET SCAN OK, ZION VALIDATION OK
(`zion-v2-native-review-final-validation.log`). These include the exact new
execution-guarantee regression; live outputs remain unaccepted.

## Kimi provisioning and bounded comparison — 2026-10-25

- [x] Operator provisioned a Kimi API credential through a hidden local prompt.
  Metadata-only authentication passed; the private directory/file modes are
  0700/0600. This did not activate a new runtime provider.
- [x] Reverify K2.6 and K3 prices against the official Kimi API pricing table;
  renew only those two candidate evaluation snapshots. Durable request/daily/
  total admission and no-automatic-retry remain in force.
- [x] Execute small synthetic PUBLIC generation cases for both models. The
  post-fix v2-101/v2-103 single-turn responses passed human factual review.
  See `COGNITIVE-V2-QUALITY-FINDINGS.md` for initial failures, exact evidence,
  token counts and separate model limitations.
- [x] Reject observed unsupported competitor and partnership-fee claims with
  deterministic regressions. The candidate delivery path gives a fixed,
  topic-specific safe reply after rejection without retaining the model text.
- [x] Final combined validation: 866 tests PASS, SECRET SCAN OK,
  ZION VALIDATION OK (`zion-v2-kimi-comparison-validation.log`).
- [ ] Multi-turn live quality acceptance: both K2.6 and K3 stopped at debate
  turn 3 on `unapproved_market_service_claim`; later turns and other scenarios
  were not executed. A K2.6 turn-2 unsupported comparison was separately
  rejected by human review. No model winner is certified.
- [ ] Real Telegram routing, one-speaker delivery and natural-answer acceptance
  on the candidate runtime; no Telegram message was sent by this evaluation.
- [ ] Model/cost/privacy decision and production approval. K2-series retirement
  is announced for the end of 2026; current production continues on Mistral.

## Bounded Kimi continuation — 2026-10-25

The exact debate turn 3 names a competitor absent from retrieved official
context. A prompt clarification keeps user-named brands out of the answer when
the source does not approve them; the brand guard remains unchanged.
One K2.6 retest still stopped at turn 3. One K3 retest passed automated checks
through turn 10 but stopped at turn 11 on `best_price_guarantee` with the
generated text withheld. Human review found unsupported competitor facts in
K3 turn 2 and a fee-information omission in turn 5. The latter traced to a
retrieval miss on “Vocês cobram mais?” and is now covered by exact-token fee
aliases and a regression. A narrow guard regression rejects the turn-2 claim.

The failed retests are documented in `COGNITIVE-V2-QUALITY-FINDINGS.md`.
No model winner, long-conversation PASS, Telegram acceptance, or production
approval is inferred. No more paid retries are scheduled merely to get green.
Final local validation for this increment: 868 tests PASS, SECRET SCAN OK,
ZION VALIDATION OK (`zion-v2-kimi-continuation-validation.log`).

The final bounded K3 follow-up again failed: automation stopped at debate
turn 10 (`safety_guarantee`, rejected text withheld), and human review rejected
an unsupported competitor comparison at turn 2 plus a three-of-four EVM fee
enumeration at turn 8. Turn 5 correctly used the recovered official fee policy.
The clause-scoped guarantee guard, narrow competitor regression and explicit
four-tier fee-list instruction are local forward-fixes without live PASS.
The isolated evaluation ledger stands at 996,139 micro-USD reserved/estimated.
Final post-fix local validation: 870 tests PASS, SECRET SCAN OK,
ZION VALIDATION OK (`zion-v2-kimi-final-validation.log`).

## Post-K3 deterministic quality hardening — 2026-10-25

- [x] Add clause-scoped tests for explicit safety denials and absolute safety
  promises, including a denial followed by an unsafe claim after “mas”.
- [x] Return a fixed, risk-qualified host reply after a rejected price or
  safety guarantee; do not retain the rejected model output.
- [x] Complete broad PUBLIC/CURRENT fee-plan retrieval with the missing
  same-source sibling section when all four authorized Free/Pro/Trader/Pilot
  sections are available. Keep exact-tier queries narrow and reserve capacity
  for the complete bundle; omit it when it cannot fit whole.
- [x] Reject an EVM or network-unspecified fee schedule naming at least three
  plans when it omits a tier or disagrees with the four percentages parsed from
  official titled context. Accept percentage-before-tier wording. Preserve
  one/two-plan comparisons and Solana-only explanations.
- [ ] Re-evaluate model output and the complete multi-turn conversation under
  a separately bounded acceptance run; deterministic regressions do not
  establish live quality or a model winner.
- [ ] Validate real Telegram routing, one-speaker delivery, source fidelity and
  natural answers on the candidate before any separately approved promotion.

Local isolated regression: 878 tests PASS, SECRET SCAN OK, ZION VALIDATION OK
(`zion-v2-post-kimi-local-validation.log`). Production remains unchanged.

## K3 acceptance follow-up — 2026-10-26 UTC

- [x] Run one bounded, live-provider, PUBLIC synthetic 12-turn debate after the
  four-tier retrieval fix. It stopped at turn 12 on `best_price_guarantee`;
  rejected text was withheld. Human review failed turn 5 (Solana fee scope)
  and flagged turn 7–8 snapshot facts presented as live proof.
- [x] Add narrow source-scope and freshness regressions, plus clause-scoped
  noun-denial tests for a reproducible price-guarantee guard false positive.
  Rechecking allowed historical responses locally now rejects turns 5/7/8.
- [x] Run one bounded K3 retest after the fixes. It stopped at turn 5 on
  `overbroad_solana_fee_scope`; the model output was withheld. No retry loop.
- [x] Carry PUBLIC/CURRENT Terminal Pro beta and Portfolio/Orders partial
  status as an atomic comparison evidence pair, and reject an answer that
  drops those qualifiers. Independent negative probes covered safe denials
  and Jupiter-only fee scoping without a paid provider retry.
- [x] Reconcile the ambiguous “other Solana pairs” sentence against the exact
  approved application snapshot; limit it to Jupiter and keep LI.FI's separate
  source path explicit. Preserve the published four-tier rates and snapshot
  classification.
- [x] Give a source-derived, host-owned Solana fee answer after this specific
  guard rejection only when the whole PUBLIC section is present; otherwise
  keep the conservative reply. This does not change the K3 evaluation FAIL.
- [ ] Obtain human-accepted multi-turn generation across all four scenarios;
  automated `REVIEW_REQUIRED` is not quality PASS. The qualifier fix has only
  deterministic retrieval/replay coverage, not a new K3 or Telegram PASS.
- [ ] Complete real Telegram candidate acceptance and independent provider/
  cost/privacy decision before proposing any production promotion.

Isolated full validation: 882 tests PASS, SECRET SCAN OK, ZION VALIDATION OK
(`zion-v2-k3-followup-validation.log`). The cumulative evaluation ledger is
1,638,178 micro-USD reserved/estimated, not a bill. Production is unchanged.

Final validation of the later comparison-status refinement: 888 tests PASS,
SECRET SCAN OK, ZION VALIDATION OK (`zion-v2-k3-final-validation.log`). The
multi-turn and Telegram gates remain open; no production promotion is implied.

Post-reconciliation isolated validation: 890 tests PASS, SECRET SCAN OK,
ZION VALIDATION OK (`zion-v2-solana-final-validation.log`). No new paid K3 run
or Telegram acceptance was performed at that checkpoint.

## Named-conversation retest checkpoint — 2026-10-26

- [x] Diagnose the failed named-conversation run without repeating a provider
  call: selection used conversation mode but execution used single-case mode.
  The attempt settled an estimated 40,680 micro-USD, then raised `KeyError`
  before writing a case row. Its empty evidence file provides no quality result.
- [x] Use one mode for both paths and add fake-provider regression of actual
  named live dispatch. Post-provider harness errors now write a minimized
  `HARNESS_FAIL` row and stop, with no response or exception text retained.
- [x] Run one bounded K3 debate retest. Turn 1 stopped at
  `AUTOMATED_FAIL / missing_feature_status`; rejected text was withheld. No
  later turn or other conversation executed. The evaluation ledger now totals
  1,713,681 micro-USD reserved/estimated, not a bill.
- [x] Add a delivery fallback that carries only beta/partial statuses present
  in the approved retrieved context. Independent review caught cross-section
  and negated-status false associations in the first local version; direct
  affirmative, same-section matching and negative regressions now cover them.
  The evaluation failure remains a failure; this is not Telegram proof.
- [ ] Obtain human-accepted multi-turn answers for all four scenarios, then
  test natural routing/delivery in the controlled Telegram group.
- [ ] Review provider reliability, latency, cost and privacy against explicit
  acceptance criteria before proposing any production activation or release.

Production remains unchanged. The candidate PR stays draft until the open
quality and real-channel gates are independently accepted. Final isolated
validation for this increment: 893 tests PASS, SECRET SCAN OK, ZION VALIDATION
OK (`zion-v2-final-reviewed-validation.log`).

## Broad comparison delivery alignment — 2026-10-26

- [x] Reconcile the evaluator's PUBLIC comparison evidence with normal ZION
  delivery for the exact failed debate question. The normal path now receives
  the same bounded PUBLIC status sections when the question is a broad product
  comparison, without widening agent authority or source classification.
- [x] Add a host-owned comparison reply that states the documented proposal and
  Terminal Pro beta / Portfolio and Orders partial status only when the
  positioning, feature map and direct status predicates are present. Missing
  evidence or a narrow/unrelated question keeps the conservative fallback.
- [x] Focused response/AI tests pass; full local validation: 895/895 tests,
  SECRET SCAN OK, ZION VALIDATION OK
  (`zion-v2-comparison-local-validation.log`). No paid model call was made.
- [ ] The last K3 debate is still FAIL at turn 1. Model quality, all remaining
  conversation turns, Telegram acceptance and production gates remain open.
