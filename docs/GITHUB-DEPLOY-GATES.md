# ZION GitHub Deployment Gates

Status: **repository-admin action required before first remote production deployment**.

At the start of Block 5, GitHub reported both `zion-v1` and `zion-v1.1-dev` as unprotected. Repository code cannot remediate that control-plane state through the currently available connection.

The current ChatGPT GitHub connection can inspect branch state but cannot modify branch protection/rulesets because repository administration permission is intentionally unavailable.

## Production branch — `zion-v1`

Minimum required control:

- require a pull request before merging;
- require GitHub Actions status check `validate` from **ZION CI**;
- require the branch to be up to date before merge when practical;
- require conversation resolution;
- block force pushes;
- block branch deletion;
- do not permit routine bypass.

Recommended when an independent human reviewer is available:

- require at least one non-author approval;
- dismiss stale approvals after new commits.

Do not enable a privileged self-hosted runner as a substitute for these controls.

The Acer's Git credential, if one is needed for fetch/ls-remote, should be **read-only** for repository contents. The production host does not need permission to push, merge PRs, alter rulesets or administer the repository. Prefer a credential mechanism that does not place a token in the remote URL or shell history.

## Development integration branch — `zion-v1.1-dev`

Minimum recommended control:

- require pull requests for feature/audit branches;
- require `validate`;
- block force pushes;
- block deletion;
- require conversation resolution.

The development branch is not deployable production input by itself.

## Production release path

Only:

```text
reviewed branch
  -> PR
  -> zion-v1.1-dev
  -> production PR
  -> zion-v1
  -> exact SHA deployment
```

A direct commit to `zion-v1`, even by an administrator, is outside the normal release model.

## Manual verification before remote deploy

In GitHub repository settings, verify the active branch rule/ruleset actually covers `zion-v1`.

Confirm:

- PR required;
- `validate` required;
- force push disabled;
- deletion disabled;
- no unexpected bypass actor;
- the Acer's Git credential is fetch/read-only and cannot push to production.

Then verify the production PR's final merged SHA is the same 40-character SHA shown by:

```bash
git rev-parse origin/zion-v1
```

Only then may the operator set:

```text
ZION_GITHUB_GATES_PROVEN=YES
```

The variable is an attestation, not an automated proof.

## Explicit initial go-live waiver

The preferred release path still requires the GitHub controls above. For the first v1.1 go-live only, the operator may explicitly accept the unresolved GitHub governance risk without pretending the branch is protected.

Use:

```text
ZION_GITHUB_GATES_WAIVED=YES
ZION_INITIAL_GO_LIVE_WAIVER=YES
ZION_EXTERNAL_WAIVER_REASON=<single-line reason>
```

together with either a proven or explicitly waived remote-network gate. The checker rejects `PROVEN=YES` and `WAIVED=YES` for the same control.

A waiver is reported as `WAIVED`, never as `PASS` or `PROVEN`. It is not persisted into production configuration. GitHub protection remains follow-up work and should be completed before later ordinary releases.

## Emergency policy

If GitHub protection must ever be bypassed during an incident:

- document why;
- do not force-push production history;
- preserve the commit SHA involved;
- restore normal repository protection before the next ordinary deployment;
- run the same CI/review gates on the forward fix.


## Verification snapshot — 2026-09-20 final repository re-audit

Live GitHub branch metadata was re-read after the implementation hardening:

- `zion-v1`: `protected=false`;
- `zion-v1.1-dev`: `protected=false`;
- required status-check enforcement in branch metadata: off;
- PR #2: open, Draft, unmerged; no submitted reviews or review threads at the checkpoint;
- repository rulesets API returned HTTP 403 with GitHub's message that the private repository must be public or the account upgraded to GitHub Pro to enable that feature;
- the connected GitHub App does not have repository-administration permission to read/change classic branch-protection settings.

The branch metadata itself is sufficient to keep the GitHub governance gate **BLOCKED**. Do not set `ZION_GITHUB_GATES_PROVEN=YES` from CI success alone.
