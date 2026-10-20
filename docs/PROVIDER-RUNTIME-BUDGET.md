# Runtime provider admission

The runtime retains Mistral as its only active completion provider. Registering a
Kimi credential does not activate it. No automatic provider or model escalation
is enabled until privacy, quality, pricing and operator acceptance gates pass.

## Durable token limits

`AIService` supplies `ProviderTokenBudget` to its Mistral client. All completion
operations share it, including answers, translation, summaries, route inference
and observation classification. Guardian decisions remain deterministic.

Each actual HTTP attempt reserves a conservative bound over the complete JSON
payload, including system instructions, before network I/O. Provider and model
counters sit beneath one shared daily ceiling. The current runtime uses the
existing `ZION_AI_DAILY_TOKEN_BUDGET` for all three ceilings; the policy type
supports narrower provider/model caps, but does not approve additional models.
A configured zero retains the existing unlimited-token policy, with accounting.

The ledger uses the existing SQLite settings transaction; there is no schema
migration. It stores aggregate token counts and opaque pending reservation IDs,
not prompts, responses, credentials, chat IDs or user IDs. It retains at most
three UTC days, 64 model/provider counters per day and 2,048 pending handles.
Clock rollback, corrupt accounting and usage exceeding a reservation fail closed.

Successful usage replaces the reservation once. Timeout, cancellation, malformed
response and uncertain retry outcomes retain their full estimated charge. A 429
retry therefore gets a separate reservation; no assumption of free failed calls
is made. Abrupt process exit leaves the pending charge durable. Normal error
cleanup removes only the pending handle, not its charged estimate.

A response crossing midnight settles against its original request day. Invalid
or duplicate settlement is rejected. Historical usage from before release
adoption remains protected by the existing AI daily ledger. Admission compares
both ledgers conservatively; it does not add overlapping successful usage twice.
The private Control Center distinguishes this new ledger from legacy totals and
shows unavailable accounting as unavailable, never as zero.

## Remaining boundaries

These are token ceilings, not a currency invoice or a verified account balance.
The isolated benchmark retains its separate monetary reservation ledger and
short-lived official price snapshots. Runtime monetary pricing, evaluated model
escalation and cross-provider fallback remain gated; they are not silently
inferred from registration or from a successful unit suite.

Existing Mistral timeout, bounded 429 retry, pacing and circuit breaker remain.
A pre-network budget denial does not increment provider failures. No retry,
fallback or model output may weaken retrieval, confidentiality or output guards.
