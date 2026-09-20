# ZION — MASTER PLAN

Status: **architectural source of truth + implementation status**  
Scope: Z-SWAP Community OS  
AI provider: **Mistral AI**  
Core principle: **AI interprets; deterministic policy or authorized humans execute irreversible moderation.**

> This document defines the target system and records the current implementation state.  
> It does **not** mean development code is deployed to production.

## 0. Status semantics

Every roadmap item uses one of four states:

- **DONE** — the intended capability exists in code, is covered by tests and has an operational contract.
- **PARTIAL** — a useful production-shaped core exists, but one or more explicit closure criteria remain.
- **TODO** — agreed scope, not yet implemented.
- **FUTURE** — intentionally outside the current release horizon.

A percentage is not a source of truth. The status and closure criteria below are.

### Current capability snapshot

Across the 25 functional capabilities in this plan:

- **18 DONE**
- **7 PARTIAL**
- **0 TODO**
- **0 fully FUTURE**

Future sub-capabilities still exist inside several DONE/PARTIAL areas.

## 1. What ZION is

ZION is the **community operating system for Z-SWAP**, not merely a Telegram moderation bot.

Its five central responsibilities are:

| Function | Role |
|---|---|
| **Guardian** | protect the community |
| **Support** | answer and guide users from approved facts |
| **Community** | onboard, organize and engage members |
| **Intelligence** | interpret context and detect patterns |
| **Operations** | help authorized administrators operate the community |

The safety boundary is non-negotiable:

> **AI may interpret. Objective rules or authorized humans decide irreversible actions.**

AI output alone does not grant authority to delete, mute or ban.

## 2. Source-of-truth hierarchy

The repository uses separate documents for separate kinds of truth:

1. **Product/architecture intent:** `ZION-MASTER-PLAN.md`
2. **Moderation behavior:** `docs/POLICIES.md`
3. **Security boundary:** `docs/SECURITY.md`
4. **Operational procedures:** `docs/OPERATIONS.md`
5. **Deployment/release controls:** `docs/DEPLOYMENT-MODEL.md`, release-gate audit documents
6. **Approved support facts:** `knowledge/`
7. **Executable truth:** code + tests

Historical Block audit documents are evidence of how a capability was reached; they do not override the current executable contract.

## 3. Conceptual architecture

Target architecture:

```text
                    ZION
                     │
          ┌──────────┴──────────┐
          │                     │
      TELEGRAM              FUTURE CHANNELS
                         Discord / Web / App
          │
          ▼
┌───────────────────────────────┐
│      1. EVENT INGESTION       │
│ messages / joins / links      │
│ commands / reports / events   │
└──────────────┬────────────────┘
               ▼
┌───────────────────────────────┐
│    2. DETERMINISTIC CORE      │
│ flood / links / secrets       │
│ strikes / permissions / bans  │
│ rate limits / allowlists      │
└──────────────┬────────────────┘
               ▼
┌───────────────────────────────┐
│       3. AI INTELLIGENCE      │
│ context / intent / Q&A        │
│ classification / summaries    │
│ translation / pattern hints   │
└──────────────┬────────────────┘
               ▼
┌───────────────────────────────┐
│        4. POLICY ENGINE       │
│ rules / risk / confidence     │
│ escalation / approval         │
└──────────────┬────────────────┘
               ▼
┌───────────────────────────────┐
│       5. ACTION ENGINE        │
│ delete / mute / ban / warn    │
│ reply / notify / escalate     │
└──────────────┬────────────────┘
               ▼
┌───────────────────────────────┐
│      6. MEMORY & DATA         │
│ users / incidents / FAQ       │
│ strikes / audit / settings    │
└──────────────┬────────────────┘
               ▼
┌───────────────────────────────┐
│     7. ADMIN / OBSERVABILITY  │
│ dashboard / alerts / metrics  │
│ configuration / audit         │
└───────────────────────────────┘
```

### Current module mapping

