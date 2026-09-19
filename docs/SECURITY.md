# ZION Security Model

## Core rule

AI interprets. Deterministic policy or an authorized human decides irreversible moderation actions.

## Secrets

- Real credentials live only in `.env` or a future secrets manager.
- `.env`, SQLite runtime files and logs are excluded from Git.
- All application log handlers use secret redaction.
- HTTP client loggers are reduced to WARNING to prevent request URLs/headers from being printed.
- Telegram-token and Bearer-token patterns are additionally redacted.
- Mistral errors are logged without request headers or API keys.

## Admin authorization

Private Telegram chats do **not** imply administrator status.

A private-chat admin must be explicitly listed in `ZION_ADMIN_USER_IDS`.

Inside a group, Telegram group administrators/owners are accepted as admins. Explicit allowlisted IDs are also accepted.

## AI trust boundary

Messages sent by community users are untrusted input.

The Mistral system prompt explicitly states that user content cannot override ZION policy. AI moderation operates in observe-only mode and cannot call delete, mute or ban functions.

## Data minimization

ZION stores operational metadata rather than full message bodies whenever possible.

The action ledger records:
- actor;
- target;
- reason;
- action;
- result;
- incident;
- timestamp.

AI events store a hash of input text rather than the raw text.

## High-confidence wallet-secret protection

The deterministic scanner only removes possible wallet secrets when a sensitive label such as "seed phrase", "recovery phrase" or "private key" is present together with secret-like content.

This is intentionally narrower than generic hex detection to avoid deleting transaction hashes.

## Lockdown

`/lockdown` is an explicit administrator action. While active, non-admin messages are deleted.

`/unlock` returns the system to NORMAL.

## Failure behavior

- Mistral failure: Guardian remains active.
- Database problem: health reports failure; bot logs the error.
- Network/DNS at boot: systemd waits for Telegram DNS before starting the bot.
- Wi-Fi degradation: the separate Wi-Fi Guardian attempts layered recovery.

## Operational telemetry

Detailed health, Guardian configuration, Mistral configuration/budget and incident/user operations are admin-only Telegram commands.

Public `/status` intentionally exposes a smaller surface.

The optional web dashboard binds only to localhost and is read-only.

## AI cost denial-of-service

Mistral use is protected by:
- per-user member-command rate limits;
- a separate observe-mode per-user limiter;
- a global concurrency limit;
- a daily token budget.

Exhausting AI resources does not disable deterministic moderation.

## Provider failure isolation

Consecutive Mistral failures open a persistent circuit breaker. While open, new AI calls are rejected locally instead of repeatedly contacting an unhealthy provider.

Provider failure cannot disable deterministic moderation.

## Bounded support-query retention

ZION does not persist ordinary community message bodies.

A narrow exception exists for explicit support questions that have no approved knowledge match: a sanitized sample is stored as a knowledge gap so administrators can improve the official knowledge base.

These samples have bounded retention and are automatically pruned.

## Privilege separation

Telegram group administrator status grants only chat-local moderator capabilities.

Global ZION controls require explicit operator allowlisting through `ZION_ADMIN_USER_IDS`.

Operator-only surfaces include:
- global operating state and lockdown;
- domain allow/block policy;
- global incident review;
- Mistral configuration telemetry and budget;
- knowledge-gap operations;
- knowledge-base reload;
- global statistics and operator brief.

This limits the blast radius if ZION is ever added to another group.

## Audit-preserving retention

For resolved/ignored user reports, ZION removes retained free-text note/evidence after the configured retention window but keeps the minimal incident row. This preserves the existence and outcome of a moderation event without keeping its detailed report contents indefinitely.


## Prompt-injection boundary

Grounded support wraps official context and the user question in separate explicit data regions. The Mistral system instruction states that neither user content nor text inside retrieved context may redefine ZION's role, request secrets or override safety rules.

Source labels are appended from the local retrieval result rather than trusted from model-generated citation text.

## Unicode / IDNA link defense

URL hosts are normalized with IDNA before allow/block comparison. Unicode lookalikes therefore resolve to their own punycode hostname and do not inherit permission from a visually similar ASCII domain.

## Distributed-abuse boundary

Chat-wide burst detection is deliberately non-punitive. Its only automatic policy effect is temporary ELEVATED state. Individual deletion/mute/ban still requires an existing deterministic per-user rule.

## Remote administration

Remote shell access is designed for Tailscale + SSH public-key authentication. TCP/22 must not be exposed by router port forwarding. Private SSH keys and Tailscale authentication material never belong in Git.

See `docs/REMOTE-ACCESS.md` and `docs/DEPLOYMENT-MODEL.md`.


## High-confidence credential exposure

In addition to wallet-secret detection, ZION v1.1 deterministically protects high-confidence credential patterns such as Telegram bot tokens, Bearer authorization values, labeled API keys/passwords and exact secret values already present in the local runtime environment.

This protection runs before administrator exemptions and before AI processing. When triggered, the message is removed, the sensitive body is not stored in the incident evidence, and the sender is advised to rotate a real credential.

Generic crypto terminology such as `token=USDC` is not treated as a credential by this detector.


## Runtime exclusivity and at-most-once controls

The writable bot runtime uses a kernel-backed file lock shared across worktrees. A second runtime cannot start while the first owns the lock. The lock path is outside the repository by default so switching worktrees does not create a second lock namespace.

Telegram command update IDs are persisted before command side effects. Duplicate delivery of the same command update is stopped before the command handler.

Scheduled Telegram sends use an atomic SQLite claim before network I/O. Because a process can die after Telegram accepts a send but before local success is committed, ZION does not claim mathematical exactly-once delivery. Instead, unknown outcomes are quarantined and require an explicit operator decision. This prevents automatic duplicate replay.
