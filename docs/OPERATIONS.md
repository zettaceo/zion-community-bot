# ZION Operations Runbook

## Production filesystem boundary

The v1.1 production service treats these areas differently:

```text
/home/zetta/zion-community-bot/                         code + .env, read-only to service
/home/zetta/.local/share/zion-community-bot/runtimes/  versioned Python runtimes, read-only to service
/home/zetta/.local/state/zion-community-bot/           mutable DB/log/lock/state, writable
/home/zetta/.local/share/zion-community-bot/deploy-backups/ verified rollback evidence, not writable by service
```

The service must not need write permission to its code, release scripts, `.env` or Python environment.

## Audited runtime dependencies

Production release validation uses the exact package set in `requirements.lock`. A runtime that merely falls inside the broader `requirements.txt` ranges is not sufficient for the audited v1.1 release.

`scripts/prepare-release-runtime.sh` builds/verifies the approved SHA runtime before downtime. `scripts/check-runtime.py` verifies the lock, rejects unexpected distributions and `python -m pip check` verifies dependency consistency. Package changes require a reviewed lock update and a new CI pass; do not mutate the runtime used by the currently running service.

## Controlled update flow

Do not run a manual second polling process while systemd is running.

Do **not** use `git pull && restart` as a production deployment procedure.

Remote production updates are commit-pinned and follow `docs/DEPLOYMENT-MODEL.md`:

1. merge an explicitly reviewed production PR into `zion-v1`;
2. fetch `origin/zion-v1` without changing the running worktree;
3. record the exact 40-character production SHA;
4. run `scripts/deployment-preflight.sh`;
5. run `scripts/verify-approved-release.sh` while the current bot remains online;
6. only then stop the service and fast-forward local `zion-v1-prod`;
7. run `scripts/apply-zion-v1.sh` with `ZION_EXPECTED_COMMIT` and the previous commit recorded for rollback;
8. complete host + Telegram acceptance.

`scripts/apply-zion-v1.sh` refuses an unpinned or non-production-ref commit.

For the first production transition from the current v1 commit to v1.1, the strict gate scripts are not yet present in the old production checkout. Use the detached-candidate bootstrap in `docs/V1.1-FIRST-UPGRADE.md`; do not skip the gates or fast-forward production merely to obtain the scripts.

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

The production Mistral key is not stored in `.env`. `MISTRAL_API_KEY` is deprecated and must remain empty. The secret path is fixed by code at `/home/zetta/.local/state/zion-community-bot/secrets/mistral-api-key` and is not configurable through `.env`.

Non-secret production configuration for the current support model:

```text
ZION_AI_ENABLED=true
ZION_AI_OBSERVE=false
ZION_AI_MAX_CONCURRENCY=3
MISTRAL_API_URL=https://api.mistral.ai/v1/chat/completions
MISTRAL_MODEL=ministral-8b-2512
MISTRAL_MIN_REQUEST_INTERVAL_MS=350
MISTRAL_RATE_LIMIT_RETRIES=2
MISTRAL_RATE_LIMIT_MAX_DELAY_SECONDS=5
```

The throughput profile intentionally queues bursts inside ZION: at most three AI calls are in flight and request starts are paced by 350 ms. A provider HTTP 429 is retried a bounded number of times, honoring `Retry-After` when supplied and otherwise using exponential fallback. Only a sanitized allowlist of rate-limit headers may be logged; Authorization and secret material are never logged.

The bot may start with `ZION_AI_ENABLED=true` while the secret is missing; the deterministic Guardian remains active and the Mistral provider reports not configured.

After an authorized v1.1 cutover, an explicit operator provisions the real key through the private chat flow:

