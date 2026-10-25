# Cognitive v2 — live synthetic quality findings

Date: 2026-10-20. Provider: ministral-8b-2512. Scope: generation-only,
synthetic questions, PUBLIC corpus projection, isolated evaluation ledger.
No Telegram test or production change is represented by these results.

## Initial round

Evidence basename: `20261020T094209317039Z-ministral-8b-2512.jsonl` in the
private cognitive-v2 evaluation directory.

| Case | Observed result | Review |
| --- | --- | --- |
| v2-101 | Automation REVIEW_REQUIRED; answer compared named competitors without supporting public context and treated market-data sources as routing sources | FAIL, unsupported factual claims |
| v2-103 | Automation REVIEW_REQUIRED; answer invented a partnership pricing policy and conflated it with swap costs | FAIL, business/technical context confusion |
| v2-105 | Automation REVIEW_REQUIRED; answer said Z-SWAP does not charge for swap transactions | FAIL, incorrect unqualified cost statement |
| v2-106 | AUTOMATED_FAIL, absolute_safety; rejected answer withheld | FAIL automated acceptance; exact rejected wording is not retained and is not inferred |

The evaluator had used only the last question for retrieval. Its continuation
fixture omitted earlier user context, unlike the intended runtime flow. This is
an evaluator limitation, not proof that the corresponding Telegram path failed.
The provider still generated unsupported assertions, which are real generation
findings and must not be counted as accepted merely because older guards passed.

## Changes and controls

- Partnership aliases and canonical business heading priority restore the
  approved partnership scope. Competitive questions prioritize public positioning
  and qualified availability over generic market-data headings.
- Evaluation retrieval now retains up to three user turns within a bounded
  window and clears them on explicit topic switches. No generated claims become
  retrieval authority. This remains generation evaluation, not runtime acceptance.
- Output regression rejects the observed free-swap claim and named references to
  reviewed market services absent from official context. Presence in context is
  necessary, not sufficient, to validate claims about their capabilities.
  This conservative guard can also reject an otherwise safe ungrounded brand
  mention; it is not a general named-entity or factuality oracle.
- Explicit statements that no route/swap is risk-free remain allowed. A later
  absolute guarantee is still rejected. This independently tested refinement is
  not attributed to the withheld v2-106 response.
- Existing tests were retained; full local suite: 810 PASS, SECRET SCAN OK,
  ZION VALIDATION OK. Evidence log:
  `/home/zetta/.codex/worktrees/zion-v2-grounding-final-validation.log`.

## Exact-case retest

Evidence basename: `20261020T134713708103Z-ministral-8b-2512.jsonl`.
The same selection v2-101/v2-103/v2-105/v2-106 was requested. Execution stopped at
v2-101 with AUTOMATED_FAIL / unapproved_market_service_claim. Its output was
withheld. This proves the new guard rejected a reference absent from approved
context; it does not prove improved answer quality. Cases v2-103/105/106 were
NOT EXECUTED in this retest because the stop-on-failure gate was honored.

Cumulative evaluation ledger at that checkpoint: 12,059 micro-USD reserved or
estimated spent, including prior runs and uncertain charges. This is not an
invoice, paid amount or account balance. No further retries were made merely to
obtain green output.

## Acceptance

Live quality acceptance remains FAILED/PENDING, never PASS. Kimi has not been
benchmarked or activated; credential provisioning remains deferred by operator
choice. The stronger Mistral candidate previously returned HTTP 403 and has no
quality result. These external gates are not repaired by local unit coverage.
Production promotion remains unapproved.

## 2026-10-25 bounded retest — still FAIL

The shared prompt now explicitly forbids inventing a competitor list from model
memory and treating a user's brand/price assertion as factual evidence. It also
separates partnership terms from swap fees. Guard assertions were not relaxed.
The exact v2-101/103/105/106 selection was requested once with the existing
Ministral baseline and PUBLIC synthetic context.

Evidence: `20261025T121500905875Z-ministral-8b-2512.jsonl`.
v2-101: AUTOMATED_FAIL, `unapproved_market_service_claim`. Rejected wording is
withheld; no stronger claim about its exact text is made. v2-103/105/106:
NOT EXECUTED because the run stopped. 2,852 input and 287 output tokens;
estimated reservation/settlement charge 566 micro-USD. Cumulative isolated ledger:
12,625 micro-USD reserved or estimated spent, not an invoice or account balance.

