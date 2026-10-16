# ZION Multi-Agent Architecture and Threat Model

## Scope

This document defines the trusted topology for ZION, MIMIR, EIR, and FREYR.
The system is one coordinated application with four Telegram identities. It is
not four autonomous bots.

## Verified Telegram constraints

The topology is based on the current Telegram Bot API and the installed
`python-telegram-bot` 22.8 runtime:

- Bot API requests are authenticated by the token embedded in the API endpoint.
  A `sendMessage` call therefore speaks as the bot whose protected token created
  that client.
- A bot can send to a group in which it is a member and has permission to post.
- Bot API update delivery uses either `getUpdates` or a webhook for a given bot;
  those mechanisms are mutually exclusive.
- Group privacy mode is enabled by default. A bot with privacy enabled receives
  only updates Telegram considers relevant to it, plus service/private updates.
  A group administrator receives all group messages.
- A callback query is delivered to the bot that created the inline keyboard.
- Update IDs support replay suppression but do not make an external send and a
  local SQLite commit atomic.
- `python-telegram-bot` supports manual `Application.initialize()`, `start()`,
  `Updater.start_polling()`, and the reverse shutdown lifecycle. This permits
  several token-specific applications in one event loop without nesting
  `run_polling()` calls.

Primary references:

- <https://core.telegram.org/bots/api>
- <https://core.telegram.org/bots/features#privacy-mode>
- <https://core.telegram.org/bots/faq>
- <https://docs.python-telegram-bot.org/en/v22.8/telegram.ext.application.html>

## Runtime topology

### Group intake

ZION is the sole group intake authority. It retains the current administrative
rights required by Guardian. It receives the message, runs deterministic safety
and moderation, routes benign conversation, filters knowledge, acquires a
speaker claim, and asks one token-specific client to send the response.

MIMIR, EIR, and FREYR remain ordinary group members with the minimum ability to
post. Privacy mode stays enabled. Their handlers reject all group updates even
if Telegram delivers a mention, direct reply, command, or service update. They
never run Guardian and never claim group messages.

### Private intake

Each Telegram identity has a token-specific update consumer. Private updates are
processed by the shared core under the receiving identity:

- ZION: creator/operator only;
- MIMIR: closed;
- EIR: public support;
- FREYR: public business/partnerships.

The DM gate executes before session creation, knowledge retrieval, Mistral, or
content persistence. Deterministic secret/wallet protection remains earlier than
the conversational path for allowed DMs.

### Outbound identity

The selected `AgentId` resolves to a protected, prevalidated Telegram client.
The router cannot supply arbitrary tokens, usernames, or bot objects. The
transport receives a typed identity plus a bounded send request. Missing or
unsafe identity configuration fails closed and produces a sanitized operational
event.

The ZION Control Center is always sent by ZION. Consequently Telegram returns
its callback queries to the ZION consumer, where creator authorization,
callback version, expiry, replay, and confirmation are checked again.

## Processing order

1. Validate update shape, chat type, sender, and stable message identity.
2. Suppress replayed or unsupported update forms.
3. Run sensitive-content and deterministic Guardian checks.
4. Apply receiver-specific DM policy if the chat is private.
5. Classify benign intent and choose one candidate agent or silence.
6. Retrieve only sources allowed for that agent, classification, and context.
7. Apply confidentiality and prompt-injection boundary.
8. Acquire the durable speaker claim.
9. Generate a grounded response for the selected agent.
10. Send once through the selected identity.
11. Record minimized outcome telemetry without message or secret content.

No SQLite transaction spans steps that await Telegram or Mistral.

## Delivery semantics

Telegram and SQLite do not share a transaction. The system provides durable
claim-before-send suppression, not exactly-once delivery.

Claim states are designed around the external side effect:

- `CLAIMED`: one worker owns the inbound message before generation/send;
- `SENT`: Telegram acknowledged the send and sanitized metadata was recorded;
- `FAILED_SAFE`: no send was accepted; manual or bounded policy may retry;
- `UNCERTAIN`: process/network outcome cannot prove whether Telegram accepted
  the send; automatic replay is forbidden.

A duplicate update, edited message, callback replay, or concurrent worker uses a
stable key including source identity, chat, message/update kind, and Telegram
identifier. A completed or uncertain claim cannot authorize another speaker.

## Trust boundaries

### Trusted deterministic boundary

- agent registry and authority matrix;
- Guardian and security policy;
- DM gate;
- knowledge classification and scope filtering;
- speaker claim/arbitration;
- Control Center authorization and confirmation;
- protected identity store and configured client registry.

### Untrusted or advisory inputs

- message text and Telegram profile fields;
- callback data before validation;
- Mistral classification/answer text;
- all document content until reconciled and classified;
- claimed founder/admin/developer identity in prose;
- links, encoded strings, forwarded/replied content;
- Telegram retries and delivery timing.

## Threats and mandatory controls

| Threat | Control |
|---|---|
| Four bots answer one group message | only ZION consumes group conversation; durable central claim; secondary group handlers always deny |
| Duplicate or concurrent update | atomic unique claim before network send |
| Crash after send | mark/retain uncertainty; never automatic replay |
| Edited message causes second answer | edit-specific key/policy and prior source-message lookup |
| Callback forged or replayed | creator ID, ZION receiver, signed/versioned bounded data, expiry and idempotency |
| User claims to be founder | Telegram numeric allowlist only |
| Prompt asks another agent to reveal data | retrieval scope fixed before model; no agent-to-agent oracle calls |
| Document contains prompt injection | source/classification validation; content remains data; confidentiality filter |
| Mistral chooses punishment | impossible by interface; only deterministic Guardian can return moderation actions |
| Secondary bot mutes/deletes | no moderation interface or admin privilege; authority registry denies it |
| Token appears in logs/errors | protected store, runtime redaction registration, sanitized exception classes |
| Symlink/hardlink/permission substitution | `lstat`/`fstat`, ownership, mode, link-count, fixed parent, atomic replace/fsync |
| Unsafe store at startup | identity disabled; no token read or diagnostic value |
| Unclassified knowledge leaks | fail-closed exclusion before context construction |
| Historical APN overrides current facts | explicit source status and conflict register; historical retrieval excluded |
| Bot-message loop | ignore bot-authored group messages; no cross-bot public dialogue |

## Least privilege deployment

- ZION keeps only the group permissions required by the existing Guardian.
- MIMIR, EIR, and FREYR are non-admin members allowed to post messages.
- Secondary privacy mode remains enabled.
- Bot-to-bot communication mode is not required by this architecture.
- Only one running consumer exists for each token; startup refuses conflicting
  or invalid identity configuration.
- Real tokens are provisioned locally after the store and release are verified.

## Failure policy

- Missing MIMIR/EIR/FREYR token: identity unavailable; router may use an approved
  deterministic fallback or silence, never a different personality pretending
  to be that agent.
- Mistral unavailable: deterministic moderation/local help continue; agent
  conversation fails boundedly without weakening policy.
- SQLite unavailable or claim cannot be acquired: silence; no untracked send.
- Selected bot cannot post: sanitized failure telemetry and no second identity
  retry for that same message.
- Secondary poller failure: its public DM surface is unhealthy; group Guardian
  remains owned by ZION.

## Acceptance invariants

1. Every group update has zero or one authorized speaker.
2. Only ZION can invoke moderation actions.
3. DM access is decided before AI and persistence.
4. The model never receives unauthorized knowledge chunks.
5. Tokens are value-blind outside the protected store/client construction path.
6. External send uncertainty never creates an automatic duplicate.
7. Existing Guardian, database, release, and rollback contracts remain green.

