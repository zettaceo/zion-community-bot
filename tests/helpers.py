from __future__ import annotations

from pathlib import Path

from zion.config import Settings


def make_settings(root: Path) -> Settings:
    return Settings(
        root_dir=root,
        telegram_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        admin_user_ids=frozenset({1}),
        db_path=root / "zion-test.db",
        legacy_state_path=root / "legacy.json",
        knowledge_dir=root / "knowledge",
        log_path=root / "zion-test.log",
        wifi_interface="test0",
        allow_links=False,
        allowed_domains=frozenset({"z-swap.example"}),
        flood_max_messages=3,
        flood_window_seconds=10,
        flood_purge_window_seconds=300,
        flood_mute_levels=(60, 300, 900),
        flood_strike_reset_seconds=3600,
        flood_ban_after_strikes=4,
        admin_cache_seconds=60,
        report_retention_days=90,
        knowledge_gap_retention_days=30,
        raid_max_joins=8,
        raid_window_seconds=60,
        raid_elevated_seconds=900,
        ai_enabled=False,
        ai_observe=False,
        ai_min_observe_chars=16,
        ai_user_requests_per_minute=4,
        ai_max_concurrency=2,
        ai_daily_token_budget=50000,
        ai_circuit_failures=3,
        ai_circuit_seconds=120,
        mistral_api_key="",
        mistral_api_url="https://api.mistral.ai/v1/chat/completions",
        mistral_model="mistral-small-latest",
        mistral_timeout_seconds=30.0,
        mistral_max_tokens=700,
    )