1. Open the **private** chat with the official ZION bot.
2. Send `/setmistralkey` with no arguments.
3. Within 120 seconds, send the key as the next text message.
4. ZION deletes that Telegram message before any local persistence. If deletion fails, the key is not stored.
5. ZION validates the credential against the official Mistral API and atomically publishes it into the local protected secret store.
6. Run `/aistatus`; it shows only CONFIGURED/MISSING/UNSAFE state, never key material.
7. Keep `ZION_AI_OBSERVE=false` for the first bounded support-only test.
8. Only after stable behavior is observed may observe-only classification be enabled through the reviewed configuration path.

Rotation repeats `/setmistralkey`; a failed rotation preserves the old valid key. Removal requires `/clearmistralkey CONFIRM`. Neither operation requires a ZION restart.

This flow intentionally sends the secret through Telegram private chat before ZION deletes the message. The application does not persist the value in SQLite/logs/backups. A local/offline procedure is required if the operator needs a channel that never transits Telegram.

Observe-only mode never punishes users.

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

Verified deployment rollback backups are written to `/home/zetta/.local/share/zion-community-bot/deploy-backups/`, outside the bot service's writable repository/state paths.

## AI budget

`ZION_AI_DAILY_TOKEN_BUDGET` limits the software-side daily Mistral budget per UTC day.

Default: `50000`.

Successful calls use recorded provider input+output token counts. If the exact success event cannot be written, the returned provider usage is persisted through the conservative accounting channel so restart cannot erase it. Responses without accountable usage telemetry are rejected instead of being treated as zero-cost success.

For a timeout or other uncertain provider outcome, ZION cannot prove that the provider consumed zero resources, so it conservatively charges the request's reserved token estimate against the same UTC-day software budget. This conservative amount is persisted as internal accounting state, survives restart and rolls over at the UTC-day boundary. Admission reservation uses a conservative UTF-8 byte-based reserve plus fixed wrapper overhead and the output ceiling rather than an average characters-per-token assumption.

If that accounting cannot be read or persisted, AI accounting fails closed and new provider calls are blocked. The deterministic Guardian is unaffected.

Set `0` only if the team intentionally wants no software-side daily token ceiling. Even with an unlimited configured ceiling, failed accounting is reported as unavailable rather than as healthy/unlimited remaining capacity.

Use admin `/aistatus` or `/diagnostics` to inspect current UTC-day usage.

## Mistral circuit breaker

Defaults:

```text
ZION_AI_CIRCUIT_FAILURES=3
ZION_AI_CIRCUIT_SECONDS=120
```

After three consecutive provider failures, ZION pauses Mistral calls for two minutes by default. Failure count and open-until are persisted together in one SQLite transaction so a partial write cannot leave contradictory circuit state across restart. The deterministic Guardian is unaffected.

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

`/diagnostics` is operator-only and reports:
- SQLite quick-check and foreign-key integrity;
- database-file presence;
- current and supported schema version;
- runtime PRAGMA verification and invariant drift;
- ZION application ID;
- SQLite total/DB/WAL/SHM sizes;
- free disk and low-disk threshold state;
- sensitive runtime file permissions;
- configured Wi-Fi interface presence;
- Telegram update-lag latest/p95/sample count and freshness;
- successful Mistral latency average/p95 over 24 hours;
- AI accounting health;
- UTC-day token usage, configured budget and remaining budget;
- Mistral circuit-breaker state and provider failure count;
- scheduler RUNNING/STOPPED state;
- hourly housekeeping status;
- passive WAL checkpoint status;
- temporary-state maintenance status;
- delivery-safety preflight;
- scheduled-delivery health gate and blocking reasons;
- alert-dedup persistence state;
- health-check and unchanged-alert repeat cadence.

Failed disk/schema/latency/SQLite telemetry is shown as UNAVAILABLE or WARNING instead of being rendered as a healthy default.

It never prints API keys, Telegram tokens, provider headers, prompts or user message bodies.

Operational health is checked independently from housekeeping. Default cadence:

```text
ZION_HEALTH_CHECK_INTERVAL_SECONDS=60
ZION_HEALTH_ALERT_REPEAT_SECONDS=21600
```

