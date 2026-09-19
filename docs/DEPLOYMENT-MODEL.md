# ZION Deployment Model

## Current rule

GitHub is the code source of truth. Runtime secrets stay local on the ZION host.

ZION v1.1 development must follow:

```text
feature/development branch
        |
        v
draft pull request
        |
        v
CI validation
        |
        v
human review
        |
        v
explicitly approved merge/update
        |
        v
controlled host deployment
```

## No privileged self-hosted runner yet

Do not install a GitHub Actions runner with production privileges on the ZION host at this stage.

A compromised workflow or repository credential must not automatically become root or production shell access.

## Remote deployment after Tailscale + SSH

Once private remote access is proven, an operator can:

1. connect over the Tailnet with the dedicated SSH key;
2. inspect `git status`, current commit and service health;
3. create/verify a local backup;
4. fetch the approved remote branch;
5. validate code before stopping ZION;
6. perform the controlled cutover;
7. verify Telegram `/status`, `/health` and `/diagnostics`;
8. roll back to the recorded commit if any gate fails.

Never copy `.env` into GitHub and never pass secrets in command-line arguments that can land in shell history.

## Future automation gate

A deployment agent or runner may be considered only after all of these exist:

- least-privilege service account;
- branch protection and required CI;
- immutable deployment artifact or commit pinning;
- explicit approval gate;
- narrow sudo policy;
- rollback command tested;
- audit log;
- no ability for ordinary PR code to read production secrets.

Until then, private SSH plus an explicit operator action is the safer control boundary.
