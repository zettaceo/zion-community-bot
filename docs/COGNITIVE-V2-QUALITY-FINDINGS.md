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

## Bounded turn-3 retest and cost-context finding — 2026-10-25

Read-only analysis of the withheld turn-3 results could not distinguish a
factual claim about the user-named competitor from a harmless repetition of its
name. The official retrieved context contained no such brand. The shared prompt
now asks the model to say “essa plataforma” when only the user supplied a brand;
the output guard still rejects an unapproved brand. No brand whitelist or
weakened assertion was added.

One K2.6 retest (`20261025T171100272571Z-kimi-k2.6.jsonl`) again stopped at
debate turn 3 with `unapproved_market_service_claim`. Its first two replies were
factually bounded on human review. The rejected text remains withheld; debate
turns 4–12 and other scenarios were NOT EXECUTED for K2.6.

One K3 retest (`20261025T171128521841Z-kimi-k3.jsonl`) passed the automated
gate through debate turn 10, then stopped at turn 11 with
`best_price_guarantee`. The turn-11 text was withheld, so the exact wording and
whether the guard rejected a denial cannot be inferred. Turn 12 and the other
three scenarios were NOT EXECUTED. Human review separately failed turn 2 for
asserting that various platforms offer similar categories of features without
official comparative evidence. Turn 5 said no official fee information was
available, although the approved corpus contains EVM and Solana fee policies.
The short question plus user-named brands retrieved no evidence at that point.
Exact-token aliases for “cobra/cobram/cobrança” now restore the published fee
sections to that query; the reviewed competitor assertion is also rejected by
the output guard. These are local forward-fixes, not a successful live retest.

Cumulative isolated evaluation ledger after both bounded runs: 635,955
micro-USD reserved or estimated spent, including earlier Mistral and Kimi runs.
This is not a provider invoice or account balance. The live multi-turn quality
gate remains FAILED/PENDING and no production model is selected.
Local validation after the forward-fixes: 868 tests PASS, SECRET SCAN OK,
ZION VALIDATION OK (`zion-v2-kimi-continuation-validation.log`).

## Final bounded K3 follow-up — 2026-10-25, still FAIL

An independent regression showed that the output guard treated common scoped
denials (“não dá para garantir o melhor preço”) as guarantees, and could let an
affirmative guarantee after “mas” inherit a preceding denial. The clause
boundary now distinguishes them. This does not establish what the withheld
turn-11 answer actually said.

One K3 follow-up with that guard correction and the natural charging-query
retrieval fix (`20261025T171800789527Z-kimi-k3.jsonl`) passed automation through
debate turn 9, then stopped at turn 10 on `safety_guarantee`. The rejected text
was withheld; turn 11–12 and the other scenarios were NOT EXECUTED. Human
review still FAILED: turn 2 asserted, without comparative evidence, that pieces
of the product already exist on other platforms. Turn 5 now correctly gave the
published EVM and qualified Solana fee policy while declining to compare an
unverified competitor price. Turn 8 gave an incomplete EVM tier schedule,
omitting Trader/0,25% while naming Free, Pro and Pilot. A narrow output regression
now rejects the observed turn-2 assertion. The prompt also explicitly forbids
presenting a partial fee schedule as a complete four-tier list; this is a local
forward-fix and has not passed a further live retest.

Cumulative isolated ledger: 996,139 micro-USD reserved or estimated spent,
including all earlier baseline and candidate calls. This is not an invoice or
account balance. The stop-on-first-failure rule remains active. No more paid
calls were made to seek a green result; multi-turn quality acceptance and model
choice remain open.
Final post-fix local validation: 870 tests PASS, SECRET SCAN OK,
ZION VALIDATION OK (`zion-v2-kimi-final-validation.log`).

## Post-K3 deterministic follow-up — 2026-10-25

The K3 rejected turn-10 text was withheld. Its `safety_guarantee` reason does
not prove whether the generated wording was an actual promise or a negated
warning. Local regression testing did show both false rejections of explicit
denials (for example, “não há como garantir a segurança”) and missed absolute
safety claims (for example, “a operação é risco zero”). The output guard now
handles these narrow constructions with clause-scoped denials, including
qualified claims such as “segurança plenamente garantida”. A rejected price
or safety guarantee produces a host-owned, topic-specific caveat. The rejected
model text is not retained in the incident/event evidence.

For K3 turn 8, the approved PUBLIC/CURRENT plan source had Free, Pro, Trader
and Pilot EVM fees, but the broad knowledge-tool result omitted the Trader
section. Retrieval now includes all four whole plan sections from that same
authorized source when a broad answer already contains at least two fee-bearing
plan sections. The evidence budget reserves space for all four whole sections;
if that matrix cannot fit, no partial plan bundle is returned. The output guard
derives the four EVM percentages from those official titled sections and rejects
an EVM or network-unspecified three-or-four-tier fee schedule if it omits
a tier or assigns an incorrect percentage. It does not apply this completeness
rule to a one- or two-plan comparison or to Solana-only wording. Percentages may
precede or follow their tier names. A local replay
of the K3 question confirmed Trader/0,25% in retrieved evidence, rejection of
the observed three-tier pattern, and acceptance of the complete four-tier
pattern. These are deterministic checks, not a new Kimi or Telegram acceptance.

The bounded live evaluation remains FAILED/PENDING: the K3 conversation
stopped at turn 10, later turns and other scenarios were not executed, and no
new paid provider requests were made for this follow-up. Kimi remains
provisioned privately but inactive; production still uses the existing model.
Local post-fix validation: 878 tests PASS, SECRET SCAN OK, ZION VALIDATION OK
(`zion-v2-post-kimi-local-validation.log`, local isolated run).

