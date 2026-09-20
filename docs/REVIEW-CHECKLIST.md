# ZION v1 — Review Checklist

This branch is intentionally separate from `dev` so the currently running bot is not changed until review.

## Before deployment

- [ ] Read `ZION-MASTER-PLAN.md`.
- [ ] Review `.env.example`; do not commit the real `.env`.
- [ ] Confirm your numeric Telegram user ID is in local `ZION_ADMIN_USER_IDS`.
- [ ] Decide whether Mistral should remain disabled for the first deployment.
- [ ] Recommended first deployment: `ZION_AI_ENABLED=false`, `ZION_AI_OBSERVE=false`.
- [ ] Run `bash scripts/validate.sh`.
- [ ] Confirm tests pass.
- [ ] Confirm `git status` is clean.

## First modular deployment

Run:

```bash
bash scripts/apply-zion-v1.sh
```

Then test:

1. `/status`
2. `/health`
3. `/aistatus`
4. `/rules`
5. flood using the test account only
6. restart the ZION service (not the computer) and confirm strike persistence

## Mistral activation

Only after the deterministic core is healthy:

1. add `MISTRAL_API_KEY` locally;
2. set `ZION_AI_ENABLED=true`;
3. keep `ZION_AI_OBSERVE=false`;
4. restart only `zion.service`;
5. test `/ask`;
6. inspect logs for redaction and errors;
7. later enable `ZION_AI_OBSERVE=true`.

Never paste the API key into chat or logs.

## Safety acceptance

- [ ] Private DM from a non-allowlisted user cannot run admin commands.
- [ ] A Telegram admin who is not in ZION_ADMIN_USER_IDS cannot run global operator commands.
- [ ] An unrelated group administrator cannot change ZION global state/domain/AI policy.
- [ ] Criticism is not automatically moderated.
- [ ] Mistral outage does not disable flood/link protection.
- [ ] Mistral daily token budget is visible in admin /aistatus.
- [ ] Mistral circuit breaker opens after configured consecutive failures.
- [ ] Circuit-breaker state survives a ZION service restart.
- [ ] Knowledge-gap retention and report retention are configured as intended.
- [ ] Public users cannot access /health, /guardian, /aistatus or other admin telemetry.
- [ ] AI observe events do not call delete/mute/ban.
- [ ] `/lockdown` and `/unlock` are admin-only.
- [ ] No real secret appears in journal or `zion.log`.
- [ ] SQLite DB is ignored by Git.


## Block 5 — remote operations acceptance

Repository / GitHub:

- [ ] `zion-v1` requires PR + `validate` and blocks force-push/deletion.
- [ ] `zion-v1.1-dev` has the intended development protection.
- [ ] No unexpected branch-protection/ruleset bypass actor exists.
- [ ] Production host has no privileged GitHub Actions self-hosted runner.
- [ ] Production release identity is one exact 40-character `origin/zion-v1` SHA.

Remote access:

- [ ] Tailscale device identity is verified.
- [ ] Router/NAT has no TCP/22 port-forward to the Acer.
- [ ] Tailnet policy permits only intended principals.
- [ ] Dedicated Android private SSH key never left the client.
- [ ] Acer ED25519 host fingerprint was verified out of band.
- [ ] `~/.ssh` is 0700 and `authorized_keys` is 0600, regular and correctly owned.
- [ ] Public-key login succeeded before sshd hardening.
- [ ] `scripts/apply-ssh-hardening.sh` completed with `sshd -t` green.
- [ ] Effective sshd disables root/password/keyboard-interactive auth and forwarding.
- [ ] Second independent SSH session succeeded before bootstrap session closed.
- [ ] Strict `scripts/remote-access-preflight.sh` exits zero.

Deployment:

- [ ] `scripts/deployment-preflight.sh` passes with real external-control attestations.
- [ ] `scripts/verify-approved-release.sh` validates the exact production SHA while old service remains online.
- [ ] Previous production SHA is recorded before cutover.
- [ ] Local `zion-v1-prod` fast-forwards only; no reset/rebase/force during normal deploy.
- [ ] Pre-deploy SQLite backup is verified and SHA-256 recorded.
- [ ] Post-deploy host + Telegram acceptance passes.
- [ ] Rollback procedure and backup location are known before the service is stopped.