A changed issue set is eligible immediately. An unchanged active alert that was successfully delivered is repeated only after the configured repeat interval. If every Telegram send fails, the alert is not marked delivered and remains retryable.

This intentionally does not provide exactly-once semantics between Telegram and SQLite. If Telegram accepts a notification and the process crashes before local dedup state is committed, a later duplicate may occur.

The alert signature and last-send timestamp are persisted as one SQLite transaction after a confirmed Telegram delivery. No Telegram I/O occurs inside that transaction. If the write fails, the live runtime preserves the newer in-memory state, marks persistence DIRTY and attempts repair without trusting a stale persisted value.

Incident-ledger persistence is retried independently from notification deduplication, so a successfully delivered alert does not permanently suppress a failed incident write. The active operational incident signature/id are persisted across restart. Recovery resolves the active incident; when the issue signature changes, the prior incident is resolved before the replacement incident becomes active.

Housekeeping and passive WAL checkpoint failures are isolated from the health-alert path. Independent housekeeping steps are isolated from each other, so one failed retention operation does not skip all later cleanup steps.

Before scheduled or recurring sends, ZION performs a delivery-safety preflight that quarantines stale unknown delivery claims. If that quarantine step itself fails, the scheduler fails closed for scheduled/recurring external delivery.

Scheduled delivery also has a critical SQLite health gate. Delivery is blocked when ZION cannot prove database integrity/identity/schema or critical runtime PRAGMAs. If the operational health cycle itself raises unexpectedly, the gate also closes until a later healthy check clears it.

The 60-second scheduler cadence uses a monotonic clock so wall-clock/NTP changes cannot postpone health checks. Retention and audit timestamps continue to use wall-clock UTC semantics.

Telegram lag samples are bounded to 100. Edited messages use the Telegram edit timestamp when present. Old samples remain visible as STALE but do not trigger a current-lag alert.

## AMA retention

Closed AMA question text is pruned according to:

```text
ZION_AMA_RETENTION_DAYS=30
```

## Private remote operations

Bootstrap inventory:

```bash
bash scripts/remote-access-preflight.sh --report-only
```

Strict access gate from a Tailscale SSH session:

```bash
sudo -v
bash scripts/remote-access-preflight.sh
```

From a physical console, set `ZION_TAILSCALE_CLIENT_IP` to the actual approved remote client address so `Match User/Address` policy is evaluated in the intended connection context.

SSH hardening is applied only after a real public-key login is proven:

```bash
ZION_REMOTE_ACCESS_PROVEN=YES \
ZION_HOSTKEY_PROVEN=YES \
  bash scripts/apply-ssh-hardening.sh
```

The installer reloads sshd after `sshd -t`; it does not restart the bot, change Tailscale or change firewall/router policy.

Before a remote deploy, the operator must separately verify GitHub branch protection and router/Tailnet exposure controls and explicitly attest them to `scripts/deployment-preflight.sh`.

Follow:

- `docs/REMOTE-ACCESS.md`
- `docs/GITHUB-DEPLOY-GATES.md`
- `docs/DEPLOYMENT-MODEL.md`


## Tailscale-only SSH host firewall

After SSH hardening and two independent key-only Tailscale sessions pass, the reviewed host firewall can be installed without redefining unrelated host traffic:

```bash
cd /home/zetta/zion-community-bot
sudo -v

ZION_EXPECTED_COMMIT=<reviewed-40-character-zion-v1.1-dev-sha> \
ZION_FIREWALL_CHANGE_AUTHORIZED=YES \
ZION_REMOTE_ACCESS_PROVEN=YES \
ZION_SECOND_SSH_PROVEN=YES \
  bash scripts/apply-ssh-firewall.sh
```

The resulting `inet zion_ssh_guard` table allows TCP/22 only from `lo` and `tailscale0`, then drops TCP/22 on every other IPv4/IPv6 interface. The unit `zion-ssh-firewall.service` keeps that narrow guard across boot. It does not enable UFW, flush nftables, or change non-SSH traffic.

