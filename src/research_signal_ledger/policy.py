"""研究方法的單向降權／停用治理。"""

from dataclasses import dataclass
from typing import Protocol


class PolicyOutcome(Protocol):
    net_return_pct: float
    excess_mkt_pct: float | None
    hit: bool | None
    analysis_date: object


class PriorMethodStatus(Protocol):
    state: str
    effective_weight: float
    failure_streak: int


@dataclass(frozen=True)
class PolicyConfig:
    min_sample_size: int = 60
    min_analysis_days: int = 20
    failure_hit_rate: float = 0.5
    degraded_weight_multiplier: float = 0.75
    # 一輪需要足夠的新證據，否則同一批資料每天排程都會被當成新的一輪。
    min_new_analysis_days: int = 5
    failures_to_degrade: int = 2
    failures_to_disable: int = 4


@dataclass(frozen=True)
class MethodStatusDecision:
    state: str
    effective_weight: float
    failure_streak: int
    reason: str
    round_advanced: bool = False


def evaluate_method_status(
    outcomes: list[PolicyOutcome], prior_status: PriorMethodStatus | None, policy: PolicyConfig
) -> MethodStatusDecision:
    sample_size = len(outcomes)
    analysis_days = {str(outcome.analysis_date) for outcome in outcomes}
    prior_state = prior_status.state if prior_status else "observe"
    prior_weight = prior_status.effective_weight if prior_status else 1.0
    prior_streak = prior_status.failure_streak if prior_status else 0
    prior_days = getattr(prior_status, "independent_analysis_days", 0) if prior_status else 0

    if prior_state == "disabled":
        return MethodStatusDecision("disabled", 0.0, prior_streak, "automatic policy cannot reactivate")
    if sample_size < policy.min_sample_size or len(analysis_days) < policy.min_analysis_days:
        return MethodStatusDecision("observe", prior_weight, prior_streak, "insufficient mature evidence")
    if prior_days and len(analysis_days) - prior_days < policy.min_new_analysis_days:
        return MethodStatusDecision(
            prior_state, prior_weight, prior_streak, "not enough new evidence for another round"
        )

    measurable = [outcome for outcome in outcomes if outcome.hit is not None]
    hit_rate = sum(outcome.hit for outcome in measurable) / len(measurable) if measurable else 0.0
    mean_net = sum(outcome.net_return_pct for outcome in outcomes) / sample_size
    excess = [outcome.excess_mkt_pct for outcome in outcomes if outcome.excess_mkt_pct is not None]
    mean_excess = sum(excess) / len(excess) if excess else 0.0
    failed = (mean_net <= 0 and mean_excess <= 0) or hit_rate < policy.failure_hit_rate
    streak = prior_streak + 1 if failed else 0

    if prior_state == "degraded" and streak >= policy.failures_to_disable:
        return MethodStatusDecision(
            "disabled", 0.0, streak, "consecutive failed evaluations after degrade", True
        )
    if prior_state in ("observe", "active") and streak >= policy.failures_to_degrade:
        return MethodStatusDecision(
            "degraded",
            prior_weight * policy.degraded_weight_multiplier,
            streak,
            "two consecutive failed evaluations",
            True,
        )
    return MethodStatusDecision(
        prior_state, prior_weight, streak, "evaluation retained current state", True
    )