# ZION Community OS

ZION is the community operating layer for Z-SWAP.

It combines deterministic moderation, persistent incident/action history, support, community operations and a controlled Mistral AI layer.

## Safety model

**AI interprets. Deterministic rules or authorized humans execute irreversible moderation.**

Mistral classification is observe-only by default and cannot delete, mute or ban users.

Criticism and disagreement are allowed.

## Current architecture

- Telegram: python-telegram-bot
- Persistence: SQLite/WAL
- AI: Mistral Chat Completions API
- Knowledge: approved local Markdown + retrieval
- Runtime: systemd
- Network resilience: DNS readiness gate + USB Wi-Fi Guardian
- Tests: stdlib unittest
- Secret handling: environment variables + log redaction
- Optional admin dashboard: read-only localhost HTTP

See [ZION-MASTER-PLAN.md](ZION-MASTER-PLAN.md).

## Local setup

```bash
cd ~/zion-community-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
```

Edit `.env` locally. Never commit or paste real credentials.

At minimum:

```text
TELEGRAM_BOT_TOKEN=<local secret>
ZION_ADMIN_USER_IDS=<your numeric Telegram user id>
```

Mistral remains disabled unless:

```text
MISTRAL_API_KEY=<local secret>
ZION_AI_ENABLED=true
```

Keep `ZION_AI_OBSERVE=false` for the first AI support test.

## Validate

```bash
bash scripts/validate.sh
```

## Deploy modular v1 after review

```bash
bash scripts/apply-zion-v1.sh
```

The script validates first and only then restarts systemd.

## Commands

Member/basic:

- `/start`
- `/rules`
- `/status`
- `/id`
- `/ask <question>`
- `/summary`
- `/translate`
- `/report` as a reply
- `/ama <question>` when an AMA is open

Admin:

- `/health`
- `/guardian`
- `/aistatus`
- `/stats`
- `/brief`
- `/gaps`
- `/resolvegap <hash>`
- `/incidents [limit]`
- `/incident <id-prefix>`
- `/resolveincident <id-prefix>`
- `/strikes`
- `/user` as a reply or with numeric ID
- `/state [STATE]`
- `/warn [reason]` as a reply
- `/mute 10m` as a reply
- `/ban` as a reply
- `/unban <user_id>`
- `/announce <message>`
- `/poll Question | Option 1 | Option 2`
- `/lockdown`
- `/unlock`
- `/allowdomain example.com`
- `/blockdomain example.com`
- `/schedule <ISO8601-with-timezone> <message>`
- `/recurring <interval> <ISO8601-with-timezone> <message>`
- `/cancelrecurring <id>`
- `/amaopen <tema>`
- `/amalist`
- `/amaclose`
- `/diagnostics`
- `/reloadkb`

## Source of truth

- Architecture: `ZION-MASTER-PLAN.md`
- Moderation policy: `docs/POLICIES.md`
- Security: `docs/SECURITY.md`
- Operations: `docs/OPERATIONS.md`
- Approved support facts: `knowledge/`

Runtime files and secrets are intentionally excluded from Git.

## Optional local dashboard

The dashboard is intentionally bound to localhost only and is read-only.

After review:

```bash
bash scripts/apply-dashboard.sh
```

Open `http://127.0.0.1:8765/` on the ZION machine.

It exposes aggregate health/counters only; moderation writes remain behind Telegram admin authorization.

## AI cost guardrails

Mistral calls are bounded by per-user request limits, global concurrency and a daily combined token budget. The default is 50,000 prompt+completion tokens per UTC day and can be changed with `ZION_AI_DAILY_TOKEN_BUDGET`; `0` means unlimited.

Observe-only moderation has its own per-user limiter so one member cannot consume the entire AI budget simply by posting repeatedly.

## Mistral circuit breaker

After the configured number of consecutive provider failures, ZION temporarily stops sending new Mistral requests.

Defaults:

- `ZION_AI_CIRCUIT_FAILURES=3`
- `ZION_AI_CIRCUIT_SECONDS=120`

The breaker state is persisted in SQLite, so restarting the bot does not immediately hammer an unavailable provider again. A successful provider call resets the failure counter.

## Privacy retention

Only explicit `/ask` questions that cannot be answered from approved knowledge are retained as knowledge-gap samples. They are sanitized before storage and expire according to `ZION_KNOWLEDGE_GAP_RETENTION_DAYS` (default: 30 days).

Resolved/ignored user-report details are redacted after `ZION_REPORT_RETENTION_DAYS` (default: 90 days), while the minimal incident/audit row is preserved.

## Admin roles

ZION distinguishes two privilege levels:

- **Chat moderator**: Telegram owner/administrator in the current group, or an explicitly configured ZION operator. Can perform chat-local moderation and community operations such as warn/mute/ban, announcements, polls and scheduling.
- **ZION operator**: user ID explicitly listed in `ZION_ADMIN_USER_IDS`. Required for global/system controls and telemetry such as state/lockdown, domain policy, incidents, Mistral status/budget, knowledge gaps and knowledge reload.

This prevents an administrator from an unrelated group from changing global ZION policy.


## ZION v1.1 development

The v1.1 branch extends the modular baseline without granting AI punitive authority.

New development surfaces include:
- bilingual PT-BR/EN onboarding and help;
- recurring announcements;
- AMA question collection with bounded retention;
- section-level knowledge source labels;
- stronger prompt-injection boundaries;
- Unicode/IDNA link normalization;
- distributed chat-burst detection that only raises temporary ELEVATED mode;
- SQLite quick-check, DB size, Telegram update-lag and AI latency diagnostics;
- deduplicated operational alerts to explicit ZION operators;
- private Tailscale + SSH remote-access runbook.

Operational alerts are deduplicated and unchanged active conditions are reminded no more often than `ZION_HEALTH_ALERT_REPEAT_SECONDS` (default: 6 hours).

Production remains on the explicitly deployed stable commit until a separate review and cutover is approved.
