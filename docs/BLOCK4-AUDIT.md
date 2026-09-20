# ZION — Block 4 Operations and Audit Hardening

Status: **development only / draft review**  
Base branch: `zion-v1.1-dev`  
Base SHA: `51c23211eb9474690aca00ddf13f6f556ff81fe2`  
Working branch: `audit/block4-operations`

## Scope

Block 4 is limited to operations and auditability:

- SQLite integrity, identity, schema and runtime invariants;
- DB/WAL/SHM sizing and disk thresholds;
- Telegram update lag;
- Mistral latency and conservative budget accounting;
- AI accounting and circuit-breaker visibility;
- operational alerts and recovery notifications;
- scheduler safety and scheduled-delivery health gates;
- operator-only `/diagnostics`;
- read-only localhost dashboard;
- hourly housekeeping observability.

No production deployment, runtime secret change, real Mistral call or production SQLite mutation belongs to this block.

## Findings and hardening

### HIGH — maintenance failure could suppress health alerts

The hourly scheduler previously ran housekeeping and WAL maintenance before the operational alert cycle inside the same outer exception boundary. A maintenance or persistence exception could therefore skip the health check that should report degradation.

**Hardening:** housekeeping, passive WAL checkpoint and operational monitoring are isolated. Independent housekeeping steps are also isolated from one another.

### HIGH — failed Telegram alert could be marked delivered

The previous alert deduplication state could advance even when every operator delivery failed. A transient Telegram outage could therefore suppress retries for the configured repeat interval.

**Hardening:** alert/recovery dedup advances only after at least one confirmed Telegram delivery.

This deliberately does **not** claim exactly-once. If Telegram accepts a notification and the process crashes before local persistence, a later duplicate remains possible. Monitoring prefers a possible duplicate over silent loss.

### HIGH — stale-delivery safety failure could leave scheduled delivery fail-open

Stale or unknown Telegram delivery claims are a safety boundary. If the quarantine check itself fails, the runtime cannot prove that replay is safe.

**Hardening:** a deterministic scheduler safety preflight now:

1. attempts temporary operating-state expiry;
2. quarantines stale/unknown delivery claims;
3. blocks scheduled/recurring external sends when the delivery-safety check fails;
4. exposes the failure in diagnostics and operational alerts;
5. attempts an immediate alert for a newly observed preflight failure.

A successful quarantine remains authoritative even if writing its audit incident later fails.

### HIGH — critical SQLite health did not gate scheduled external effects

Operational monitoring could detect database identity/integrity failures while the scheduler continued sending due messages.

**Hardening:** scheduled/recurring external delivery now has a fail-closed health gate. Delivery is blocked when ZION cannot prove critical SQLite invariants, including:

- database/integrity health;
- database file presence;
- foreign-key integrity;
- readable and supported schema version;
- readable critical PRAGMAs;
- WAL mode;
- foreign-key enforcement;
- FULL synchronous mode;
- trusted schema disabled;
- correct ZION application ID.

If the operational health cycle itself raises unexpectedly, scheduled delivery is blocked until a later healthy check clears the gate.

### MEDIUM — SQLite PRAGMA observation failed open

A failed runtime-PRAGMA read produced sentinels such as `unknown`, `-1` and `0`, while parts of the alert path tolerated those values.

**Hardening:** diagnostics distinguishes unavailable telemetry from valid values and verifies:

- `journal_mode=WAL`
- `foreign_keys=ON`
- `synchronous=FULL`
- `trusted_schema=OFF`
- `application_id=0x5A494F4E`
- `busy_timeout>=5000ms`
- `wal_autocheckpoint=1000`
- `journal_size_limit=16777216`

An unavailable PRAGMA read is an operational issue, not a healthy unknown state.

### MEDIUM — runtime schema drift was readable but not monitored as incompatible

Startup already rejects future schema versions, but runtime diagnostics previously distinguished only read success/failure.

