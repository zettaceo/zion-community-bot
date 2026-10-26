## Current cognitive-v2 handoff — 2026-10-26

The active isolated candidate is `codex/multi-agent-cognitive-v2` in
`/home/zetta/.codex/worktrees/zion-cognitive-v2`. Its last committed HEAD before
this handoff update is `9926cc959033b8d2d857fda077eab50779f55075`;
exact-SHA CI run `40298660922` succeeded. The newer local comparison-context
refinement passed 895 tests, `SECRET SCAN: OK` and `ZION VALIDATION: OK`, but
requires its own commit and exact-SHA CI. Draft PR #66 targets `zion-v1.1-dev`.

The operator privately provisioned Kimi through a hidden local terminal prompt.
Registration passed metadata-only validation, but Kimi remains inactive in
Telegram. Bounded synthetic/PUBLIC provider trials have **not** established a
winner: the latest K3 12-turn debate stopped at turn 1 on
`missing_feature_status`; later turns and three other scenarios were not run.
The delivery fallback is local deterministic containment, not model-quality
acceptance. The details, costs and earlier human findings are in
`COGNITIVE-V2-QUALITY-FINDINGS.md`.

Production checkout/runtime remain at
`472a4b3f0ce73a8635d400c0073701013c357b92`; a read-only check on
2026-10-26 found `zion.service` active/running, NRestarts 0. The current
candidate has not been promoted. An independent v2 release audit, provider
quality/privacy decision, new production approval, pinned cutover and real
Telegram acceptance are still required. See the top of
`MULTI-AGENT-IMPLEMENTATION-PLAN.md` for the active phase status. Older entries
below are historical checkpoints, not current acceptance.

## Historical implementation evidence — 2026-10-19

774/774 tests PASS, SECRET SCAN OK, ZION VALIDATION OK. Added private provider
panel, 24-turn context regression, safety-guarantee filtering and an allowlisted
stronger Mistral evaluation candidate. Mistral baseline's five-case smoke needed
review; v2-001 made a safety guarantee, now covered by rejection regression.
Large 3 smoke stopped on HTTP 403; no quality result or winner. Kimi is deferred
until operator provisioning after a scoped release. Production remains unchanged.
See the active plan for evidence paths and remaining gates.

## Operator preference update — Kimi credential

The operator now explicitly requests provisioning through the private ZION chat,
not terminal input. `/setkimikey`, `/cancelkimikey`, `/kimistatus` and an early
private capture handler have been implemented in the isolated branch. Do not
ask the operator to run the earlier terminal command or send a key until the
new DM flow is actually included in an approved production release.
No real Kimi key was received or provisioned during implementation.

## Active v2 recovery checkpoint — 2026-10-19

Worktree: `/home/zetta/.codex/worktrees/zion-cognitive-v2`, branch
`codex/multi-agent-cognitive-v2`. The former temporary worktree disappeared;
commits were preserved and recorded source edits restored. Recovery: 754 tests PASS. Subsequent knowledge-tool/planner increment:
763 tests, secret scan and normal validation PASS. Full recovery log:
`/home/zetta/.codex/worktrees/zion-cognitive-recovery-validation.log`.

Kimi provisioning command now uses this persistent path:
`PYTHONDONTWRITEBYTECODE=1 /home/zetta/.local/share/zion-community-bot/runtimes/current/bin/python /home/zetta/.codex/worktrees/zion-cognitive-v2/scripts/provision-kimi.py`.
Only hidden local terminal input; never paste credentials into chat.
Credential has NOT been confirmed. Provider evaluation is synthetic/public only.
No production activation or full-mission acceptance is claimed.
Mistral synthetic smoke stopped on absolute_safety at v2-031; no benchmark
acceptance. Prompt changed afterward, so a new common-input baseline is needed.
Remaining work is tracked at the top of MULTI-AGENT-IMPLEMENTATION-PLAN.md.

---

# 2026-10-18 — Cognitive v2 initial checkpoint (development only)

The active mission is Cognitive Architecture v2. See the current section at the
top of `MULTI-AGENT-IMPLEMENTATION-PLAN.md`; historical readiness statements below
must not be interpreted as current host or v2 completion evidence.

- Feature: `codex/multi-agent-cognitive-v2`, isolated `/tmp/zion-cognitive-v2`.
- Base dev: `57a10444422373271fbd602acc083199346b5031`.
- First increment: `1c0cff7ae5c318eb96c3d67a747e1c29eb9dc4b9`.
- Fresh baseline 724 PASS; increment full suite 727 PASS; secret scan/validation OK.
- Fix: explicit topic switches do not inherit previous retrieval/history merely
  because they begin with a follow-up conjunction. Six paired scenarios pass;
  five failed before the fix. This is not complete semantic language recovery.
- Public Solana fee policy reconciled against Z-SWAP `986ae759...`; current
  projection corrected, APN archival text preserved with supersession notice.
