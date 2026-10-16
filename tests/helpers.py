from __future__ import annotations

import json
from pathlib import Path

from zion.config import Settings


def write_test_knowledge_manifest(
    root: Path,
    files: tuple[str, ...] = ("official.md", "orders.md"),
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "sources": [
            {
                "file": filename,
                "classification": "PUBLIC",
                "status": "CURRENT",
                "version": "test-v1",
                "source_identity": "test-fixture",
                "allowed_agents": ["zion", "mimir", "eir", "freyr"],
            }
            for filename in files
        ],
    }
    (root / "MANIFEST.md").write_text(
        "# Test manifest\n\n```json\n"
        + json.dumps(payload)
        + "\n```\n",
        encoding="utf-8",
    )


def make_settings(root: Path) -> Settings:
    write_test_knowledge_manifest(root / "knowledge")
    return Settings(
        root_dir=root,
        telegram_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        admin_user_ids=frozenset({1}),
        db_path=root / "zion-test.db",
        legacy_state_path=root / "legacy.json",
        knowledge_dir=root / "knowledge",
        log_path=root / "zion-test.log",
        log_max_bytes=1024 * 1024,
        log_backup_count=3,
        runtime_lock_path=(
            root.parent / f"{root.name}-state" / "runtime.lock"
        ),
        wifi_interface="test0",
        allow_links=False,
        allowed_domains=frozenset({"z-swap.example"}),
        flood_max_messages=3,
        flood_window_seconds=10,
        flood_sustained_max_messages=10,
        flood_sustained_window_seconds=120,
        flood_purge_window_seconds=300,
        flood_mute_levels=(60, 300, 900),
        flood_strike_reset_seconds=3600,
        flood_ban_after_strikes=4,
        admin_cache_seconds=60,
        report_retention_days=90,
        report_requests_per_minute=3,
        ama_requests_per_minute=5,
        user_event_retention_days=30,
        idempotency_retention_days=30,
        knowledge_gap_retention_days=30,
        ai_event_retention_days=90,
        completed_job_retention_days=30,
        raid_max_joins=8,
        raid_window_seconds=60,
        raid_elevated_seconds=900,
        chat_burst_max_messages=12,
        chat_burst_window_seconds=10,
        chat_burst_min_users=4,
        chat_burst_elevated_seconds=600,
        disk_warn_mb=128,
        db_warn_mb=512,
        wal_warn_mb=128,
        update_lag_warn_seconds=120,
        health_check_interval_seconds=60,
        health_alert_repeat_seconds=21600,
        schedule_max_attempts=5,
        schedule_retry_seconds=60,
        delivery_claim_timeout_seconds=300,
        recurring_max_failures=10,
        ama_retention_days=30,
        ai_enabled=False,
        ai_observe=False,
        ai_min_observe_chars=16,
        ai_user_requests_per_minute=4,
        ai_max_concurrency=3,
        ai_daily_token_budget=50000,
        ai_circuit_failures=3,
        ai_circuit_seconds=120,
        telegram_identity_secret_dir=(
            root.parent
            / f"{root.name}-state"
            / "secrets"
            / "telegram-identities"
        ),
        mistral_secret_path=(
            root.parent
            / f"{root.name}-state"
            / "secrets"
            / "mistral-api-key"
        ),
        legacy_mistral_api_key_present=False,
        mistral_api_url="https://api.mistral.ai/v1/chat/completions",
        mistral_model="ministral-8b-2512",
        mistral_timeout_seconds=30.0,
        mistral_max_tokens=700,
        mistral_min_request_interval_ms=350,
        mistral_rate_limit_retries=2,
        mistral_rate_limit_max_delay_seconds=5.0,
    )
