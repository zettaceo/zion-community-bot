from __future__ import annotations

from dataclasses import dataclass

from .agents import AgentProfile, DMPolicy


@dataclass(frozen=True, slots=True)
class DMAccessDecision:
    allowed: bool
    reason: str


def evaluate_dm_access(
    profile: AgentProfile,
    *,
    user_id: int,
    admin_user_ids: frozenset[int],
) -> DMAccessDecision:
    """Apply the identity DM boundary before AI, retrieval, or sessions."""

    if profile.dm_policy is DMPolicy.PUBLIC:
        return DMAccessDecision(allowed=True, reason="public_dm")
    if profile.dm_policy is DMPolicy.CLOSED:
        return DMAccessDecision(allowed=False, reason="dm_closed")
    if profile.dm_policy is DMPolicy.CREATOR_ONLY:
        if user_id in admin_user_ids:
            return DMAccessDecision(allowed=True, reason="authorized_creator")
        return DMAccessDecision(
            allowed=False,
            reason="creator_authorization_required",
        )
    return DMAccessDecision(allowed=False, reason="unknown_dm_policy")
