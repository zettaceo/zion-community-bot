# Cognitive routing v2 — incremental implementation

Status: partial, development only. Full semantic router and provider benchmark
remain pending in MULTI-AGENT-IMPLEMENTATION-PLAN.md.

## First increment: context isolation

The original group session remains bounded by its existing TTL, maximum session
count, query size and transcript size. It is shared within a public chat/thread,
not across chats/threads or DMs. This increment adds one in-memory topic label;
no schema change, new raw-message persistence or chain-of-thought storage.

`conversation_state.explicit_topic` classifies an explicit subject from at most
6,000 characters of a user question. It does not inspect generated answers.
`_continues_active_group_topic` rejects an explicit topic switch before checking
follow-up prefixes such as "E...". A new topic receives neither prior retrieval
query nor prior transcript, and starts a fresh session after confirmed delivery.
Same-topic corrections retain conversational context while retrieving facts from
the corrected question. Ambiguous pronouns retain the existing bounded behavior;
this is not a claim of complete referent resolution.

Topic labels cannot authorize moderation, tools, secrets or knowledge. Guardian,
DM policy and the existing authority registry remain separate controls. The
module is deliberately not reused for punitive inference.

Tests use the ordinary handler with fake transport/provider and assert exactly
one send per message, absence of old retrieval/history on switches, and reset of
the remembered retrieval query. Existing follow-up, cross-member public context,
thread isolation, moderation and delivery tests are preserved.

## Known gaps

Language recovery, per-user issue state, interrupted conversations, confidence
scoring, fragmented messages, structured summaries and model escalation remain
pending. The topic rules are ordered and lexical, and do not fully disambiguate
polysemous terms. Live Telegram generated answers require separate acceptance.

## Public-fact correction included with reconciliation

At Z-SWAP main `986ae759c1c76fe23967a8e61489d986b2bb9a51`, the public truth table
and `src/lib/tier/fees.ts` / `src/lib/solana/conta-de-taxa.ts` agree on the
qualified Solana fee policy effective 2026-10-16. The old assertion of universally
disabled Solana platform fees was replaced with the current policy and a stronger
retrieval test across all four agents. The old assertion was factually obsolete,
not removed to hide a failing implementation. Network/tier/Founder public
source files checked for this comparison were byte-identical to the prior
snapshot. This does not certify every other corpus fact or live app deployment.

## Second increment — 2026-10-19

`language_recovery.py` keeps the original input and derives a bounded ephemeral
interpretation through a small reviewed alias map. It does not fuzzy-match
operator identities, grant authority or replace the raw Guardian/security input.
Confidence describes interpretation, not factual truth. Unknown short references
need recent context or one clarification. Arbitrary typo correction is not proven.

Product, plan, roadmap, security, competitive objection and API integration have
explicit routing intents and one registry owner. Product/commercial objections
stay with ZION; an explicit partnership goes to FREYR; technical integration goes
to MIMIR; operational failures win and go to EIR. The schema-4 delivery ledger
stores the stable parent family; routing reason carries the fine intent. Registry
membership is validated before projecting the family. No DB migration is needed.

Fragmented support has a 90-second, non-sliding window keyed by chat, thread and
user, capped at 2048 entries. Only fixed product/problem/network/asset slots are
kept, never raw text, secrets or generated reasoning. Unrelated input resets it.
The four-message fixture uses normal pauses; flood protection still applies.
Public group follow-ups retain the existing bounded shared-topic contract.

The output guard rejects known absolute guarantees, unauthorized action claims,
internal paths/addresses/provenance, credentials and URLs absent from retrieved
context. It is deliberately NOT a complete factuality or leakage proof. Rejected
answers are replaced before delivery and only a reason code is audited. Cost of
the original provider call remains accounted. The shared prompt builder preserves
the same grounding contract for candidate-provider generation comparisons.
