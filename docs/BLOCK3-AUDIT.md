# Block 3 audit

Base: d4cda026e0b9099d18af73d73322d876b7dc8e57.

Static review found one medium-scope boundary issue: community moderation rules currently also run in private chats. The recommended patch is to keep the universal safety preflight, then skip group-only lockdown, containment, flood, burst and link-policy enforcement for private chats. Regression tests should prove that private commands and ordinary private messages avoid group moderation while the existing universal safety preflight remains active.

A second known residual risk remains unchanged: external Telegram effects and local SQLite recording are not a distributed transaction. Do not place network awaits inside SQLite transactions. Unknown outcomes across a crash require explicit state-machine design rather than replay assumptions.

Reviewed controls with no blocking finding in this pass: explicit operator allowlist, admin lookup fail-closed behavior, command idempotency before command side effects, handler ordering, Telegram URL/text-link entity inspection, observe-only AI authority boundary, scheduler claim/quarantine behavior, and persisted operating-state transitions.

Local/Telegram verification is still required for real supergroup permission semantics, admin-role changes during cache TTL, real media/entity update shapes, concurrent update rate limiting, and crash timing around external effects.
