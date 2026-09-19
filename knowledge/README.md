# ZION Knowledge Base

Markdown files in this directory are treated as approved local context for Mistral support answers.

Rules:

1. Put only facts that the team is prepared to treat as official.
2. Prefer short sections with clear headings.
3. Add dates/version notes to facts that may become stale.
4. Do not store secrets, private keys, API keys, user conversations or private customer data here.
5. ZION is instructed not to fill gaps from model memory when answering Z-SWAP-specific questions.
6. After editing knowledge files, an authorized admin may run `/reloadkb`.

The retrieval implementation is deliberately local and simple in v1. It can later be replaced by embeddings/vector search without changing the safety contract.
