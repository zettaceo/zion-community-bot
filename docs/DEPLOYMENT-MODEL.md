# ZION Deployment Model

Status: **manual, commit-pinned deployment model; host application pending**.

## Branch roles

```text
feature / audit branch
        |
        | PR + CI
        v
zion-v1.1-dev
        |
        | production PR + CI + explicit approval
        v
zion-v1
        |
        | exact 40-char SHA
        v
manual operator deployment over Tailscale + SSH
        |
        v
local zion-v1-prod worktree on Acer
```

`zion-v1` is the only remote ref authorized as a production release source.

No feature branch, PR head, local-only commit or arbitrary SHA may be deployed merely because it passes tests.

Any Git credential present on the Acer should be fetch/read-only. The host has no operational need to push to `zion-v1` or modify repository administration state.

## GitHub governance gate

Before the first remote deployment, `zion-v1` must have repository rules/branch protection that at minimum:

- require pull requests;
- require the `validate` CI job;
- block force-push and deletion;
- require conversation resolution;
- prevent routine bypass.

See `docs/GITHUB-DEPLOY-GATES.md`.

Host scripts cannot independently query/guarantee GitHub administration state. Therefore `scripts/deployment-preflight.sh` requires explicit operator attestation:

```text
ZION_GITHUB_GATES_PROVEN=YES
```

Do not set that variable until the repository control plane has actually been verified.

## No privileged self-hosted runner

Do not install a GitHub Actions self-hosted runner on the production Acer.

A workflow/PR must not automatically become a production shell with access to:

- `.env`;
- Telegram/Mistral credentials;
- SQLite state;
- systemd;
- SSH material;
- sudo.

The deployment preflight fails if it detects a conventional `actions.runner.*` service or GitHub Runner process.

CI remains GitHub-hosted and unprivileged relative to the Acer.

## Release selection

The deploy target is a full 40-character Git commit SHA.

After a production PR is merged:

```bash
cd /home/zetta/zion-community-bot
git fetch --prune origin zion-v1
```

Read the exact new `origin/zion-v1` SHA and compare it with the reviewed GitHub merge result.

Do not use `latest`, a tag that can move, a branch name alone or a short SHA as deployment identity.

Set:

```bash
export ZION_DEPLOY_COMMIT=<40-character-approved-sha>
```

## Remote/network gate

Remote deployment is allowed only after the Tailscale/OpenSSH ceremony in `docs/REMOTE-ACCESS.md` is complete.

Router/NAT and Tailnet control-plane settings cannot be proven by local host inspection, so deployment also requires explicit operator confirmation:

```text
ZION_REMOTE_NETWORK_PROVEN=YES
```

This means the operator has actually verified:

- no public TCP/22 forwarding;
- intended Tailnet identity/device policy;
- private SSH path works with pinned host identity;
- Tailscale SSH/Funnel/Serve are not unexpectedly exposing the host.

## Read-only deployment preflight

Run while the current ZION service is still active:

```bash
ZION_DEPLOY_COMMIT="$ZION_DEPLOY_COMMIT" \
ZION_GITHUB_GATES_PROVEN=YES \
ZION_REMOTE_NETWORK_PROVEN=YES \
  bash scripts/deployment-preflight.sh
```

This proves, among other things:

- expected GitHub `origin` repository identity;
- exact local `origin/zion-v1` SHA match;
- a read-only `git ls-remote` check that the live GitHub `zion-v1` head equals the approved SHA;
- local production branch identity;
- clean tracked worktree;
- fast-forward relationship from current production;
- private `.env` ownership/mode;
- no detected self-hosted Actions runner;
- strict remote-access preflight;
- local runtime/predeploy tooling availability.

It does not stop/restart ZION or change production files.

## Isolated approved-release verification

Before cutover, validate the approved release in a detached temporary worktree:

```bash
ZION_DEPLOY_COMMIT="$ZION_DEPLOY_COMMIT" \
ZION_GITHUB_GATES_PROVEN=YES \
  bash scripts/verify-approved-release.sh
```

