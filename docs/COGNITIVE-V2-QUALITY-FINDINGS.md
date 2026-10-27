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

## Named-conversation harness failure and bounded K3 retest — 2026-10-26

The first `--conversation-id conversation-debate` attempt created an empty
evidence file (`20261026T090158342604Z-kimi-k3.jsonl`) and exited with
`KeyError`. Its isolated ledger rose by 40,680 micro-USD to 1,678,858
micro-USD reserved/estimated. Independent offline reproduction found that the
CLI selected a conversation fixture but dispatched it to the single-case
evaluator. That evaluator completed the provider call and budget settlement,
then attempted to read the conversation's absent `required_terms` field. No
model response was retained from that attempt, so it has no quality verdict.

The candidate now uses one conversation-mode decision for selection and
dispatch. A fake-provider integration regression proves that a named
conversation emits its first turn. A second fake-provider path forces a
post-provider `KeyError` and verifies that a sanitized `HARNESS_FAIL` row is
durably written without response text, exception message, or a second request.
This fixes the evidence gap without reinterpreting the lost answer.

One bounded K3 retest after that local harness fix produced
`20261026T090942234213Z-kimi-k3.jsonl`. It stopped on debate turn 1:
`AUTOMATED_FAIL / missing_feature_status`. The generated text was withheld.
The record shows 4,064 input tokens, 309 output tokens, 9,220 ms latency and
34,823 micro-USD estimated charge. Debate turns 2–12 and the three other
conversations were NOT EXECUTED. The cumulative isolated ledger is now
1,713,681 micro-USD reserved/estimated, not an invoice or provider balance.
The reason code establishes that a source-backed beta/partial qualifier was
missing under the deterministic gate; it does not reveal the exact wording.

The candidate delivery path now offers a short host-owned reply that includes
only Terminal Pro beta and/or Portfolio/Orders partial statuses found in the
already retrieved PUBLIC context. Without that evidence it keeps the existing
conservative fallback. Independent diff review found that the first local
version could wrongly attach another section's or a negated status to a
feature. The source-status matcher now requires a direct affirmative predicate
within the same evidence section; regressions cover cross-section and
same-section false associations plus negation. Focused source/guard and
fake-provider tests pass, but
this does not turn the failed model generation into a PASS. Human-accepted
multi-turn quality, real Telegram acceptance, provider decision and production
promotion remain open. Final isolated validation: 893 tests PASS, SECRET SCAN
OK, ZION VALIDATION OK (`zion-v2-final-reviewed-validation.log`). No
production setting or runtime was changed.

## Broad comparison delivery alignment — 2026-10-26

An independent local check found that the isolated evaluator's approved PUBLIC
tool projection supplied the beta/partial sections for the exact debate turn 1,
while the ordinary ZION answer path could retrieve only a smaller four-chunk
context. The model-quality failure remains unchanged. For this broad product
comparison only, the normal answer path now uses the same bounded PUBLIC tool
projection. A rejected answer can receive a fuller host-owned reply about the
Z-SWAP proposal, Terminal Pro beta and Portfolio/Orders partial status, but
only when the retrieved positioning, feature map and all three status predicates
are present. It does not assert competitor equivalence or superiority. Missing
sections, narrow feature questions and unrelated/negated status text retain a
conservative fallback. Focused delivery/guard tests and the complete local
895-test suite pass with secret scan and ZION validation
(`zion-v2-comparison-local-validation.log`).

No Kimi call or Telegram message was sent for this refinement. The last actual
K3 debate remains **AUTOMATED_FAIL at turn 1**; turns 2–12 and the other three
scenarios remain NOT EXECUTED. This delivery containment is not a model PASS.

## Independent output review and benchmark preparation — 2026-10-26

