# ZION — CHAT HANDOFF / CURRENT STATE

Date: 2026-09-20  
Purpose: authoritative context transfer for a new ChatGPT conversation.  
Repository: `zettaceo/zion-community-bot`

This document is a handoff, not a production-authorization document.

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
