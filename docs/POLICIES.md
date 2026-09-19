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