Keep both recovery sessions open and prove a third Tailscale key-only session before closing either one. Then run:

```bash
sudo -v
bash scripts/remote-access-preflight.sh
sudo nft list table inet zion_ssh_guard
```

Router/NAT and Tailnet ACL/device policy remain separate manual/control-plane gates.

## Operational alert cadence

Operational health checks are independent from hourly housekeeping.

Defaults:

```text
ZION_HEALTH_CHECK_INTERVAL_SECONDS=60
ZION_HEALTH_ALERT_REPEAT_SECONDS=21600
```

The first health check and housekeeping pass run on the first scheduler iteration after startup.

An unchanged active condition is not sent on every health check. ZION records the alert signature and last successful-send time, then repeats the unchanged delivered alert only after the repeat interval.

A changed issue set is eligible immediately. When all tracked issues clear, explicit operators receive a recovery notification. Failed alert or recovery delivery remains retryable.


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


## SQLite persistence hardening

At runtime, pre-existing `zion.db`, `zion.db-wal`, `zion.db-shm` and active log files must be regular files with exactly one hard link. Symlink/hardlink state is rejected rather than normalized. This complements the private state directory and prevents a prepared filesystem alias from being treated as ordinary ZION mutable state.

ZION v1.1 treats SQLite as critical runtime state.

Runtime invariants:

```text
journal_mode=WAL
synchronous=FULL
foreign_keys=ON
trusted_schema=OFF
busy_timeout=5000ms
wal_autocheckpoint=1000 pages
journal_size_limit=16777216 bytes
application_id=0x5A494F4E ("ZION")
```

A new database receives the ZION application ID before schema creation. A recognizable legacy ZION database with application ID zero can be adopted during migration. A non-empty SQLite database that does not match a known ZION schema is rejected before ZION creates any tables in it.

The runtime performs `quick_check + foreign_key_check` during startup and refuses to operate when either fails. Runtime health repeats the lightweight integrity check on the configured health cadence, capped at five minutes; with the default 60-second health interval, integrity/FK state is refreshed every 60 seconds. Deployment and backup gates use the full `integrity_check`.

Schema migrations are versioned and a database with a schema newer than the running ZION build is rejected before mutation. Each migration version is committed atomically.

Multi-write persistence paths use explicit transactions. If an SQL statement or the final COMMIT fails, the transaction is rolled back before the connection is reused.

### Verified backup

The controlled deploy uses the SQLite backup API while production is still running. The candidate code verifies the source database, writes a consistent snapshot, runs full integrity and foreign-key checks on the snapshot, applies mode 0600, and records its SHA-256 before production can be stopped.

Backups can be checked without modifying them:

```bash
.venv/bin/python scripts/verify-sqlite-backup.py /path/to/zion.db --sha256 <expected-sha256>
```

The verifier checks SHA-256 when supplied, full SQLite integrity, foreign-key integrity and schema compatibility.

### Bounded persistence growth

Defaults:

```text
ZION_AI_EVENT_RETENTION_DAYS=90
ZION_COMPLETED_JOB_RETENTION_DAYS=30
ZION_DB_WARN_MB=512
ZION_WAL_WARN_MB=128
```

Hourly housekeeping prunes expired idempotency keys, bounded user events and knowledge gaps, old AI metadata, expired containments, closed AMA question/session data and completed one-shot jobs.

One-shot jobs in `uncertain` state are deliberately **not** auto-pruned. They represent an unknown external delivery outcome and require operator resolution.

Incidents/actions are not silently deleted by this housekeeping policy because they are the audit ledger. Database and WAL growth thresholds surface through `/diagnostics` and operational alerts instead of silently destroying audit history.

ZION does not run automatic `VACUUM` in production. A passive WAL checkpoint is used; if a reader prevents checkpoint progress, WAL growth is surfaced as an alert rather than forcing a blocking maintenance operation.