## K3 long-conversation acceptance follow-up — 2026-10-26 UTC

One bounded PUBLIC synthetic conversation run on the candidate at
`1ddccee01c419b449676555775c1c348fb503504` reached debate turn 12.
Evidence basename: `20261026T024614070697Z-kimi-k3.jsonl`. Turns 1–11 were
`REVIEW_REQUIRED`, which is an automated allow decision, not a human PASS.
Turn 12 was `AUTOMATED_FAIL / best_price_guarantee`; the rejected response was
withheld. Its text and the possibility of a false positive cannot be inferred
from the reason code. The other three 12-turn conversations were NOT EXECUTED.

Human review found a material fee-scope error at turn 5: the answer applied
Jupiter's USDC-or-SOL condition to Solana broadly and said other Solana pairs
have no Z-SWAP platform fee. The approved source treats Jupiter and LI.FI routes
leaving Solana separately. Turns 7–8 called snapshot facts “verificáveis
agora/hoje” and treated a suggested future UI check as proof already obtained;
the evaluation performed no live product check. The EVM Free/Pro/Trader/Pilot
rates were complete and correct. These findings make human quality acceptance
FAIL despite the earlier automated allow decisions.

The candidate prompt now requires Jupiter/LI.FI fee scoping and marks the
PUBLIC corpus as a reviewed snapshot. Narrow output regressions reject the
observed Solana overgeneralization and unwarranted live-proof claims. A
separate reproducible guard false positive for “Não há garantia de melhor
preço” was corrected with clause-scoped denials; this is **not** evidence that
the withheld turn-12 output used that wording. Rechecking only the previously
accepted responses through the revised local guard yields rejection at turns
5, 7 and 8 for the intended reasons. No rejected model text was opened or
stored as a fixture.

One post-fix bounded K3 retest, evidence basename
`20261026T025841571973Z-kimi-k3.jsonl`, stopped at turn 5 with
`AUTOMATED_FAIL / overbroad_solana_fee_scope`. Turns 1–4 were
`REVIEW_REQUIRED`; human review marked turns 2 and 4 factual PASS, turn 1 WARN
for unqualified Portfolio wording, and turn 3 FAIL for presenting Terminal Pro
without its beta status and Portfolio without its partial status in a
capability comparison. Turns 6–12 and all other conversations were NOT EXECUTED. The
guard prevented that answer from being counted as accepted, but the model
still did not complete the conversation. No further paid retries were made.

The isolated evaluation ledger after the retest is 1,638,178 micro-USD
reserved or estimated spent (about USD 1.64), not an invoice or provider
balance. Local validation after the deterministic fixes: 882 tests PASS,
SECRET SCAN OK, ZION VALIDATION OK
(`zion-v2-k3-followup-validation.log`). Kimi remains privately provisioned
and inactive in production. Multi-turn quality and Telegram acceptance remain
FAILED/PENDING; no provider winner or production promotion is certified.

After that retest, the candidate retrieval was extended for broad product
comparisons: the same approved PUBLIC/CURRENT evidence now carries Terminal Pro
beta and Portfolio/Orders partial status together, including a natural
“o que oferece que outra plataforma não oferece?” question. The output gate
checks those source-derived qualifiers without treating the user-named
competitor as official evidence. A local replay of the already accepted K3
turn 3 is now rejected as `missing_feature_status`; this is a deterministic
replay, not a new provider result. Independent negative probes also led to
narrow corrections for a correctly scoped Jupiter statement and a negated
availability statement. No new K3 request or Telegram test was performed.

Final isolated validation for these additional changes: 888 tests PASS,
SECRET SCAN OK, ZION VALIDATION OK
(`zion-v2-k3-final-validation.log`). The K3 conversation still failed at turn 5, all later
turns and the three other scenarios remain unexecuted, and the cumulative
estimated/reserved evaluation ledger remains 1,638,178 micro-USD.

## Solana fee-source scope reconciliation — 2026-10-26

The approved plan projection at application snapshot
`986ae759c1c76fe23967a8e61489d986b2bb9a51` said “outros pares Solana”
without repeating its Jupiter scope immediately before the LI.FI sentence.
Read-only source inspection at that exact snapshot found the USDC/SOL pair
selection in `src/lib/solana/conta-de-taxa.ts` on the Jupiter path, while
`src/app/api/quote/route.ts` passes the plan fee to LI.FI through its separate
integrator path. The public source text in `src/lib/founders-public/content.ts`
names both paths. `knowledge/z-swap-plans.md` now scopes the “other pairs”
sentence explicitly to Jupiter and says LI.FI routes leaving Solana do not use
that pair condition. The four published plan rates and source version did not
change. This is a clarification of the existing approved snapshot, not proof
of live availability or fee collection in production.

When a generated answer still overgeneralizes that Solana condition, the
candidate delivery path now attempts a host-owned answer from the complete
already-retrieved PUBLIC section. It derives the four rates from that section,
states Jupiter and LI.FI separately, notes third-party costs and declines to
claim a competitor price comparison. A missing or altered section keeps the
short conservative fallback. This is a local delivery-path test only: the K3
evaluation runner stops on `AUTOMATED_FAIL` before the delivery fallback, so
neither the model nor Telegram acceptance becomes PASS by this change.
Local post-reconciliation validation: 890 tests PASS, SECRET SCAN OK, ZION
VALIDATION OK (`zion-v2-solana-final-validation.log`). No additional provider
call was made; the evaluation ledger remains unchanged.
