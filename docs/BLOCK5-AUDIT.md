# ZION — Block 5 Remote Operations Audit

Status: **implementation in isolated development branch; host application pending**.

Base:
- `zion-v1.1-dev`
- `039e0d2ff44513920a664b3b904657a381bdb2da`

Working branch:
- `block5-remote-ops`

Production `zion-v1` is out of scope for code mutation in this block.

## Scope

Block 5 prepares:

- private Tailscale + OpenSSH administration;
- SSH identity/hardening and lockout-safe application;
- remote-access preflight;
- GitHub production governance requirements;
- exact-SHA deployment selection;
- isolated approved-release verification;
- rollback metadata and procedure;
- CI/static contracts for those controls.

Actual Acer/Tailscale/SSH/firewall changes are deferred to a separate host gate.

## Initial findings

### HIGH — production branch has no enforced GitHub protection

At Block 5 start, GitHub reported both `zion-v1` and `zion-v1.1-dev` as unprotected.

That means repository policy itself did not prevent direct writes/force-history operations from becoming production-source commits.

**Remediation available in repository code:** document mandatory production rules, require explicit external attestation before host deploy, and exact-SHA bind all deploy scripts to `origin/zion-v1`.

**Residual:** enabling branch protection/rulesets requires repository administration permission outside the available connector. Remote deployment remains prohibited until that control-plane action is performed and verified.

### HIGH — deployment script accepted an optional expected commit

`apply-zion-v1.sh` previously enforced `ZION_EXPECTED_COMMIT` only when supplied. An operator could therefore run a deploy from the wrong local HEAD.

**Remediation:** expected commit is mandatory, full-length, must equal current HEAD and must equal the approved production ref. Previous commit can be recorded in backup metadata for rollback.

### MEDIUM — predeploy candidate identity was not bound to production ref

`predeploy-v11.sh` displayed the candidate SHA but did not require an exact approved SHA/ref relationship.

**Remediation:** candidate verification now requires full `ZION_EXPECTED_COMMIT` and exact equality with `origin/zion-v1` (or an explicitly supplied approved ref).

### MEDIUM — remote-access preflight was informational only

The previous preflight reported installation/state but did not enforce key ownership/mode, effective sshd policy, host identity or a strict success/failure result.

**Remediation:** strict read-only preflight now fails on missing critical controls and offers `--report-only` for bootstrap inventory.

### MEDIUM — first-contact SSH trust used `accept-new`

Automatically accepting the first observed host key does not independently authenticate that first connection.

**Remediation:** the runbook now requires out-of-band ED25519 host-key fingerprint comparison before storing the key; normal client config uses `StrictHostKeyChecking yes`.

### MEDIUM — sshd hardening had no authoritative reviewed template

**Remediation:** `ops/sshd/99-zion-remote.conf` is now the repository-authoritative drop-in. A guarded installer requires proven key access, validates with `sshd -t`, reloads instead of restarting, verifies effective policy and rolls back the drop-in on failure.

## Security invariants

- no public TCP/22 router forwarding;
- no private key or Tailscale auth material in Git;
- root/password/keyboard-interactive SSH disabled after key proof;
- no SSH agent/TCP/X11/tunnel forwarding;
- host key pinned out of band;
- second-session test before bootstrap session closes;
- no privileged Actions runner on production host;
- only exact `origin/zion-v1` SHA is deployable;
- candidate release validation occurs before service stop;
- production secrets remain host-local;
- no force-push rollback of the remote production branch.

## Files

Primary Block 5 surfaces:

- `docs/REMOTE-ACCESS.md`
- `docs/DEPLOYMENT-MODEL.md`
- `docs/GITHUB-DEPLOY-GATES.md`
- `scripts/remote-access-preflight.sh`
- `scripts/apply-ssh-hardening.sh`
- `scripts/deployment-preflight.sh`
- `scripts/verify-approved-release.sh`
- `scripts/predeploy-v11.sh`
- `scripts/apply-zion-v1.sh`
- `ops/sshd/99-zion-remote.conf`

## Residual host/control-plane gates

Cannot be certified by repository CI:

- real Tailscale installation and Tailnet identity;
- router/NAT exposure;
- Tailnet ACL/device policy;
- real Acer sshd version/effective config;
- real authorized-key login from Android;
- physical host-key fingerprint ceremony;
- second SSH session;
- actual firewall policy;
- GitHub branch-protection/ruleset enablement;
- actual remote deploy/rollback rehearsal.

Those must remain explicit external gates, not simulated claims.