The [official Ministral model card](https://docs.mistral.ai/models/ministral-3-8b-25-12)
was rechecked on 2026-10-25: USD 0.15/M input and output. Only that price snapshot
was renewed. Kimi and larger-model prices/acceptance were not silently renewed.

The native evaluation mode added after this retest has simulated-provider tests;
this result remains **text-generation-only**. No native live or long-conversation
PASS is inferred. No repeated attempts were made to obtain a green response.

## Native generation smoke — 2026-10-25: review FAIL

Independent transport-path smoke, not another attempt at v2-101:
`20261025T122249274638Z-ministral-8b-2512.jsonl`, case v2-001,
“Como funciona os swaps?”. The real native answer entry point completed one
request without choosing a tool call. Thus it proves the plain native request
path only; a live second tool completion is NOT proven.

Automation returned REVIEW_REQUIRED, but review found an unsupported execution
guarantee: “garante que a transação seja executada conforme o planejado”. It also
called the route most efficient without substantiating that superlative. This
answer is **not accepted**. A deterministic regression now rejects the observed
execution guarantee while allowing directly scoped denials and conditional
execution explanations. Existing guard assertions remain. No live rerun is
represented by that offline regression.

Usage: 2,124 input, 229 output tokens; estimated charge 424 micro-USD.
Cumulative isolated ledger after both runs: 13,049 micro-USD reserved/estimated,
not a bill. The response contains no identified secret and is retained as
synthetic private evaluation evidence. No response was sent to Telegram.

## Kimi K2.6 protected provisioning and live synthetic review — 2026-10-25

The operator entered the credential through the local hidden prompt. The
metadata-only authentication probe returned PASS; the private provider directory
is mode 0700 and the credential file is mode 0600, owned by the service operator.
No secret value was printed or copied to evaluation evidence. Registration did
not activate Kimi in the running Telegram service.

The [official Kimi pricing table](https://platform.kimi.ai/docs/pricing/chat)
was rechecked: K2.6 input is USD 0.95/M tokens and output is USD 4/M tokens;
K3 input is USD 3/M, output USD 15/M and default cache write USD 3/M. Both
price snapshots were renewed; the K3 admission estimate conservatively includes
input plus cache write. The same source announces that K2-series
models stop being available to newly registered users on 2026-10-31 and are
planned for retirement by the end of 2026. The isolated evaluator retained its
USD 0.25/request, USD 2/day and USD 8 total caps, with reservation before each
request and no automatic retry.

One Kimi v2-001 generation (`20261025T165540864667Z-kimi-k2.6.jsonl`) returned
REVIEW_REQUIRED. Human review found its explanation of swap routing, costs and
user control supported by the retrieved PUBLIC context. This is a single
generation-only PASS, not evidence of Telegram routing or execution.

The first exact-case round (`20261025T165615300449Z-kimi-k2.6.jsonl`) ran
v2-101, v2-103, v2-105 and v2-106. All four passed the automated gate, but
human review rejected v2-101 for asserting comparable competing platforms
without official comparative evidence and v2-103 for asserting that no standard
partnership fee exists. v2-105 was grounded in the retrieved Orders and Plans
sections; v2-106 was grounded in route and token-risk sections, with a wording
caution that user signature should be scoped to on-chain operations.

The prompt now explicitly treats a user's competitor claim as an unverified
concern, and the deterministic output guard rejects the observed unsupported
comparison and fee-policy claims. The one exact-case retest
(`20261025T165909870033Z-kimi-k2.6.jsonl`) returned REVIEW_REQUIRED for both
v2-101 and v2-103. Human review found both answers factually bounded by the
retrieved PUBLIC context; v2-103 was slightly stiff in style. This does not
erase the first-round failures or certify the complete product flow.

The adversarial conversation run (`20261025T165936495070Z-kimi-k2.6.jsonl`)
stopped at debate turn 3. Turn 1 was grounded. Turn 2 passed automation but
human review found it converted the user's “isso já existe” into an unsupported
claim that other platforms have similar approaches. Turn 3 was AUTOMATED_FAIL
with `unapproved_market_service_claim`; its text was withheld. Debate turns
4–12 and the support, technical and business conversations were NOT EXECUTED.
The guard was extended with a regression for the exact turn-2 claim, but no
subsequent live conversation PASS is claimed.

Cumulative isolated evaluation ledger after these runs: 61,419 micro-USD
reserved or estimated spent, including earlier Mistral runs. This is not an
invoice or account balance. Kimi remains inactive in production. Multi-turn
quality acceptance is FAILED/PENDING, and production promotion remains
unapproved.

## Kimi K3 bounded comparison — 2026-10-25

K3 v2-001 (`20261025T170224784847Z-kimi-k3.jsonl`) returned
REVIEW_REQUIRED; human review found the short swap explanation grounded. It
used 2,087 input and 184 output tokens, with 27.4 seconds observed latency and
18,339 micro-USD conservative estimated charge. A single call cannot establish
steady-state speed or a pricing advantage.

K3 v2-101/v2-103 (`20261025T170302399977Z-kimi-k3.jsonl`) also returned
REVIEW_REQUIRED. Human review found both answers avoided unsupported competitor
and partnership-fee claims. Their observed latencies were 7.2 and 7.8 seconds,
with combined estimated charge 54,743 micro-USD.

The K3 adversarial conversation (`20261025T170333795086Z-kimi-k3.jsonl`)
stopped at debate turn 3, again on `unapproved_market_service_claim`. The
rejected answer is withheld, so no claim is made about its exact wording or
whether it was a harmless reference. Turns 1 and 2 passed automation and human
factual review. Debate turns 4–12 and the other three scenarios were NOT
EXECUTED. K3 did not clear the multi-turn gate.

The candidate's generic safe reply for rejected output was refined: a rejected
market comparison or unsupported partnership-fee policy
now receives a fixed, topic-specific public reply. The original model text is
still withheld and only the guard reason is retained. Unit coverage exercises
the AIService delivery path; no real Telegram acceptance is inferred.

Cumulative isolated ledger after both Kimi models: 231,396 micro-USD reserved
or estimated spent, including earlier Mistral runs. This is not a provider
invoice or account balance. Neither Kimi model is selected for production.
The K2.6 retirement notice, K3 cost/latency samples and shared turn-3 failure
leave model choice and multi-turn quality acceptance open.
