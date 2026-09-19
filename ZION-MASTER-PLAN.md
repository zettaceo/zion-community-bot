# ZION — MASTER PLAN

Status: implementation baseline for ZION v1  
AI provider: **Mistral AI**  
Principle: **AI interprets; deterministic policy or authorized humans execute irreversible moderation.**

## Mission

ZION is the community operating system for Z-SWAP. It is not only a Telegram moderation bot.

Its target responsibilities are:

1. Guardian — safety and deterministic moderation.
2. Support — answer questions from approved knowledge.
3. Community — onboarding, reports, announcements and member assistance.
4. Intelligence — Mistral-based classification, Q&A and future summarization.
5. Operations — health, audit, incidents, admin commands and observability.

## Invariants

1. Criticism is allowed and is not automatically classified as FUD.
2. AI never independently deletes, mutes or bans in v1.
3. Every punitive action must have a deterministic rule or identified human actor.
4. Every relevant action must be auditable.
5. Secrets must not be logged.
6. User message bodies should not be persisted unless a future feature has an explicit necessity and retention policy.
7. The Guardian must continue when Mistral is unavailable.
8. Private chat does not confer administrator privilege.
9. Product answers must be grounded in approved Z-SWAP knowledge.
10. Unknown product facts are acknowledged as unknown rather than invented.

## Architecture

```text
Telegram / future channels
        |
        v
Event ingestion
        |
        +--> Deterministic Guardian
        |      flood
        |      links/domains
        |      wallet-secret protection
        |      containment
        |      lockdown
        |
        +--> Mistral Intelligence
        |      /ask
        |      observe-only classification
        |      future summarization
        |
        v
Policy boundary
        |
        v
Action engine
 delete / warn / mute / ban / escalate / reply
        |
        v
SQLite persistence
 users / strikes / incidents / actions / AI events / settings
        |
        v
Admin + health + audit
```

## Operating states

- NORMAL
- ELEVATED
- ATTACK
- LOCKDOWN
- DEGRADED_AI
- DEGRADED_NETWORK
- MAINTENANCE
- SAFE_MODE

v1 actively implements NORMAL and LOCKDOWN and models the complete state set for future transitions.

## Guardian

Implemented baseline:

- persistent users;
- persistent recent-message window;
- persistent strikes;
- persistent containments;
- flood escalation;
- deletion of tracked recent flood messages;
- Telegram mute;
- repeat-flood ban;
- link/domain policy;
- high-confidence possible wallet-secret exposure removal;
- action ledger;
- incident ledger;
- manual lockdown.

## Identity and reputation

ZION stores factual operational history, not a single social-credit score.

User summary includes:
- observed message count;
- active strikes;
- incident count;
- active containment.

Future reputation features must retain separate evidence categories rather than compressing a member into one opaque score.

## Mistral AI

Provider is fixed to Mistral for the current design.

Default endpoint:
`POST https://api.mistral.ai/v1/chat/completions`

Default model:
`mistral-small-latest`

Environment:
- `MISTRAL_API_KEY`
- `MISTRAL_API_URL`
- `MISTRAL_MODEL`
- `ZION_AI_ENABLED`
- `ZION_AI_OBSERVE`

Use cases:
- grounded support Q&A;
- observe-only moderation classification;
- future conversation summaries;
- future FAQ gap discovery;
- future operator briefs.

The API key never belongs in Git.

## Knowledge / RAG

v1 ships a local Markdown knowledge base and lexical retrieval.

This intentionally avoids an external vector database in the first modular release.

Contract:
- approved facts only;
- source sections supplied to Mistral;
- if retrieval cannot support an answer, ZION says it cannot confirm;
- `/reloadkb` reloads Markdown after an admin edit.

Future:
- embeddings;
- versioned source registry;
- freshness dates;
- source citations in Telegram replies;
- Supabase/pgvector if justified.

## Admin command surface

Public/basic:
- `/start`
- `/rules`
- `/status`
- `/health`
- `/id`
- `/ask`
- `/aistatus`
- `/report`