- Provider research started; no Kimi implementation, paid requests or credentials.
- Measured production remains `472a4b3f0ce73a8635d400c0073701013c357b92`, active,
  PID 534477/NRestarts 0. No production mutation in this increment.
- Full v2 implementation, official provider review, secure provisioning, benchmark,
  release audit, promotion and live Telegram acceptance remain pending.

---

# ZION — CHAT HANDOFF / CURRENT STATE

Date: 2026-09-20  
Purpose: authoritative context transfer for a new ChatGPT conversation.  
Repository: `zettaceo/zion-community-bot`

This document is a handoff, not a production-authorization document.

---

## 2026-10-16 — MULTI-AGENT COMMAND SYSTEM DEVELOPMENT HANDOFF

An isolated feature branch based on verified `origin/zion-v1.1-dev`
`c88c3dd8947fa32168feddaa88dbfb870a1eed64` implements the coordinated ZION,
MIMIR, EIR, and FREYR core. It has not been claimed as deployed by this entry.

Implemented development boundaries:

- ZION is the sole group intake, deterministic Guardian, arbiter, and Control
  Center; secondary identities have no moderation tools;
- protected identity-bound tokens stay outside Git, `.env`, SQLite, backups,
  diagnostics, and chat;
- ZION DM is creator-only, MIMIR DM is closed, and EIR/FREYR DMs are public;
- deterministic intent routing runs before a bounded non-moderating AI fallback;
- invisible cross-agent handoff permits one internal hop and one final speaker;
- knowledge retrieval enforces PUBLIC/CONTROLLED/INTERNAL/SECRET scope before
  model context construction;
- schema v4 stores content-free routing telemetry and prunes it on the existing
  retention cadence;
- EIR triages support and escalates sensitive classes without asking secrets;
- FREYR accepts labelled minimum fields, forwards through the primary ZION bot,
  creates no lead record, and leaves commercial commitments to a human;
- the local confidentiality boundary covers direct/encoded exfiltration and
  full-document reproduction requests.

The official audited-runtime validation completed with **714/714 PASS**, runtime
and imports compatible, shell checks green, `SECRET SCAN: OK`, and
`ZION VALIDATION: OK`. The feature HEAD, GitHub CI, promotion SHA, Acer
deployment, real token provisioning, minimum Telegram privileges, and 17-case
live acceptance must be recorded only after they actually occur. Do not treat
this paragraph as production evidence.

Development integration then completed through PR #59 at
`1e639f063497fd7528b58193610fa9dda181c2d0`. ZION CI #1328 (run
`38981413006`) succeeded on that exact implementation merge. Production and
live acceptance remain separate gates.

---

## 1. Executive state

The repository development line has completed:

- Block 1 — runtime/concurrency;
- Block 2 — SQLite/persistence;
- Block 3 — Guardian/Telegram;
- Block 4 — operations/audit;
- Block 5 — remote operations preparation;
- Release Gate v1.1 — repository/development scope.

The architectural source of truth is now:

- `ZION-MASTER-PLAN.md`

Current master-plan capability matrix:

- **18 DONE**
- **7 PARTIAL**
- **0 TODO**
- **0 fully FUTURE**

The 7 PARTIAL capabilities are:

1. Guardian / community security;
2. identity and reputation;
3. AI layer;
4. scam sentinel;
5. administrative panel;
6. observability;
7. policy system.

Important: completion of Blocks 1–5 and the Release Gate does **not** mean v1.1 is deployed in production.

---

## 2. Exact Git state at handoff preparation

State used to prepare this handoff:

- development branch: `zion-v1.1-dev`
- development integration SHA before this handoff-only documentation commit:
  `0df3507b7e2cb009b225cbed181596e5c76f5efe`

- production branch: `zion-v1`
- production SHA:
  `f8c704f16d05c5fba3b55957721b025c9abbaa23`

At handoff preparation time GitHub reported:

- `zion-v1.1-dev`: **unprotected**
- `zion-v1`: **unprotected**

Production PR:

- PR #2
- `zion-v1.1-dev -> zion-v1`
- state: **OPEN**
- draft: **YES**
- merged: **NO**
- mergeable: **YES**

Release Gate PR:

- PR #10
- merged: **YES**
- merge commit:
  `0df3507b7e2cb009b225cbed181596e5c76f5efe`

Do not infer a newer SHA from this document. Always query GitHub before making a mutation.

---

## 3. Final repository validation already achieved

Release Gate implementation HEAD:

`173c211dcb2221ef7f5aa4997ace7a840e5a0b27`

Final pre-merge validation:

- GitHub Actions **ZION CI #1042**
- **397/397 tests**
- Python 3.12.14
- locked packages: 9
- runtime compatibility: PASS
- imports: PASS
- shell validation: PASS
- sensitive-file check: PASS
- SECRET SCAN: OK
- ZION VALIDATION: OK

Post-merge validation on:

