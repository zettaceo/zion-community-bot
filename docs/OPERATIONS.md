# ZION Operations Runbook

## Normal update flow

Do not run a manual second polling process while systemd is running.

Recommended deployment flow:

```bash
sudo systemctl stop zion.service
git pull
bash scripts/validate.sh
sudo systemctl start zion.service
systemctl status zion.service --no-pager --full
```

For the v1 modular migration, use `scripts/apply-zion-v1.sh` after review.

## Health checks

Telegram:

`/status`

`/health`

Admin:

`/diagnostics`

`/stats`

`/incidents`

`/aistatus`

Linux:

```bash
systemctl show zion.service -p NRestarts -p ActiveState -p SubState -p ExecMainStartTimestamp
systemctl status zion-wifi-guardian.timer --no-pager
```

## Mistral activation

1. Store the Mistral key in local `.env`; never paste it into chat or commit it.
2. Set `ZION_AI_ENABLED=true`.
3. Keep `ZION_AI_OBSERVE=false` for the first support-only test.
4. Validate `/aistatus` and `/ask`.
5. Only after observing stable behavior, enable `ZION_AI_OBSERVE=true`.
6. Observe-only mode never punishes users.

## Emergency

If moderation behaves unexpectedly:

```bash
sudo systemctl stop zion.service
```

The database and legacy state remain on disk.

If the AI provider is problematic, disable only:

```text
ZION_AI_ENABLED=false
ZION_AI_OBSERVE=false
```

The deterministic Guardian remains available.

## Database

Default local DB:

`/home/zetta/zion-community-bot/zion.db`

SQLite runs in WAL mode. Runtime DB/WAL/SHM files are ignored by Git.

The old `zion_state.json` is imported once into SQLite when modular v1 first starts; the original file is preserved.

## Backup

A future remote backup target can be added after deciding retention/privacy policy. Until then, do not upload the SQLite file to public storage.

## AI budget

`ZION_AI_DAILY_TOKEN_BUDGET` limits combined recorded Mistral input+output tokens per UTC day.

Default: `50000`.

Set `0` only if the team intentionally wants no software-side daily token ceiling.

Use admin `/aistatus` to inspect current UTC-day usage.

## Mistral circuit breaker

Defaults:

```text
ZION_AI_CIRCUIT_FAILURES=3
ZION_AI_CIRCUIT_SECONDS=120
```

After three consecutive provider failures, ZION pauses Mistral calls for two minutes by default. State is persisted in SQLite. The deterministic Guardian is unaffected.

Admin `/aistatus` shows:
- breaker open/closed;
- remaining open time;
- current consecutive failure count;
- daily token use.

## Privacy housekeeping

The scheduler runs housekeeping approximately hourly.

Defaults:

```text
ZION_KNOWLEDGE_GAP_RETENTION_DAYS=30
ZION_REPORT_RETENTION_DAYS=90
```

Knowledge-gap samples older than the configured retention are deleted. Resolved/ignored community reports have their free-text note and evidence redacted after retention, while the minimal incident/audit row is preserved. Open reports are retained.


## v1.1 diagnostics

`/diagnostics` reports:
- SQLite quick-check status;
- SQLite/WAL/SHM aggregate size;
- free disk and low-disk threshold state;
- sensitive runtime file permissions;
- configured Wi-Fi interface presence;
- recent Telegram update-lag latest/p95 sample;
- successful Mistral latency average/p95 over 24 hours.

The hourly scheduler deduplicates operational alerts so unchanged conditions do not create repeated notifications.

## AMA retention

Closed AMA question text is pruned according to:

```text
ZION_AMA_RETENTION_DAYS=30
```

## Private remote operations

Use `scripts/remote-access-preflight.sh` for a read-only host check after physical access is available.

Follow `docs/REMOTE-ACCESS.md` for Tailscale + SSH setup and `docs/DEPLOYMENT-MODEL.md` for the deployment trust boundary.


## Operational alert cadence

Unchanged active operational conditions are not sent on every hourly health cycle. ZION records the alert signature and last-send time, then repeats an unchanged active alert only after `ZION_HEALTH_ALERT_REPEAT_SECONDS` (default: 21600 seconds / 6 hours).

A changed issue set is alerted immediately. When all tracked issues clear, explicit operators receive one recovery notification.


## Runtime and concurrency hardening

ZION v1.1 uses a cross-worktree kernel file lock at a private per-user path. Only one writable ZION runtime may hold that lock at a time. The lock file is required to be a regular, non-symlinked, non-hard-linked file with private permissions, and its descriptor is non-inheritable.

The scheduler also refuses to create a second live scheduler task inside one application process.

### Delivery claim state machine

One-shot delivery:

```text
pending -> sending -> sent
                   -> pending   (bounded retry after confirmed failure)
                   -> failed    (retry budget exhausted)
sending -> uncertain            (process crash / stale unknown outcome)
```

Recurring delivery:

```text
active -> sending -> active
                  -> active     (bounded retry after confirmed failure)
                  -> paused     (failure threshold reached)
sending -> paused               (process crash / stale unknown outcome)
```

A job is atomically claimed in SQLite before the Telegram API call. Another worker cannot claim the same due job.

An unknown outcome is **never replayed automatically**. If ZION dies after claiming a delivery, the next runtime quarantines that one-shot as `uncertain` and pauses the recurring job. This intentionally prefers a missed delivery over an accidental duplicate.

For a recurring job paused because of an unknown crash outcome, `/resumerecurring` skips the uncertain occurrence and preserves the next future interval.

For a one-shot `uncertain` job, an operator must inspect `/jobs` and explicitly choose whether to cancel it or run `/retryscheduled`. An explicit retry can duplicate a delivery that Telegram accepted before the crash but that ZION could not confirm.

Default stale-claim timeout while the process remains alive:

```text
ZION_DELIVERY_CLAIM_TIMEOUT_SECONDS=300
```

### Command idempotency

Telegram command update IDs are persisted before command side effects. A redelivered command update is suppressed across process restarts. This is an at-most-once boundary for command execution.

Idempotency keys expire and are pruned by housekeeping. Default retention:

```text
ZION_IDEMPOTENCY_RETENTION_DAYS=30
```
