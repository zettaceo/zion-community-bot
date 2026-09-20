# ZION — Block 5 Remote Operations Audit

Status: **repository implementation and adversarial review complete; host/control-plane application pending**.

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

**Remediation:** expected commit is mandatory and full-length. Pre-cutover gates require exact equality with the approved production ref and live GitHub `zion-v1` head. The apply phase requires the candidate HEAD to equal that immutable SHA and verifies it remains in the approved production history. The previous commit is mandatory and recorded for rollback.

### MEDIUM — predeploy candidate identity was not bound to production ref

`predeploy-v11.sh` displayed the candidate SHA but did not require an exact approved SHA/ref relationship.

**Remediation:** candidate verification now requires full `ZION_EXPECTED_COMMIT` and exact equality with the fixed `origin/zion-v1` production ref.

### MEDIUM — remote-access preflight was informational only

The previous preflight reported installation/state but did not enforce key ownership/mode, effective sshd policy, host identity or a strict success/failure result.

**Remediation:** strict read-only preflight now fails on missing critical controls and offers `--report-only` for bootstrap inventory.

### MEDIUM — first-contact SSH trust used `accept-new`

Automatically accepting the first observed host key does not independently authenticate that first connection.

**Remediation:** the runbook now requires out-of-band ED25519 host-key fingerprint comparison before storing the key; normal client config uses `StrictHostKeyChecking yes`, and the hardening installer requires a separate `ZION_HOSTKEY_PROVEN=YES` attestation.

### MEDIUM — sshd hardening had no authoritative reviewed template or precedence guarantee

A late `99-` drop-in could lose to an earlier distro/cloud drop-in because OpenSSH commonly keeps the first value obtained for a keyword.

**Remediation:** `ops/sshd/00-zion-remote.conf` is now the repository-authoritative high-precedence drop-in. A guarded installer requires proven key access and host identity, validates with `sshd -t`, reloads instead of restarting, verifies effective key/forwarding/session policy and rolls back the drop-in on failure. The strict preflight treats inability to prove effective sshd policy as a failure rather than a warning.

## Independent adversarial review findings

### HIGH — global `sshd -T` did not prove the real `Match` policy

A global configuration dump can miss user/address-specific `Match` behavior. ZION could therefore appear hardened while the effective policy for the actual `zetta` Tailscale session differed.

**Remediation:** installer and strict preflight now evaluate `sshd -T -C` with the real operator user, Tailscale client address, Tailscale local address and SSH port. Strict mode fails if that context cannot be proven.

### HIGH — strict SSH preflight inherited path/user overrides

Environment overrides intended for CI/reporting could redirect strict checks to alternate `.ssh`, `authorized_keys` or sshd drop-in paths.

**Remediation:** strict mode fixes the operational identity to `zetta`, `/home/zetta/.ssh/authorized_keys` and `/etc/ssh/sshd_config.d/00-zion-remote.conf`. Overrides remain available only for `--report-only` test/inventory mode. The installer uses fixed sensitive paths and its template relative to its own reviewed worktree.

### MEDIUM — SSH backup filename could collide

A malformed shell interpolation produced a literal `.$.conf` suffix rather than a per-process identifier.

**Remediation:** backups now include `$BASHPID` in addition to the UTC timestamp.

### MEDIUM — rollback identity was optional

A deployment could proceed without recording the prior production commit.

**Remediation:** `ZION_PREVIOUS_COMMIT` is now mandatory, must be a full SHA, must exist, must differ from the candidate and must be an ancestor of it.

### MEDIUM — live remote equality check created a cutover race

After the operator had already selected/verified an immutable SHA, a later advance of `zion-v1` could make `apply-zion-v1.sh` refuse solely because the branch head changed, potentially after the service had already been stopped.

**Remediation:** exact live-remote equality remains a **pre-cutover** gate in deployment preflight and approved-release verification. The apply phase verifies that the selected immutable SHA still belongs to the locally approved `origin/zion-v1` history, avoiding an unnecessary availability race while preserving the reviewed release identity.

### MEDIUM — direct dependency gate omitted `idna`

`idna` became a direct runtime dependency but `check-runtime.py` validated only the earlier three direct packages.

**Remediation:** runtime compatibility now checks `idna>=3,<4`, and both predeploy/apply run `python -m pip check` before any production stop.

### MEDIUM — low-priority sshd drop-in could lose precedence

A `99-` drop-in may be too late on systems where earlier included files already set a keyword and OpenSSH keeps the first value.

**Remediation:** the authoritative file moved to `00-zion-remote.conf`. Effective policy is still verified after installation. Alternate key/certificate sources are disabled with `AuthorizedKeysCommand none`, `TrustedUserCAKeys none` and `AuthorizedPrincipalsFile none`.

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
- `ops/sshd/00-zion-remote.conf`

## Automated regression coverage

Block 5 source/behavior contracts cover:

- strict preflight remains read-only and fails closed;
- report-only mode cannot be confused with strict acceptance;
- fixed production repo/branch/user/path identities;
- full 40-character release SHA binding;
- live GitHub production-head verification before cutover;
- approved-release validation in a detached temporary worktree;
- mandatory rollback SHA metadata;
- runtime direct dependency ranges plus `pip check`;
- `00-` sshd precedence and exclusive authorized-key sources;
- real Tailscale client `sshd -T -C` Match context;
- SSH reload + rollback behavior without bot/service restart;
- GitHub-hosted CI remains read-only and is not self-hosted.

Full repository CI, shell syntax validation and secret scan remain mandatory before integration.

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