`0df3507b7e2cb009b225cbed181596e5c76f5efe`

- **ZION CI #1043 (push): SUCCESS**
- **ZION CI #1044 (PR): SUCCESS**
- **397/397 tests**
- secret scan and full validation green.

If this handoff commit moves `zion-v1.1-dev`, its own CI must also be checked before treating the new branch head as green.

---

## 4. Non-negotiable architecture/safety invariants

### AI authority

Core rule:

> **AI may interpret. Objective rules or authorized humans decide irreversible actions.**

AI may:

- classify;
- answer;
- summarize;
- translate;
- detect context;
- suggest human review;
- retrieve approved knowledge.

AI does **not** get direct punitive authority merely from model output.

### Deterministic / human authority

Objective deterministic policy or authorized humans may:

- delete;
- mute;
- strike;
- ban;
- block configured domains;
- enforce flood controls;
- enforce lockdown;
- resolve ambiguous incidents.

### SQLite transaction boundary

Do not add network awaits inside SQLite transactions.

### Delivery semantics

Do not claim exactly-once delivery between Telegram and SQLite.

### Production boundary

Until the user explicitly authorizes otherwise:

- do not merge PR #2;
- do not merge directly into `zion-v1`;
- do not deploy;
- do not modify the real Acer production DB;
- do not change live systemd/Tailscale/Wi-Fi/router/firewall state;
- do not activate autonomous punitive behavior.

---

## 5. Master-plan architecture already implemented

The project is no longer a monolithic Telegram script.

Representative modules:

- `zion/telegram_app.py` — Telegram orchestration/commands;
- `zion/guardian.py` — deterministic Guardian;
- `zion/db.py` — SQLite/WAL/migrations/transactions;
- `zion/ai_service.py` — AI policy, accounting, budget, circuit;
- `zion/mistral.py` — Mistral provider boundary/prompts;
- `zion/knowledge.py` — approved knowledge retrieval;
- `zion/health.py` — diagnostics/self-health;
- `zion/admin_dashboard.py` — localhost read-only dashboard;
- `zion/logging_safe.py` — log redaction;
- `zion/process_lock.py` — single-process guard;
- `zion/config.py` / `zion/models.py` — configuration/state models.

Canonical operating states exist:

- NORMAL
- ELEVATED
- ATTACK
- LOCKDOWN
- DEGRADED_AI
- DEGRADED_NETWORK
- MAINTENANCE
- SAFE_MODE

Not every state lifecycle is fully automatic. See `ZION-MASTER-PLAN.md`.

---

## 6. Important current functional capabilities

Already present in development include:

- deterministic anti-flood / recurrence controls;
- strikes, mute, ban and containment paths;
- domain allow/block;
- Unicode/IDNA link handling;
- raid/distributed-burst protections;
- incident ledger and action ledger;
- factual user/event persistence;
- onboarding PT/EN;
- grounded `/ask` against approved knowledge;
- knowledge gaps;
- AI moderation observe-only;
- summaries and translations;
- reports and incidents;
- scheduled and recurring messages;
- polls;
- AMA support;
- health / diagnostics / operator alerts;
- AI budget/accounting/circuit breaker;
- Telegram update lag monitoring;
- SQLite integrity/schema/PRAGMA gates;
- localhost read-only admin dashboard;
- deployment/rollback safety tooling.

See the master plan for exact DONE/PARTIAL status and closure criteria.

---

## 7. Release Gate v1.1 — what was built

Key release files:

- `requirements.lock`
- `scripts/check-runtime.py`
- `scripts/check-env-boundary.py`
- `scripts/check-git-release-boundary.py`
- `scripts/prepare-release-runtime.sh`
- `scripts/deployment-preflight.sh`
- `scripts/predeploy-v11.sh`
- `scripts/verify-approved-release.sh`
- `scripts/apply-zion-v1.sh`
- `docs/V1.1-RELEASE-AUDIT.md`
- `docs/V1.1-FIRST-UPGRADE.md`
- `docs/DEPLOYMENT-MODEL.md`
- `docs/GITHUB-DEPLOY-GATES.md`

### Runtime model

The reviewed release model uses:

```text
/home/zetta/zion-community-bot/
    code + .env
    read-only to runtime service

/home/zetta/.local/share/zion-community-bot/runtimes/
    runtime per approved SHA
    read-only to runtime service

/home/zetta/.local/state/zion-community-bot/
    SQLite / WAL / SHM / log / runtime lock / state
    writable by service

/home/zetta/.local/share/zion-community-bot/deploy-backups/
    rollback evidence
    inaccessible to runtime services
```

`runtime/current` points to the active per-SHA runtime.

### Dependency model

- Python release line: **3.12.x**
- exact package set: `requirements.lock`
- CI/runtime checks require the lock;
- no unexpected distributions except venv bootstrap tools;
- runtime preparation uses isolated pip;
- explicit HTTPS PyPI index;
- no implicit dependency resolution;
- binary wheels only;
- published runtime has write bits removed.

