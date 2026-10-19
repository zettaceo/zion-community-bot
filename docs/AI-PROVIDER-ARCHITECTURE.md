# AI provider architecture v2 — research checkpoint

Status: DESIGN/RESEARCH, not implemented or enabled. Checked 2026-10-18.

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