| Conceptual layer | Current implementation |
|---|---|
| Event ingestion | `zion/telegram_app.py` |
| Deterministic core | `zion/guardian.py`, `docs/POLICIES.md` |
| AI intelligence | `zion/ai_service.py`, `zion/mistral.py`, `zion/knowledge.py` |
| Policy boundary | deterministic Guardian rules + operator authorization + observe-only AI |
| Actions | Telegram action handlers + transactional ledger writes |
| Memory/data | `zion/db.py` SQLite/WAL |
| Admin/observability | `zion/health.py`, admin commands, `zion/admin_dashboard.py` |

The destination architecture does **not** require a mechanical rewrite into an `app/` folder tree. Separation of responsibilities and testable boundaries are the requirement.

## 4. Capability implementation matrix

| # | Capability | Status | Current evidence | Closure criteria |
|---:|---|---|---|---|
| 1 | Guardian / community security | **PARTIAL** | `guardian.py`; flood, strikes, mute/ban escalation, links/domains, Unicode/IDNA, raid/chat burst, secret exposure, containment, lockdown; Guardian tests | add reviewed official-identity/wallet scam signals, shortener/known-scam handling where justified, and complete ATTACK automation policy |
| 2 | Identity and reputation | **PARTIAL** | `users`, `user_events`, strikes, incidents, containments, `/user` | explicit username-history representation and separate positive-contribution indicators without social-score collapse |
| 3 | Intelligent welcome | **DONE** | bilingual onboarding, rules/security notice, join persistence, raid-aware onboarding | future staged onboarding is optional enhancement |
| 4 | Z-SWAP support | **DONE** | grounded `/ask`, approved knowledge only, explicit unknown fallback, knowledge-gap escalation | expand factual corpus as product evolves |
| 5 | Knowledge base / RAG | **DONE** | local approved Markdown, lexical retrieval, section/source labels, bounded gaps, `/reloadkb` | embeddings/version registry/freshness metadata are future upgrades, not baseline blockers |
| 6 | AI layer | **PARTIAL** | classification, Q&A, summaries, translation, human-review signal, token budget, circuit breaker, accounting | richer emerging-topic/pattern analysis and a more explicit task router/review queue |
| 7 | Contextual moderator | **DONE** | criticism is explicitly allowed; AI classification is observe-only; harassment/scam categories escalate | continue false-positive measurement |
| 8 | Human escalation | **DONE** | incidents contain category/severity/source/evidence; operator incident commands and resolution | richer UI queue belongs to admin-panel work |
| 9 | Community Assistant | **DONE** | help/rules/status, grounded support, summary, translation, reports, document/source assistance | add future channels only when justified |
| 10 | Community Manager | **DONE** | announcements, polls, one-shot schedules, recurring schedules, AMA, 24h brief, knowledge gaps | richer editorial approval/templates are optional enhancement |
| 11 | Scam sentinel | **PARTIAL** | domain allow/block, Unicode/IDNA, suspicious links, secret/seed-like content protection, AI scam/phishing/impersonation signals, lockdown | official usernames/wallet registry and additional deterministic high-confidence scam intelligence |
| 12 | Incident response | **DONE** | persistent incident IDs, timestamps, evidence, actions, status lifecycle, operator review | optional richer correlation UI |
| 13 | Admin commands | **DONE** | health/guardian/AI/stats/brief/gaps/incidents/strikes/user/state/warn/mute/ban/unban/domain/lockdown/schedule/AMA/diagnostics/reload | commands may grow, baseline control surface exists |
| 14 | Administrative panel | **PARTIAL** | read-only localhost dashboard with DB/integrity/state/health counters | authenticated management UI for users/incidents/domains/policies/config only if operationally justified |
| 15 | Observability | **PARTIAL** | uptime, SQLite integrity/schema/WAL/SHM/size, disk, Wi-Fi, Telegram update lag, AI latency/accounting/circuit, alerts, scheduler/delivery state | CPU/memory process metrics and/or structured metrics exporter if needed |
| 16 | Self-health | **DONE** | health snapshots, diagnostics, integrity checks, low-disk checks, AI/network/Telegram telemetry, operator alerts | keep host acceptance tested |
| 17 | Safe degradation | **DONE** | AI failure does not grant punitive authority; circuit breaker; scheduled delivery health gate; Guardian deterministic; network/Wi-Fi recovery; fail-closed DB paths | remote-service fallback may be added only if a remote DB is adopted |
| 18 | Professional persistence | **DONE** | versioned SQLite/WAL schema, migrations, integrity, backups, idempotency, retention, transactional actions | PostgreSQL/Supabase remains FUTURE until evidence justifies migration |
| 19 | Security by design | **DONE** | secret-safe logging, `.env` boundary, admin authorization, rate limits, input normalization, systemd hardening, process lock, release gates | continue release/security review per change |
| 20 | Multi-language | **DONE** | PT-BR/EN onboarding/help plus AI reply-in-user-language and explicit translation | expand official bilingual knowledge coverage |
| 21 | Controlled memory | **DONE** | factual users/events/strikes/incidents/actions/settings/gaps; bounded retention; no opaque opinion score | review retention whenever new data is added |
| 22 | Anti-abuse of AI | **DONE** | prompt-injection boundaries, untrusted JSON/text framing, no AI punitive tools, output validation, rate/budget controls | adversarial prompt tests continue |
| 23 | Policy system | **PARTIAL** | `docs/POLICIES.md`, Guardian rule modules, settings, severity/escalation logic, operating state | first-class versioned policy registry + per-policy observe/action mode + explicit policy version on every action |
| 24 | Action Ledger | **DONE** | persistent `actions` table; actor/action/reason/evidence/result linkage across moderation/admin/operations | policy-version field can be added with capability #23 |
| 25 | Simulation before production | **DONE** | AI moderation observe-only; new high-risk rules are developed/tested before activation; release gates keep development separate from production | maintain this as a release invariant |