Admin:
- `/stats`
- `/incidents`
- `/user`
- `/warn`
- `/mute`
- `/ban`
- `/lockdown`
- `/unlock`
- `/allowdomain`
- `/blockdomain`
- `/schedule`
- `/reloadkb`

## Community operations

v1 includes a persistent announcement scheduler.

An administrator can schedule a Telegram message with an explicit ISO-8601 timezone.

The scheduler loop checks due messages without requiring the optional python-telegram-bot JobQueue dependency.

Future:
- recurring announcements;
- polls;
- AMA collection;
- daily/weekly briefs;
- unanswered-question mining;
- admin approval queues.

## Data model

SQLite v1 tables:

- users
- user_events
- strikes
- containments
- recent_messages
- incidents
- actions
- domains
- settings
- ai_events
- scheduled_messages

Migration to PostgreSQL/Supabase remains possible because data access is centralized in `zion/db.py`.

## Observability

v1 exposes:
- database health;
- process uptime;
- operating state;
- configured Mistral state;
- Wi-Fi interface presence;
- free disk;
- user/strike/incident/action/AI-event counts.

System-level resilience already includes:
- systemd process supervision;
- DNS readiness gate;
- USB Wi-Fi Guardian.

Future observability:
- latency percentiles;
- Telegram update lag;
- Mistral availability window;
- cost/token budgets;
- disk thresholds;
- alert delivery;
- structured metrics exporter.

## Threat model

Primary threats:
- flood/spam;
- phishing/scams;
- admin impersonation;
- secret exposure;
- prompt injection;
- stolen Telegram/Mistral credentials;
- compromised admin account;
- bot API outage;
- DNS/network outage;
- database corruption;
- abusive automation;
- false-positive moderation.

Controls:
- deterministic enforcement;
- AI observe-only;
- secret redaction;
- explicit admin authorization;
- local persistence;
- action ledger;
- rate limiting;
- safe degradation;
- systemd recovery;
- Wi-Fi recovery;
- CI/tests before deployment.

## Delivery phases

### Phase 0 — Foundation
Implemented:
- systemd;
- DNS readiness;
- secret-safe logging;
- persistent local state;
- Wi-Fi Guardian.

### Phase 1 — Guardian
Implemented in modular v1:
- SQLite persistence;
- flood/strike/containment engine;
- links;
- wallet-secret protection;
- incidents/actions;
- admin moderation;
- lockdown.

### Phase 2 — Data
Implemented baseline:
- normalized local schema;
- user history;
- incidents;
- action ledger;
- AI events;
- runtime settings;
- legacy JSON migration.

Future:
- PostgreSQL/Supabase migration after operational evidence justifies it.

### Phase 3 — Intelligence
Implemented baseline:
- Mistral client;
- grounded /ask;
- observe-only classifier;
- hashed AI-event input;
- concurrency and per-user request controls.

Future:
- summaries;
- FAQ discovery;
- embeddings;
- richer human-review queue.

### Phase 4 — Community OS
Implemented baseline:
- onboarding;
- reports;
- knowledge support;
- scheduled messages.

Future:
- recurring content;
- polls;
- AMA workflows;
- richer bilingual templates.

### Phase 5 — Operations
Implemented baseline:
- /health;
- /stats;
- /incidents;
- /user;
- local runbooks;
- CI validation.

Future:
- authenticated web admin UI;
- remote metrics;
- alerting.

### Phase 6 — Controlled autonomy
Not authorized by default.

Any future autonomous action must:
1. have an explicit policy;
2. start in observe-only;
3. measure false positives;
4. maintain an audit record;
5. provide a kill switch;
6. define human escalation;
7. degrade safely when AI/network/database fail.

## Definition of done for modular v1

- modular package compiles;
- unit tests pass;
- secrets remain excluded/redacted;
- legacy state can migrate;
- current systemd entrypoint remains `bot.py`;
- Guardian works without Mistral;
- Mistral remains disabled until explicitly configured;
- AI observe mode cannot perform punitive actions;
- admin private-chat access requires explicit ID;
- deployment script validates before restart.

This document is the architectural source of truth for ZION v1.
