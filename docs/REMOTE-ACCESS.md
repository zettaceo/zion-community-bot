# ZION Remote Access Runbook

Status: **prepared, not applied to the Acer host**.

This design uses OpenSSH **over a private Tailscale path**. It does not require or authorize public TCP/22 exposure.

## Trust boundary

```text
Android / Termux
    |
    | dedicated SSH client key
    | Tailscale private network
    v
Linux Mint / Acer ZION host
    |
    | OpenSSH public-key auth only
    v
zetta account
    |
    | explicit sudo only for host administration
    v
systemd / sshd / ZION deployment controls
```

GitHub remains the code source of truth. Runtime secrets remain local on the host.

Remote access and bot deployment are separate changes. Applying SSH/Tailscale configuration must not restart `zion.service`.

## Non-negotiable controls

1. Do **not** configure router/NAT forwarding for TCP/22.
2. Do **not** place SSH private keys, Tailscale auth material, Telegram tokens, Mistral keys or passwords in Git.
3. Use a dedicated ED25519 key for this host.
4. Verify the server ED25519 host-key fingerprint out of band before permanently trusting it.
5. Keep `~/.ssh` mode `0700`; keep `authorized_keys` mode `0600`.
6. Public-key login must be proven **before** password authentication is disabled.
7. Never close the bootstrap session until a second independent session succeeds.
8. Root SSH login, password auth, keyboard-interactive auth, agent forwarding, TCP forwarding, X11 forwarding and tunnels stay disabled.
9. SSH hardening does not replace Tailnet policy or host firewall policy.
10. This design uses ordinary OpenSSH over Tailscale. Do not enable Tailscale SSH, Funnel or Serve as part of this block unless they receive a separate review.
11. Review every entry in `authorized_keys`; no unknown or stale key is acceptable.
12. Do not install a privileged GitHub Actions self-hosted runner on the production host.
13. Do not change the USB Wi-Fi topology or reboot the Acer as part of remote-access setup.
14. `.env`, SQLite runtime files and host backups remain outside GitHub.

## Phase 0 — physical-console prerequisites

Do the initial bootstrap while physical/local access to the Acer is available.

Run the read-only report first:

```bash
cd /home/zetta/zion-community-bot
bash scripts/remote-access-preflight.sh --report-only
```

Expected before setup: missing Tailscale/SSH controls may be reported as failures. The command does not change configuration.

Install Tailscale only from its official Linux distribution channel and authenticate the Acer into the intended Tailnet. Do not put reusable Tailscale auth keys in the repository or shell scripts.

Verify that the host receives a Tailscale address and that the intended Android device appears as the expected Tailnet identity.

## Phase 1 — Android / Termux client key

Create a dedicated client key locally on Android:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
ssh-keygen -t ed25519 -a 100 -f ~/.ssh/zion-server
chmod 600 ~/.ssh/zion-server
chmod 644 ~/.ssh/zion-server.pub
```

The private file `~/.ssh/zion-server` never leaves Android.

Transfer only `zion-server.pub` to the Acer using a trusted local method.

## Phase 2 — Acer authorized key

On the Acer, as `zetta`:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
touch ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Append the **public** Android key once. Do not replace existing authorized keys blindly.

Inventory every existing line in `authorized_keys`. Each retained key must have a known owner/device and current operational reason. Remove an unknown/stale key only from a physical console or while a second proven session remains available.

Verify ownership:

```bash
stat -c '%a %U %G %n' ~/.ssh ~/.ssh/authorized_keys
```

Expected owner: `zetta`. Expected modes: `700` and `600`.

## Phase 3 — pin the server host key

At the Acer physical console:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Record the SHA256 fingerprint through a trusted out-of-band channel.

On Android, fetch the public host key over the Tailscale address/MagicDNS name into a temporary file:

```bash
ssh-keyscan -t ed25519 <tailscale-host> > /tmp/zion-hostkey
ssh-keygen -lf /tmp/zion-hostkey
```

Compare the fingerprint character-for-character with the one read physically on the Acer.

Only after they match:

```bash
cat /tmp/zion-hostkey >> ~/.ssh/known_hosts
chmod 600 ~/.ssh/known_hosts
rm -f /tmp/zion-hostkey
```

Do not treat `ssh-keyscan` by itself as identity proof.

Recommended Android alias after pinning:

```sshconfig
Host zion-server
    User zetta
    HostName <tailscale-ip-or-magicdns-name>
    IdentityFile ~/.ssh/zion-server
    IdentitiesOnly yes
    PreferredAuthentications publickey
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    ServerAliveInterval 30
    ServerAliveCountMax 3
    ConnectTimeout 10
    StrictHostKeyChecking yes