Representative test evidence includes:

- `tests/test_guardian.py`
- `tests/test_guardian_surface.py`
- `tests/test_raid_guardian.py`
- `tests/test_moderation.py`
- `tests/test_db.py`
- `tests/test_persistence_v11.py`
- `tests/test_transaction_atomicity.py`
- `tests/test_ai.py`
- `tests/test_mistral_boundaries.py`
- `tests/test_knowledge.py`
- `tests/test_community_commands.py`
- `tests/test_health.py`
- `tests/test_block4_operations.py`
- `tests/test_dashboard.py`
- `tests/test_block5_remote_ops.py`

## 5. Operating states

The canonical state enum is implemented in `zion/models.py`:

| State | Status | Current behavior / gap |
|---|---|---|
| `NORMAL` | **DONE** | ordinary operation |
| `ELEVATED` | **DONE** | temporary tightening after deterministic raid/distributed-burst conditions |
| `ATTACK` | **PARTIAL** | modeled and affects deterministic thresholds; complete automatic transition/exit policy remains |
| `LOCKDOWN` | **DONE** | explicit operator-controlled containment |
| `DEGRADED_AI` | **PARTIAL** | modeled; AI circuit/accounting degradation exists, but full state-transition lifecycle is not centralized |
| `DEGRADED_NETWORK` | **PARTIAL** | modeled; network/Wi-Fi recovery exists outside a complete state-transition lifecycle |
| `MAINTENANCE` | **PARTIAL** | modeled; deployment procedures exist, but maintenance-state orchestration is not complete |
| `SAFE_MODE` | **PARTIAL** | fail-closed behavior exists for critical health/data failures; full system-wide state semantics can be tightened |

No state grants additional punitive power to AI.

## 6. Brain versus police

### Deterministic code may

- delete when an objective policy permits;
- mute;
- apply strikes;
- ban for objective repeat-offense rules;
- block a configured domain;
- rate-limit flood;
- remove high-confidence protected-secret exposure;
- enforce lockdown.