### Environment boundary

`.env.example` is the versioned allowed-key boundary.

Production `.env` must be:

- regular file;
- non-symlink;
- single-link;
- mode 0600;
- owned by `zetta`;
- valid UTF-8 assignment syntax;
- no duplicate keys;
- no unknown/non-allowlisted keys;
- values are never printed by the validator.

### Git release boundary

Release gates reject/neutralize relevant local Git state including:

- active hooks;
- `core.hooksPath`;
- replace refs;
- grafts;
- shallow release repositories;
- dangerous `GIT_*` environment overrides;
- URL rewrite configuration;
- origin upload-pack override;
- tracked or non-ignored untracked contamination.

Bootstrap/cutover commands neutralize hooks/replace refs where required.

### Cutover semantics

- normal release starts only from healthy current production;
- `apply-zion-v1.sh` refuses to act as a quick-deploy shortcut while `zion.service` is active;
- candidate runtime is prepared before downtime;
- current service state layout determines the real production DB source;
- first v1 -> v1.1 release can migrate from legacy repo DB to isolated state DB;
- future releases recognize the state-dir DB from the installed root-owned unit;
- state/DB paths reject symlink redirection;
- HEAD/worktree/.env/runtime are revalidated at cutover;
- installed dashboard joins the same cutover and shares DB/runtime;
- dashboard enabled/disabled intent is preserved;
- rollback metadata records prior commit/runtime/unit/DB evidence.

---

## 8. Findings already closed

The release audit closed repository-level HIGH/MEDIUM findings including:

- service could write its own code/.env;
- Python runtime shared a writable repo boundary;
- dashboard could remain on stale DB/runtime;
- env-key contamination;
- tracked-only worktree checks;
- Git hooks/replace/config tampering;
- rollback evidence in bot-writable storage;
- first-upgrade tooling absent from old v1 checkout;
- candidate-vs-production path confusion;
- release while current production is already down;
- stale legacy DB inference in future releases;
- range-based runtime drift;
- implicit pip resolver/index behavior;
- cutover TOCTOU on inputs;
- dashboard DB divergence;
- .env hard-link inconsistency.

Final repository source review before integration found no unresolved HIGH or MEDIUM repository finding.

---

## 9. What is still missing before production

This is the next operational frontier.

### A. GitHub control plane — REQUIRED

Current branches were still unprotected at handoff preparation.

A repository administrator must configure and verify branch protection/rulesets, especially for `zion-v1`.

Expected gates include:

- PR-only change path for production;
- required ZION CI;
- no unexpected bypass actors;
- force push disabled;
- deletion disabled;
- appropriate review requirement;
- Acer Git credential, if used, read/fetch-only.

Repository code cannot substitute for this control-plane configuration.

### B. Real Acer / network / SSH acceptance — REQUIRED

Must be verified on the actual host:

- Tailscale installed and healthy;
- intended Tailnet identity/policy;
- no public router/NAT TCP/22 exposure;
- no unreviewed Tailscale SSH/Funnel/Serve;
- authorized_keys inventory;
- ED25519 host fingerprint verified out of band;
- public-key login proven;
- second simultaneous remote session proven before closing bootstrap access;
- effective `sshd -T -C` policy for real zetta/client context;
- firewall/listening surface checked.

### C. Real production runtime/filesystem — REQUIRED

Verify on Acer:

- user/path ownership;
- exact Python 3.12 availability;
- runtime preparation can build/verify the locked environment;
- production `.env` passes the new environment boundary;
- state/runtime/backup directories are canonical and not redirected;
- systemd unit state matches expectations;
- current production is healthy before release.

### D. Real production DB rehearsal — REQUIRED

Before real cutover:

- identify the actual live v1 SQLite DB;
- full integrity check;
- create verified backup;
- copy to disposable location;
- run v1.1 migration against the copy;
- verify schema/application_id/foreign keys/WAL/integrity;
- verify expected legacy-state migration semantics;
- do not mutate the live DB during rehearsal.

### E. Production PR #2 final review — REQUIRED

PR #2 remains Draft and unmerged.

Before any production merge:

- re-audit the full final delta from current `zion-v1` to current `zion-v1.1-dev`;
- verify exact final SHA;
- verify required CI;
- verify GitHub ruleset/protection is actually active;
- verify all Acer/live gates above;
- receive explicit user authorization for production merge/deploy.

### F. Live acceptance after an explicitly authorized deployment

After cutover:

- service active / no restart loop;
- `/status`;
- operator `/health`;
- operator `/diagnostics`;
- operator `/jobs`;
- operator `/aistatus`;
- dashboard if previously enabled;
- DB/state path alignment;
- Telegram update flow;
- rollback readiness.

---

## 10. What to do next in a new chat

The new chat should:

1. fetch this file from the latest `zion-v1.1-dev`;
2. fetch `ZION-MASTER-PLAN.md`;
3. fetch:
   - `docs/V1.1-RELEASE-AUDIT.md`
   - `docs/V1.1-FIRST-UPGRADE.md`
   - `docs/DEPLOYMENT-MODEL.md`
   - `docs/GITHUB-DEPLOY-GATES.md`;
4. query current GitHub SHAs and PR #2 state;
5. verify CI on the actual current `zion-v1.1-dev` SHA;
6. continue with **production-readiness gates**, not a new fictional Block 6.

### Recommended immediate next task

First, finish the production-readiness audit that does **not** require touching the Acer:

- current PR #2 full delta;
- current branch protection/ruleset state;
- current required-check evidence;
- exact list of host facts still needed.

Then move to Acer/live gates only with explicit user authorization for the corresponding host actions.

---

## 11. Codex usage policy

Use Codex sparingly.

Current preference:

- ChatGPT does architecture, audit, GitHub review, docs and deterministic corrections when possible.
- Codex is useful when:
  - direct access to local Acer files/state is necessary;
  - an independent adversarial review has high value;
  - a local multi-file change is materially easier through the workstation.
- If using Codex as independent reviewer, first request **review only, no edits**.
- Validate Codex findings independently before applying them.

Do not spend Codex credits on work that can be completed through GitHub/CI from ChatGPT.

---

## 12. User working rule

If the requested block/project scope cannot be recovered from repository/context:

> **STOP and ask. Do not invent the scope.**

This rule prevented the accidental invention of a nonexistent “Block 6”.

---

## 13. Final handoff principle

The next conversation should not reconstruct ZION from memory or from chat summaries when the repository can answer the question.

Use the repository as source of truth, distinguish development from production, and never turn a green CI result into an unsupported claim about the real Acer/control plane.


---

## 2026-09-20 — FINAL ADVERSARIAL RE-AUDIT HANDOFF

**This section supersedes older SHA / CI / delta snapshots in this file.** Older sections remain as historical evidence only.

### Final implementation/security identity

- development branch: `zion-v1.1-dev`;
- implementation/security HEAD: `bae040899c9294ab912d349eb1cca58f2cedaf13`;
- production branch: `zion-v1`;
- production SHA remained untouched: `f8c704f16d05c5fba3b55957721b025c9abbaa23`;
- implementation delta at this checkpoint: **655 commits ahead / 0 behind**, **103 changed files**;
- PR #2 remained **OPEN + DRAFT + UNMERGED**.

### Final implementation CI evidence

GitHub Actions **ZION CI #1146** on `bae040899c9294ab912d349eb1cca58f2cedaf13`:

- Python 3.12.14;
- runtime lock: 9 packages;
- wheel artifacts pinned by SHA-256 and installed with `--require-hashes`;
- runtime compatibility: PASS;
- imports: PASS;
- **441/441 tests: OK**;
- shell validation: PASS;
- sensitive-file check: PASS;
- secret scan: PASS;
- **ZION VALIDATION: OK**.

### Additional re-audit closures

The final adversarial pass added and validated repository-side protections for:

- Git `assume-unchanged` / `skip-worktree` index flags that can hide tracked-file tampering from ordinary status checks;
- ignored importable artifacts and local ignore/attribute overrides;
- executable Git credential helpers and askpass programs;
- executable / reroutable SSH client configuration during Git remote proof;
- disabled Git HTTPS TLS verification / custom CA overrides;
- exact SHA-256 pinning of all release wheel artifacts;
- DB/WAL/SHM/log symlink/hardlink boundaries;
- fixed executable paths and clean Python release environment;
- first-upgrade pre-check before candidate worktree checkout.

No unresolved HIGH or MEDIUM **repository/development** finding is known at the implementation/security HEAD above.

### External gates still blocking production

The repository is not production-authorized. The following remain external evidence gates:

1. GitHub governance: `zion-v1` and `zion-v1.1-dev` were still reported as `protected:false`; required branch/ruleset controls must be configured and verified by a repository administrator.
2. Acer/Tailnet/SSH: real device identity, Tailnet policy, router/NAT TCP/22 exposure, SSH key inventory, ED25519 host fingerprint, effective sshd policy and second-session recovery must be proven on the real host/control plane.
3. Real host/runtime: production `.env`, Python 3.12/runtime-by-SHA, filesystem ownership/modes and current systemd state must be inspected.
4. Real SQLite: integrity, verified backup, disposable-copy migration rehearsal and rollback rehearsal must pass using the Acer's actual production data.
5. Live acceptance: Telegram commands and service/dashboard health are post-cutover gates and have not been executed.

### Next execution boundary

Repository/GitHub development hardening should not be extended by inventing a new feature block. The next phase is **local Acer evidence gathering**, preferably with Codex used first as a **review-only local inspector**. It must not mutate systemd, SSH, Tailscale, Wi-Fi, router/firewall, production `.env`, production SQLite, or deploy anything until the corresponding evidence has been reviewed and explicit authorization is given.

