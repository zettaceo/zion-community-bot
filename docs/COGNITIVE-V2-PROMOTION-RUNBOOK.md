# Cognitive v2 — production promotion runbook

Status: PREPARED, NOT EXECUTED. This document is not a production
authorization. Every step marked **OWNER** needs the owner's explicit
approval for that step; approval of one step does not carry to the next.

## What changes in production

| Area | Production `472a4b3` | Candidate (`codex/multi-agent-cognitive-v2`) |
| --- | --- | --- |
| SQLite schema | v4 | v4, no migration (`zion/db.py` adds one read method) |
| `requirements.lock`, systemd units | — | unchanged |
| Generation model | `ministral-8b-2512` | `ministral-8b-2512`; `AIService` is composed without candidate providers, approvals or currency budget, so Kimi cannot be selected |
| Output guard | **none** | `validate_public_response` on every generated answer; phishing-only `scam_surface_reason` on `/summary` and `/translate` |
| Kimi | absent | `/setkimikey`, `/cancelkimikey`, `/kimistatus` (operator DM only); store status shown in the Control Center; activation BLOCKED |
| Telegram identity | `.env` token | protected `zion.token` would take precedence; it is **absent** on the host (only `mimir`, `eir`, `freyr` tokens exist), so the same bot keeps running |

Read-only host checks on 2026-11-01: `zion.service` active since
2026-10-30 19:48 -03, production checkout at `472a4b3`, identity store and
provider store directories `0700`, files `0600`.

## Gates

| Gate | State |
| --- | --- |
| Exact-SHA CI on the candidate | PASS on every pushed commit; record the final SHA's run |
| Local validation (tests, shell, sensitive files, secret scan) | PASS, 988/988 |
| v2-041 delivered answer, local, zero provider calls | Independent review PASS; human review APPROVED 2026-11-01 |
| Production-baseline delivery smoke, `ministral-8b-2512`, 10 cases | Authorized and run 2026-11-01 (four rounds, about USD 0.016). Last round `08a312b`: 6 PASS (3 local), 3 contained by deterministic replies, v2-001 mild embellishment. Every overclaim found was turned into a guard rule. Human review: **APPROVED by the owner 2026-11-01** (`COGNITIVE-V2-HUMAN-REVIEW-2026-11-01.md`) |
| K3 candidate smoke | Optional for this release; Kimi stays inactive |
| Full 108-case benchmark and four 12-turn conversations | NOT RUN; requires the same spend authorization |
| Independent security review of the diff | Guard red-team done in this branch (financial promises, advice, phishing, DM scams, `/summary`/`/translate`); a separate reviewer is still recommended |
| Disposable DB rehearsal at the exact production SHA | PENDING (step 5) |
| Controlled Telegram acceptance | PENDING after cutover (`COGNITIVE-V2-TELEGRAM-ACCEPTANCE.md`) |

## Live smoke (OWNER authorizes spend)

Run from the clean candidate worktree at the exact SHA, one case at a time,
and stop at the first FAIL or REVIEW finding judged fatal:

```bash
cd /home/zetta/.codex/worktrees/zion-cognitive-v2
PY=/home/zetta/.local/share/zion-community-bot/runtimes/current/bin/python
for id in v2-001 v2-021 v2-041 v2-051 v2-061 v2-065 v2-091 v2-094 v2-101 v2-103; do
  PYTHONDONTWRITEBYTECODE=1 "$PY" scripts/evaluate-cognitive-v2-delivery.py \
    --live --model ministral-8b-2512 --case-id "$id" || break
  # review the printed EVIDENCE file before continuing
done
```

Evidence goes to `~/.local/state/zion-community-bot/evaluations/cognitive-v2/`
(`0700`/`0600`). A price older than one day blocks the run: reverify the
official page and update `zion/evaluation_budget.py` first.

## Promotion

1. **OWNER** — merge PR #66 into `zion-v1.1-dev` after its CI passes (authorized 2026-11-01).
2. **OWNER** — open and approve the production PR `zion-v1.1-dev` → `zion-v1`.
   Record the merge SHA as `ZION_DEPLOY_COMMIT` and the current production
   SHA `472a4b3f0ce73a8635d400c0073701013c357b92` as `ZION_PREVIOUS_COMMIT`.
3. While the bot stays online, follow `docs/OPERATIONS.md` "Controlled
   update flow": `scripts/deployment-preflight.sh`,
   `scripts/verify-approved-release.sh` and
   `scripts/prepare-release-runtime.sh` with `ZION_RELEASE_SOURCE=production`
   and the exact SHA. The two `*_PROVEN` variables are set only when
   actually verified.
4. Rehearse against a disposable copy:
   `scripts/rehearse-sqlite-copy.py` at the exact SHA (read-only source,
   private temp directory, metadata output only).
5. **OWNER** — downtime window: stop `zion.service`, fast-forward the local
   `zion-v1-prod` worktree to the exact SHA, run `scripts/apply-zion-v1.sh`
   with `ZION_EXPECTED_COMMIT` and `ZION_PREVIOUS_COMMIT`. It writes
   `rollback-head.txt`, validates, and restarts the service.
6. Health: `systemctl status zion.service`, `/health`, `/status` and `/aistatus` in the
   operator DM. The Control Center "AI & KNOWLEDGE" view must show
   `Active provider: Mistral`, `Kimi activation: BLOCKED` and
   `Accounting: OK`.
7. Run the controlled Telegram acceptance in
   `docs/COGNITIVE-V2-TELEGRAM-ACCEPTANCE.md`. Also check, from a
   non-privileged account, that a phishing restatement through `/translate`
   is replaced by the fixed notice.

## Rollback

Follow "Rollback model" in `docs/DEPLOYMENT-MODEL.md`. Stop at the first
failed acceptance case and do not edit production code during the test.
For this release specifically:

- the rollback SHA is `472a4b3`, recorded in `rollback-head.txt` and the
  verified pre-deploy backup under
  `/home/zetta/.local/share/zion-community-bot/deploy-backups/`;
- stop `zion.service`, return the **local** `zion-v1-prod` worktree to that
  SHA and start the service. `472a4b3` is itself a v1.1 build that reads the
  same protected Mistral store, so the legacy-build step of clearing the
  Mistral secret does not apply;
- the schema stays v4, so no database restore is needed; still verify the
  backup checksum/integrity before deciding that;
- Kimi credentials, if provisioned, stay in the protected store and are
  unused by `472a4b3`;
- never push or rewrite `zion-v1` backward; repeat host + Telegram checks
  and open a forward-fix PR.