### AI may

- interpret;
- classify;
- answer;
- summarize;
- translate;
- detect context;
- flag possible scam/phishing/impersonation;
- recommend human review;
- retrieve and use approved knowledge.

### AI + human approval

Ambiguous harassment, manipulation, contested moderation, interpersonal conflict and cases without an objective deterministic rule remain human-review territory.

## 7. Code architecture

The original destination sketch proposed many small packages. The current modular line already removed the single-file architecture risk:

```text
bot.py                    thin runtime entrypoint
zion/config.py            configuration boundary
zion/models.py            states and decision models
zion/telegram_app.py      Telegram orchestration + command surface
zion/guardian.py          deterministic Guardian
zion/db.py                persistence / migrations / transactions
zion/ai_service.py        AI policy, budgets, accounting, circuit
zion/mistral.py           provider boundary and prompts
zion/knowledge.py         approved knowledge retrieval
zion/health.py            self-health / diagnostics
zion/admin_dashboard.py   read-only localhost dashboard
zion/logging_safe.py      log redaction
zion/process_lock.py      single-process guard
```

### Remaining modularization criterion

`telegram_app.py` is still the largest orchestration surface. Split it further only when a cohesive boundary (commands, scheduler, onboarding, operational alerts, actions) can move with its own tests. Do not refactor solely to reproduce a directory diagram.

## 8. Data model

Current SQLite entities already cover most of the target model:

| Target concept | Current implementation | Status |
|---|---|---|
| users | `users` | **DONE** |
| user events | `user_events` | **DONE** |
| strikes | `strikes` | **DONE** |
| incidents | `incidents` | **DONE** |
| actions | `actions` | **DONE** |
| message metadata | `recent_messages` | **PARTIAL** — intentionally minimal |
| domains | `domains` | **DONE** |
| policies | docs/settings/code rules | **PARTIAL** — no versioned policy registry yet |
| admins | `ZION_ADMIN_USER_IDS` + Telegram chat-admin checks | **PARTIAL** — no DB admin entity by design |
| reports | incident category `user_report` | **DONE** for operational need |
| knowledge | approved Markdown + knowledge gaps | **DONE** baseline |
| AI events | `ai_events` | **DONE** |
| health | computed diagnostics + alerts | **DONE** operationally; no health-history table |
| settings | `settings` | **DONE** |
| scheduled/recurring | `scheduled_messages`, `recurring_messages` | **DONE** |
| AMA | `ama_sessions`, `ama_questions` | **DONE** |

Additional operational tables include containments, idempotency keys and schema migrations.

### FUTURE storage

PostgreSQL/Supabase/pgvector is **not** required merely because it appeared in the original future design. Migrate only when multi-process, remote query, scale, analytics or backup requirements justify the added network dependency. Local survival remains a first-class requirement.

## 9. AI architecture

Current AI surface is already task-separated even though it is exposed through one service:

```text
user/content
   |
   +--> grounded support answer
   +--> observe-only moderation classify
   +--> summarize
   +--> translate
   |
   +--> budget / accounting / circuit / rate gates
   |
   +--> human incident escalation when required
```

### PARTIAL target

A future explicit router may add emerging-topic analysis, engagement analysis and richer operator intelligence. Each route must receive only the data/tools it needs.

No future router may turn untrusted user text into administrative authority.

## 10. ZION personality

The implemented Mistral system prompt defines ZION as:

> **precise, serene, technical and protective.**

Behavioral requirements:

- not childish;
- not aggressive;
- not a salesperson;
- not a fanboy;
- not a censor of criticism;
- explicit when official evidence is insufficient;
- never invent product facts;
- never request seed phrases, private keys, passwords or tokens.

The implemented grounded fallback is intentionally equivalent to:

> “I did not find enough official information to confirm that.”

## 11. Roadmap phases

The original roadmap names stages **0 through 6** (seven numbered stages).