**Hardening:** runtime and dashboard health require `schema_version == SUPPORTED_SCHEMA_VERSION`. Drift blocks scheduled delivery and is surfaced as an operational issue.

### MEDIUM — dashboard health was weaker than runtime health

The localhost dashboard previously used structural SQLite integrity without the full runtime identity/relationship checks.

**Hardening:** dashboard health requires:

- database file present;
- quick integrity check;
- foreign-key integrity;
- ZION application ID;
- supported schema version.

DB/WAL/SHM sizing is exposed separately while preserving the aggregate size field.

### MEDIUM — unavailable telemetry could look healthy

Additional cases were converted from silent fallback to explicit degraded/unavailable state:

- unexpected integrity-probe exception;
- `community_stats` read failure;
- health-alert dedup persistence read failure;
- disk-usage probe failure;
- AI-latency telemetry read failure;
- schema-version read failure.

A deliberately disabled AI layer stays quiet even if stale provider/accounting state exists.

### MEDIUM — health detection inherited hourly housekeeping cadence

Health checks were effectively tied to hourly housekeeping, making detection of disk/SQLite failures slower than intended.

**Hardening:** operational health is checked independently, default every **60 seconds**, while housekeeping remains hourly. Repetition of an unchanged successfully delivered alert remains separately bounded at **21600 seconds / 6 hours**.

Scheduler cadence uses `time.monotonic()`; retention timestamps and persisted audit timestamps continue to use wall-clock time.

The first health check and first housekeeping cycle still run immediately after scheduler startup.

### MEDIUM — health-alert dedup pair could partially persist

Alert signature and last-send timestamp form one logical state but were persisted separately.

**Hardening:** after Telegram delivery is confirmed, the pair is committed in one SQLite transaction. No Telegram I/O occurs inside that transaction.

If the local write fails after a confirmed Telegram delivery:

- in-memory state remains authoritative for the live single locked runtime;
- persistence is marked dirty;
- the runtime attempts to repair persisted dedup state;
- diagnostics shows `Alert dedup persistence: DIRTY`;
- stale persisted state is not trusted over newer live state.

### MEDIUM — incident persistence and notification dedup were coupled

A failed incident write followed by a successful Telegram alert could cause later deduplication to suppress another attempt to write the incident.

**Hardening:** incident-ledger persistence is retried independently of Telegram-notification dedup. Repeated notification attempts do not create duplicate incidents for the same active issue signature.

### MEDIUM — Telegram update lag could create stale or edited-message false positives

A bounded deque of the last 100 values already existed, but samples had no age and edited messages used the original message timestamp.

**Hardening:**

- edited messages use `edit_date` when available;
- future timestamps clamp to zero lag;
- samples remain bounded to 100;
- last sample monotonic time is recorded;
- old samples are shown as `STALE`;
- stale samples remain visible diagnostically but do not trigger a current-lag alert.

### MEDIUM — uncertain provider failures could undercount AI budget

A Mistral timeout/failure released the in-flight budget reservation and recorded zero provider tokens. A timeout does not prove zero external cost: the provider may have processed the request before the client lost confirmation.

**Hardening:** uncertain provider outcomes conservatively charge the reserved token estimate against the current UTC-day software budget.

The estimate is persisted without a schema migration using an internal settings key. It:

- survives runtime restart;
- rolls over by UTC day;
- is included in `tokens_used_today()`;
- never pretends to be exact provider billing;
- forces AI accounting to fail closed if the conservative charge cannot be persisted.

The deterministic Guardian is unaffected.

## Diagnostics

Operator-only `/diagnostics` now exposes, without secrets:

- SQLite quick check and FK integrity;
- runtime PRAGMA availability and drift;
- ZION application ID;
- current and supported schema version;
- total/DB/WAL/SHM sizes;
- disk state;
- Telegram update lag latest/p95/sample count and sample age state;
- successful Mistral latency avg/p95 over 24h;
- AI enabled/provider-ready state;
- AI accounting state;
- UTC token usage, configured budget and remaining budget;
- circuit-breaker state and remaining open time;
- consecutive provider failure count;
- scheduler task RUNNING/STOPPED;
- hourly housekeeping state;
- passive WAL checkpoint state;
- temporary-state maintenance state;
- delivery-safety preflight state;
- scheduled-delivery health gate state and blocking reasons;
- alert-dedup persistence state;
- health-check and alert-repeat cadence;
- explicit UNAVAILABLE/WARNING state for failed telemetry.

