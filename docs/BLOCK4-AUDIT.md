# ZION — Block 4 Operations and Audit Hardening

Status: **development only / draft review**  
Base branch: `zion-v1.1-dev`  
Base SHA: `51c23211eb9474690aca00ddf13f6f556ff81fe2`  
Working branch: `audit/block4-operations`

## Scope

Block 4 is limited to operations and auditability:

- SQLite integrity and runtime invariants;
- DB/WAL/SHM sizing and disk thresholds;
- Telegram update lag;
- Mistral latency;
- AI accounting, daily budget and circuit breaker visibility;
- operational alerts;
- operator-only `/diagnostics`;
- read-only localhost dashboard;
- hourly housekeeping observability.

No production deployment, runtime secret change, real Mistral call or production SQLite mutation belongs to this block.

## Findings

### HIGH — maintenance failure could suppress health alerts

The hourly scheduler ran housekeeping and WAL maintenance before the operational alert cycle inside the same outer exception boundary. A persistence or housekeeping exception could therefore skip the health alert that should report the degraded state.

**Hardening:** hourly maintenance is isolated from operational alert evaluation. Housekeeping and passive WAL checkpoint failures are captured as runtime health state and the alert cycle still runs.

### HIGH — failed Telegram alert could be marked as delivered

The previous deduplication state advanced even when every operator delivery failed. A transient Telegram outage could therefore suppress retries for the configured repeat interval.

**Hardening:** an alert/recovery advances the deduplication state only after at least one external Telegram delivery is confirmed successful. If no operator receives it, the state remains eligible for retry.

This is not an exactly-once guarantee. If Telegram accepts a notification and the process crashes before local persistence, a later duplicate notification is acceptable. Operational monitoring prefers a possible duplicate over silent loss.

### MEDIUM — SQLite PRAGMA observation failed open

A failed runtime-PRAGMA read produced sentinel values such as `unknown`, `-1` and `0`, while the alert path tolerated several of those sentinels.

**Hardening:** diagnostics now distinguishes PRAGMA read failure from valid values and verifies the documented runtime invariants:

- `journal_mode=WAL`
- `foreign_keys=ON`
- `synchronous=FULL`
- `trusted_schema=OFF`
- `application_id=0x5A494F4E`
- `busy_timeout>=5000ms`
- `wal_autocheckpoint=1000`
- `journal_size_limit=16777216`

An unavailable PRAGMA read is an operational issue rather than a healthy unknown state.

### MEDIUM — dashboard integrity semantics were weaker than runtime health

The localhost dashboard used `PRAGMA quick_check` without the foreign-key integrity check used by the runtime HealthService.

**Hardening:** the dashboard uses `verify_integrity(full=False)`, including foreign-key integrity, and reports DB/WAL/SHM sizing separately while preserving the existing aggregate size field.

## Diagnostics

Operator-only `/diagnostics` now exposes, without secrets:

- SQLite quick check and FK integrity;
- runtime PRAGMA verification state and drift list;
- application ID, WAL, synchronous mode, trusted schema and timeout settings;
- total/DB/WAL/SHM sizes;
- disk and sensitive-file state;
- Telegram update lag latest/p95 over the bounded in-memory sample;
- successful Mistral latency avg/p95 over 24h;
- AI enabled/provider-ready state;
- AI accounting state;
- UTC token usage, configured budget and remaining budget;
- circuit breaker state and remaining open time;
- consecutive provider failure count.

It does not expose API keys, Telegram tokens, headers, prompts or message bodies.

## Operational alert semantics

Operational notifications are at-least-retryable, not exactly-once.

- A changed issue set is eligible immediately.
- An unchanged successfully delivered issue set is bounded by the configured repeat interval.
- A notification for which every Telegram send fails is **not** marked delivered.
- A recovery notification follows the same rule.
- Local persistence failure after a successful Telegram send may cause a later duplicate.
- No Telegram I/O occurs inside SQLite transactions.

## Hourly maintenance boundary

Housekeeping and WAL checkpoint are maintenance operations. Their failure must not disable monitoring.

The runtime records the most recent maintenance error type in memory and surfaces a generic operational issue. Raw exception text is not included in the Telegram alert.

A successful later maintenance cycle clears the corresponding runtime error state.

## Tests added

Block 4 regression coverage includes:

- PRAGMA read failure fails closed;
- application ID zero is not healthy after runtime initialization;
- PRAGMA failure reaches operational alerts;
- failed alert delivery remains retryable;
- successful alert delivery remains deduplicated;
- failed recovery delivery remains retryable;
- housekeeping failure does not block health alerts;
- deliberately disabled AI does not create provider/circuit false alerts;
- `/diagnostics` reports AI budget/circuit/accounting state without exposing the configured key;
- Telegram update-lag sampling remains bounded and non-negative;
- dashboard database health fails on foreign-key corruption.

## Residual host/live validation

These checks still require the controlled Acer/Telegram gate before production:

- actual filesystem permissions and free-disk behavior;
- real production DB/WAL/SHM growth patterns;
- real Telegram update-lag distribution;
- operator DM delivery during a real Telegram network interruption;
- dashboard localhost binding on the host;
- passive WAL checkpoint behavior with real concurrent readers;
- Mistral latency/budget telemetry only after a future explicitly approved AI activation.

## Production boundary

This branch must not be merged to `zion-v1` as part of Block 4 work.

Production remains a separate deployment decision with backup, host validation, Telegram live gates and rollback preparation.
