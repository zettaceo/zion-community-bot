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

## Audited Python runtime

`requirements.txt` documents the supported dependency ranges for development, while `requirements.lock` is the exact audited v1.1 release environment.

GitHub CI installs `requirements.lock`. Production releases do **not** mutate the venv used by the currently running bot.

Before cutover, `scripts/prepare-release-runtime.sh` creates/verifies a runtime keyed by the approved release SHA under:

```text
/home/zetta/.local/share/zion-community-bot/runtimes/<sha>/
```

`scripts/check-runtime.py` requires Python 3.12.x, every locked distribution at the exact version, no unexpected distributions other than venv bootstrap tooling, and `pip check` consistency.

The active service uses only:

```text
/home/zetta/.local/share/zion-community-bot/runtimes/current/bin/python
```

The `current` pointer is switched to the candidate only after the old service has stopped. Rollback records and restores the previous runtime target.

Do not install/upgrade packages ad hoc during the cutover window.

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

Release-time Python is also treated as an executable boundary. Before any non-isolated candidate/runtime interpreter is used, the release scripts require a clean caller environment with no inherited `PYTHON*` variables. Environment checks themselves run with `/usr/bin/python3 -I`; Python-only host probes use isolated mode directly. This prevents `PYTHONPATH`/related process variables from importing code outside the approved SHA and locked runtime.

## First v1 → v1.1 bootstrap

The current v1 production commit predates the strict v1.1 release-gate scripts. For the first upgrade, do not assume those scripts already exist in the production checkout.

Use the exact candidate SHA in a detached temporary worktree and follow:

`docs/V1.1-FIRST-UPGRADE.md`

The candidate preflight binds its own worktree HEAD to the approved SHA while inspecting the unchanged production root.

Before the first candidate worktree is created, the bootstrap must extract `scripts/check-git-release-boundary.py` directly from the exact approved commit as a raw Git blob and run it against the production repository. This pre-check prevents local attribute/smudge state from executing during the first `worktree add`; disabling Git hooks alone is not a sufficient checkout boundary.

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
- clean worktree including non-ignored untracked files;
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

## Disabled legacy mutation paths

The v1.1 repository intentionally disables the old direct host installers:

- `scripts/apply-systemd.sh` — no longer allowed to install/restart the bot outside the exact-SHA release flow;
- `scripts/apply-wifi-guardian.sh` — no longer allowed to mutate Wi-Fi host components without a separately reviewed physical procedure.

Do not revive or bypass these scripts during release troubleshooting. A failed governed gate is a stop condition, not permission to use an older installer.

## Controlled cutover

Only after both preflights are green:

```bash
cd /home/zetta/zion-community-bot

PREVIOUS_HEAD="$(git rev-parse HEAD)"
test "$(git branch --show-current)" = "zion-v1-prod"
test "$(git rev-parse origin/zion-v1)" = "$ZION_DEPLOY_COMMIT"

DASHBOARD_LOAD_STATE="$(
  systemctl show zion-dashboard.service -p LoadState --value 2>/dev/null || true
)"
if [[ -n "$DASHBOARD_LOAD_STATE" && "$DASHBOARD_LOAD_STATE" != "not-found" ]]; then
  sudo systemctl stop zion-dashboard.service
fi
sudo systemctl stop zion.service

GIT_NO_REPLACE_OBJECTS=1 \
git -c core.hooksPath=/dev/null \
  merge --ff-only "$ZION_DEPLOY_COMMIT"
```

If the fast-forward fails, do **not** improvise with reset/rebase/force. The worktree is still on the previous release; restart the old service and investigate.

After the fast-forward succeeds:

```bash
ZION_EXPECTED_COMMIT="$ZION_DEPLOY_COMMIT" \
ZION_PREVIOUS_COMMIT="$PREVIOUS_HEAD" \
ZION_GITHUB_GATES_PROVEN=YES \
  bash scripts/apply-zion-v1.sh
```

`apply-zion-v1.sh` now refuses to deploy unless the local branch is exactly `zion-v1-prod`, current HEAD equals the selected immutable release SHA, that SHA remains in the locally approved `origin/zion-v1` history, the GitHub origin identity is correct, and the GitHub-governance attestation is present. The previous production SHA is mandatory and is recorded in pre-deploy backup metadata. Exact equality with the **live** remote branch head is intentionally a pre-cutover gate, not a post-stop gate, so a later fast-forward of `zion-v1` cannot create an unnecessary availability failure.

If `apply-zion-v1.sh` fails **before** it stops `zion.service`, production runtime state has not been cut over; restore the local worktree to `PREVIOUS_HEAD` only if necessary and keep/restart the old service. If it fails after the stop/migration phase may have begun, do not guess: use the verified backup + recorded rollback SHA and follow the rollback procedure below.

## First dashboard bootstrap

The dashboard is not an alternate deployment path. Its one-time installer may be used only **after** the v1.1 bot release is already running from the approved production SHA.

`scripts/apply-dashboard.sh` therefore requires:

- `ZION_DEPLOY_COMMIT` as the full approved 40-character SHA;
- `ZION_GITHUB_GATES_PROVEN=YES`;
- local branch exactly `zion-v1-prod`;
- clean local Git boundary and clean non-ignored worktree;
- local `origin/zion-v1` and the live GitHub `zion-v1` head both equal to the approved SHA;
- `runtime/current` resolves to the per-SHA runtime for that same commit;
- the installed `zion.service` already uses the v1.1 state/runtime layout and is active;
- the dashboard unit is not already installed.

The script revalidates HEAD, worktree and runtime immediately before the first `sudo`. If a dashboard unit is already installed, **do not** use the bootstrap script to update it; later dashboard changes participate in the ordinary controlled release through `apply-zion-v1.sh`.

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

Verified deployment backups are stored outside the bot-writable repository:

```text
/home/zetta/.local/share/zion-community-bot/deploy-backups/
```

The bot service's systemd writable paths do not include that directory.

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

## Immutable code / mutable state boundary

The production service must not have write access to its code, `.env` or Python runtime.

The reviewed v1.1 systemd contract forces mutable state to:

```text
/home/zetta/.local/state/zion-community-bot/
```

and marks the repository/runtime tree read-only.

The main mutable artifacts are SQLite (including WAL/SHM), logs, legacy migration state when retained and the shared runtime lock. This prevents a compromised bot process from persisting by modifying repository code, release scripts, `.env` or its own Python environment.

The currently installed root-owned `zion.service` is also the authority for where current production state lives: first-upgrade releases can read the legacy repository DB, while later v1.1 releases recognize the state-dir layout forced by the installed unit. This prevents future predeploy/backup logic from silently inspecting a stale legacy DB.

## Separation of duties

- GitHub CI proves repository tests.
- GitHub branch/ruleset controls define what may become `zion-v1`.
- Tailscale + SSH authenticate the human operator.
- Host preflight proves local deployment prerequisites.
- Exact SHA pinning binds the host action to the reviewed release.
- Backup/rollback protects runtime state.

None of these controls substitutes for the others.
