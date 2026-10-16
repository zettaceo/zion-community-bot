# ZION Knowledge Base

Markdown files in this directory are eligible for local context only when they
have a valid entry in `MANIFEST.md`. The loader applies classification, status,
version, source identity, and per-agent access before context reaches Mistral.

Rules:

1. Put only facts that the team is prepared to treat as official.
2. Prefer short sections with clear headings.
3. Add dates/version notes to facts that may become stale.
4. Do not store secrets, private keys, API keys, user conversations or private customer data here.
5. ZION is instructed not to fill gaps from model memory when answering Z-SWAP-specific questions.
6. After editing knowledge files, an authorized admin may run `/reloadkb`.
7. When product tiers, pricing, quotas or availability change, update the plan
   matrix and its retrieval tests in the same release. Never document only one
   paid tier as though it represented the others.
8. A source without manifest metadata is rejected. `INTERNAL`, `SECRET`,
   `HISTORICAL`, `SUPERSEDED`, and `EXCLUDED` sources never enter public model
   context.

The retrieval implementation is deliberately local and simple in v1. It can later be replaced by embeddings/vector search without changing the safety contract.


# Public-authority boundary for Z-SWAP

The Z-SWAP product corpus is a curated public derivative of a pinned source snapshot. It is intentionally not a repository mirror.

Rules for maintainers:

1. Prefer current code-backed public behavior over stale marketing counts or historical documents.
2. When two source files disagree, do not silently choose the more attractive claim. Reconcile it first or omit the claim.
3. Never copy secrets, credentials, infrastructure identifiers, internal endpoints, admin routes, database internals, logs, incident evidence, pentest findings, unannounced roadmap or private business metrics into this directory.
4. Publicly visible source code can still contain operational details that are inappropriate for community support. Public repository visibility is not the same as approval for disclosure.
5. Record the source snapshot in each derived Z-SWAP knowledge file.
6. If a fact depends on runtime environment or a user's account, describe the general rule and avoid claiming current account-specific state.
7. ZION may know more internally than it is allowed to reveal. The knowledge directory contains only the revealable subset.