A read-only candidate review reproduced two additional output-guard gaps with
actual retrieved PUBLIC evidence: an incorrect Free EVM fee could pass when
only one or two plans were named, and a Terminal Pro answer could say both
“beta” and “em produção para todos.” The isolated forward-fix compares stated
plan percentages to the retrieved plan sections and rejects explicit general
release claims that contradict the retrieved beta state. Adversarial follow-up
also found a natural inverse-fee phrasing, a valid negated correction and the
false Free rate “nove por cento”; all received local regressions. A small
written-percentage parser now checks explicit EVM plan-fee claims against the
retrieved PUBLIC rate and fails closed on unknown bounded wording. A rejected
fee claim may receive a source-derived reply only when the requested plan
sections and EVM condition are present. The guard still cannot certify
arbitrary model claims or every linguistic fee formulation.

The evaluator now has an opt-in mode to keep collecting independent cases
after a failed case, while keeping every failed 12-turn scenario stopped. The
comparison protocol, fixed ten-case smoke and human scorecard are recorded in
`AI-BENCHMARK.md`; the controlled Telegram checklist is in
`COGNITIVE-V2-TELEGRAM-ACCEPTANCE.md`. Neither document is execution evidence.
Local validation of this revision: 903/903 tests, `SECRET SCAN: OK`, `ZION
VALIDATION: OK` (`/tmp/zion-v2-candidate-final-validation-2.log`). No
provider call, Telegram message, production write or new model PASS occurred.

## Frozen ten-case provider smoke — 2026-10-26: both models FAIL

The predeclared selection in `AI-BENCHMARK.md` was generated once per model at
candidate `6774e8b21c4a512bc77c5eb83d62c40aa119ef46`, using synthetic
questions and exact retrieved PUBLIC context. The private manifest basename is
`20261026T205218780145Z-smoke-manifest.json`. All ten responses from each
model received automated `REVIEW_REQUIRED` with the deterministic guard
accepting them. That status is **not** human approval. The generation batches
had completed before human review found the fatal cases; review stopped at each
model's first fatal finding. Later generated responses are not counted as PASS.

| Model | Human-reviewed cases | First fatal finding | Later cases |
| --- | --- | --- | --- |
| Ministral 8B | v2-001 FAIL | Claimed best-quote selection and automatic fee/liquidity optimization that the retrieved “Swaps e pontes” section does not establish | Other nine generated; NOT HUMAN REVIEWED |
| Kimi K3 | v2-001 PASS; v2-021 PASS; v2-041 FAIL | Treated wallet connection as categorically signature-only, beyond the authentication evidence, and named wallets without retrieved compatibility support | Other seven generated; NOT HUMAN REVIEWED |

The Ministral result fails the rubric's invented-feature gate; its reviewed
v2-001 factuality and calibration scores were both 2/5. K3 v2-041 failed the
factuality threshold at 3/5. The two K3 PASS labels above apply only to those
individual synthetic generation answers, not the model, Telegram delivery or
product readiness. No secret disclosure was found in the reviewed answers.

Private evidence basenames: `20261026T205229854612Z-ministral-8b-2512.jsonl`
and `20261026T205229854612Z-ministral-8b-2512-human-review.md` for Ministral;
`20261026T205308750562Z-kimi-k3.jsonl` and
`20261026T205308750562Z-kimi-k3-human-review.md` for K3. No raw answers or
credential values are copied into this report.

All ten generated attempts cost an estimated 5,132 micro-USD for Ministral
and 266,221 micro-USD for K3. The cumulative isolated ledger is 1,985,034
micro-USD reserved or estimated spent. These are admission/evidence estimates,
not an invoice or provider account balance. Both smoke verdicts are **FAIL**.
At that earlier checkpoint, material forward-fixes for the two observed
claims passed 911/911 local tests,
`SECRET SCAN: OK` and `ZION VALIDATION: OK` in
`/tmp/zion-v2-smoke-forward-fix-validation-3.log`. Their exact-SHA CI and a
newly frozen provider retest were pending; this did not erase either smoke
FAIL at that time. Neither full
108-case benchmark nor all four 12-turn conversations nor controlled Telegram
acceptance followed this smoke. Kimi remains inactive and production unchanged.

## Frozen retest and full-continuation gate — 2026-10-27

