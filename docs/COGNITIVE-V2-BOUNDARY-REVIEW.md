# Cognitive v2 boundary review — 2026-10-25

Scope: isolated candidate, deterministic code and synthetic tests. This is not
live Telegram acceptance, a hosted configuration audit or approval to deploy.

| Boundary / threat | Enforcement and evidence | Remaining limitation |
|---|---|---|
| User claims founder/admin status | `dm_policy.py` uses configured numeric operator identity; MIMIR DM stays closed even for the operator. `test_dm_policy.py`, `test_conversation.py` exercise denial before AI. | Actual Telegram identity/membership needs human acceptance. |
| Secondary bot receives group traffic | `multi_agent_transport.py` registers a no-side-effect non-private handler, shared core and private identity handler. Tokens cannot duplicate the primary identity. Transport tests cover rejection/lifecycle/uncertain send. | Telegram delivery and host membership are external. |
| Selected speaker sends twice | Durable delivery gate and native two-request fixture in `test_cognitive_delivery_v2.py`; uncertain outcome is not automatically replayed. | Real concurrent Telegram acceptance pending. |
| Controlled source reaches wrong agent | Manifest permits only MIMIR for the curated technical projection; current/expiry/agent filters run before context construction. Other agents cannot inherit it through fixed-label handoff. | This explicitly scoped projection is not authorization to index the raw paper or any future controlled source. |
| Controlled source exported to another provider | KnowledgeTools is PUBLIC-only; candidate generation removes unclassified historical assistant context. | Source authenticity and factual currency still require review. |
| Tool request grants authority | Fixed registry, exact argument validation, batch bound, host identity, one tool round. Invalid batch runs no operation. `test_native_knowledge_tools.py`. | Model quality is not guaranteed by tool validation. |
| Prompt injection / fabricated answer | Input remains data; shared output guard blocks reviewed disclosures/unsupported claims for all four agents. Rejected text is not stored as incident evidence. | Pattern checks cannot prove arbitrary factuality or complete semantic non-disclosure. Live failure remains open. |
| Kimi capture leaks after restart | Interception metadata persists; candidate deletion precedes validation/storage; fresh authorization needed after restart; registration never activates the provider. | Operator-selected Telegram DM is not end-to-end secret provisioning. |
| Retry/fallback overspends | Runtime per-attempt token admission, optional reviewed currency policy; no implicit cross-provider fallback. Evaluation reserves durably before each native request, retains uncertain charges and disables retries. | Estimated accounting is not the provider invoice. |
| Generated history becomes authority | Bounded whole exchanges for synthetic evaluation; PUBLIC retrieval is separate; human review remains mandatory. Runtime handoff uses fixed labels, not transcripts. | Generated history may still influence model reasoning; it is not certified factual evidence. |
| AI becomes punitive authority | Guardian remains deterministic; provider tools expose knowledge operations, not moderation actions. | Live group permissions must be checked at deployment acceptance. |

## Telegram contract check

Official [Bot API](https://core.telegram.org/bots/api#sendmessage) and
[FAQ](https://core.telegram.org/bots/faq#what-messages-will-my-bot-get) checked
2026-10-25. Bot administrators / privacy-disabled bots receive ordinary user group
messages; private user messages are delivered independently of privacy mode.
The FAQ excludes messages from other bots. The design uses direct host-side
selection and the chosen identity's transport, not bot-to-bot messaging as a bus.
A message sent by another bot is therefore not a substitute for human acceptance.
No new Telegram API surface, group configuration or permission was changed.

## Current verdict

Local architecture retains the required authority separation. The identified
live competitive-answer failure is still an acceptance failure, not erased by
passing boundary tests. A successful output guard is containment, not quality.
The actual candidate runtime, model/account policy, real conversation quality
and controlled production release still require their separate gates.
