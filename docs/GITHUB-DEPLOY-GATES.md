# ZION GitHub Deployment Gates

Status: **repository-admin action required before first remote production deployment**.

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
- no unexpected bypass actor.

Then verify the production PR's final merged SHA is the same 40-character SHA shown by:

```bash
git rev-parse origin/zion-v1
```

Only then may the operator set:

```text
ZION_GITHUB_GATES_PROVEN=YES
```

The variable is an attestation, not an automated proof.

## Emergency policy

If GitHub protection must ever be bypassed during an incident:

- document why;
- do not force-push production history;
- preserve the commit SHA involved;
- restore normal repository protection before the next ordinary deployment;
- run the same CI/review gates on the forward fix.