Candidate `c06f53b1f1cdd018deadebc2e25991ee44162459` passed exact-SHA
[ZION CI 40474911066](https://github.com/zettaceo/zion-community-bot/actions/runs/40474911066),
911/911 local tests, `SECRET SCAN: OK` and `ZION VALIDATION: OK`. K3 and
Ministral prices were reverified on 2026-10-27. The private frozen smoke
manifest is `20261027T083840602194Z-smoke-rerun-manifest.json`; final K3
review is `20261027T083840602194Z-smoke-rerun-human-review-v2.jsonl`.

The smoke used one attempt per case and stopped each model on its first failed
gate. Ministral 8B's v2-001 was `AUTOMATED_FAIL` for
`unsupported_route_optimization`; nine other smoke cases were **NOT
EXECUTED**. Its estimated charge was 438 micro-USD. Kimi K3 passed independent
human review on all ten smoke cases, with mean 4.7811/5 and estimated charge
292,681 micro-USD. This supersedes the earlier *candidate's* smoke verdict,
not its historical failure or other acceptance gates.

The private continuation manifest
`20261027T085139396155Z-full-continuation-manifest.json` froze the 98
remaining cases without repeating smoke. All 98 were verified offline as
synthetic/PUBLIC-only. K3 v2-002 passed human review, with estimated charge
34,413 micro-USD. K3 v2-003 failed human review: an allowed output suggested
that Bridge universally incurs a platform fee without the documented
conditions. Factuality and calibration were 3/5, while its mean 4.33/5 does
not override the individual gate. That attempt cost an estimated 29,409
micro-USD. The other 96 cases were **NOT EXECUTED**. This is a factuality
finding and a bounded guard coverage gap; it does not establish a different
provider as a winner. The full 108-case result is **FAIL/incomplete**. The
cumulative isolated ledger after v2-003 is 2,341,975 micro-USD
reserved/estimated, not an invoice or account balance.

A material forward-fix for v2-003 passed 914/914 local tests, `SECRET SCAN: OK`
and `ZION VALIDATION: OK` on 2026-10-27. Exact-SHA CI and a fresh provider
retest remain **PENDING** at this checkpoint.
No raw answer or secret is reproduced here. The four 12-turn conversations,
native delivery and controlled Telegram acceptance have no new PASS; Kimi
remains inactive and production unchanged.

## Fee-scope fix retest and best-quote finding — 2026-10-27

Candidate `a4944356f7d1f10ff890393ca97bdd8077391e23` passed exact-SHA
[ZION CI 40515511601](https://github.com/zettaceo/zion-community-bot/actions/runs/40515511601),
914/914 local tests, secret scan and validation. The private new smoke manifest
is `20261027T135123615841Z-bridge-fee-smoke-manifest.json`; only Ministral
v2-001 was generated. Automated status was `REVIEW_REQUIRED / accepted`, but
independent review recorded **FAIL** because the answer implied finding the
best quote despite the PUBLIC “Swaps e pontes” section only documenting source
selection by networks and the returned route. The answer's later all-source
caveat did not repair the earlier assertion. Review metadata is private in
`20261027T135123615841Z-bridge-fee-smoke-human-review.jsonl`. No raw answer
or secret is copied here. Estimated charge: 462 micro-USD. Nine other
Ministral smoke cases and all ten K3 smoke cases were **NOT EXECUTED**.

The isolated ledger after this attempt is 2,342,437 micro-USD
reserved/estimated, not an invoice. The first bounded best-quote prompt/guard
fix at `79c2dcc735e95603939413e4fea60483b4c60999` passed 914/914 local
tests, secret scan, validation and exact-SHA
[ZION CI 40516764932](https://github.com/zettaceo/zion-community-bot/actions/runs/40516764932).
Independent red-team then reproduced both overblocking of user-selected
routes/denials and underblocking of unsupported minimum-price claims with
PUBLIC context. A narrow follow-up guard change covers these examples and
passed 914/914 local tests, secret scan and validation; exact-SHA CI and a
fresh provider retest are **PENDING**.
The a494 and c06f failures remain separate historical findings. No full-model,
multi-turn, Telegram or production acceptance follows. Kimi remains inactive.

## 0b67cbe frozen smoke and retrieved-grounding findings — 2026-10-27

Candidate `0b67cbe6ca254f5d120fc872f4d8f3da89a92325` passed 914/914
local tests, `SECRET SCAN: OK`, `ZION VALIDATION: OK` and exact-SHA
[ZION CI 40520733751](https://github.com/zettaceo/zion-community-bot/actions/runs/40520733751)
with 914 tests. The private manifest
`20261027T142417435209Z-route-guard-smoke-manifest.json` froze both models,
the same ten synthetic/PUBLIC case IDs and dated source/price identities.
Preflight accepted all 20 model/case combinations without making a provider
request. Only v2-001 was then generated once per model.

| Model | Automated result | Initial factual review | Finding |
| --- | --- | --- | --- |
| Ministral 8B | `REVIEW_REQUIRED / accepted` | **FAIL** | Named quote-source example absent from the retrieved “Swaps e pontes” section; categorical wallet-signature confirmation mechanism not established by that section. |
| Kimi K3 | `REVIEW_REQUIRED / accepted` | **FAIL** | Applied the source's bridge availability qualifier to swaps and changed a normative seed-phrase warning into an unconditional future promise. |

The later independent corpus check found temporal swap availability in other
PUBLIC/CURRENT sections. Thus the K3 temporal concern is specifically a
retrieval/context-scoping issue, not a demonstrated contradiction of the
public product corpus. The unconditional seed-phrase phrasing remains an
overstatement. The original review FAIL is retained; no PASS is inferred
from this nuance. Private review metadata is in
`20261027T142417435209Z-route-guard-smoke-review.jsonl`. No raw model answer
or secret is reproduced here. The other nine smoke cases per model were
**NOT EXECUTED**, so neither model advanced to the full benchmark.

The next candidate adds an atomic, bounded bundle of three
PUBLIC/CURRENT swap sections for explanatory singular/plural questions,
prompts that require claims to follow retrieved source scope, and deterministic
source-conditional checks for unsupported named quote sources, signature
mechanisms and absolute seed-request promises. Focused tests passed 21/21
for KnowledgeTools and 39/39 for response/prompt boundaries. Full local
validation passed **922/922**, secret scan and validation OK. Exact-SHA CI
and a newly frozen provider smoke are **PENDING**;
this is not a model-quality PASS. Kimi remains inactive and no production
change follows from this evidence.

## f678720 frozen smoke and passive seed-promise gap — 2026-10-27

Candidate `f6787207ec45de6f52edd846962cb7f37f3acd9f` passed 922/922
local tests, secret scan and project validation and exact-SHA
[ZION CI 40579482818](https://github.com/zettaceo/zion-community-bot/actions/runs/40579482818)
with the same test total. Private manifest
`20261027T203709932920Z-swap-context-smoke-manifest.json` froze two models,
ten synthetic/PUBLIC cases each and source/price identities; 20/20 preflights
passed. Only v2-001 was executed once per model.

| Model | Automated result | Factual review | Finding |
| --- | --- | --- | --- |
| Ministral 8B | `AUTOMATED_FAIL / unsupported_route_optimization` | **FAIL**, text withheld and not scored | An unsupported best-route claim was caught; no generated text was retained in the result. |
| Kimi K3 | `REVIEW_REQUIRED / accepted` | **FAIL** | Network-specific source selection was grounded, but a passive future promise about never requesting a seed phrase exceeded the normative PUBLIC rule. |

The other nine smoke IDs for each model are **NOT EXECUTED**. Private review
metadata is in `20261027T203709932920Z-swap-context-smoke-review.jsonl`; no
raw model answer is reproduced. A narrow candidate forward-fix extends the
absolute-promise guard to the observed passive wording and steers the prompt
toward advice to the user. Focused response/prompt tests passed 39/39; full
local validation passed 922/922, secret scan and validation OK. Exact-SHA CI
and new provider acceptance remain **PENDING**. This
does not establish model quality, Telegram acceptance or production readiness.
