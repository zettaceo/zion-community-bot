# Generation policy and bounded public tools

Implementation checkpoint, 2026-10-20. This is not production or model-quality
acceptance. The ordinary runtime composition still constructs the Mistral
baseline with no candidate approvals and no optional currency policy. Registering
Kimi never changes this composition.

## Native Mistral tools

The answer path supplies the local PUBLIC knowledge registry as native function
schemas. The registry has ten fixed operations, including public agent scope.
There is no shell, filesystem, HTTP fetch, arbitrary SQL, secret or punitive tool.
The trusted caller fixes the agent; arguments cannot override identity or scope.

At most one batch of three calls is accepted. The full batch is validated before
any read: operation, exact argument keys, bounded query, unique bounded call ID
and JSON without duplicate keys. A result is PUBLIC-only, audience-filtered and
subject to source validity/freshness. Each chunk stays whole. Combined evidence
is bounded to 12,000 characters; requests are bounded before transmission.

Only validated function envelopes go back to the provider. Accompanying model
text and hidden reasoning are discarded. The second request forces tool_choice
none; another tool request or truncated/inconsistent completion fails closed.
Every HTTP attempt, including each 429 retry, gets durable token admission. Usage
from both successful rounds is added once to the ordinary AI event. Locally
retrieved evidence is transient and used by the final output guard, not persisted
as a transcript. An uncertain second request never erases the first charge.

Protocol reviewed against the official [Mistral function-calling guide](https://docs.mistral.ai/studio/conversations/function-calling)
on 2026-10-20. Kimi remains a text-only candidate adapter: native Kimi tool cycles
are not enabled or claimed tested. Knowledge tools return corpus snapshots, not
live account, chain, exchange or availability probes.

## Candidate selection

`GenerationPolicy` is host-owned. It preserves the configured baseline for simple
requests, missing evidence, non-public evidence, unavailable candidates or absent/
expired approval. Comparison, objection and complex requests may select a reviewed
candidate only with explicit quality, privacy and pricing approval, an available
adapter, and a configured monetary budget. No approval is derived from a prompt,
founder claim, token registration, model output or test-suite success.

`AIService` accepts these deployment-policy dependencies explicitly. The current
Runtime supplies none; enabling a candidate requires a reviewed composition-root
change after its acceptance gates. There is no hidden database toggle or public
command to activate one. Candidate history excludes prior assistant transcripts,
which may have used CONTROLLED evidence. Retrieval retains the bounded user query;
the candidate receives only the current question and PUBLIC evidence.

Candidate output crosses the same guard and AI accounting path. Mistral candidate
adapters use HTTP-attempt admission; Kimi uses one reservation around its non-retrying
request. Unknown outcomes, timeout or invalid responses do not trigger an implicit
fallback. An unavailable candidate can select the existing baseline before any
candidate request. This policy never alters speaker ownership or Guardian authority.

## Optional monetary admission

`RuntimeCostBudget` adds a distinct existing-settings ledger in micro-USD estimates.
No migration or dependency is added. `RequestAdmission` reserves token and currency
allowances in one synchronous SQLite transaction before HTTP. Daily global,
provider/model and per-request currency caps are positive; zero cannot mean unlimited.

Rates are explicit dated `PriceSnapshot` objects, valid for at most one day after
verification. Missing, stale or future prices block requests. Reservations use the
higher input/output rate for the entire token bound plus 20 percent headroom and
assume no cache discounts. Each reservation freezes its rates for settlement, so
price changes or midnight cannot retrospectively change a charge. Overruns persist
a fail-closed state. Uncertain outcomes retain both charges across restart.

The private panel reports optional estimated/reserved micro-USD, NOT CONFIGURED,
or UNAVAILABLE. These are neither invoices nor account balances. No new currency
limit or price refresh is imposed on the existing deployment; operator review of
actual prices and caps is still needed before candidate activation.

## Handoff

A retained conversation handed to another agent uses fixed structured labels,
not the other agent's generated transcript. Labels explicitly grant no authority.
Another user's issue/objection is omitted. Topic changes, ordinary request pacing,
DM gates and durable single-speaker delivery remain in force.