The verifier refuses to run candidate code unless the candidate SHA equals `origin/zion-v1`.

It creates a temporary detached worktree, uses the installed production Python runtime, and runs `predeploy-v11.sh`. Production remains online while:

- code/tests/secret scan run;
- production config readiness is inspected;
- production SQLite is verified through a disposable backup;
- candidate migrations are applied only to the disposable copy.

The temporary worktree is removed afterward.

This is the last code gate before stopping the service.

## Controlled cutover

Only after both preflights are green:

```bash
cd /home/zetta/zion-community-bot

PREVIOUS_HEAD="$(git rev-parse HEAD)"
test "$(git branch --show-current)" = "zion-v1-prod"
test "$(git rev-parse origin/zion-v1)" = "$ZION_DEPLOY_COMMIT"

sudo systemctl stop zion.service

git merge --ff-only "$ZION_DEPLOY_COMMIT"
```

If the fast-forward fails, do **not** improvise with reset/rebase/force. The worktree is still on the previous release; restart the old service and investigate.

After the fast-forward succeeds:

```bash
ZION_EXPECTED_COMMIT="$ZION_DEPLOY_COMMIT" \
ZION_PREVIOUS_COMMIT="$PREVIOUS_HEAD" \
ZION_GITHUB_GATES_PROVEN=YES \
  bash scripts/apply-zion-v1.sh
```

`apply-zion-v1.sh` now refuses to deploy unless the local branch is exactly `zion-v1-prod`, the expected SHA matches current HEAD and the approved production ref, the expected GitHub origin/live production branch still match, and the GitHub-governance attestation is present. It records the previous commit in pre-deploy backup metadata when supplied.

If `apply-zion-v1.sh` fails **before** it stops `zion.service`, production runtime state has not been cut over; restore the local worktree to `PREVIOUS_HEAD` only if necessary and keep/restart the old service. If it fails after the stop/migration phase may have begun, do not guess: use the verified backup + recorded rollback SHA and follow the rollback procedure below.

## Post-deploy acceptance

Do not call deployment successful until all of these are checked:

Host:

```bash
systemctl status zion.service --no-pager --full
systemctl show zion.service -p NRestarts -p ActiveState -p SubState -p ExecMainStartTimestamp
bash scripts/remote-access-preflight.sh
```

Telegram:

1. `/status`
2. operator `/health`
3. operator `/diagnostics`
4. operator `/jobs`
5. operator `/aistatus`

Also inspect the deployment backup directory printed by `apply-zion-v1.sh`.

## Rollback model

Rollback is a manual incident procedure, not an automatic GitHub action.

The pre-deploy backup contains:

- deployed candidate SHA;
- approved production ref/SHA;
- previous/rollback SHA when provided;
- SQLite backup and SHA-256 when a DB exists;
- installed systemd unit when present;
- environment file metadata/hash, never the secret file itself.

If post-deploy acceptance fails:

1. keep the incident contained; do not push/rewrite `zion-v1`;
2. stop `zion.service`;
3. verify the backup SQLite checksum/integrity before restoration;
4. return the **local** production worktree to the recorded rollback SHA;
5. restore the verified database backup if the candidate changed/migrated DB state;
6. restore the prior systemd unit if necessary;
7. remove stale DB WAL/SHM sidecars only while the service is stopped and only as part of a deliberate DB restore;
8. start the service;
9. repeat host + Telegram acceptance;
10. open a forward-fix PR. Do not force-push the remote production branch backward.

A host rollback can temporarily leave local `zion-v1-prod` behind `origin/zion-v1`. That is an emergency state, not a branch rewrite.

## Separation of duties

- GitHub CI proves repository tests.
- GitHub branch/ruleset controls define what may become `zion-v1`.
- Tailscale + SSH authenticate the human operator.
- Host preflight proves local deployment prerequisites.
- Exact SHA pinning binds the host action to the reviewed release.
- Backup/rollback protects runtime state.

None of these controls substitutes for the others.
