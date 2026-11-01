# Cognitive Architecture v2 — current execution checkpoint

Date: 2026-10-29. Status: IN PROGRESS, not production accepted.
This section supersedes older current-state labels below; the prior mission's
checklists remain historical evidence, not proof of v2 completion.

## Delivery-path consolidation — in progress

- [x] Replace raw-only wallet retests with a separate, single-case synthetic
  `AIService.answer` probe. The evaluation-only adapter uses PUBLIC/CURRENT
  knowledge, a disposable service DB, durable isolated K3 cost admission and
  no runtime model approval. Local wallet and finite-list replies are labeled
  separately from provider generations. Guard fallback, missing audit event,
  unexpected local fallback and budget exhaustion cannot become a pass.
  After the independent review's two measurement fixes (expected delivery
  event required; cost read from the case's own reservation), local
  validation passed 951/951 tests, shell, sensitive-file check and secret scan.
- [x] Clean exact-SHA local v2-041 delivered manifest frozen on `873ce55`
  (exact-SHA [ZION CI 41300932530](https://github.com/zettaceo/zion-community-bot/actions/runs/41300932530)
  SUCCESS): `20261101T111810087496Z-delivery-v2-041-873ce553-manifest.json`,
  0 provider calls, 0 micro-USD, guard accepted, model `zion-local`. Delivered
  answer: "Para entender a dificuldade de conexão, diga qual carteira e rede
  você usa e qual mensagem de erro aparece. Não compartilhe seed phrase, chave
  privada ou senha da carteira." Independent (AI) review: PASS — it asks only
  triage facts, makes no claim beyond PUBLIC evidence and gives the normative
  secret warning. Human review: PENDING. Kimi K3 price reverified 2026-11-01
  on platform.kimi.ai (unchanged).
- [ ] Human review of the delivered v2-041 answer.
- [x] Production-baseline delivery probe (2026-11-01). Production serves
  `ministral-8b-2512` through `AIService`/`MistralClient` with Kimi inactive,
  so K3 smoke results alone cannot describe what members receive.
  `--live --model ministral-8b-2512` now runs the unchanged production
  generation path (real tool round, rate-limit retries, output guard) on the
  PUBLIC/CURRENT corpus and an isolated durable `evaluation-baseline.db`.
  Every HTTP attempt is admitted by the existing `RequestAdmission` +
  `RuntimeCostBudget` at the worst dated rate before it is sent (request cap
  USD 0.05, day cap USD 0.50); the case charge is its own settled or
  uncertain reservations, never a ledger delta. Ministral price reverified
  2026-11-01 (0.15/0.15 USD/M, unchanged). Kimi provisioning clients moved
  to `kimi-k3`: Moonshot retires the K2 series by end of December 2026.
- [x] Output-guard defect found while testing the probe: the guard accepted
  "A Z-SWAP garante lucro", "Lucro garantido", "retorno garantido" and
  "Os swaps nunca falham". New `financial_return_guarantee` and
  `absolute_reliability` rules (PT/EN) block outcome and infallibility
  promises, keep scam warnings and honest caveats ("não há garantia de
  lucro", "desconfie de quem promete lucro", "nenhum dos planos promete
  lucro"), close "não só garante"/"not only guarantees" bypasses and reply
  with a fixed no-promise fallback. 21 promise and 22 caveat regressions,
  zero official knowledge sentences flagged, and a replay of 164 stored
  private model outputs changed none of their verdicts. Local validation
  963/963, secret scan and ZION validation OK.
- [x] Second guard gap from the same review: buy/sell/invest
  recommendations and price forecasts ("Recomendo comprar ZETTA agora",
  "O preço do ZETTA vai dobrar", "ZETTA will moon") were accepted. Note that
  the running production commit `472a4b3` has no output guard at all. New
  `investment_advice` and `price_prediction` rules (PT/EN) with a fixed
  no-advice fallback; uncertainty ("ninguém sabe se o preço vai subir"),
  scam warnings, refusals and operational guidance ("recomendo conferir os
  detalhes", "a venda depois do fechamento oficial") stay accepted; plan
  purchase wording keeps its own plan-access rule. 14 advice and 13 neutral
  regressions; zero official knowledge sentences and zero of 164 stored
  outputs flagged. Local validation 965/965, secret scan, ZION validation OK.
- [x] Third guard gap, the most severe: a reply could ask for the seed
  phrase, private key or password ("Me mande sua seed phrase"), solicit
  funds ("Envie 0.1 ETH ... e receba o dobro"), show an unofficial wallet
  address, or point to scheme-less phishing hosts (`claim-zswap.xyz`,
  `bit.ly/...`) and WhatsApp/phone contacts — the URL check only saw
  `https://`. A prompt injection could have turned a member reply into a
  phishing message. New `_scam_surface` check (`secret_solicitation`,
  `fund_solicitation`, `unapproved_wallet_address`, `unapproved_contact`,
  bare-host `unapproved_url`) runs before the quality rules; hosts,
  addresses and contacts are allowed only when present in the official
  context. Safety warnings ("nunca envie sua seed", "em nenhum momento
  compartilhe", "se alguém pedir, é golpe"), unlocking inside the wallet and
  funding one's own wallet stay allowed. The fallback is normative, not a
  categorical promise. 15 scam and 17 safe regressions; zero official
  knowledge sentences and zero of 164 stored outputs flagged (one stored
  "em nenhum momento compartilhe" warning drove a fix). Local validation
  967/967, secret scan, ZION validation OK.
- [x] `/summary` and `/translate` published model output with no guard (in
  v1 production too): a phishing message posted in another language could
  be relayed by ZION in its own voice. Their output now passes the
  phishing-only `scam_surface_reason` check (factual quality rules do not
  apply to a restatement of member text); a hit is replaced by a fixed
  notice and audited as `response_guard` failure. Official hosts come from
  the PUBLIC corpus (`swap-z.app`, `zettaword.global`); lookalikes such as
  `swap-z-app.xyz` are contained. Guard errors fail closed. Local
  validation 970/970, secret scan, ZION validation OK.
- [x] Telegram support-scam shapes: "um administrador vai te chamar no
  privado", "sou um atendente humano", "podemos recuperar seus fundos" and
  unknown `@handles` were accepted. New `dm_contact_promise`,
  `human_impersonation`, `fund_recovery_promise` and handle-level
  `unapproved_contact` (handles pass only from official context; the PUBLIC
  corpus publishes none) with an automated-assistant safety fallback;
  warnings and refusals stay accepted. 25 scam and 26 safe regressions;
  official corpus and the 164-output replay unchanged. Local validation
  970/970, secret scan, ZION validation OK.
- [x] Owner authorized the production-baseline smoke on 2026-11-01. First
  case v2-001 on `c99cdc3` (1 provider call, 717 micro-USD): the swap flow
  matched `z-swap.md` (source chosen by network, no all-source comparison,
  fee/impact/minimum shown), but the answer ended with "garantindo que você
  mantenha o controle total sobre seus fundos" — a guarantee beyond the
  source ("a carteira continua sob controle do próprio usuário"). Review:
  **FAIL**; stop-on-first-fatal applied, remaining cases not run on that SHA.
  Forward-fix: `controle total` joins `safety_guarantee`; present-tense
  promises about *people* ("a equipe nunca pede") join
  `unsupported_universal_secret_promise` while product statements ("a
  Z-SWAP não pede sua senha", reviewed in c4d1f36) stay allowed; and
  `repair_public_response` drops at most two reassurance-type overclaim
  sentences when the rest keeps ≥60% of the answer and re-passes the full
  guard, appending the normative secret instruction when a secret promise
  was dropped. Repairs are audited as `response_repair` and flagged
  `repaired` in delivery evidence — never a clean pass. Every other guard
  failure keeps the whole-answer fallback. Local validation 977/977.
- [ ] Production-baseline smoke on the forward-fix SHA (estimated well
  under USD 0.10 for all ten cases) and, separately, the K3 candidate smoke.
- [ ] Run the remaining provider smoke cases one at a time under
  dated pricing and stop-on-first-fatal review. A local result does not erase
  the historical raw K3 FAIL.
- [ ] Controlled Telegram, full 108-case and four 12-turn evaluations,
  account data-handling and independent release/security gates remain open.

## 2026-10-29 4271c98 synthetic/PUBLIC smoke — stopped at v2-041

- [x] Candidate `4271c98b294256b8d4e7cc307cad7edb82de3f83` passed
  exact-SHA [ZION CI 40890714571](https://github.com/zettaceo/zion-community-bot/actions/runs/40890714571):
  SUCCESS, 937/937 tests. Frozen synthetic/PUBLIC source and cost preflights
  passed 20/20; these were not provider calls.
- [!] K3 v2-001 and v2-021 **PASSED human and independent review**. v2-041
  **FAILED human and independent review** despite passing the automated guard:
  EIR claimed the entire wallet connection always occurs inside the wallet,
  beyond retrieved PUBLIC evidence. Stop-on-first-failure left seven remaining
  K3 cases and all Ministral cases **NOT EXECUTED**. The isolated ledger totals
  4,957,617 micro-USD reserved/estimated, not an invoice. This frozen FAIL
  remains unchanged.
- [~] A local deterministic EIR triage forward-fix is implemented. Local
  validation passed 941/941 tests, imports, shell, secret scan and ZION
  validation; 78 focused AIService/guard tests and an independent 32/32 bounded
  selector matrix with source-id/filename spoof negatives passed. Exact-SHA
  [ZION CI 40936957422](https://github.com/zettaceo/zion-community-bot/actions/runs/40936957422)
  on `20639367a2a3a2cc527b12737df20b5d218f8f2f` passed 941/941 tests;
  controlled Telegram and the remaining provider cases remain release gates.
  Next, verify v2-041 on the delivered AIService path; repeating raw-only
  generation would not prove the user receives the fixed answer. The 4271c98
  raw FAIL is unchanged.
- [ ] Full benchmark, conversations, controlled Telegram, account
  data-handling, independent security and release gates remain open. Draft
  PR #66 remains preproduction; Kimi inactive and production unchanged.

## 2026-10-29 prior 413dc6a synthetic/PUBLIC smoke — stopped at v2-041

- [x] Candidate `413dc6a1e3b36d368de3173ec496b82182f71389` passed
  exact-SHA [ZION CI 40850555948](https://github.com/zettaceo/zion-community-bot/actions/runs/40850555948):
  935/935 tests, imports, secret scan and validation. The private frozen
  `20261029T093516334894Z-wallet-local-unlock-smoke-manifest.json` passed
  20/20 synthetic/PUBLIC source and cost preflights; these were not provider calls.
- [!] K3 v2-001 and v2-021 passed human and independent review. v2-041
  **FAILED** despite passing the automated guard: EIR correctly distinguished
  a wallet's local unlock password from sharing it in chat, then said nobody
  from Z-SWAP would request the secrets. The PUBLIC source says staff should
  not request them, not that every future person will comply. Stop-on-first-
  failure applied; seven remaining K3 cases and Ministral **NOT EXECUTED**.
  The isolated ledger totaled 4,828,833 micro-USD reserved/estimated, not an
  invoice. The frozen FAIL remains unchanged.
- [~] A local prompt/guard follow-up now distinguishes categorical promises
  from normative safety guidance, checks Portuguese and English variants,
  and preserves a source-safe wallet triage fallback. The first 17 existing
  private K3 outputs were replayed locally: only the failed 413dc6a v2-041
  output matched the new guard. Intermediate `b318218` passed exact-SHA
  [ZION CI 40889458286](https://github.com/zettaceo/zion-community-bot/actions/runs/40889458286)
  with 937/937, but an independent adversarial review found additional
  bypasses and false positives. The subsequent local adjustment passed all
  19 reviewed probes and 937/937 tests, imports, secret scan and validation.
  Final exact-SHA CI and a new frozen provider round remain pending.
- [ ] Full benchmark, conversations, controlled Telegram, account
  data-handling, independent security and release gates remain open. Draft
  PR #66 remains preproduction; Kimi inactive and production unchanged.

## 2026-10-29 c4d1f36 synthetic/PUBLIC smoke — stopped at v2-041

- [x] Candidate `c4d1f362f4979975fd0fc6f786a6866c256afeef` passed
  exact-SHA [ZION CI 40844847015](https://github.com/zettaceo/zion-community-bot/actions/runs/40844847015):
  932/932 tests, imports, secret scan and validation. The private
  `20261029T085032831430Z-confirmed-handoff-smoke-manifest.json` passed
  20/20 synthetic/PUBLIC source and cost preflights.
- [!] K3 v2-001 and v2-021 passed independent human review. v2-041 **FAILED**:
  EIR said a password is never needed to connect a wallet, although the
  PUBLIC source only instructs users not to share passwords with the bot or
  in chat. The guard accepted this factual overreach. The seven remaining K3
  cases and Ministral were **NOT EXECUTED**. The private matching review file
  records the verdict; isolated ledger total was 4,700,924 micro-USD
  reserved/estimated, not an invoice. This frozen FAIL remains unchanged.
- [~] A new local candidate distinguishes local wallet unlock from sharing a
  password, with focused prompt, guard and delivery tests. Local validation
  passed 935/935, imports, secret scan and project validation. Exact-SHA CI
  and a new frozen provider round remain pending.
- [ ] Full benchmark, conversations, controlled Telegram, account
  data-handling, independent security and release gates remain open. Kimi
  inactive; production unchanged.

## 2026-10-29 eb43f28 synthetic/PUBLIC smoke — stopped at v2-103

- [x] Candidate `eb43f289525242bf6abe2033359a6fb2319023e6` passed local
  929/929 and exact-SHA [ZION CI 40792690647](https://github.com/zettaceo/zion-community-bot/actions/runs/40792690647)
  with imports, secret scan and validation. Private manifest
  `20261029T001519105610Z-no-named-modules-smoke-manifest.json` passed 20/20
  synthetic/PUBLIC source and cost preflights.
- [!] K3's first nine cases passed human review, including the previously
  failing v2-101. v2-103 **FAILED independent human review** after the guard
  accepted an overbroad offer to forward a partnership evaluation. Real FREYR
  handoff is DM-only and requires qualification and confirmed delivery; no
  handoff was executed by this generation-only probe. The round stopped.
  Ministral was **NOT EXECUTED**. Private review metadata is in the matching
  `-review.jsonl`; isolated ledger totals 4,576,396 micro-USD
  reserved/estimated, not an invoice.
- [~] A narrow local prompt/guard follow-up separates public triage wording
  from actual handoff, blocks generated offers or confirmations, and preserves
  the deterministic success/failure path. Local 932/932, imports, secret scan
  and validation passed. Exact-SHA CI and a new frozen provider round remain
  required. The eb43f28 FAIL cannot be rewritten.
- [ ] Full 108-case, four 12-turn, controlled Telegram, account data-handling,
  independent security and release gates remain open. Kimi inactive and
  production unchanged.

## 2026-10-28/29 prior 8a293c1 synthetic/PUBLIC smoke — stopped at v2-101

- [x] Candidate `8a293c1d4fb26a7e0f5d97ad3d392b661c2650e2` passed
  local 929/929 and exact-SHA [ZION CI 40790171180](https://github.com/zettaceo/zion-community-bot/actions/runs/40790171180)
  with imports, secret scan and validation. Frozen private manifest
  `20261028T235239935394Z-generic-objection-smoke-manifest.json` passed 20/20
  PUBLIC/source/cost preflights.
- [!] Eight K3 smoke cases passed human and independent review in order.
  v2-101 **FAILED automated acceptance** as `missing_feature_status`; output
  withheld, no content score. Stop-on-first-failure applied; v2-103 and
  Ministral were **NOT EXECUTED**. Private review metadata is in the matching
  `-review.jsonl`; isolated ledger totals 4,201,546 micro-USD reserved/estimated.
- [~] A 13-section PUBLIC retrieval was observed for v2-101, without evidence
  of the withheld wording. A proposed global context reduction broke existing
  plan/fallback regressions and was reverted before commit. A prompt-only
  restriction now avoids named modules/plans for generic objections; focused
  tests pass, but exact-SHA CI and a new frozen provider round remain required.
  The 8a293c1 and earlier FAIL verdicts cannot be rewritten.
- [ ] Full 108-case, four 12-turn, controlled Telegram, account data-handling,
  independent security and release gates remain open. Kimi inactive and
  production unchanged.

## 2026-10-28 prior bb9bfc3 synthetic/PUBLIC smoke — stopped at v2-101

- [x] Exact-SHA [ZION CI 40751134298](https://github.com/zettaceo/zion-community-bot/actions/runs/40751134298)
  for `bb9bfc348f5859fbe5b45489fb2884b6ed747249` succeeded: 928 tests,
  imports, secret scan and validation. Private frozen manifest
  `20261028T190606376383Z-future-status-smoke-manifest.json` passed 20/20
  synthetic/PUBLIC source and cost preflights.
- [!] K3's first eight cases (v2-001, 021, 041, 051, 061, 065, 091, 094)
  passed independent human review in order. v2-101 then **FAILED automated
  acceptance** with `missing_feature_status`; its generated text was withheld
  and not scored. The source-bounded host fallback passes, but does not turn
  model generation into PASS. v2-103 is **NOT EXECUTED**; no Ministral result
  was established. Stop-on-first-failure applied.
- [~] Private review metadata is in
  `20261028T190606376383Z-future-status-smoke-review.jsonl`; raw answers stay
  private. The isolated ledger after v2-101 is 3,863,923 micro-USD
  reserved/estimated, not an invoice or provider balance. This frozen FAIL
  cannot be converted into PASS by a later code change.
- [x] Inspected the observed guard reason without inferring withheld text.
  The exact PUBLIC retrieval already contains beta/partial/future qualifiers;
  a new prompt contract keeps generic objections concise instead of listing
  capabilities without their adjacent states. Independent false-negative
  guard probes now reject, including restricted audiences and pronoun carry-over;
  safe negative/conditional probes pass.
  Full local validation passed 929/929, secret scan and project validation.
  Conservative K3/Ministral prices were reverified on 2026-10-28.
- [ ] Exact-SHA CI and a newly frozen provider round are required. Full 108-case,
  four 12-turn, controlled Telegram, account data-handling/security and
  release gates remain open. Draft PR #66 stays preproduction; Kimi inactive
  and production unchanged.

## 2026-10-28 prior bc7218b synthetic/PUBLIC smoke — stopped at v2-094

- [x] Exact-SHA [ZION CI 40703279757](https://github.com/zettaceo/zion-community-bot/actions/runs/40703279757)
  for `bc7218bbe9d4b0b04f67ee467eff4f4c3a804047` succeeded: 926 tests,
  secret scan and validation. Private frozen manifest
  `20261028T141131043314Z-plan-status-smoke-manifest.json` passed 20/20
  synthetic/PUBLIC source and cost preflights.
- [!] K3's first seven cases (v2-001, 021, 041, 051, 061, 065, 091) passed
  human review in order. v2-094 was the first **FAIL**: the six status values
  were correct, but the generated answer promised that each status would be
  updated as public information advances without an official commitment. The
  deterministic guard accepted it. Stop-on-first-failure applied; v2-101 and
  v2-103 are **NOT EXECUTED**. No Ministral result was established.
- [~] Private review metadata is in
  `20261028T141131043314Z-plan-status-smoke-review.jsonl`; raw answers stay
  private. The isolated ledger after v2-094 is 3,537,237 micro-USD
  reserved/estimated, not an invoice or provider balance. This FAIL cannot be
  converted into a PASS by a subsequent code change.
- [x] Narrow prompt/guard forward-fix rejects the historical v2-094 private
  answer, preserving safe questions, reported quotes and conditional review
  language. The source-bounded PUBLIC fallback carries all six statuses and
  passes the guard. Independent bounded adversarial replay passed 8/8,
  including three initially missed wording variants and two safe controls.
  Full local validation passed 928/928, secret scan and project validation.
- [ ] Exact-SHA CI and a newly frozen provider round remain required. Full
  108-case, four 12-turn, controlled Telegram, account data-handling/security
  and release gates remain open. Draft PR #66
  stays preproduction; Kimi inactive and production unchanged.

## 2026-10-28 prior badec8e synthetic/PUBLIC smoke — stopped at v2-101

- [x] Exact-SHA [ZION CI 40661172474](https://github.com/zettaceo/zion-community-bot/actions/runs/40661172474)
  for `badec8ee0ef066da8dd5bab582a85d59ef05164d` succeeded: 923 tests,
  secret scan and project validation. Local validation also passed 923/923.
  The private frozen manifest
  `20261028T090459739318Z-wallet-notice-smoke-manifest.json` passed 20/20
  synthetic/PUBLIC source and cost preflights.
- [!] K3's first eight cases (v2-001, 021, 041, 051, 061, 065, 091, 094)
  passed independent human review in declared order. v2-091 has a mild
  naturalness warning for documentary phrasing, without a factual omission.
  v2-101 is the **first human FAIL**: a price/maturity answer named order
  planning and portfolio-like tracking without the relevant PUBLIC partial
  availability qualifiers. The guard accepted the Portuguese paraphrases.
  The sequence stopped; v2-103 was **NOT EXECUTED**. No Ministral result was
  established in this round.
- [x] A bounded prompt and deterministic response-guard forward-fix requires
  source-grounded beta/partial/future qualifiers for the observed product
  descriptions and blocks unsupported immediate plan-access claims. The
  private v2-101 answer is rejected by the new guard; its PUBLIC fallback
  passes. Independent adversarial replay passed the final bounded claims and
  safe negative/conditional controls. Focused tests passed 99/99; full local
  validation passed 926/926, secret scan and project validation. Exact-SHA CI
  subsequently passed for `bc7218b`, but its provider smoke failed at v2-094.
- [~] Private review metadata is in
  `20261028T090459739318Z-wallet-notice-smoke-review.jsonl`; raw answers stay
  private. The isolated ledger after v2-101 is 3,257,164 micro-USD
  reserved/estimated, not an invoice or provider balance. The forward-fix
  cannot convert this round's FAIL into PASS.
- [ ] Full 108-case, four 12-turn, controlled Telegram, account
  data-handling/security and release gates remain open. Draft PR #66 stays
  preproduction; Kimi is inactive and production unchanged.

## 2026-10-28 prior 80633ce smoke and source-grounding checkpoint

- [x] Verify exact-SHA [ZION CI 40658239837](https://github.com/zettaceo/zion-community-bot/actions/runs/40658239837)
  for `80633cebe33163de1b177ce40c23301cc645becf`: 922 tests, secret scan
  and project validation. Private frozen synthetic/PUBLIC manifest
  `20261028T083844656088Z-comparison-status-smoke-manifest.json` passed
  20/20 source/cost preflights.
- [!] K3 v2-001 and v2-021 passed human review. v2-041 is the **first human
  FAIL** for an unsupported wallet-connection-by-signature claim. The initial
  PASS review was corrected in a private append-only event. v2-051, 061, 065,
  091 and 094 were called before that correction; they remain evidence/cost
  **outside the qualifying stop-on-first-failure smoke sequence**. v2-094 also
  promised community notification without a source. v2-101 and v2-103 were
  NOT EXECUTED. No Ministral result was established in this round. Review
  metadata is private in
  `20261028T083844656088Z-comparison-status-smoke-review.jsonl`; no raw
  answer is in the repository.
- [x] An isolated guard/prompt forward-fix blocks the two unsupported claims
  and bounded paraphrases while preserving denial/quotation controls. 40
  focused tests and 923/923 local tests, secret scan and validation pass.
- [~] Isolated ledger: 2,952,594 micro-USD reserved/estimated, not an invoice
  or provider balance. Exact-SHA CI and a fresh frozen provider retest are
  **PENDING**. Do not relabel earlier failures or out-of-sequence calls PASS.
- [ ] Full 108-case, four 12-turn, controlled Telegram, data-handling/security
  and release gates remain open. Draft PR #66 remains preproduction; Kimi
  inactive and production unchanged.

## 2026-10-27 prior 11c26ff smoke and comparison-status checkpoint

- [x] Verify exact-SHA [ZION CI 40580235294](https://github.com/zettaceo/zion-community-bot/actions/runs/40580235294)
  for `11c26ffd328b76d27f51842c4f546657ad26d23f`: 922 tests, secret scan,
  validation. Frozen synthetic/PUBLIC preflight passed 20/20.
- [!] K3 passed human review for the first eight smoke IDs. v2-101 then failed
  `missing_feature_status` with text withheld, and v2-103 was NOT EXECUTED.
  Ministral was not retested because the passive-seed fix did not target its
  previous best-route failure. No model passed the entire smoke.
- [~] Extend the existing PUBLIC/CURRENT comparison-status companion and
  delivery classifier/fallback to the exact v2-101 phrasing. Focused
  KnowledgeTools and AIService tests passed 22/22, including exact-tier and
  generic-price negative controls and a source-bounded concern-aware fallback.
  Local validation passed 922/922 tests, secret scan and project validation
  on 2026-10-28. Exact-SHA CI and fresh provider acceptance are pending.
- [ ] Full 108-case, four 12-turn, controlled Telegram, data-handling/security
  and release gates remain open. Kimi stays inactive; production unchanged.

## 2026-10-27 prior f678720 smoke and forward-fix checkpoint

- [x] Freeze `f6787207ec45de6f52edd846962cb7f37f3acd9f` and verify exact-SHA
  [ZION CI 40579482818](https://github.com/zettaceo/zion-community-bot/actions/runs/40579482818):
  SUCCESS with 922 tests, secret scan and validation; local 922/922 also passed.
  All 20 synthetic/PUBLIC source and cost preflights passed.
- [!] Execute v2-001 once per model. Ministral stopped on
  `AUTOMATED_FAIL / unsupported_route_optimization`, with output withheld.
  K3 passed automated checks but human factual review marked **FAIL** for an
  unconditional passive future seed-request promise; its 0x/Jupiter/LI.FI
  routing explanation was grounded. Nine other smoke IDs per model were
  NOT EXECUTED. Private metadata is in
  `20261027T203709932920Z-swap-context-smoke-review.jsonl`.
- [x] A narrow forward-fix adds a passive-voice guard and explicit seed-safety
  wording in the prompt; focused tests passed 39/39 and full local validation
  passed 922/922 with secret scan and project validation OK. Exact-SHA CI and
  any new frozen smoke are pending. No prior model FAIL is erased.
- [ ] Qualify a model through smoke, 108-case, four 12-turn and controlled
  Telegram stages; complete security/data-handling and release approval gates.
  Kimi remains inactive and production unchanged.

## 2026-10-27 prior 0b67cbe smoke and forward-fix checkpoint

- [x] Freeze `0b67cbe6ca254f5d120fc872f4d8f3da89a92325` and verify
  exact-SHA [ZION CI 40520733751](https://github.com/zettaceo/zion-community-bot/actions/runs/40520733751):
  SUCCESS with 914 tests, secret scan and validation; local 914/914 also passed.
- [!] Execute the first synthetic/PUBLIC v2-001 case once per model from private
  manifest `20261027T142417435209Z-route-guard-smoke-manifest.json`.
  Both automated results were `REVIEW_REQUIRED / accepted`, then factual
  review marked Ministral and K3 **FAIL**. Ministral named a quote source not
  present in its retrieved section and generalized wallet-signature
  confirmation. K3 moved a bridge availability qualifier to swaps and made a
  categorical future promise from a seed-phrase warning. Broader PUBLIC/CURRENT
  corpus does discuss temporal swap availability; the K3 finding is about
  retrieved grounding and wording, and its original FAIL remains recorded.
  Nine other smoke IDs per model were NOT EXECUTED.
- [x] Prepare a material fix: bounded three-section PUBLIC/CURRENT
  companion retrieval for explanatory singular/plural swap questions, a prompt
  that preserves the scope of retrieved facts, and a source-conditional output
  guard. Focused tests passed 21/21 and 39/39; full local validation passed
  922/922 with secret scan and project validation OK. Exact-SHA CI and a new
  frozen smoke are still pending.
- [ ] Human-accept both models' smoke before a comparable full benchmark; run
  the remaining 108-case and four 12-turn acceptance stages as applicable.
  Controlled Telegram, account data-handling/security and release approval
  remain open. Kimi is inactive; production is unchanged by this work.

## 2026-10-27 prior smoke and forward-fix

- [x] Freeze fee-scope candidate `a4944356f7d1f10ff890393ca97bdd8077391e23`.
  Exact-SHA [ZION CI 40515511601](https://github.com/zettaceo/zion-community-bot/actions/runs/40515511601)
  and 914/914 local tests, secret scan and project validation passed.
- [!] Run one case on the frozen synthetic/PUBLIC smoke manifest
  `20261027T135123615841Z-bridge-fee-smoke-manifest.json`. Ministral v2-001
  was automated `REVIEW_REQUIRED / accepted`, then independent review **FAILED**
  an unsupported best-quote assertion. Nine other Ministral cases and all K3
  cases were NOT EXECUTED. This candidate did not pass smoke.
- [x] Add a bounded best-quote prompt/guard forward-fix and delivery regression;
  independent adversarial review found negation, provider-name punctuation and
  sentence-carry bypasses, now covered by tests. Candidate
  `79c2dcc735e95603939413e4fea60483b4c60999` passed 914/914 local
  tests, secret scan, project validation and exact-SHA
  [ZION CI 40516764932](https://github.com/zettaceo/zion-community-bot/actions/runs/40516764932).
- [x] Reproduce and cover false positives on user-selected routes/denials and
  false negatives on unsupported minimum-price claims. The narrow follow-up
  guard change passed 914/914 local tests, secret scan and validation.
- [!] Exact-SHA CI later passed for this follow-up at 0b67cbe; the newly
  frozen provider acceptance then failed as recorded above. Full 108-case,
  four 12-turn, controlled Telegram, data-handling/security and release gates
  remain open. The isolated evaluation ledger after a494 v2-001 was
  2,342,437 micro-USD reserved/estimated, not a provider invoice. Kimi
  remains inactive and production unchanged.

## Prior 2026-10-27 provider benchmark checkpoint

- [x] Freeze candidate `c06f53b1f1cdd018deadebc2e25991ee44162459`
  and refresh K3/Ministral official price snapshots on 2026-10-27. Exact-SHA
  [ZION CI 40474911066](https://github.com/zettaceo/zion-community-bot/actions/runs/40474911066)
  succeeded; 911/911 local tests, secret scan and project validation passed.
- [x] Run the predeclared ten-case synthetic/PUBLIC smoke on private manifest
  `20261027T083840602194Z-smoke-rerun-manifest.json`. Ministral stopped on
  v2-001 `AUTOMATED_FAIL / unsupported_route_optimization`; nine cases were
  NOT EXECUTED. K3 passed human review 10/10, mean 4.7811/5. The final K3
  review is `20261027T083840602194Z-smoke-rerun-human-review-v2.jsonl`.
- [!] Freeze the remaining 98 synthetic/PUBLIC-only cases without repeating
  smoke in private manifest
  `20261027T085139396155Z-full-continuation-manifest.json`. K3 v2-002
  passed human review; v2-003 failed human review on a Bridge platform-fee
  generalization accepted by the guard (factuality and calibration 3/5;
  mean 4.33/5). The other 96 cases were NOT EXECUTED. Full 108-case quality
  remains FAIL/incomplete, with no provider winner.
- [x] Implement the material v2-003 fee-scope forward-fix; focused guard and
  delivery regressions, 914/914 local tests, secret scan and validation passed
  on 2026-10-27. Independent adversarial review supplied the negative and
  conditional-positive examples now covered by tests.
- [x] Complete exact-SHA CI for the fee-scope fix; the subsequent frozen
  provider round failed as recorded above. All
  four 12-turn conversations, controlled Telegram acceptance, security and
  release gates remain open.

Estimated charges in this round: Ministral smoke 438, K3 smoke 292,681,
K3 v2-002 34,413 and K3 v2-003 29,409 micro-USD. Cumulative isolated ledger
after v2-003: 2,341,975 micro-USD reserved/estimated, not an invoice or
provider balance. Kimi remains inactive and production unchanged. The
following 2026-10-26 checkpoint is historical.

## Historical 2026-10-26 provider smoke decision

The frozen ten-case synthetic/PUBLIC smoke at candidate
`6774e8b21c4a512bc77c5eb83d62c40aa119ef46` returned automated
`REVIEW_REQUIRED` for all ten generated attempts per model, but both models
**FAILED human smoke acceptance**. Ministral 8B failed at v2-001 on unsupported
best-route/quote optimization; its other nine generated answers were not human
reviewed. Kimi K3 passed v2-001 and v2-021, then failed v2-041 on an unsupported
wallet connection/signature generalization and named wallet examples; its
other seven generated answers were not human reviewed. See
`COGNITIVE-V2-QUALITY-FINDINGS.md` for private evidence basenames and costs.

- [x] Make material, source-bounded candidate fixes for both fatal findings;
  keep provider output advisory and Guardian authority deterministic. Local
  validation: 911/911 tests, secret scan and project validation OK. This is
  not a provider quality PASS.
- [ ] Freeze a new versioned candidate/manifest before any retest. Keep every
  prior failure in the evidence; do not repeat requests merely to obtain green.
- [ ] Human-accept smoke, then run the full comparable 108-case benchmark and
  four independent 12-turn conversations under the bounded budget.
- [ ] Complete controlled Telegram acceptance and separate operator approval
  before any production promotion or Kimi activation.

No full benchmark or production readiness is claimed by this smoke checkpoint.
Cumulative isolated ledger: 1,985,034 micro-USD
reserved/estimated, not an invoice or provider balance.

## Measured identity and environment

- main: `d5db6a1c4308243a0bbb8d811e2ac8f0af408a0e`; CI run 36140123319 SUCCESS.
- development: `57a10444422373271fbd602acc083199346b5031`; CI run 39163089575 SUCCESS.
- production: `472a4b3f0ce73a8635d400c0073701013c357b92`; CI run 39163164036 SUCCESS.
- Production is four history commits ahead of development, with identical tracked content.
- Working branch: `codex/multi-agent-cognitive-v2` at `/home/zetta/.codex/worktrees/zion-cognitive-v2`.
- The operator explicitly authorized an isolated worktree on the Acer after the
  mission's section 64 host restriction was raised. Production checkout is not
  a development directory.
- Read-only host check on 2026-10-26: service active/running, NRestarts 0;
  current runtime and production checkout resolve to the production SHA above.
  No restart/deploy in this increment.
- The active SQLite database is already schema v4. A private disposable copy
  passed candidate v4→v4 double-initialization with integrity/FK, 19-table
  count and fingerprint preservation. A separate synthetic v2→v4 regression
  passed; there is no candidate schema/migration delta. Release-time backup
  and exact-SHA preflight remain pending.
- Open unrelated PR #11 remains untouched. Recent related merged PRs: #59–65.
- Rulesets and production protection endpoints returned HTTP 403 (account plan
  restriction). Governance is NOT PROVEN. Prior waivers are not silently renewed.
- Fresh local baseline: 724 tests PASS, SECRET SCAN OK, ZION VALIDATION OK.
  Log: `/tmp/zion-cognitive-v2-baseline.log`. This is base evidence, not v2 evidence.

## Existing architecture and gaps

One ZION group intake already selects bounded identities; registry, DM gates,
protected secondary identity store, durable speaker arbitration, minimized
routing telemetry, Control Center and agent-filtered Knowledge already exist.
Mistral-specific Settings/client/accounting remain the current provider path.
Kimi registration and bounded synthetic evaluations have been measured, but no
full comparative benchmark, production model choice or activation is claimed.

The user-reported endpoint-to-swap contamination was reproduced for five
explicit topic-switch variants. Existing follow-up heuristics accepted `E...`
before checking the new subject. The exact unprefixed swap question passed the
baseline fixture; the real Telegram failure is not claimed reproduced verbatim.

The Z-SWAP source repo is now `/home/zetta/swap-z-app`; fetched main is
`986ae759c1c76fe23967a8e61489d986b2bb9a51`. Its public source of truth and fee
implementation supersede the bot's old claim that Solana platform fees are
universally disabled. `tier/types.ts`, `founders-commercial-truth.ts`,
`chains.ts` and `founders-public/facts.ts` are unchanged from the prior snapshot.
This comparison does not prove deployment/runtime availability of all app features.

## Production authorization boundary — latest operator instruction

Prepare and finish the implementation and available validations first. Deliver
an evidence-backed final report for operator review. Production merge and deploy
require a NEW explicit approval after that report. Prior statements permitting
production work do not authorize bypassing this latest boundary. Until then,
work remains in the isolated development branch/draft PR.

## Revised delivery sequence authorized by operator

The earlier plan expected Kimi registration after publication through ZION DM.
The operator subsequently chose and completed hidden local terminal provisioning
on 2026-10-25. Metadata-only validation passed; the credential remains private
and Kimi is not active in Telegram. Release planning still distinguishes:

1. Infrastructure/conversation release with Mistral retained and protected Kimi
   registration present. It still needs ordinary code, CI, security, release and
   controlled cutover checks; this change of sequence does not waive those gates.
2. Synthetic/public A/B evaluation and account policy review. Bounded Kimi
   evaluations have exposed unresolved quality failures; registration is not
   provider acceptance. Kimi remains inactive until the independent gates pass.
3. Real Telegram acceptance, which cannot be inferred from unit tests or smoke.

Never label deferred Kimi benchmarks PASS or the entire v2 mission complete.

## v2 phase tracking (mission sections 63–73)

- [~] 00 Reconciliation: mandatory documents reviewed; remote identities/CI and
  fresh baseline measured. Older deployment labels need continued reconciliation.
- [~] 01 Threat model and architecture: preserve existing boundaries; extend for
  provider data handling, cost admission, context isolation and output validation.
- [~] 02 Registry/authority: expanded intents and existing deterministic authority implemented; final v2 acceptance pending.
- [~] 03 Telegram store: protected primary-token resolution and matching release
  preflight implemented; actual primary-token migration deferred to approved cutover.
- [~] 04 Bounded provider protocol and Kimi adapter implemented/tested; host-owned runtime selection and approval expiry implemented. No candidate is activated.
- [~] 05 Provider-aware protected store and private DM provisioner implemented;
  pending Kimi capture survives restart as interception-only metadata, with fresh
  authorization required for storage. The operator also provisioned a Kimi
  credential through hidden local terminal input; private registration does not
  activate the runtime provider.
- [~] 06 DM enforcement: identity/private-channel paths reviewed; deterministic denial-before-AI and
  v2 native delivery regressions retained. Real Telegram acceptance pending.
- [~] 07 Bounded reviewed aliases and confidence tiers implemented; wider evaluation pending.
- [~] 08 Expanded intents, stable DB delivery families and noisy-language handler regressions pass.
- [~] 09 Context isolation: first bounded topic-label increment implemented; six
  switch pairs, including five baseline failures, now pass. Structured user/issue
  state, fixed fragment slots, bounded whole-turn history and a 24-turn adversarial
  regression are implemented. Live acceptance remains pending.
- [~] 10 Speaker arbitration: v2 duplicate-intake test exercises native two-request generation and proves one external speaker with usage counted once. Live concurrency acceptance remains pending.
- [~] 11 Identity transport: official Bot API/FAQ rechecked 2026-10-25 and local transport boundary
  reviewed. Actual Telegram configuration/delivery acceptance remains pending.
- [~] 12 Control Center: private provider/model token usage, optional estimated currency accounting and credential-versus-activation views implemented. Currency caps are not imposed without a reviewed host policy.
- [~] 13 Knowledge classification: pre-generation classification/expiry/agent boundaries reviewed with DM
  policy: only the explicit MIMIR technical projection is CONTROLLED-accessible;
  raw paper excluded and alternate-provider/tool context PUBLIC-only. Broader live
  source certification remains pending.
- [~] 14 APN/paper: canonical APN and final 83-page controlled paper identified;
  all 83 pages visually classified in `technical-paper/Z-SWAP-83-PAGE-REVIEW.md`.
  Routing and portfolio contradictions reconciled against the exact application
  snapshot; broader live source certification remains pending. Raw controlled
  material is not indexed.
- [~] 15 Manifest/freshness: plans snapshot updated after current source/code check;
  schema-2 snapshot/expiry/supersession enforcement implemented. Existing sources
  explicitly remain snapshot_only; no fresh runtime verification is fabricated.
- [~] 16 PUBLIC knowledge registry now wired to native Mistral function transport: one validated batch, bounded outputs, no second tool round and no arbitrary operations. Kimi remains text-only.
- [~] 17 Host-owned model-selection policy implemented: complexity/evidence/scope and valid quality/privacy/pricing approvals required, plus configured currency admission. Candidate quality acceptance remains pending.
- [~] 18 Fixed response-mode planner integrated into shared provider prompt; live quality acceptance pending.
- [~] 19 ZION executive response policy implemented; live competitive quality still FAIL/PENDING.
- [~] 20 MIMIR mechanism/evidence policy implemented; live response acceptance still pending.
- [~] 21 EIR diagnosis/claim boundaries implemented; observed cost hallucination now guarded, live retest pending.
- [~] 22 FREYR objection planning and business retrieval corrected; live pricing-context retest pending.
- [~] 23 Structured handoff implemented: fixed labels, no generated transcript transfer, no authority grant and no other-user issue transfer. Existing one-hop delivery bound is preserved.
- [~] 24 Confidentiality: shared AIService output boundary tested across all four
  identities with 24 malicious/unsupported outputs, plus rejection-to-safe-answer
  recovery. Rejected content is absent from SQLite and usage remains accounted.
  This is deterministic simulated-provider evidence, not live model acceptance.
- [~] 25 Injection: preserve existing controls; expanded source/provider matrix pending.
- [~] 26 Deterministic output guard implemented; not a complete factuality or confidentiality proof.
- [~] 27 Mistral timeout/bounded 429 retry/circuit preserved; every HTTP attempt
  now has durable admission. Cross-provider fallback remains blocked by acceptance.
- [~] 28 Isolated monetary evaluation ledger and integrated runtime provider/model
  token reservations implemented. Optional runtime currency caps, dated prices, frozen-rate settlement and bounded model selection are implemented. Real candidate activation remains blocked by acceptance.
- [~] 29 Versioned 108-case synthetic dataset (18 categories), generation evaluator and human-review gate implemented.
- [!] 30 Live A/B benchmark: store, dated official prices, credential, bounded
  spend and synthetic/PUBLIC-only inputs supported small Mistral/Kimi trials.
  The full comparable benchmark, human review and provider decision remain open.
  The frozen-run protocol, predeclared smoke set and scoring rubric are prepared
  in `AI-BENCHMARK.md`; no new provider PASS is inferred from that document.
- [~] 31 Four versioned 12-turn generation scenarios and bounded actual-answer
  history implemented; stop on provider/guard/repetition failure, per-turn durable
  evidence and mandatory human review. Simulated-provider regression passes;
  the latest bounded K3 debate stopped at turn 1 on `missing_feature_status`;
  other scenarios and runtime routing/tools/Telegram acceptance remain pending.
  See `COGNITIVE-V2-CONVERSATION-EVALUATION.md`.
- [~] 32 Full regression: prior committed candidate `220803f` passed exact-SHA
  CI [40345835465](https://github.com/zettaceo/zion-community-bot/actions/runs/40345835465)
  with 895/895. This revision's fee/status guard and opt-in independent-case
  evaluation changes passed 903/903 locally, SECRET SCAN OK and ZION
  VALIDATION OK (`/tmp/zion-v2-candidate-final-validation-2.log`). Its own
  exact-SHA CI is pending. The baseline was 724/724.
- [~] 33 Documentation: this checkpoint and cognitive routing contract added.
- [~] 34 Draft PR #66 open against development. Exact-SHA CI passed at
  `220803f06ad7911a4e93adedcada77f7f68a56b5` (run 40345835465).
  This later local revision needs its own exact-SHA check and final v2 release audit.
- [!] 35 Production promotion: requires NEW user approval after the final report,
  plus release/security gates. Kimi activation separately blocked.
- [ ] 36 Exact production SHA revalidation.
- [ ] 37 Controlled Acer cutover.
- [!] 38 Real Telegram acceptance: requires messages from a real human/test account;
  sending with a bot is not a substitute. The 17-case and cognitive-v2 record
  is prepared in `COGNITIVE-V2-TELEGRAM-ACCEPTANCE.md`; none was executed on
  this candidate. New v2 behavior is not deployed.

## Tools, policy and source checkpoint — 2026-10-20

- Native Mistral tools, host-approved selection, optional monetary admission and
  structured handoff are implemented; see `COGNITIVE-V2-GENERATION-POLICY.md`.
- Baseline composition still supplies no candidate approvals, alternative adapters
  or monetary policy. Kimi registration does not create any of them. Promotion
  and actual model/cap activation require the separate acceptance gates.
- Final combined validation on 2026-10-21: 847 tests PASS, SECRET SCAN OK,
  ZION VALIDATION OK (`zion-v2-final-policy-validation.log`). Focused transport/
  policy/store suite: 27 PASS. An earlier 845-test run had one fixture error: the
  synthetic HTTP response omitted `content`, required by the new body-size guard.
  The fixture now supplies serialized content; the guard and assertions remain.
  The final run includes two additional response-bound/retry-accounting tests.
- Exact paper hash/page count reacquired, with fresh visual matrices 76–78 review.
  Corrected the CoW-as-quote-source conflation in all three affected knowledge
  sections using source `986ae759` and retained all classifications/qualifiers.
  Removed repo/SHA prose from the loaded public status chunk; provenance remains
  in manifest metadata. The subsequent 2026-10-21 review classified all 83 pages;
  see the page ledger for source conflicts and remaining runtime boundaries.
- Existing live failures remain open. No further paid calls were made merely to
  obtain green output. The generation-only evaluator is not acceptance for the
  new native tool path; controlled live tests still need to exercise that path.

## Private capture and shared output checkpoint — 2026-10-20

- Restart before the first Kimi candidate now preserves an interception-only
  latch. The candidate is deleted/refused, never validated or sent to AI; a fresh
  command is required to authorize storage. Explicit cancellation and switching
  to Mistral clear the latch durably. Failure to persist/read/clear it fails closed.
- Focused private provisioning: 34 tests PASS. Full suite at that source state:
  815 PASS, SECRET SCAN OK, ZION VALIDATION OK.
- Additional output matrix: six rejected output classes for each of four agents,
  with untrusted founder authorization in conversation context; eight sequential
  rejected/safe responses verify recovery without poisoning the circuit. Focused
  AI suite: 31 PASS. No network, live token or production state used.
- Evidence: `zion-v2-capture-restart-validation.log` under the persistent worktrees
  directory. Final combined regression: **817 tests PASS**, SECRET SCAN OK,
  ZION VALIDATION OK, in `zion-v2-capture-output-validation.log`.
- The earlier real Mistral quality failures remain open in
  `docs/COGNITIVE-V2-QUALITY-FINDINGS.md`. These controls do not certify factuality.

## Recovery checkpoint — 2026-10-19

The temporary worktree disappeared between turns. Both committed checkpoints
survived. Uncommitted source edits were recovered from recorded file-writing
commands into the persistent worktree above; no operational/provisioning commands
were replayed. Fresh full validation: **754/754 PASS**, SECRET SCAN OK,
ZION VALIDATION OK. Evidence outside repo:
`/home/zetta/.codex/worktrees/zion-cognitive-recovery-validation.log`.

The second increment includes ephemeral user/thread fragment slots, shared A/B
prompt construction, public-only candidate-provider context, and fail-closed
output handling. It does not constitute complete cognitive architecture v2.
No schema, production service, production checkout, token or release ref changed.
The former `/tmp` evidence files are historical references and may no longer exist.

The final PT-BR 83-page paper was initially reviewed at pages 2, 22, 77, 78;
all 83 pages were subsequently visually classified on 2026-10-21. It is CONTROLLED, not blanket public authority.
See the source inventory addendum; broad feature/runtime reconciliation remains
pending. Do not index the raw PDF or promote unverified features.

## Conversation hardening and smoke review — 2026-10-19

- Full regression after private provider panel, explicit risk-caveat handling,
  private-route filtering and long-context regression: 773/773 PASS; secret
  scan and normal validation OK. Evidence: `zion-v2-hardening-validation.log`
  under `/home/zetta/.codex/worktrees/`.
- A 24-turn topic-switch test initially hit the fixture's real four-requests/minute
  cap at turn five. The fixture now advances both wall/monotonic clocks by 31s;
  neither AI pacing nor Guardian thresholds were disabled. It passes including
  a final founder-identity claim requesting private endpoints/API key.
- Mistral smoke evidence `20261019T231516206919Z-ministral-8b-2512.jsonl`
  completed five generation cases, all marked REVIEW_REQUIRED automatically.
  Assistant review found an unsupported transaction-safety guarantee in v2-001.
  Therefore this is NOT accepted. A regression now rejects that exact expression
  while allowing explicit denials of such guarantees. The private response guard
  is still not a complete factuality proof. Cumulative estimated evaluation cost
  at that checkpoint: 2,942 micro-USD, not an invoice or account balance.
- Full regression after this safety-guarantee fix: 773/773 PASS, secret scan and
  validation OK (`zion-v2-smoke-finding-validation.log`).
- Kimi evaluation remains deferred by operator choice. The isolated stronger
  Mistral smoke returned HTTP 403 on the first case and stopped. It is NOT
  EXECUTED for quality; the reason for provider refusal is not independently
  known. Evidence: `20261019T231750801923Z-mistral-large-2512.jsonl` in the same
  private evaluation directory. Cumulative reserved-or-spent estimate is 10,090
  micro-USD; the rejected request reservation was retained, not claimed billed.
- Current full validation including stronger-candidate price accounting:
  **774/774 PASS**, SECRET SCAN OK, ZION VALIDATION OK. Evidence:
  `/home/zetta/.codex/worktrees/zion-v2-large-validation.log`.
  No production, configuration, key or runtime switch occurred.

## Executive quality checkpoint — 2026-10-20

- Competitive objection planning and role instructions implemented; the exact
  mission objection is now included alongside seven additional synthetic cases.
  Original 100 evaluation cases preserved. Selection supports bounded exact IDs.
- Initial four-case live round failed human/automated review. Retrieval and
  evaluator continuation issues were fixed, and observed unsupported output
  received regression guards. The exact retest stopped at the first case because
  an unapproved market-service reference was blocked. Remaining three cases were
  NOT EXECUTED in that retest, not PASS.
- Full local regression: 810 tests PASS, SECRET SCAN OK, ZION VALIDATION OK.
  Live quality is still FAILED/PENDING. See
  `docs/COGNITIVE-V2-QUALITY-FINDINGS.md` for evidence and limitations, and
  `docs/EXECUTIVE-ARGUMENTATION.md` for the response contract.
- Kimi remains unactivated. No production configuration, service or token changed.

## Runtime budgets and primary identity — 2026-10-20

- Every runtime Mistral HTTP attempt now reserves tokens durably before I/O,
  including retries and route/classification calls. Shared/provider/model caps
  use the existing daily token policy, without changing production configuration.
- Unknown results retain the reservation across timeout, cancellation and restart.
  Successful usage settles once; overrun/corruption fails closed. No prompts or
  identities are stored in this ledger; SQLite schema is unchanged.
- Private Control Center shows charged/reserved totals and reports unavailable
  accounting explicitly. This is not a currency invoice. No Kimi activation,
  model upgrade or automatic fallback occurred.
- Budget checkpoint: 801 tests PASS, SECRET SCAN OK, ZION VALIDATION OK.
  Evidence: `/home/zetta/.codex/worktrees/zion-v2-runtime-budget-final-validation.log`.
- Primary Telegram resolution now supports the protected store in both startup
  and release preflight. Unsafe storage blocks fallback; absent storage preserves
  legacy behavior until an approved migration. No real token was read/moved.
  Focused identity/application/config validation: 20 tests PASS.
- Details: `docs/PROVIDER-RUNTIME-BUDGET.md` and
  `docs/PRIMARY-TELEGRAM-IDENTITY.md`. Full combined validation: 805 tests
  PASS, SECRET SCAN OK, ZION VALIDATION OK. Evidence:
  `/home/zetta/.codex/worktrees/zion-v2-budget-identity-validation.log`.

## Knowledge freshness enforcement — 2026-10-20

- Manifest schema 2 carries source ID/title/type, snapshot date, authority,
  reciprocal supersession, freshness, expiry and notes. Schema 1 remains readable
  for legacy fixtures with the previous status semantics.
- DRAFT and UNVERIFIED are explicitly excluded; a CURRENT source cannot also be
  superseded. Unknown, conflicting, duplicate or cyclic links reject the manifest.
- Expiry is checked on every retrieval in UTC, including after the reload date.
  Existing approved projections are labelled snapshot_only, not freshly verified.
- Focused retrieval/freshness tests: 42 PASS. Full validation: 787 tests PASS,
  SECRET SCAN OK, ZION VALIDATION OK. Evidence:
  `/home/zetta/.codex/worktrees/zion-v2-freshness-validation.log`. This does not semantically reconcile contradictory claims in
  different current documents; those still require source review.

## Structured state and replay hardening — 2026-10-19

- Structured ephemeral summaries track only bounded topic/agent/entity labels,
  unverified open issue and objection state. Whole exchanges replace arbitrary
  character slicing. A different participant cannot inherit another user's issue.
- Monetary claims absent from approved context are rejected by currency/amount.
  This does not certify attribution to the correct plan or network.
- Full validation of these changes: 779 tests PASS, SECRET SCAN OK, ZION
  VALIDATION OK (`zion-structured-state-validation.log`).
- A regression reproduced Kimi capture re-entry after failed validation and a
  runtime restart: the capture handler returned without stopping dispatch.
  A minimized message-identity marker now blocks replays within the configured
  idempotency retention window. No candidate/hash is stored in that marker;
  schema unchanged. Metadata is persisted before deletion/provider validation
  so a crash does not discard the replay boundary. DB failures stop dispatch.
  Full regression: 782 tests PASS, SECRET SCAN OK, ZION VALIDATION OK;
  evidence: `/home/zetta/.codex/worktrees/zion-v2-replay-validation.log`.
  The focused restart regression passes. This is not a guarantee about arbitrary
  unsolicited keys or credentials first sent after an expired/lost capture arm.
- Production remains untouched and requires approval after the final report.

## Kimi private-chat provisioning — 2026-10-19

Operator-selected input channel: private ZION DM. Implemented explicit-operator
capture, delete-before-validation, bounded TTL, cancellation, metadata-only
status/audit, rollback on audit failure, and mutually exclusive Mistral capture.
No automatic provider activation. Full validation: **771/771 PASS**, SECRET SCAN
OK, ZION VALIDATION OK. Focused provisioning/application tests: 13 PASS.
Evidence: `/home/zetta/.codex/worktrees/zion-kimi-dm-validation.log`.
Production delivery is pending an approved release containing these handlers;
do not invite the operator to paste a credential into the running older bot.

## Tools/planner checkpoint — 2026-10-19

Fresh full validation after local knowledge operations, response planning,
contextual `cm` recovery and provider-output persistence regression:
**763/763 PASS**, SECRET SCAN OK, ZION VALIDATION OK.
Evidence: `/home/zetta/.codex/worktrees/zion-cognitive-tools-planner-validation.log`.
Focused tools/evaluation/language: 14 PASS. Planner/boundaries/acceptance: 18 PASS.
The service was independently read as active/running with NRestarts=0, still at
production `472a4b3f0ce73a8635d400c0073701013c357b92`; no cutover occurred.

## Live baseline smoke — 2026-10-19

A generation-only synthetic/public smoke on `ministral-8b-2512` stopped after
case `v2-031` returned `AUTOMATED_FAIL`, reason `absolute_safety`. Case `v2-001`
is `REVIEW_REQUIRED`, not accepted. The rejected answer was withheld from the
evidence by design, so the exact phrasing and potential guard false-positive
cannot be inferred from the retained record. No automatic retry or weakened
rule was used. Two provider calls; estimated cost 770 micro-USD (USD 0.00077).
Evidence:
`/home/zetta/.local/state/zion-community-bot/evaluations/cognitive-v2/20261019T161009625327Z-ministral-8b-2512.jsonl`.
No full benchmark or winner declaration. Remaining smoke cases were NOT EXECUTED.

## Increment evidence and limitations

- Focused: 84 tests PASS (`/tmp/zion-cognitive-v2-focused.log`).
- Baseline failure: `/tmp/zion-context-v2-before.log`, five failing switch variants.
- New code is a bounded lexical topic discriminator, NOT complete semantic routing.
- No DB/schema, Guardian, authority, dependencies, services or real secrets changed.
- First increment used no paid provider requests; see the subsequent smoke evidence above.
- First increment implementation commit: `1c0cff7ae5c318eb96c3d67a747e1c29eb9dc4b9`.
  Local full validation 727/727 PASS; no new remote CI or production acceptance yet.

---

# Historical implementation plan (v1 multi-agent mission)

# ZION Multi-Agent Command System - Implementation Plan

## Mission status

- Status: ACTIVE
- Development base: `origin/zion-v1.1-dev`
- Verified base SHA: `c88c3dd8947fa32168feddaa88dbfb870a1eed64`
- Work branch: `feature/zion-multi-agent-core`
- Production branch: `zion-v1` (no development is performed there)
- Baseline: 611/611 tests passed with the audited release runtime on 2026-10-15.

This document is the tracked execution authority for the multi-agent mission. An
item is DONE only when its implementation, relevant tests, documentation, and
validation evidence are complete.

Status markers:

- `[ ]` TODO
- `[~]` IN PROGRESS
- `[x]` DONE
- `[!]` BLOCKED

## Objective

Evolve the existing Telegram application into one coordinated ZION Multi-Agent
Core. ZION remains the only deterministic Guardian and orchestrator. MIMIR, EIR,
and FREYR receive bounded public speaking roles without moderation authority.
For every inbound message, the system produces either no conversational reply or
one reply from exactly one authorized identity.

## Reconciled repository state

| Ref | Verified SHA | State |
|---|---|---|
| `origin/main` | `d5db6a1c4308243a0bbb8d811e2ac8f0af408a0e` | CI #1322 SUCCESS |
| `origin/zion-v1` | `68e860c411ecf0e63305baa72c6ca66688d7832c` | CI #1326 SUCCESS; production line |
| `origin/zion-v1.1-dev` | `c88c3dd8947fa32168feddaa88dbfb870a1eed64` | CI #1325 SUCCESS; development authority |

`origin/zion-v1.1-dev` is an ancestor of `origin/zion-v1`. Their tracked content
is identical at reconciliation time; production contains one promotion commit.
The pre-existing local development branch was stale and is not used. The work
branch was created from the verified remote development SHA in an isolated
worktree.

## Preserved invariants

- Deterministic Guardian decisions remain outside Mistral.
- Only ZION has delete, strike, mute, ban, containment, and lockdown authority.
- Sensitive-content checks run before AI and before DM conversation handling.
- No network await occurs inside a SQLite transaction.
- Telegram delivery plus SQLite state is never described as exactly once.
- Secrets never enter Git, logs, SQLite, diagnostics, backups, prompts, or chat.
- SQLite/WAL integrity, process exclusivity, circuit breaker, token accounting,
  commit-pinned runtimes, rollback, and the existing host boundary remain intact.

## Target architecture

```text
Telegram updates
       |
       v
ZION Multi-Agent Core
       |
       +--> deterministic security and Guardian (ZION only)
       +--> DM access policy (before AI)
       +--> deterministic intent router, bounded AI fallback when needed
       +--> authority-filtered knowledge retrieval
       +--> durable speaker arbitration
       +--> one selected Telegram identity, or silence
```

The group has one intake authority. ZION receives and evaluates group updates.
MIMIR, EIR, and FREYR are outbound identities selected by the core; they do not
run competing group responders. Their private-update intake is isolated and
enforces the identity's DM policy before AI. A durable claim keyed by the source
chat and message/update identity is acquired before any external send. Retry and
uncertain-delivery handling fail closed against duplicate speakers.

## Initial identity and authority matrix

| Identity | Role | Group | DM | Moderation | Knowledge scope |
|---|---|---:|---|---|---|
| ZION | CCO / orchestrator | yes | creator only | full deterministic | community public |
| MIMIR | CTO | yes | closed | none | technical public/approved controlled |
| EIR | CXO / support | yes | public | none | support public |
| FREYR | CBO / partnerships | yes | public | none | business public/approved controlled |

## Decisions

1. Agent definitions are immutable registry data, not name-based conditionals.
2. Routing returns an intent and one candidate identity; arbitration owns the
   final speaking decision.
3. AI can help classify ambiguous benign intent, but cannot bypass authority,
   DM, knowledge, Guardian, or speaker policy.
4. Knowledge classification is enforced before context construction. Prompts are
   a second boundary, never the primary one.
5. Token storage extends the existing protected-store model with one explicitly
   bound token per identity and status-only diagnostics.
6. Public group intake remains centralized. This avoids four independent
   consumers racing on the same message.
7. Existing operational commands remain available. The creator-only inline
   Control Center becomes the preferred administrative surface.

## Principal risks

| Risk | Control / gate |
|---|---|
| Duplicate replies during races, retries, callbacks, or edits | durable speaker claim, deterministic message key, concurrent and crash-boundary tests |
| Secondary identity receives group updates and competes | centralized group intake, group handlers disabled for secondary identities, topology tests |
| DM policy checked after AI | policy gate before session, retrieval, or provider call; negative provider-call assertions |
| Cross-agent or prompt-injection exfiltration | pre-retrieval classification/scope filter, deterministic confidentiality filter, adversarial tests |
| Token disclosure or unsafe filesystem state | 0700/0600, owner/link checks, atomic writes, runtime redaction, no DB/log values |
| Schema migration harms live DB | additive migration, disposable rehearsal, rollback and preservation tests |
| Historical APN/pitch facts become current truth | source manifest, page-level reconciliation, conflict register, HISTORICAL/EXCLUDED state |
| Telegram API/privacy assumptions are wrong | verify official Bot API and library lifecycle before transport implementation |
| Unprotected GitHub branches weaken promotion governance | do not claim PROVEN; require explicit evidence or documented waiver at release gate |
| Real bot tokens unavailable during development | finish store/runtime with fakes; mark only real provisioning and live acceptance blocked |

## Phase checklist

### PHASE 0 - Repository reconciliation

- [x] P00.01 Fetch remote refs and record exact authoritative heads.
  - Evidence: table above; GitHub CI #1322/#1325/#1326.
- [x] P00.02 Reconcile development and production history/content.
  - Evidence: development is the direct ancestor of production; no tracked content delta.
- [x] P00.03 Create isolated worktree and work branch from remote development SHA.
  - Evidence: `feature/zion-multi-agent-core` at `c88c3dd...`.
- [x] P00.04 Run the unmodified baseline suite with the audited runtime.
  - Evidence: 611 tests, PASS, 2026-10-15.
- [x] P00.05 Read mandatory architecture, security, operations, deployment, release, configuration, and lock documents.
- [x] P00.06 Inspect the current Telegram, Guardian, AI, knowledge, DB, health, dashboard, logging, secret, model, config, and process-lock surfaces.

### PHASE 1 - Architecture and threat model

- [x] P01.01 Document centralized intake and multi-identity send topology.
  - Evidence: `docs/MULTI-AGENT-ARCHITECTURE.md`.
- [x] P01.02 Verify Telegram Bot API privacy, update, callback, reply, DM, and multi-token constraints from primary sources.
  - Evidence: official references recorded in the architecture document; runtime uses python-telegram-bot 22.8.
- [x] P01.03 Define trust boundaries, abuse cases, failure states, and least privilege.
  - Evidence: architecture threat table and least-privilege deployment section.
- [x] P01.04 Record delivery semantics and recovery policy without exactly-once claims.
  - Evidence: claim-before-send and UNCERTAIN state contract in the architecture document.
- [x] P01.05 Add architecture and threat-model tests or contract assertions.
  - Evidence: immutable registry, DM matrix, routing authority, claim-key, replay,
    edit, uncertainty, concurrency, migration, and privacy contracts are executable.

### PHASE 2 - Agent registry

- [x] P02.01 Add immutable identity, role, DM, authority, and knowledge-scope models.
  - Evidence: `zion/agents.py` immutable profiles and enums.
- [x] P02.02 Add registry validation for unique IDs/usernames and safe defaults.
  - Evidence: one owner per speaking intent; only ZION can moderate; silence intents have no speaker.
- [x] P02.03 Add complete registry unit tests.
  - Evidence: `tests/test_agent_registry.py`, 10 focused tests PASS.

### PHASE 3 - Secure multi-token identity store

- [x] P03.01 Implement identity-bound protected token storage outside Git.
  - Evidence: `zion/telegram_identity_store.py`; fixed state path is outside the worktree.
- [x] P03.02 Enforce owner, 0700/0600, regular file, no symlink/hardlink, atomic durability, and fail-closed reads.
  - Evidence: wrapper reuses the audited atomic `SecretStore`; focused filesystem tests PASS.
- [x] P03.03 Register loaded tokens with runtime log redaction.
  - Evidence: formatter test proves loaded token material becomes `[REDACTED]`.
- [x] P03.04 Expose CONFIGURED/MISSING/UNSAFE only.
  - Evidence: value-blind status matrix test PASS.
- [x] P03.05 Prove tokens never enter logs, SQLite, diagnostics, backups, or repository files.
  - Evidence: protected-store values are redacted from logs and absent from
    safe status, health/diagnostics, SQLite dumps, verified backups, WAL/SHM,
    and tracked repository content; secret scan PASS.

### PHASE 4 - DM access policies

- [x] P04.01 Enforce ZION CREATOR_ONLY before AI/session/retrieval.
  - Evidence: the existing ZION private intake returns before session, retrieval,
    or provider access for every non-operator numeric ID.
- [x] P04.02 Enforce MIMIR CLOSED before AI/session/retrieval.
  - Evidence: the secondary private handler rejects MIMIR before content,
    idempotency, retrieval, or provider access; negative test PASS.
- [x] P04.03 Enable EIR PUBLIC support DM.
  - Evidence: private intake preserves the EIR identity through retrieval and
    provider prompt; duplicate update is suppressed.
- [x] P04.04 Enable FREYR PUBLIC business DM.
  - Evidence: private intake preserves the FREYR identity through retrieval and
    provider prompt; duplicate update is suppressed.
- [x] P04.05 Add operator, ordinary-user, replay, and loop-prevention tests.
  - Evidence: ZION creator boundary, MIMIR closed DM, EIR/FREYR public DM,
    duplicate update suppression, and secondary group discard tests PASS.

### PHASE 5 - Intent routing

- [x] P05.01 Implement MODERATION/COMMUNITY/TECHNICAL/SUPPORT/PARTNERSHIP/UNRELATED/AMBIGUOUS taxonomy.
  - Evidence: `zion/router.py` returns registry-backed decisions for the full taxonomy.
- [x] P05.02 Add deterministic high-confidence routing and bounded AI fallback.
  - Evidence: deterministic routing runs first; Mistral can return only an
    allowlisted benign intent, confidence below 0.80 fails closed, and
    moderation is impossible through the fallback interface.
- [x] P05.03 Preserve natural conversation and silence for irrelevant chatter.
  - Evidence: unrelated and addressed-but-ambiguous messages resolve to silence.
- [x] P05.04 Test mixed, ambiguous, injection, and adversarial intent.
  - Evidence: support/technical precedence, confidentiality, agent injection,
    ambiguity, moderation, and private-route cases PASS.

### PHASE 6 - Speaker arbitration

- [x] P06.01 Add durable, atomic speaker claim keyed by inbound message identity.
  - Evidence: schema v3 `speaker_claims` plus atomic `BEGIN IMMEDIATE` claim.
- [x] P06.02 Enforce zero-or-one external speaker and authorized handoff.
  - Evidence: registry authority, concurrent durable arbitration, token-specific
    external send, sent-state completion, and duplicate-update suppression PASS.
- [x] P06.03 Define retry, uncertain-send, callback, edit, replay, and expiration behavior.
  - Evidence: sent/uncertain states never replay; only `failed_safe` can retry;
    edits share the original key; callbacks use the update identity; stale claims
    are quarantined.
- [x] P06.04 Add concurrent connections/tasks and crash-boundary tests.
  - Evidence: two-connection race, stale crash recovery, replay, and error-state tests PASS.

### PHASE 7 - Telegram multi-identity transport

- [x] P07.01 Implement one group intake and bounded secondary-DM intake.
  - Evidence: ZION owns group intake; secondary applications discard non-private
    updates and apply each identity's DM policy before AI.
- [x] P07.02 Send through the selected identity without exposing its token.
  - Evidence: `MultiAgentTransport` selects the protected token-specific client;
    safe statuses and timeout/failure-state tests PASS.
- [!] P07.03 Restrict secondary identities to minimum Telegram privileges.
  - Evidence: code grants no moderation authority and ignores secondary group
    intake. Live BotFather/group privilege configuration requires the real bot
    identities and remains blocked until Phase 23 acceptance on the Acer.
- [x] P07.04 Add lifecycle, offset, callback, error, and shutdown tests.
  - Evidence: per-token polling startup, pending-update discard, callback/edit
    claim identity, group discard, safe/uncertain errors, and reverse lifecycle
    shutdown tests PASS.

### PHASE 8 - ZION admin Control Center

- [x] P08.01 Add creator-only inline main menu and required submenus.
  - Evidence: all required top-level areas and per-agent/routing detail views
    have authorized inline callbacks.
- [x] P08.02 Show agent status, policy, scope, health, activity, and routing telemetry.
  - Evidence: per-agent runtime/store/DM/scope/moderation/routed/sent/failure/
    last-success data and aggregate routing telemetry render without secrets.
- [x] P08.03 Require explicit confirmation for dangerous actions.
  - Evidence: LOCKDOWN requires a separate one-time confirmation session.
- [x] P08.04 Reject unauthorized, stale, replayed, and malformed callbacks.
  - Evidence: authorization, nonce expiry, action allowlist, and one-time
    confirmation tests PASS.
- [x] P08.05 Ensure no menu surface reveals secret values.
  - Evidence: menu renders safe status only; secret-value negative test PASS.

### PHASE 9 - Knowledge classification

- [x] P09.01 Add PUBLIC/CONTROLLED/INTERNAL/SECRET metadata and source identity.
- [x] P09.02 Filter by agent scope and context before model context is built.
- [x] P09.03 Add freshness/status/version and source-aware internal provenance.
- [x] P09.04 Fail closed on missing/invalid classification.
- [x] P09.05 Add per-agent retrieval and leakage tests.
  - Evidence: machine-readable manifest, agent-aware retrieval, current-status
    filter, invalid/unclassified fail-closed behavior, and INTERNAL/SECRET
    exclusion tests PASS.

### PHASE 10 - Knowledge reconciliation

- [x] P10.01 Locate and authenticate the current Technical Paper source.
  - Evidence: the named `technical-paper/01-PAGE-BY-PAGE-ROUTE.md` is absent
    from fetched Git history, local search and accessible Drive search. The
    current Drive master project, README and 67-section content plan dated
    2026-10-14 were authenticated and transcribed without inventing the absent
    route file.
- [x] P10.02 Locate the current 21-page APN PDF.
  - Evidence: final v2 PDF SHA-256 `f11814ff...a8b5c4d`, 21 pages, plus its
    matching authorized textual source and assembly QA.
- [x] P10.03 Visually and textually inspect all relevant pages of both current sources.
  - Evidence: all 21 APN pages visually reviewed; authorized 21-page text and
    all 67 Technical Paper plan sections reviewed.
- [x] P10.04 Distinguish the current APN from historical `docs/PITCH-DECK.md`.
  - Evidence: canonical APN source marks the old Solana/Colosseum deck
    HISTORICAL / EXCLUDED.
- [x] P10.05 Create `docs/apn/Z-SWAP-APN-SOURCE.md` from verified content only.
- [x] P10.06 Classify every APN and Technical Paper section.
  - Evidence: APN page groups and all 67 paper sections are classified;
    technical raw sources remain outside retrieval.
- [x] P10.07 Reconcile conflicts against current executable/public facts and record decisions.
  - Evidence: reconciliation used Z-SWAP `origin/main` `166fd5be...` and its
    public source of truth. Superseded Founder prices/supply/version-3 clause
    were removed; Autopilot is now IMPLEMENTED_DISABLED; Portfolio/Orders are
    PARTIAL.
- [x] P10.08 Create `knowledge/MANIFEST.md` with authority, status, version, and allowed agents.
- [x] P10.09 Test retrieval filters and cross-agent/injection leakage.
  - Evidence: APN projection is available to institutional roles; the
    CONTROLLED technical projection is retrievable by MIMIR and excluded from
    ZION. INTERNAL/SECRET/non-current sources still fail closed.

### PHASE 11 - MIMIR CTO

- [x] P11.01 Add grounded technical identity prompt and public technical scope.
- [x] P11.02 Reject internal implementation, security, infrastructure, and unpublished facts.
- [x] P11.03 Test depth, uncertainty, roadmap boundaries, and closed DM.
  - Evidence: reconciled public Technical Paper projections, identity,
    confidentiality, unknown-agent, completeness, status-boundary, uncertainty,
    and closed-DM tests PASS.

### PHASE 12 - EIR CXO

- [x] P12.01 Add support identity, support triage, and public DM flow.
- [x] P12.02 Prevent requests for seed, private key, password, API secret, token, or 2FA.
- [x] P12.03 Test question/problem/bug/account/human escalation classes.
  - Evidence: deterministic triage covers question, usage problem, user error,
    possible incident, possible bug, account, and human; sensitive classes
    require human review.

### PHASE 13 - FREYR CBO

- [x] P13.01 Add institutional/partnership identity and public DM flow.
- [x] P13.02 Add data-minimized partnership qualification and operator summary.
  - Evidence: only labelled fields are accepted; minimum required groups are
    enforced; the summary is delivered through the primary ZION bot.
- [x] P13.03 Define and test retention, privacy, and audit behavior if persistence is used.
  - Evidence: lead content is not persisted; audit stores only field/delivery
    counts and decision status; SQLite dump negative tests PASS.

### PHASE 14 - Cross-agent handoff

- [x] P14.01 Implement invisible, bounded rerouting before external response.
  - Evidence: one-hop handoff is computed before claim/send; the addressed
    identity emits no acknowledgement.
- [x] P14.02 Prove handoff preserves single-speaker and authority boundaries.
  - Evidence: the durable final-speaker claim and transport capture prove one
    authorized external identity.
- [x] P14.03 Test technical/support/business loops and ambiguity.
  - Evidence: EIR-to-MIMIR, FREYR-to-EIR, MIMIR-to-FREYR, multi-address
    ambiguity, and handoff_count<=1 tests PASS.

### PHASE 15 - Confidentiality and prompt-injection hardening

- [x] P15.01 Apply deterministic internal-information and credential boundary to every agent.
- [x] P15.02 Test founder/admin impersonation and system-prompt/source requests.
- [x] P15.03 Test cross-agent oracle and controlled/internal/secret exfiltration.
- [x] P15.04 Test document reproduction/copyright-safe behavior.
  - Evidence: whole APN/Technical Paper reproduction receives a bounded summary
    offer; the provider prompt independently prohibits whole-document output.

### PHASE 16 - Persistence, privacy, and retention

- [x] P16.01 Add the minimum schema required for durable arbitration/telemetry/leads.
  - Evidence: schema v4 adds content-free routing telemetry; no lead table is
    created because FREYR intentionally does not persist lead content.
- [x] P16.02 Add atomic migrations and pre-upgrade compatibility tests.
  - Evidence: schema 2 to 4 migration preserves prior data; v3 to v4 is
    additive; migration rollback and future-schema tests remain green.
- [x] P16.03 Minimize stored user content and define retention/pruning.
  - Evidence: claims and routing telemetry exclude message/contact/user/chat
    content; lead data is not stored; terminal rows have bounded housekeeping.
- [x] P16.04 Prove no transaction spans a network await.
  - Evidence: claim/complete are separate synchronous DB operations; transport is
    structurally outside the transaction boundary.

### PHASE 17 - Observability, health, and diagnostics

- [x] P17.01 Add per-identity status without secret values.
- [x] P17.02 Add routing, arbitration, silence, handoff, and failure telemetry.
  - Evidence: schema-v4 aggregates cover routed/sent/send failure, silence,
    ambiguity, handoff, denied DM, routing failure, and last success.
- [x] P17.03 Extend `/status`, `/health`, `/diagnostics`, `/aistatus`, dashboard, and menu coherently.
  - Evidence: status/health remain compatible; diagnostics, AI status, and the
    creator Control Center expose value-blind multi-agent state and routing.
- [x] P17.04 Add safe-log and degraded-state tests.
  - Evidence: protected-store log redaction, UNSAFE health, missing/disabled,
    duplicate-token, unavailable primary/secondary transport, failed-safe and
    uncertain delivery, no ghost conversation context, and safe recovery tests PASS.

### PHASE 18 - Adversarial test matrix

- [x] P18.01 Routing, mixed intent, unrelated chatter, and ambiguity.
- [x] P18.02 Concurrent messages, duplicate updates, edits, callbacks, retries, and uncertain sends.
- [x] P18.03 DM authority and non-operator access.
- [x] P18.04 Secret-store filesystem attacks and secret propagation.
- [x] P18.05 Knowledge/injection/cross-agent exfiltration.
- [x] P18.06 Guardian/flood/link/secret behavior through centralized intake.
  - Evidence: focused routing/workflow/conversation matrix 60/60 PASS;
    Guardian/moderation/security matrix 163/163 PASS; persistence/release matrix
    104/104 PASS; complete suite PASS.

### PHASE 19 - Full regression

- [x] P19.01 Run focused new tests.
- [x] P19.02 Run all Guardian/moderation/security/persistence tests.
- [x] P19.03 Run the complete suite with zero removed/weakened tests.
- [x] P19.04 Run secret scan and normal repository validation.
  - Evidence: audited Python 3.12 runtime, 9 locked packages, imports PASS,
    714/714 tests PASS, shell checks PASS, sensitive-file boundary PASS,
    `SECRET SCAN: OK`, `ZION VALIDATION: OK` on 2026-10-16.

### PHASE 20 - Documentation reconciliation

- [x] P20.01 Update architecture, policies, security, operations, configuration, and deployment docs.
  - Evidence: master plan, architecture, policy, security, operations, and
    deployment contracts describe the implemented boundaries.
- [x] P20.02 Document Telegram topology and provisioning procedure without token values.
  - Evidence: architecture/deployment docs define centralized intake, secondary
    privacy/minimum privilege, protected local provisioning, and value-blind verification.
- [x] P20.03 Update `docs/CHAT-HANDOFF.md`.
  - Evidence: dated development handoff records implementation and separates
    pending release/live gates.
- [x] P20.04 Reconcile plan evidence and remove stale claims.
  - Evidence: implementation statuses and evidence log reconciled after the
    714-test full validation; live-only gates remain explicitly blocked/pending.

### PHASE 21 - Development release audit

- [x] P21.01 Create `docs/MULTI-AGENT-RELEASE-AUDIT.md`.
  - Evidence: adversarial boundary, validation, migration, file, matrix, finding,
    and pending external-gate evidence is recorded without production claims.
- [x] P21.02 Verify clean tree, exact SHA, CI, migrations, runtime, rollback, and all evidence.
  - Evidence: implementation candidate
    `2dc52ee40179218d2115e680a14f22bcae65f4f9`, clean worktree, migration and
    rollback tests, 714-test local validation, and exact integrated SHA
    `1e639f063497fd7528b58193610fa9dda181c2d0` with ZION CI #1328 SUCCESS.
    Exact production runtime/rehearsal remains Phase 22 rather than dev evidence.
- [x] P21.03 Review the full diff for authority/security/knowledge regressions.
  - Evidence: full 49-file base-to-candidate delta reviewed; no unresolved
    CRITICAL/HIGH/MEDIUM repository finding; one non-runtime LOW warning recorded.
- [x] P21.04 Open PR to `zion-v1.1-dev`, obtain green CI/review, and merge.
  - Evidence: PR #59 merged as
    `1e639f063497fd7528b58193610fa9dda181c2d0`; PR CI run `38981339446`
    and integrated push CI #1328 run `38981413006` both SUCCESS.

### PHASE 22 - Production promotion

- [ ] P22.01 Open production PR from audited development to `zion-v1`.
- [ ] P22.02 Verify the exact production merge SHA and rerun release verification.
- [ ] P22.03 Prepare exact runtime, disposable DB rehearsal, preflight, and rollback evidence.
- [ ] P22.04 Stop on any failed gate; never deploy a dev/arbitrary SHA.

### PHASE 23 - Acer deployment and acceptance

- [ ] P23.01 Provision real secondary tokens locally into the completed protected store.
- [ ] P23.02 Validate bot identities without logging tokens and add bots with minimum privilege.
- [ ] P23.03 Execute controlled cutover and verify host/service/DB/store/runtime state.
- [ ] P23.04 Execute all 17 group/DM acceptance cases.
- [ ] P23.05 Prove one message has at most one speaker and Guardian remains authoritative.
- [ ] P23.06 Verify rollback readiness and complete final audit evidence.

## Immediate implementation sequence

1. Finish Phase 1 using official Telegram behavior and a repository threat model.
2. Implement the formal agent registry (Phase 2) as the first code change.
3. Implement the identity token store and its filesystem/redaction test matrix.
4. Add DM policy and durable arbitration before enabling multi-token transport.
5. Add routing/knowledge/agents, then Control Center and observability.
6. Reconcile APN/Technical Paper independently of runtime work; never index an
   unclassified source.
7. Only after all development gates, use PR-based promotion and exact-SHA deploy.

## Evidence log

| Date | Evidence | Result |
|---|---|---|
| 2026-10-15 | Remote refs and ancestry/content comparison | reconciled |
| 2026-10-15 | GitHub runs #1322, #1325, #1326 | SUCCESS |
| 2026-10-15 | Audited-runtime full baseline | 611/611 PASS |
| 2026-10-15 | APN `pdfinfo` | 21 pages |
| 2026-10-15 | Technical prototype `pdfinfo` | 6 pages; not accepted as the described 83-page route source |
| 2026-10-15 | Registry and protected identity-store focused tests | 20/20 PASS |
| 2026-10-15 | Full suite after first implementation increment | 631/631 PASS |
| 2026-10-15 | DM, deterministic routing, durable arbitration, and schema v3 tests | focused PASS |
| 2026-10-15 | Full suite after second implementation increment | 656/656 PASS |
| 2026-10-16 | Identity prompts, knowledge firewall, transport, DM, Control Center, and safe health focused suite | 112/112 PASS |
| 2026-10-16 | Full suite after third implementation increment | 678/678 PASS |
| 2026-10-16 | APN/Technical Paper source discovery, classification and public-truth reconciliation | complete; absent named route explicitly recorded |
| 2026-10-16 | Reconciled knowledge/Mistral focused suite | 45/45 PASS |
| 2026-10-16 | Full suite after fourth implementation increment | 682/682 PASS |
| 2026-10-16 | Bounded fallback, one-hop handoff, EIR/FREYR workflows, schema v4 telemetry and Control Center | focused 60/60 PASS; degraded/security/persistence matrices PASS |
| 2026-10-16 | Final development validation before release audit | runtime/imports/shell PASS; 714/714 tests; SECRET SCAN OK; ZION VALIDATION OK |
| 2026-10-16 | PR #59 and exact integrated development SHA `1e639f0634...` | PR CI and ZION CI #1328 SUCCESS |

## Final acceptance forward-fix — 2026-10-18

Production baseline: `24b069afc38099e464742bfa9e3cf0d03d4721b4`.
Development base: `3d053e87010a95ed239b0ce57e15fbaae7666fc0`.

- [x] Reproduce short swap and developer-interface routing gaps without history.
- [x] Recognize singular/plural swap, bridge, orders, routing, liquidity and
  developer vocabulary in both the admission gate and deterministic router.
- [x] Assert exactly one MIMIR delivery for all acceptance phrases through the
  ordinary-message handler; no command or prior conversation required.
- [x] Fail closed for interface discovery before retrieval/provider/history.
  No developer interface is explicitly approved in the current public corpus.
  MIMIR explains the boundary and asks for the intended use case. Publishing an
  interface later requires a reviewed public authority contract; this change
  does not infer approval from a URL or generic technical document.
- [x] Add provider-contract regressions against best-price guarantees, universal
  smart-contract execution claims, and categorical platform safety claims.
- [x] Full regression: 724/724 PASS; runtime/imports/shell PASS;
  SECRET SCAN OK; ZION VALIDATION OK. Focused routing/conversation: 64 PASS.
- [ ] Repeat both exact failed messages in a controlled Telegram acceptance
  environment; inspect actual MIMIR answers and one-speaker behavior.
- [ ] Only after both real cases pass, consider a separately approved promotion.

Quality tests assert the prompt contract; they do not certify every possible
provider-generated response. Live answer quality acceptance remains required.
The production service and release refs are not changed by this forward-fix.

## Visual source and long-conversation checkpoint — 2026-10-21

All 83 controlled paper pages are visually classified in the new ledger.
Generic swap descriptions now match the selected-source routing contract.
Portfolio unknown values / partial totals are reconciled against exact source
`986ae759`, not assumed from a PDF or claimed as new live production proof.
Knowledge/tool regressions: 48 PASS; source-only full validation: 849 PASS,
SECRET SCAN OK, ZION VALIDATION OK (`zion-v2-paper-validation.log`).

The subsequent multi-turn evaluation harness adds four 12-turn synthetic scenarios
and real prior-answer continuity with bounded history. Focused harness regression:
11 PASS (`zion-v2-conversations-tests.log`), using simulated providers only.
No paid calls, real provider acceptance, production changes or Kimi activation.
Final combined validation: 854 tests PASS, SECRET SCAN OK, ZION VALIDATION OK
(`zion-v2-source-conversations-validation.log`). Result and unchanged branch base
rechecked on 2026-10-25. Exact-SHA CI is recorded in the draft PR after commit.

## Boundary audit and native evaluation — 2026-10-25

See `COGNITIVE-V2-BOUNDARY-REVIEW.md`. The official Telegram contract and local
identity/DM/source/provider boundaries were reviewed without changing production.
Native Mistral evaluation now invokes the real bounded tool-generation path and
reserves estimated cost before each request; no implicit retry or double outer
reservation. Its synthetic tests do not certify real model quality or Telegram.

One bounded text-generation retest of the original four failing cases was made
after tightening commercial grounding and verifying only the baseline price.
v2-101 still failed `unapproved_market_service_claim`; the other three cases
were not executed. No blocked response was retained. The current baseline is
NOT quality-accepted; see the exact evidence and accounting in the findings doc.

Native smoke v2-001 completed one HTTP request, no tool call selected. Review
FAILED on an execution guarantee missed by the earlier output guard; a new
regression now blocks the exact claim and preserves explicit caveats. No real
second tool round or improved live answer is claimed. Both current live findings
remain acceptance blockers. Remote main/development/production identities were
rechecked on 2026-10-25 and match the measured hashes above.

Validation for this increment: native evaluation/transport harness 25 PASS;
identity/DM/transport/delivery suite 49 PASS; output guarantee/native suite
11 PASS. Final combined suite: 860 PASS, SECRET SCAN OK, ZION VALIDATION OK
(`zion-v2-native-review-final-validation.log`). These include the exact new
execution-guarantee regression; live outputs remain unaccepted.

## Kimi provisioning and bounded comparison — 2026-10-25

- [x] Operator provisioned a Kimi API credential through a hidden local prompt.
  Metadata-only authentication passed; the private directory/file modes are
  0700/0600. This did not activate a new runtime provider.
- [x] Reverify K2.6 and K3 prices against the official Kimi API pricing table;
  renew only those two candidate evaluation snapshots. Durable request/daily/
  total admission and no-automatic-retry remain in force.
- [x] Execute small synthetic PUBLIC generation cases for both models. The
  post-fix v2-101/v2-103 single-turn responses passed human factual review.
  See `COGNITIVE-V2-QUALITY-FINDINGS.md` for initial failures, exact evidence,
  token counts and separate model limitations.
- [x] Reject observed unsupported competitor and partnership-fee claims with
  deterministic regressions. The candidate delivery path gives a fixed,
  topic-specific safe reply after rejection without retaining the model text.
- [x] Final combined validation: 866 tests PASS, SECRET SCAN OK,
  ZION VALIDATION OK (`zion-v2-kimi-comparison-validation.log`).
- [ ] Multi-turn live quality acceptance: both K2.6 and K3 stopped at debate
  turn 3 on `unapproved_market_service_claim`; later turns and other scenarios
  were not executed. A K2.6 turn-2 unsupported comparison was separately
  rejected by human review. No model winner is certified.
- [ ] Real Telegram routing, one-speaker delivery and natural-answer acceptance
  on the candidate runtime; no Telegram message was sent by this evaluation.
- [ ] Model/cost/privacy decision and production approval. K2-series retirement
  is announced for the end of 2026; current production continues on Mistral.

## Bounded Kimi continuation — 2026-10-25

The exact debate turn 3 names a competitor absent from retrieved official
context. A prompt clarification keeps user-named brands out of the answer when
the source does not approve them; the brand guard remains unchanged.
One K2.6 retest still stopped at turn 3. One K3 retest passed automated checks
through turn 10 but stopped at turn 11 on `best_price_guarantee` with the
generated text withheld. Human review found unsupported competitor facts in
K3 turn 2 and a fee-information omission in turn 5. The latter traced to a
retrieval miss on “Vocês cobram mais?” and is now covered by exact-token fee
aliases and a regression. A narrow guard regression rejects the turn-2 claim.

The failed retests are documented in `COGNITIVE-V2-QUALITY-FINDINGS.md`.
No model winner, long-conversation PASS, Telegram acceptance, or production
approval is inferred. No more paid retries are scheduled merely to get green.
Final local validation for this increment: 868 tests PASS, SECRET SCAN OK,
ZION VALIDATION OK (`zion-v2-kimi-continuation-validation.log`).

The final bounded K3 follow-up again failed: automation stopped at debate
turn 10 (`safety_guarantee`, rejected text withheld), and human review rejected
an unsupported competitor comparison at turn 2 plus a three-of-four EVM fee
enumeration at turn 8. Turn 5 correctly used the recovered official fee policy.
The clause-scoped guarantee guard, narrow competitor regression and explicit
four-tier fee-list instruction are local forward-fixes without live PASS.
The isolated evaluation ledger stands at 996,139 micro-USD reserved/estimated.
Final post-fix local validation: 870 tests PASS, SECRET SCAN OK,
ZION VALIDATION OK (`zion-v2-kimi-final-validation.log`).

## Post-K3 deterministic quality hardening — 2026-10-25

- [x] Add clause-scoped tests for explicit safety denials and absolute safety
  promises, including a denial followed by an unsafe claim after “mas”.
- [x] Return a fixed, risk-qualified host reply after a rejected price or
  safety guarantee; do not retain the rejected model output.
- [x] Complete broad PUBLIC/CURRENT fee-plan retrieval with the missing
  same-source sibling section when all four authorized Free/Pro/Trader/Pilot
  sections are available. Keep exact-tier queries narrow and reserve capacity
  for the complete bundle; omit it when it cannot fit whole.
- [x] Reject an EVM or network-unspecified fee schedule naming at least three
  plans when it omits a tier or disagrees with the four percentages parsed from
  official titled context. Accept percentage-before-tier wording. Preserve
  one/two-plan comparisons and Solana-only explanations.
- [ ] Re-evaluate model output and the complete multi-turn conversation under
  a separately bounded acceptance run; deterministic regressions do not
  establish live quality or a model winner.
- [ ] Validate real Telegram routing, one-speaker delivery, source fidelity and
  natural answers on the candidate before any separately approved promotion.

Local isolated regression: 878 tests PASS, SECRET SCAN OK, ZION VALIDATION OK
(`zion-v2-post-kimi-local-validation.log`). Production remains unchanged.

## K3 acceptance follow-up — 2026-10-26 UTC

- [x] Run one bounded, live-provider, PUBLIC synthetic 12-turn debate after the
  four-tier retrieval fix. It stopped at turn 12 on `best_price_guarantee`;
  rejected text was withheld. Human review failed turn 5 (Solana fee scope)
  and flagged turn 7–8 snapshot facts presented as live proof.
- [x] Add narrow source-scope and freshness regressions, plus clause-scoped
  noun-denial tests for a reproducible price-guarantee guard false positive.
  Rechecking allowed historical responses locally now rejects turns 5/7/8.
- [x] Run one bounded K3 retest after the fixes. It stopped at turn 5 on
  `overbroad_solana_fee_scope`; the model output was withheld. No retry loop.
- [x] Carry PUBLIC/CURRENT Terminal Pro beta and Portfolio/Orders partial
  status as an atomic comparison evidence pair, and reject an answer that
  drops those qualifiers. Independent negative probes covered safe denials
  and Jupiter-only fee scoping without a paid provider retry.
- [x] Reconcile the ambiguous “other Solana pairs” sentence against the exact
  approved application snapshot; limit it to Jupiter and keep LI.FI's separate
  source path explicit. Preserve the published four-tier rates and snapshot
  classification.
- [x] Give a source-derived, host-owned Solana fee answer after this specific
  guard rejection only when the whole PUBLIC section is present; otherwise
  keep the conservative reply. This does not change the K3 evaluation FAIL.
- [ ] Obtain human-accepted multi-turn generation across all four scenarios;
  automated `REVIEW_REQUIRED` is not quality PASS. The qualifier fix has only
  deterministic retrieval/replay coverage, not a new K3 or Telegram PASS.
- [ ] Complete real Telegram candidate acceptance and independent provider/
  cost/privacy decision before proposing any production promotion.

Isolated full validation: 882 tests PASS, SECRET SCAN OK, ZION VALIDATION OK
(`zion-v2-k3-followup-validation.log`). The cumulative evaluation ledger is
1,638,178 micro-USD reserved/estimated, not a bill. Production is unchanged.

Final validation of the later comparison-status refinement: 888 tests PASS,
SECRET SCAN OK, ZION VALIDATION OK (`zion-v2-k3-final-validation.log`). The
multi-turn and Telegram gates remain open; no production promotion is implied.

Post-reconciliation isolated validation: 890 tests PASS, SECRET SCAN OK,
ZION VALIDATION OK (`zion-v2-solana-final-validation.log`). No new paid K3 run
or Telegram acceptance was performed at that checkpoint.

## Named-conversation retest checkpoint — 2026-10-26

- [x] Diagnose the failed named-conversation run without repeating a provider
  call: selection used conversation mode but execution used single-case mode.
  The attempt settled an estimated 40,680 micro-USD, then raised `KeyError`
  before writing a case row. Its empty evidence file provides no quality result.
- [x] Use one mode for both paths and add fake-provider regression of actual
  named live dispatch. Post-provider harness errors now write a minimized
  `HARNESS_FAIL` row and stop, with no response or exception text retained.
- [x] Run one bounded K3 debate retest. Turn 1 stopped at
  `AUTOMATED_FAIL / missing_feature_status`; rejected text was withheld. No
  later turn or other conversation executed. The evaluation ledger now totals
  1,713,681 micro-USD reserved/estimated, not a bill.
- [x] Add a delivery fallback that carries only beta/partial statuses present
  in the approved retrieved context. Independent review caught cross-section
  and negated-status false associations in the first local version; direct
  affirmative, same-section matching and negative regressions now cover them.
  The evaluation failure remains a failure; this is not Telegram proof.
- [ ] Obtain human-accepted multi-turn answers for all four scenarios, then
  test natural routing/delivery in the controlled Telegram group.
- [ ] Review provider reliability, latency, cost and privacy against explicit
  acceptance criteria before proposing any production activation or release.

Production remains unchanged. The candidate PR stays draft until the open
quality and real-channel gates are independently accepted. Final isolated
validation for this increment: 893 tests PASS, SECRET SCAN OK, ZION VALIDATION
OK (`zion-v2-final-reviewed-validation.log`).

## Broad comparison delivery alignment — 2026-10-26

- [x] Reconcile the evaluator's PUBLIC comparison evidence with normal ZION
  delivery for the exact failed debate question. The normal path now receives
  the same bounded PUBLIC status sections when the question is a broad product
  comparison, without widening agent authority or source classification.
- [x] Add a host-owned comparison reply that states the documented proposal and
  Terminal Pro beta / Portfolio and Orders partial status only when the
  positioning, feature map and direct status predicates are present. Missing
  evidence or a narrow/unrelated question keeps the conservative fallback.
- [x] Focused response/AI tests pass; full local validation: 895/895 tests,
  SECRET SCAN OK, ZION VALIDATION OK
  (`zion-v2-comparison-local-validation.log`). No paid model call was made.
- [ ] The last K3 debate is still FAIL at turn 1. Model quality, all remaining
  conversation turns, Telegram acceptance and production gates remain open.
