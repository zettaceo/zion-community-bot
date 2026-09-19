# ZION Operations Runbook

## Normal update flow

Do not run a manual second polling process while systemd is running.

Recommended deployment flow:

```bash
sudo systemctl stop zion.service
git pull
bash scripts/validate.sh
sudo systemctl start zion.service
systemctl status zion.service --no-pager --full
```

For the v1 modular migration, use `scripts/apply-zion-v1.sh` after review.

## Health checks

Telegram:

`/status`

`/health`

Admin:

`/stats`

`/incidents`

`/aistatus`

Linux:

```bash
systemctl show zion.service -p NRestarts -p ActiveState -p SubState -p ExecMainStartTimestamp
systemctl status zion-wifi-guardian.timer --no-pager
```

## Mistral activation

1. Store the Mistral key in local `.env`; never paste it into chat or commit it.
2. Set `ZION_AI_ENABLED=true`.
3. Keep `ZION_AI_OBSERVE=false` for the first support-only test.
4. Validate `/aistatus` and `/ask`.
5. Only after observing stable behavior, enable `ZION_AI_OBSERVE=true`.
6. Observe-only mode never punishes users.

## Emergency

If moderation behaves unexpectedly:

```bash
sudo systemctl stop zion.service
```

The database and legacy state remain on disk.

If the AI provider is problematic, disable only:

```text
ZION_AI_ENABLED=false
ZION_AI_OBSERVE=false
```

The deterministic Guardian remains available.

## Database

Default local DB:

`/home/zetta/zion-community-bot/zion.db`

SQLite runs in WAL mode. Runtime DB/WAL/SHM files are ignored by Git.

The old `zion_state.json` is imported once into SQLite when modular v1 first starts; the original file is preserved.

## Backup

A future remote backup target can be added after deciding retention/privacy policy. Until then, do not upload the SQLite file to public storage.
