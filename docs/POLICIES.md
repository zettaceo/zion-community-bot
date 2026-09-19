# ZION Policy Contract

## Deterministic automatic actions

ZION may automatically act on:

- flood thresholds;
- active containment;
- manually activated lockdown;
- unauthorized links/domains;
- high-confidence possible wallet-secret exposure;
- repeat flood escalation up to ban, according to configured strike count.

These rules are objective, inspectable and auditable.

## AI observe-only categories

Mistral may classify a message as:

- `support_question`
- `criticism`
- `normal`
- `spam_suspected`
- `harassment_suspected`
- `scam_suspected`
- `phishing_suspected`
- `impersonation_suspected`
- `other`

AI classification cannot directly punish a user.

If the model requests human review or returns high risk, ZION creates an incident with category/risk metadata for an administrator.

## Criticism

Statements such as "I dislike this", "the fee is high", "this feature is bad", "I do not trust this", or reports of product problems are not automatic moderation violations.

## Flood escalation

Default configuration:

1. first active strike: 60-second mute;
2. second active strike: 300-second mute;
3. third active strike: 900-second mute;
4. fourth active strike: ban.

Values are configurable by environment variables.

Strikes expire according to `FLOOD_STRIKE_RESET_SECONDS`.

## Link policy

By default, member links are blocked.

Allowed domains may come from:
- `ALLOWED_DOMAINS`;
- the runtime domain table via `/allowdomain`.

An admin can add explicit block entries via `/blockdomain`.

## Human actions

Administrators can:
- warn;
- mute;
- ban;
- inspect users/incidents;
- allow/block domains;
- activate/deactivate lockdown;
- schedule announcements;
- reload the knowledge base.

All relevant actions are written to the action ledger.

## Raid / mass-join

ZION counts join events in a deterministic time window. If the configured threshold is crossed while state is NORMAL, it enters temporary ELEVATED mode.

ELEVATED mode tightens the flood threshold. It does not grant punitive authority to AI.

The state returns to NORMAL after the configured expiry unless an administrator explicitly changes the state.

## AI resource abuse

AI-backed member commands are rate-limited per user.

Observe-only classification uses a separate per-user limiter and the same global Mistral daily token budget.

When the budget is exhausted, deterministic Guardian features remain active.


## Unicode and disguised domains

Domains are normalized to their ASCII IDNA representation before policy comparison. This prevents a Unicode lookalike from matching an unrelated ASCII allowlist entry.

Telegram URL/text-link entities are evaluated in addition to visible text.

## Distributed chat bursts

A high message rate spread across multiple distinct members can move ZION from NORMAL to temporary ELEVATED mode.

This trigger:
- does not create an individual strike by itself;
- does not mute or ban an individual by itself;
- tightens deterministic flood thresholds temporarily;
- creates an auditable incident and state-change action.

## Community operations retention

Explicit AMA questions are stored only because the member invokes the AMA collection command. Questions from closed AMAs are deleted after the configured retention period.

Recurring announcements are administrative content and remain active until cancelled.

## Operational alerts

Health alerts can notify explicit ZION operators about database/integrity problems, low disk, sensitive-file permissions, missing Wi-Fi interface or abnormal Telegram update lag. Health alerts do not perform destructive recovery actions.
