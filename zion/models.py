from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OperatingState(str, Enum):
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    ATTACK = "ATTACK"
    LOCKDOWN = "LOCKDOWN"
    DEGRADED_AI = "DEGRADED_AI"
    DEGRADED_NETWORK = "DEGRADED_NETWORK"
    MAINTENANCE = "MAINTENANCE"
    SAFE_MODE = "SAFE_MODE"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionType(str, Enum):
    OBSERVE = "observe"
    WARN = "warn"
    DELETE = "delete"
    MUTE = "mute"
    BAN = "ban"
    ESCALATE = "escalate"
    LOCKDOWN = "lockdown"
    UNLOCK = "unlock"


@dataclass(slots=True)
class FloodDecision:
    triggered: bool = False
    strike_count: int = 0
    mute_seconds: int = 0
    should_ban: bool = False
    message_ids: list[int] = field(default_factory=list)
    incident_id: str | None = None
    reason: str = "flood"
    window_seconds: int = 0


@dataclass(slots=True)
class AbuseDecision:
    detected: bool = False
    category: str = ""
    severity: Severity = Severity.LOW
    rule_id: str = ""
    normalized_hash: str = ""
    directed: bool = False
    reporting_context: bool = False
    should_delete: bool = False
    should_strike: bool = False
    immediate_mute: bool = False


@dataclass(slots=True)
class ChatBurstDecision:
    triggered: bool = False
    message_count: int = 0
    unique_users: int = 0
    window_seconds: int = 0
    elevated_seconds: int = 0


@dataclass(slots=True)
class LinkDecision:
    has_links: bool = False
    domains: list[str] = field(default_factory=list)
    unauthorized_domains: list[str] = field(default_factory=list)
    unsupported_schemes: list[str] = field(default_factory=list)
    should_delete: bool = False
    reason: str = ""


@dataclass(slots=True)
class SensitiveContentDecision:
    detected: bool = False
    kind: str = ""
    reason: str = ""


@dataclass(slots=True)
class AIClassification:
    category: str = "other"
    risk: float = 0.0
    requires_human: bool = False
    rationale: str = ""
    language: str = "unknown"
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AIRouteClassification:
    intent: str = "ambiguous"
    confidence: float = 0.0
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


@dataclass(slots=True)
class AIAnswer:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


@dataclass(slots=True)
class HealthSnapshot:
    state: OperatingState
    db_ok: bool
    telegram_configured: bool
    ai_enabled: bool
    ai_configured: bool
    wifi_interface_present: bool
    disk_free_mb: int
    uptime_seconds: int
    details: dict[str, Any] = field(default_factory=dict)
