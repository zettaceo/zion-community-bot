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
- `/health`
- `/id`
- `/ask <question>`
- `/aistatus`
- `/summary`
- `/translate`
- `/report` as a reply

Admin:

- `/stats`
- `/gaps`
- `/resolvegap <hash>`
- `/incidents [limit]`
- `/user` as a reply or with numeric ID
- `/state [STATE]`
- `/warn [reason]` as a reply
- `/mute 10m` as a reply
- `/ban` as a reply
- `/lockdown`
- `/unlock`
- `/allowdomain example.com`
- `/blockdomain example.com`
- `/schedule <ISO8601-with-timezone> <message>`
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
