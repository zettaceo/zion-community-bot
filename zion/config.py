from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import idna
from dotenv import load_dotenv


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    raise ValueError(
        f"invalid boolean for {name}; use true/false, yes/no, on/off or 1/0"
    )


def _int(name: str, default: int, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    value = default if raw in (None, "") else int(raw)
    if minimum is not None and value < minimum:
        return minimum
    return value


def _float(name: str, default: float, minimum: float | None = None) -> float:
    raw = os.getenv(name)
    value = default if raw in (None, "") else float(raw)
    if minimum is not None and value < minimum:
        return minimum
    return value


def _csv(name: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in os.getenv(name, "").split(",")
        if item.strip()
    )


def _domain_set(name: str) -> frozenset[str]:
    result: set[str] = set()
    for item in _csv(name):
        raw = item.strip().lower().strip(".")
        if not raw or any(char in raw for char in "/:@"):
            continue
        try:
            normalized = idna.encode(
                raw,
                uts46=True,
                transitional=False,
            ).decode("ascii").lower()
        except idna.IDNAError:
            continue
        if normalized:
            result.add(normalized)
    return frozenset(result)


def _int_set(name: str) -> frozenset[int]:
    result: set[int] = set()
    for item in _csv(name):
        try:
            value = int(item)
        except ValueError:
            continue
        if value > 0:
            result.add(value)
    return frozenset(result)


@dataclass(frozen=True, slots=True)
class Settings:
    root_dir: Path
    telegram_token: str
    admin_user_ids: frozenset[int]

    db_path: Path
    legacy_state_path: Path
    knowledge_dir: Path
    log_path: Path
    log_max_bytes: int
    log_backup_count: int
    runtime_lock_path: Path
    wifi_interface: str

    allow_links: bool
    allowed_domains: frozenset[str]

    flood_max_messages: int
    flood_window_seconds: int
    flood_purge_window_seconds: int
    flood_mute_levels: tuple[int, ...]
    flood_strike_reset_seconds: int
    flood_ban_after_strikes: int

    admin_cache_seconds: int
    report_retention_days: int
    report_requests_per_minute: int
    ama_requests_per_minute: int
    user_event_retention_days: int
    idempotency_retention_days: int
    knowledge_gap_retention_days: int
    ai_event_retention_days: int
    completed_job_retention_days: int

    raid_max_joins: int
    raid_window_seconds: int
    raid_elevated_seconds: int

    chat_burst_max_messages: int
    chat_burst_window_seconds: int
    chat_burst_min_users: int
    chat_burst_elevated_seconds: int

    disk_warn_mb: int
    db_warn_mb: int
    wal_warn_mb: int
    update_lag_warn_seconds: int
    health_check_interval_seconds: int
    health_alert_repeat_seconds: int
    schedule_max_attempts: int
    schedule_retry_seconds: int
    delivery_claim_timeout_seconds: int
    recurring_max_failures: int
    ama_retention_days: int

    ai_enabled: bool
    ai_observe: bool
    ai_min_observe_chars: int
    ai_user_requests_per_minute: int
    ai_max_concurrency: int
    ai_daily_token_budget: int
    ai_circuit_failures: int
    ai_circuit_seconds: int

    mistral_api_key: str
    mistral_api_url: str
    mistral_model: str
    mistral_timeout_seconds: float
    mistral_max_tokens: int

    def configuration_issues(self) -> tuple[str, ...]:
        issues: list[str] = []

        if not self.admin_user_ids:
            issues.append("operator_allowlist_empty")
        if self.ai_enabled and not self.mistral_api_key:
            issues.append("ai_enabled_without_key")
        if self.ai_observe and not self.ai_enabled:
            issues.append("ai_observe_without_ai")
        if not self.wifi_interface:
            issues.append("wifi_interface_empty")

        try:
            lock_path = self.runtime_lock_path.resolve(strict=False)
            root_path = self.root_dir.resolve(strict=False)
            lock_path.relative_to(root_path)
        except ValueError:
            pass
        else:
            issues.append("runtime_lock_inside_worktree")

        return tuple(issues)

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(__file__).resolve().parent.parent
        load_dotenv(root / ".env")

        mute_levels: list[int] = []
        for item in _csv("FLOOD_MUTE_LEVELS") or ("60", "300", "900", "3600"):
            try:
                value = int(item)
            except ValueError:
                continue
            if value > 0:
                mute_levels.append(value)

        allowed_domains = _domain_set("ALLOWED_DOMAINS")

        return cls(
            root_dir=root,
            telegram_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
            admin_user_ids=_int_set("ZION_ADMIN_USER_IDS"),
            db_path=Path(
                os.getenv("ZION_DB_PATH", str(root / "zion.db"))
            ).expanduser(),
            legacy_state_path=Path(
                os.getenv(
                    "ZION_STATE_FILE",
                    str(root / "zion_state.json"),
                )
            ).expanduser(),
            knowledge_dir=Path(
                os.getenv(
                    "ZION_KNOWLEDGE_DIR",
                    str(root / "knowledge"),
                )
            ).expanduser(),
            log_path=Path(
                os.getenv("ZION_LOG_PATH", str(root / "zion.log"))
            ).expanduser(),
            log_max_bytes=_int(
                "ZION_LOG_MAX_BYTES",
                5 * 1024 * 1024,
                1024 * 1024,
            ),
            log_backup_count=_int(
                "ZION_LOG_BACKUP_COUNT",
                5,
                1,
            ),
            runtime_lock_path=Path(
                os.getenv(
                    "ZION_RUNTIME_LOCK_PATH",
                    str(
                        Path.home()
                        / ".local"
                        / "state"
                        / "zion-community-bot"
                        / "runtime.lock"
                    ),
                )
            ).expanduser(),
            wifi_interface=os.getenv(
                "ZION_WIFI_INTERFACE",
                "wlx78bdbc575d1c",
            ).strip(),
            allow_links=_bool("ALLOW_LINKS", False),
            allowed_domains=allowed_domains,
            flood_max_messages=_int("FLOOD_MAX_MESSAGES", 6, 2),
            flood_window_seconds=_int("FLOOD_WINDOW_SECONDS", 10, 2),
            flood_purge_window_seconds=_int(
                "FLOOD_PURGE_WINDOW_SECONDS",
                300,
                10,
            ),
            flood_mute_levels=tuple(mute_levels) or (60,),
            flood_strike_reset_seconds=_int(
                "FLOOD_STRIKE_RESET_SECONDS",
                3600,
                60,
            ),
            flood_ban_after_strikes=_int(
                "FLOOD_BAN_AFTER_STRIKES",
                4,
                0,
            ),
            admin_cache_seconds=_int("ADMIN_CACHE_SECONDS", 60, 5),
            report_retention_days=_int("ZION_REPORT_RETENTION_DAYS", 90, 1),
            report_requests_per_minute=_int(
                "ZION_REPORT_REQUESTS_PER_MINUTE",
                3,
                1,
            ),
            ama_requests_per_minute=_int(
                "ZION_AMA_REQUESTS_PER_MINUTE",
                5,
                1,
            ),
            user_event_retention_days=_int(
                "ZION_USER_EVENT_RETENTION_DAYS",
                30,
                1,
            ),
            idempotency_retention_days=_int(
                "ZION_IDEMPOTENCY_RETENTION_DAYS",
                30,
                1,
            ),
            knowledge_gap_retention_days=_int(
                "ZION_KNOWLEDGE_GAP_RETENTION_DAYS",
                30,
                1,
            ),
            ai_event_retention_days=_int(
                "ZION_AI_EVENT_RETENTION_DAYS",
                90,
                1,
            ),
            completed_job_retention_days=_int(
                "ZION_COMPLETED_JOB_RETENTION_DAYS",
                30,
                1,
            ),
            raid_max_joins=_int("ZION_RAID_MAX_JOINS", 8, 2),
            raid_window_seconds=_int("ZION_RAID_WINDOW_SECONDS", 60, 10),
            raid_elevated_seconds=_int("ZION_RAID_ELEVATED_SECONDS", 900, 60),
            chat_burst_max_messages=_int(
                "ZION_CHAT_BURST_MAX_MESSAGES",
                45,
                10,
            ),
            chat_burst_window_seconds=_int(
                "ZION_CHAT_BURST_WINDOW_SECONDS",
                15,
                5,
            ),
            chat_burst_min_users=_int(
                "ZION_CHAT_BURST_MIN_USERS",
                6,
                2,
            ),
            chat_burst_elevated_seconds=_int(
                "ZION_CHAT_BURST_ELEVATED_SECONDS",
                600,
                60,
            ),
            disk_warn_mb=_int("ZION_DISK_WARN_MB", 2048, 128),
            db_warn_mb=_int("ZION_DB_WARN_MB", 512, 16),
            wal_warn_mb=_int("ZION_WAL_WARN_MB", 128, 8),
            update_lag_warn_seconds=_int(
                "ZION_UPDATE_LAG_WARN_SECONDS",
                120,
                10,
            ),
            health_check_interval_seconds=_int(
                "ZION_HEALTH_CHECK_INTERVAL_SECONDS",
                60,
                20,
            ),
            health_alert_repeat_seconds=_int(
                "ZION_HEALTH_ALERT_REPEAT_SECONDS",
                21600,
                3600,
            ),
            schedule_max_attempts=_int(
                "ZION_SCHEDULE_MAX_ATTEMPTS",
                5,
                1,
            ),
            schedule_retry_seconds=_int(
                "ZION_SCHEDULE_RETRY_SECONDS",
                60,
                10,
            ),
            delivery_claim_timeout_seconds=_int(
                "ZION_DELIVERY_CLAIM_TIMEOUT_SECONDS",
                300,
                30,
            ),
            recurring_max_failures=_int(
                "ZION_RECURRING_MAX_FAILURES",
                10,
                1,
            ),
            ama_retention_days=_int(
                "ZION_AMA_RETENTION_DAYS",
                30,
                1,
            ),
            ai_enabled=_bool("ZION_AI_ENABLED", False),
            ai_observe=_bool("ZION_AI_OBSERVE", False),
            ai_min_observe_chars=_int("ZION_AI_MIN_OBSERVE_CHARS", 16, 1),
            ai_user_requests_per_minute=_int(
                "ZION_AI_REQUESTS_PER_MINUTE",
                4,
                1,
            ),
            ai_max_concurrency=_int("ZION_AI_MAX_CONCURRENCY", 2, 1),
            ai_daily_token_budget=_int(
                "ZION_AI_DAILY_TOKEN_BUDGET",
                50000,
                0,
            ),
            ai_circuit_failures=_int(
                "ZION_AI_CIRCUIT_FAILURES",
                3,
                1,
            ),
            ai_circuit_seconds=_int(
                "ZION_AI_CIRCUIT_SECONDS",
                120,
                10,
            ),
            mistral_api_key=os.getenv("MISTRAL_API_KEY", "").strip(),
            mistral_api_url=os.getenv(
                "MISTRAL_API_URL",
                "https://api.mistral.ai/v1/chat/completions",
            ).strip(),
            mistral_model=os.getenv(
                "MISTRAL_MODEL",
                "mistral-small-latest",
            ).strip(),
            mistral_timeout_seconds=_float(
                "MISTRAL_TIMEOUT_SECONDS",
                30.0,
                3.0,
            ),
            mistral_max_tokens=_int("MISTRAL_MAX_TOKENS", 700, 64),
        )