| Phase | Current status | What closes the remaining gap |
|---|---|---|
| **0 — Foundation** | **DONE** | maintain release/host evidence |
| **1 — Guardian** | **PARTIAL** | close capability #1/#11 scam and ATTACK-policy gaps |
| **2 — Data** | **DONE** for local architecture | remote DB remains optional FUTURE |
| **3 — Intelligence** | **PARTIAL** | richer router/pattern intelligence and review workflow |
| **4 — Community OS** | **DONE** baseline | future channel/editorial enhancements |
| **5 — Operations** | **PARTIAL** | admin management UI + remaining observability only if justified |
| **6 — Autonomous Operations** | **PARTIAL / deliberately constrained** | policy-versioning, observe-first evidence, kill switches and explicit approval for each autonomous class |

The project is no longer “between Phase 0 and Phase 1.” That historical statement is obsolete.

## 12. Controlled autonomy requirements

Any new autonomous behavior must satisfy all of these before action mode:

1. explicit named policy;
2. deterministic or tightly bounded authority;
3. observe-only trial first;
4. measurable false-positive review;
5. audit/action ledger record;
6. policy version or equivalent immutable evidence;
7. kill switch;
8. human escalation path;
9. safe degradation when AI/network/database is impaired;
10. deliberate production activation separate from code merge.

## 13. Threat model

Primary threats include:

- flood/spam and coordinated raids;
- phishing/scams and lookalike domains;
- administrator impersonation;
- wallet/seed/private-key exposure;
- prompt injection;
- stolen Telegram/Mistral/SSH credentials;
- compromised admin account;
- Telegram/provider/DNS/network outage;
- SQLite corruption or wrong-database operation;
- disk exhaustion;
- duplicated scheduler delivery;
- abusive automation;
- false-positive moderation;
- local Git/release-state tampering;
- secret/config contamination during deployment.

Current controls include deterministic enforcement, observe-only AI, secret redaction, explicit admin authorization, local transactional persistence, action/incident ledgers, rate limits, circuit breakers, health gates, systemd recovery, Wi-Fi recovery, release/runtime/environment/Git boundaries and CI.

## 14. Current release boundary

The **development** line contains Blocks 1–5. That does not mean production has been upgraded.

Production release work is governed separately by:

- `docs/DEPLOYMENT-MODEL.md`
- `docs/GITHUB-DEPLOY-GATES.md`
- `docs/V1.1-RELEASE-AUDIT.md`
- `docs/V1.1-FIRST-UPGRADE.md`

External host/control-plane checks must never be marked DONE merely because repository CI is green.

## 15. Priority backlog derived from this plan

The remaining product work, in dependency order, is:

1. finish and integrate the v1.1 release gate without deploying;
2. complete external GitHub branch/ruleset protection;
3. perform real Acer/Tailscale/SSH/runtime/DB acceptance;
4. execute the controlled v1 → v1.1 release only after explicit authorization;
5. complete versioned policy-engine semantics (#23);
6. close Guardian/scam intelligence gaps (#1/#11);
7. complete operating-state lifecycle semantics;
8. decide whether richer admin UI/metrics are operationally justified;
9. only then expand controlled autonomy.

Do not start advanced autonomy merely to increase feature count.

## 16. Definition of ZION complete

The target described by this plan is complete when:

- every capability above is DONE or explicitly moved to FUTURE with a written reason;
- all irreversible actions have deterministic or identified-human authority;
- AI remains bounded and auditable;
- product answers are grounded;
- criticism remains protected;
- incidents/actions can reconstruct important moderation decisions;
- health and degraded behavior are explicit;
- production deployment/rollback is reproducible;
- host/control-plane acceptance has real evidence;
- autonomous policies have observe-only evidence and kill switches;
- the production release matches the reviewed repository state.

Until then, “complete” refers only to a named block/phase/capability, never to the entire ZION system.

---

This file is the architectural and roadmap source of truth for ZION. Update its status matrix only in the same reviewed change that supplies the corresponding code/tests/evidence.
