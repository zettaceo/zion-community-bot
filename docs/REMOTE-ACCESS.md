# ZION Remote Access Runbook

Status: preparation only. This document does not expose SSH to the public internet and contains no credentials.

## Architecture

```text
Android / Termux
      |
      | Tailscale private network
      v
Linux Mint host
      |
      | SSH public-key authentication
      v
zetta@zion host
```

## Security invariants

1. Do not forward TCP/22 on the router.
2. Do not store private SSH keys, Telegram tokens, Mistral keys, passwords or Tailscale auth keys in Git.
3. Use a dedicated ED25519 client key for the Android device.
4. Keep password authentication disabled for the dedicated Termux alias after public-key access has been proven.
5. Authorize only the public key in `~/.ssh/authorized_keys`.
6. Prefer the Tailscale address or MagicDNS name as the SSH target.
7. Do not reboot the ZION host as part of remote-access setup.
8. Do not change the USB Wi-Fi topology or unbind its parent hub.
9. Test a second terminal session before tightening sshd rules, so a configuration mistake cannot lock out the operator.
10. Keep ZION runtime secrets local in `.env`; GitHub remains code-only.

## Android side

Expected files:

```text
~/.ssh/zion-server       # private; 0600; never copied
~/.ssh/zion-server.pub   # public; may be authorized on server
~/.ssh/config            # 0600
```

Recommended alias:

```sshconfig
Host zion-server
    User zetta
    HostName <tailscale-ip-or-magicdns-name>
    IdentityFile ~/.ssh/zion-server
    IdentitiesOnly yes
    PreferredAuthentications publickey
    PasswordAuthentication no
    ServerAliveInterval 30
    ServerAliveCountMax 3
    ConnectTimeout 10
    StrictHostKeyChecking accept-new
```

## Linux Mint side — when physically available

Perform these steps interactively and verify output after each step:

1. Install Tailscale from its official Linux distribution channel.
2. Authenticate the host into the same Tailnet as the Android device.
3. Verify the Tailscale interface/address and peer visibility.
4. Verify OpenSSH server is installed and listening locally.
5. Back up `~/.ssh/authorized_keys` if it already exists.
6. Append the Android `zion-server.pub` key only.
7. Enforce `0700` on `~/.ssh` and `0600` on `authorized_keys`.
8. Test `ssh zion-server` from Android over Tailscale.
9. Open a second SSH session and keep the first alive.
10. Only after both work, restrict sshd/firewall access to the Tailscale interface if desired.
11. Re-test ZION service health; remote-access work must not restart the bot.

## Rollback

If SSH hardening causes trouble while a local terminal is available:

- restore the previous sshd configuration from backup;
- validate with `sshd -t`;
- reload, rather than reboot, sshd;
- keep Tailscale installed unless it is itself the source of the problem.

ZION service deployment and remote-access configuration are separate concerns. A remote-access change must never be coupled to a bot deployment.