Any documentation-only descendant created after `bae040899c9294ab912d349eb1cca58f2cedaf13` must pass ZION CI before becoming the current release-candidate head.


---

## 2026-09-21 — ACER READ-ONLY AUDIT RECONCILIATION

A read-only Codex audit of the real Acer completed without host mutation.

### Confirmed legacy production facts

- local production branch: `zion-v1-prod`;
- local/remote production SHA at audit: `f8c704f16d05c5fba3b55957721b025c9abbaa23`;
- audited candidate at that moment: `ef815e685725000fc4203c80ab2df8c45a2a9e65`;
- `zion.service`: active/running, zero observed restarts;
- live DB: `/home/zetta/zion-community-bot/zion.db`;
- legacy runtime: repository-local `.venv`;
- Tailscale absent;
- OpenSSH Server absent;
- both GitHub branches still reported `protected=false`.

These facts describe the pre-v1.1 installation. Repository-writable code/runtime, the lack of the v1.1 runtime lock, and the absence of the v1.1 sandbox are inherited legacy conditions that the controlled v1.1 cutover is designed to replace; they are not evidence that the candidate itself regressed.

### Real blockers found on the host

Before any release rehearsal:

1. GitHub governance remains unproven/unprotected.
2. The Acer Git boundary rejects the executable GitHub CLI credential helper.
3. The Acer contains ignored importable bytecode caches that the release checker rejects; they must be inventoried and only proven generated caches may be removed.
4. The same Acer user has a GitHub credential with broader-than-fetch permissions; production Git authentication must be separated/reduced before release.
5. Current backup/rollback evidence is not sufficient for a v1.1 migration.
6. Tailscale/OpenSSH/private remote access and router/firewall control-plane evidence remain incomplete.

### Repository defect discovered by the host audit

The audit identified a genuine MEDIUM release-procedure contradiction: repository handoff policy required the real candidate/DB rehearsal before production merge, but the verifier was hard-bound to `origin/zion-v1`, making that rehearsal possible only after merge.

The release flow was corrected in development:

- `ZION_RELEASE_SOURCE=candidate` binds only to `origin/zion-v1.1-dev` for the pre-merge rehearsal;
- `ZION_RELEASE_SOURCE=production` binds only to `origin/zion-v1` after explicit merge authorization;
- arbitrary refs remain forbidden;
- the exact pre-merge candidate must pass disposable-copy DB rehearsal before PR #2 may merge;
- the actual resulting production SHA must then be staged and verified again before downtime.

Implementation/security HEAD after this correction: `70c269f6b1a983ec197a958e5727fca117a514a1`.

GitHub Actions **ZION CI #1152** passed on that exact SHA with Python 3.12.14, the 9-package SHA-256-pinned runtime, **444/444 tests**, imports, shell validation, secret scan and **ZION VALIDATION: OK**.

### Safety state

The Acer audit performed no package installation, service control, DB connection/migration, Git fetch/checkout/merge, SSH/Tailscale/firewall change, Telegram command, or deployment. Production remained untouched.



---

## 2026-09-21 — CONTROLLED ACER REMEDIATION RECONCILIATION

The authorized controlled-remediation phase completed without production deploy, production merge or live DB mutation.

### Host remediation evidence

Confirmed on the real Acer:

- local and remote production remained `f8c704f16d05c5fba3b55957721b025c9abbaa23`;
- PR #2 remained OPEN + DRAFT + UNMERGED;
- `zion.service` remained active with the same PID and `NRestarts=0`;
- Git release boundary passed after remediation;
- the executable GitHub CLI credential helper was removed from Git configuration;
- production fetch now uses a repository-scoped, verified read-only SSH deploy key;
- the user's administrative `gh` session was preserved;
- 25 ignored CPython bytecode caches were provenance-checked and removed;
- Tailscale is installed, authenticated and running;
- OpenSSH is installed and active;
- exact candidate runtime preparation succeeded for the then-current candidate `c564d1ad3792e48e79375c6bd45f1b9a83e281c6`, with `runtime/current` still pointing to the legacy `.venv`;
- the live SQLite DB passed full integrity;
- a disposable backup migrated from schema 0 to schema 2 with the expected ZION application ID, foreign keys, WAL, FULL synchronous and `trusted_schema=0`;
- disposable rollback/restoration evidence passed;
- no Telegram live acceptance was executed.

The runtime prepared for `c564d1ad...` is now historical staging only because the development candidate advanced after repository fixes. It must not be activated or treated as the current candidate runtime.

### Repository findings triggered by the Acer phase

The controlled remediation exposed two repository-side defects that were fixed before continuing:

1. Three release scripts were tracked as mode `100644` even though the release gate requires them executable. They are now `100755`, and CI has a regression test that reads the Git index and enforces those modes.
2. The v1.1 bot/dashboard sandbox could still read the operator's `~/.config/gh` administrative session and `~/.ssh` private keys because the services run as `zetta`. The candidate units now make those locations, plus common file-based credential files, inaccessible inside the service mount namespaces.

### Current implementation/security identity after remediation fixes

- `zion-v1.1-dev`: `09ddea27261669a1bdeb4ec8b320ee9aa9625cd5`;
- production `zion-v1`: `f8c704f16d05c5fba3b55957721b025c9abbaa23`;
- delta: **682 ahead / 0 behind / 103 changed files**;
- PR #2: OPEN + DRAFT + UNMERGED.

GitHub Actions **ZION CI #1164** on `09ddea27261669a1bdeb4ec8b320ee9aa9625cd5`:

- Python 3.12.14;
- locked packages: 9;
- runtime compatibility: PASS;
- imports: PASS;
- **445/445 tests: OK**;
- shell validation: PASS;
- secret scan: PASS;
- **ZION VALIDATION: OK**.

### Remaining blockers

1. GitHub governance remains BLOCKING: both release branches still report `protected=false`. The private repository's ruleset endpoint reports that GitHub Pro or a public repository is required; do not fake `ZION_GITHUB_GATES_PROVEN=YES`.
2. SSH hardening is not yet complete: the reviewed ZION sshd drop-in is absent, password authentication has been observed, and the privileged `sshd -t/-T` validation still requires an authenticated sudo session.
3. Firewall policy is not yet proven with privileged reads.
4. Router/NAT TCP/22 exposure is not yet proven.
5. Tailnet ACL/grants/device-approval policy is not yet proven from the control plane.
6. The exact current candidate `09ddea...` has not yet been staged/rehearsed on the Acer. The prior `c564d1ad...` runtime/rehearsal must not substitute for it.
7. Official pre-merge rehearsal remains blocked until the governance and remote/network attestations are factually true.
8. Full release rollback rehearsal and Telegram live acceptance remain later gates.

Production merge/deploy remains unauthorized.


---

## 2026-09-22 — MISTRAL PRIVATE SECRET PROVISIONING

The production candidate is being hardened so the Mistral API key is no longer configured directly in `.env`.

### Implemented repository boundary

- `MISTRAL_API_KEY` is deprecated and must remain empty; a non-empty legacy value blocks candidate startup/predeploy rather than being migrated automatically.
- The production secret path is fixed by code at `/home/zetta/.local/state/zion-community-bot/secrets/mistral-api-key`.
- `zion/secret_store.py` owns the provider-secret filesystem boundary: canonical 0700 directory, 0600 single-link regular file, owner validation, symlink/hardlink rejection, `O_NOFOLLOW` reads where available, atomic writes, directory fsync and rollback after post-publication failures.
- Mistral requests read the secret dynamically, so set/rotate/clear take effect without restarting ZION.
- `/setmistralkey` is restricted to explicit `ZION_ADMIN_USER_IDS` operators in private chat. It arms a 120-second in-memory capture; the next non-command message is deleted before validation/persistence and stopped before the generic Guardian/AI/SQLite pipeline.
- Accidental `/setmistralkey <value>` input is intercepted and deleted before command idempotency persistence, including non-space whitespace separators.
- Provider validation uses the official `GET https://api.mistral.ai/v1/models` endpoint with HTTPS, redirects disabled and sanitized error handling.
- A failed provider validation preserves the previous key. A failed Action Ledger write also reverts a successful local set/rotation/clear rather than leaving an unaudited secret mutation.
- `/clearmistralkey CONFIRM` is required for removal.
- `/aistatus`, health and diagnostics expose only MISSING/PRIVATE/UNSAFE or CONFIGURED state, never key bytes/fingerprint.
- The dashboard unit cannot access the secrets directory.
- Deployment backups do not copy or fingerprint the Mistral secret.
- Legacy rollback must clear and verify the secret as MISSING before older same-user code starts.

### Privacy statement

The private-chat provisioning flow is deliberately honest about transport: the credential transits Telegram private chat before ZION deletes the incoming message. Application-level DB/log/backup persistence is prohibited. An operator who requires a channel that never transits Telegram must use a separately reviewed local/offline path.

### Final repository evidence for this implementation

The Mistral private-secret implementation was merged into `zion-v1.1-dev`.

Current development HEAD:

```text
c0528ce81e3dfc1254149e083b90a41986d79b94
```

GitHub Actions **ZION CI #1221** passed on that exact post-merge HEAD:

- runtime compatibility: PASS;
- Python 3.12.14;
- locked packages: 9;
- imports: PASS;
- **496/496 tests: OK**;
- secret scan: PASS;
- **ZION VALIDATION: OK**.