```

## Phase 4 — prove key login before hardening

With the existing sshd policy still available, prove:

```bash
ssh zion-server
```

Inside that session, confirm that the source path is Tailscale and keep the session open.

Do **not** disable password authentication merely because the key exists on disk. A real public-key login must succeed first.

## Phase 5 — apply the reviewed sshd drop-in

Authoritative template:

`ops/sshd/00-zion-remote.conf`

The `00-` priority is deliberate: OpenSSH generally keeps the first value obtained for a keyword, so the ZION drop-in must precede ordinary distro/cloud drop-ins. The installer still verifies the resulting effective policy rather than trusting filename order alone.

The guarded installer refuses to run unless the operator explicitly attests that **both** public-key login and the out-of-band ED25519 host fingerprint were proven.

From a proven Tailscale SSH session:

```bash
cd /home/zetta/zion-community-bot
ZION_REMOTE_ACCESS_PROVEN=YES \
ZION_HOSTKEY_PROVEN=YES \
  bash scripts/apply-ssh-hardening.sh
```

From a physical console instead, also provide the **actual Tailscale IP of the Android client** that will be used for remote administration. This lets `sshd -T -C` evaluate any `Match User/Address` rules against the real access context:

```bash
cd /home/zetta/zion-community-bot
ZION_REMOTE_ACCESS_PROVEN=YES \
ZION_HOSTKEY_PROVEN=YES \
ZION_PHYSICAL_CONSOLE=YES \
ZION_TAILSCALE_CLIENT_IP=<android-tailscale-ip> \
  bash scripts/apply-ssh-hardening.sh
```

The installer:

- validates the current authorized-key boundary;
- backs up an existing ZION sshd drop-in;
- installs the reviewed drop-in;
- runs `sshd -t`;
- reloads, never restarts, the SSH daemon;
- verifies the effective hardening in the real `zetta` + Tailscale client context, including `Match` rules;
- disables alternate key/certificate authorization sources (`AuthorizedKeysCommand`, trusted user CAs and principals files);
- rolls back the drop-in if a post-install gate fails;
- does not alter Tailscale, firewall, router, Wi-Fi or `zion.service`.

Keep the current session open.

## Phase 6 — second-session gate

Open a **new** Android terminal and run:

```bash
ssh zion-server
```

Only after the second session succeeds may the bootstrap session be closed.

Then run strict host verification. Because proving the *effective* sshd policy can require access to root-owned host keys, refresh sudo credentials first; the preflight itself uses only non-interactive read-only `sudo -n sshd -T` if the unprivileged check cannot prove the configuration:

```bash
cd /home/zetta/zion-community-bot
sudo -v
bash scripts/remote-access-preflight.sh
```

A non-zero exit means the remote-access gate is not complete.

## Phase 7 — network-exposure gate

The host cannot prove router/NAT configuration or Tailnet ACL/device policy by itself.

Before any remote deployment, manually verify:

- router has no TCP/22 port-forward to the Acer;
- no cloud/VPN forwarding exposes SSH publicly;
- intended devices/users are the only Tailnet principals allowed to reach the Acer;
- device approval/key-expiry policy is acceptable;
- Tailscale SSH, Funnel and Serve are not enabled unless separately reviewed;
- host firewall rules do not unintentionally expose SSH on an untrusted interface.

If firewall rules are tightened, do it while two SSH sessions are available and test a third session before closing either existing connection.

Do not paste generic firewall commands blindly: interface names and existing policy must be inspected on the Acer first.

## Ongoing preflight

Read-only report:

```bash
bash scripts/remote-access-preflight.sh --report-only
```

Strict gate:

```bash
bash scripts/remote-access-preflight.sh
```

The script checks Tailscale presence/address, sshd state, authorized-key permissions/ownership, root-owned single-link ZION sshd drop-in permissions, effective sshd controls (including StrictModes, AuthorizedKeysFile and forwarding restrictions), host-key fingerprint availability and listening surface.

Router/NAT and Tailnet control-plane policy remain explicit manual checks.

## Rollback of SSH hardening

The installer stores previous ZION drop-ins under:

```text
/home/zetta/.local/state/zion-community-bot/ssh-hardening-backups/
```

If hardening must be reverted, do it from a still-open SSH session or physical console:

1. restore the previous drop-in (or remove the ZION drop-in if none existed);
2. run `sudo /usr/sbin/sshd -t`;
3. reload `ssh.service` / `sshd.service`;
4. test a new session;
5. investigate before attempting hardening again.

Never reboot as a recovery substitute for an unvalidated sshd configuration.

## Relationship to deployment

Remote access only provides the private operator path. It does not authorize a code release.

A remote deployment additionally requires the GitHub/commit gates in:

- `docs/GITHUB-DEPLOY-GATES.md`
- `docs/DEPLOYMENT-MODEL.md`
- `scripts/deployment-preflight.sh`
- `scripts/verify-approved-release.sh`