It does not expose API keys, Telegram tokens, provider headers, prompts or user message bodies.

## Operational alert semantics

Operational notifications are retryable, not exactly-once.

- A changed issue set is eligible immediately.
- An unchanged successfully delivered issue set is bounded by the configured repeat interval.
- A notification for which every Telegram send fails is not marked delivered.
- A recovery notification follows the same rule.
- A confirmed Telegram delivery followed by local persistence failure may later duplicate after a restart.
- Local dedup state is persisted atomically after external delivery.
- Incident-ledger persistence is independent from notification dedup.
- No Telegram I/O occurs inside SQLite transactions.

## Maintenance boundary

Housekeeping and WAL checkpoint are maintenance operations. Their failure must not disable monitoring.

A failed independent housekeeping step does not skip later housekeeping steps in the same hourly cycle.

The runtime records only safe step/error-type information for operational exposure; raw exception payloads are not inserted into Telegram alert text.

## Tests

The full validation suite at implementation-validation SHA
`cc8e579526c83426a787093e13202130e87290c3`
ran **319 tests** successfully in GitHub Actions ZION CI run **#888**.

Block 4 regression coverage includes:

- PRAGMA read failure fails closed;
- application ID mismatch;
- schema-version mismatch and unreadable schema;
- missing SQLite file;
- dashboard FK corruption, wrong application ID and unsupported schema;
- failed alert delivery remains retryable;
- successful alert delivery remains deduplicated;
- failed recovery remains retryable;
- atomic rollback of the alert dedup pair;
- dirty dedup persistence repair;
- incident persistence retry independent of notification dedup;
- no duplicate health incidents during failed notification retries;
- housekeeping failure does not block monitoring;
- later housekeeping steps continue after an independent failure;
- delivery safety preflight blocks scheduled effects;
- critical SQLite health blocks scheduled effects;
- health-cycle exception blocks scheduled effects;
- disabled AI does not create provider/circuit/accounting false alerts;
- diagnostics exposes operational/AI state without configured secrets;
- Telegram update lag remains bounded and non-negative;
- edited Telegram messages use edit timestamp;
- stale high lag does not generate a current alert;
- fresh high lag does generate an alert;
- 60-second health cadence is independent from hourly housekeeping;
- scheduler cadence is monotonic and immediate after startup;
- unavailable disk/schema/latency/community telemetry is explicit;
- provider-failure uncertain token usage is conservatively charged;
- uncertain AI budget survives restart and rolls over by UTC day;
- failure to persist uncertain AI usage makes accounting fail closed;
- existing transaction tests continue to prove no network `await` spans a DB transaction.

Validation evidence for that SHA:

- Python compile: PASS
- runtime compatibility: PASS
- imports: OK
- unit tests: **319/319**
- shell syntax: PASS
- tracked sensitive-file check: PASS
- SECRET SCAN: OK
- ZION VALIDATION: OK

## Residual host/live validation

These checks still require the controlled Acer/Telegram gate before production:

- actual filesystem permissions and free-disk behavior;
- real production DB/WAL/SHM growth patterns;
- real Telegram update-lag distribution;
- operator DM delivery during a real Telegram network interruption;
- dashboard localhost binding on the host;
- passive WAL checkpoint behavior with real concurrent readers;
- scheduled-delivery health-gate behavior against a disposable/local test database only;
- Mistral latency/budget telemetry only after a future explicitly approved AI activation.

## Production boundary

This branch must not be merged directly to `zion-v1`.

Production remains a separate deployment decision with backup, host validation, Telegram live gates and rollback preparation.