The adversarial pass also closed:
- dangling/alias secret-directory handling;
- post-`os.replace` durability rollback;
- failed clear rollback;
- accidental `/setmistralkey <secret>` deletion before idempotency persistence;
- fixed non-configurable production secret path;
- audit-ledger failure rollback for set/rotate/clear;
- dashboard denial of secret-store access.

No unresolved HIGH or MEDIUM **repository/development** finding is known after this implementation pass.

### Current safety boundary

This implementation does **not** authorize production. PR #2 remains Draft/unmerged; the real Mistral key must not be requested or provisioned until after an explicitly authorized v1.1 cutover.

The next required work is host/control-plane evidence against the exact current candidate `c0528ce81e3dfc1254149e083b90a41986d79b94`: SSH hardening, privileged firewall inspection, router/NAT and Tailnet policy proof, exact-candidate runtime staging and disposable DB rehearsal, plus GitHub governance.


---

## 2026-09-22 — FINAL ACER PRE-PRODUCTION RECONCILIATION

The final Acer pre-production pass against candidate `af93361ef244f91436239dd69c62a32c35b6ea69` completed without production merge, cutover or live-database migration.

### Host evidence proved

- production local/remote remained `f8c704f16d05c5fba3b55957721b025c9abbaa23`;
- PR #2 remained OPEN + DRAFT + UNMERGED;
- `zion.service` remained active on the legacy runtime with `NRestarts=0`;
- Git release boundary passed with the repository-scoped read-only deploy key;
- SSH hardening was installed and effective: key-only auth, password/keyboard-interactive/root disabled, forwarding/tunnel controls disabled;
- a second independent Tailscale SSH session succeeded with `Accepted publickey`;
- Tailscale local state passed; Serve/Funnel/Tailscale SSH were not enabled;
- exact `af93361...` per-SHA runtime passed `check-runtime.py` and `pip check`;
- candidate bot/dashboard systemd units passed verification without installation;
- legacy `MISTRAL_API_KEY` was absent and the new secret store remained MISSING;
- live SQLite full integrity/foreign-key checks passed without migration;
- verified backup + disposable schema 0 → 2 migration + rollback rehearsal passed.

### Host blockers proved

- local firewall was permissive while sshd listened on wildcard IPv4/IPv6;
- router/NAT and public IPv6 control-plane exposure were not proven;
- Tailnet ACL/grants/device-approval policy was not proven;
- GitHub still reported `zion-v1` and `zion-v1.1-dev` as `protected=false`, and private-repository governance endpoints required an account-plan upgrade or a public repository;
- the official rehearsal correctly remained blocked because the external attestations were not true.

### Repository finding discovered by the host pass

The candidate's `scripts/predeploy-v11.sh` disposable-migration subprocess referenced `ZION_APPLICATION_ID` without importing it, producing a real `NameError` at step 8/8.

This HIGH repository finding was fixed in PR #28. A regression test now requires the import before the application-ID comparison.

Post-merge development HEAD after the fix:

```text
557722f461c84b4df485b9d403595946cc65cbdf
```

GitHub Actions **ZION CI #1228** passed with **497/497 tests**, imports, secret scan and **ZION VALIDATION: OK**.

### Reviewed SSH firewall procedure added after the host pass

The host report correctly refused to improvise firewall rules. PR #29 adds a reviewed, candidate-pinned and reversible host firewall procedure:

- dedicated `inet zion_ssh_guard` nftables table;
- allow TCP/22 only on `lo` and `tailscale0`;
- drop TCP/22 on every other IPv4/IPv6 interface;
- leave all non-SSH traffic untouched;
- require exact candidate, clean Git boundary, explicit authorization, proven Tailscale key access and a second independent session;
- install through a persistent systemd unit ordered before SSH service/socket activation;
- record a root-only pre-change nftables snapshot;
- require a third Tailscale SSH session after application;
- provide a guarded rollback that removes only ZION's dedicated firewall table/artifacts;
- strict `remote-access-preflight.sh` now fails closed until the dedicated guard is active and persistent.

Post-merge development HEAD after this repository hardening:

```text
7d6587245ebb1f566bcc1360ad1a028a9347a992
```

GitHub Actions **ZION CI #1245** passed on that SHA with Python 3.12.14, the 9-package audited runtime, **507/507 tests**, imports, shell validation, secret scan and **ZION VALIDATION: OK**.

### Current boundary

All runtime/rehearsal evidence collected for `af93361...` is historical evidence only. The exact current development candidate `7d658724...` must receive a fresh per-SHA runtime and disposable DB rehearsal before it can become release evidence.

Remaining external/host work:

1. apply the reviewed SSH firewall from the exact current candidate and prove a third Tailscale key-only session;
2. prove router/NAT and IPv6 control-plane state;
3. prove Tailnet ACL/grants/device-approval policy;
4. resolve GitHub private-repository governance without making the repository public merely to bypass the gate;
5. stage/rehearse the exact current candidate;
6. run the official pre-merge rehearsal only with truthful attestations.

Production merge/deploy remains unauthorized.
