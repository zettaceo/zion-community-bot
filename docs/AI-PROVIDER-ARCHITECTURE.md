# AI provider architecture v2 — research checkpoint

Status: implementation in isolated branch; Mistral remains the only active runtime provider.
The research observations below are dated 2026-10-18; subsequent checkpoints supersede implementation status.

The current code uses Mistral-specific Settings, client and accounting. Preserve
its protected secret and deterministic Guardian separation while introducing a
provider-neutral generation boundary. A provider must never grant tools,
knowledge scope or punitive authority.

## Official Kimi evidence

- [Quickstart](https://platform.kimi.ai/docs/overview): official catalog now lists
  Kimi K3, K2.7 Code and K2.6; OpenAI-compatible Chat Completions use the
  `https://api.moonshot.ai/v1` base and Bearer authentication. Model names are
  candidates for evaluation, not a production selection.
- [Pricing](https://platform.kimi.ai/docs/pricing/chat): input/output billing and
  K3 cache-write charges must be represented. Numeric prices were not present
  in the text extraction; do not substitute third-party prices or spend until
  official model-specific rates have been captured.
- [Terms, section 4](https://platform.kimi.ai/docs/agreement/modeluse): absent a
  separate agreement, submitted content may be used for service/model improvement.
- [ZDR](https://platform.kimi.ai/docs/guide/zero-data-retention): enterprise ZDR is
  available by request; it cannot be assumed enabled for this account. Batch and
  uploaded media have exclusions.

Decision: no real community messages, leads, CONTROLLED, INTERNAL or SECRET
knowledge may be sent to Kimi under this research checkpoint. Initial evaluation
must use synthetic prompts and approved PUBLIC projections only. Production
use requires documented account data-handling compatibility and policy review.

## Remaining implementation gates

Secure provider-aware store; no-echo local provisioning; HTTP endpoint/model
allowlist; sanitized errors; usage validation; conservative reservation including
reasoning/cache charges; persistent atomic budgets; bounded retries and circuit;
response validator; official capability/rate-limit review; smoke then full A/B.
No actual credential was read, requested or provisioned during research.

## Implemented evaluation boundary — 2026-10-19

This supersedes the research-only implementation label above. Runtime provider
selection is still unchanged; Kimi is NOT active in Telegram.

- `provider_secrets.py`: provider-bound fixed filenames reuse SecretStore atomic
  rotation, private permissions, canonical path, owner and hardlink checks.
- `providers.py`: completion protocol, existing Mistral adapter and text-only Kimi
  transport with fixed official URL, reviewed model allowlist, redirect rejection,
  no environment proxies, bounded messages/body, typed usage and sanitized errors.
  No tool execution, implicit retries, hidden-reasoning export or fallback.
- `scripts/provision-kimi.py`: interactive TTY-only, getpass-no-echo, metadata-only
  authentication probe then atomic store. No argument/env/Telegram credential input.
  Existing Mistral/Telegram secrets are untouched.
- `evaluation_budget.py`: SQLite-atomic reservations before network, shared daily
  and total caps across candidate models, restart-safe uncertain charges, one-time
  settlement and a persistent fail-closed flag for usage overruns. A dedicated
  evaluation DB is used; no production DB writes. Prices expire after one day.
- `evaluations/cognitive-v2.jsonl`: 100 synthetic cases, 13 categories, single and
  multiple turns. Gold expectations still require review, not auto-certification.
- `scripts/evaluate-cognitive-v2.py`: offline by default; explicit live smoke uses
  five cases; full uses 100. PUBLIC-only retrieval is enforced before candidate
  requests, even for MIMIR. The harness measures generation, not Telegram routing.
  Any provider/automated failure stops the run; human review remains mandatory.

Official numeric rates were subsequently captured from the
[official model cards](https://platform.kimi.ai/) on 2026-10-19 (USD per million):
K2.6 input 0.95, output 4.00, cache hit 0.16; K3 input 3.00, output 15.00,
cache write 3.00, cache hit 0.30. Reservations ignore cache discounts and include
K3's default cache-write cost plus 20% budget headroom. They are estimates, not
invoices or account-balance claims. Cap: USD 0.25/request, USD 2/day, USD 8 total.

[Mistral's model card](https://docs.mistral.ai/models/ministral-3-8b-25-12)
provides the current Ministral 8B price of USD 0.15/M input and output, captured
on the same date. This baseline can be compared without rotating its credential.

[K2.6 parameter reference](https://platform.kimi.ai/docs/guide/kimi-k2-6-quickstart):
non-thinking mode explicitly disabled thinking; omit sampling overrides. K3 uses
low reasoning effort. Both candidates cap completion at 700 tokens in evaluation;
truncation must be a failure, not a falsely accepted answer. Account eligibility,
actual latency, error recovery and comparative quality require live results.

Validation at the second checkpoint: 749 tests PASS, SECRET SCAN OK, ZION
VALIDATION OK (`/home/zetta/.codex/worktrees/zion-cognitive-v2-increment2-validation.log`). Later harness
additions require another complete run. No live benchmark success is claimed here.


## Operator-requested Kimi provisioning through ZION DM

The operator explicitly selected ZION private chat instead of terminal entry.
`/setkimikey` (no arguments) arms a single private capture for an explicit
operator, for 120 seconds. It cancels any Mistral capture, and vice versa.
The next non-command text is deleted before provider validation or storage.
Delete failure blocks validation/storage. Expired captures are also consumed
and deleted, preventing a late secret from entering normal conversation.
`/cancelkimikey` cancels capture; `/kimistatus` returns protected-store status only.

Validation uses the fixed official Kimi models endpoint, never an LLM prompt.
Atomic protected storage is followed by metadata-only audit; audit failure rolls
back the credential. Neither receipt nor validation activates Kimi for users.
Telegram receives the credential in transit: deletion does not certify removal
from all Telegram copies. No real credential is used in tests or printed.
These commands require a release containing the handlers; they are not available
in the currently running production SHA merely because this code exists.

### Restart during private registration

Arming Kimi capture persists only a pending/closed latch scoped to the authorized
private chat and operator in existing settings. It contains no credential, hash
or message content and requires no schema change. A restart loses the in-memory
120-second authorization, but not the interception latch: the next non-command
text is deleted, marked against replay and rejected as expired. A fresh command
is required to validate and store a key.

The latch remains pending until consumption, explicit cancellation or switching
to Mistral capture; it does not silently expire into ordinary conversation.
Failure to persist the latch prevents the invitation to submit a credential.
Failure to read/clear it blocks dispatch and provider validation. The durable
replay marker is written before clearing the latch. This protects the documented
armed flow, not arbitrary unsolicited credentials sent after cancellation or
without ever issuing the registration command.


## Stronger Mistral candidate — isolated evaluation only

The official [Large 3 model card](https://docs.mistral.ai/models/mistral-large-3-25-12)
and [pricing](https://docs.mistral.ai/inference/pricing) were checked on
2026-10-19: `mistral-large-2512`, USD 0.50/M input and 1.50/M output.
The evaluator now allowlists this exact model using the existing protected
Mistral credential. It shares the same durable evaluation caps and 20% cost
headroom; cached-input discounts are ignored. This does not change Settings,
Telegram provider selection, production model or key. No model winner is inferred
from catalog descriptions or a small smoke result.
