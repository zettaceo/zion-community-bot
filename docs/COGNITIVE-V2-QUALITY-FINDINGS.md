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
