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
