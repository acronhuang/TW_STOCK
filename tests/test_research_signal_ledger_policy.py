"""TDD: 方法治理只允許維持、降權與停用。"""

from dataclasses import dataclass

import pytest

from src.research_signal_ledger.policy import PolicyConfig, evaluate_method_status


@dataclass(frozen=True)
class Outcome:
    net_return_pct: float
    excess_mkt_pct: float
    hit: bool
    analysis_date: str


@dataclass(frozen=True)
class PriorStatus:
    state: str
    effective_weight: float
    failure_streak: int


POLICY = PolicyConfig()


def make_outcomes(count, days, net_return=1.0, excess=1.0, hit=True):
    return [Outcome(net_return, excess, hit, f"2026-09-{index % days + 1:02d}") for index in range(count)]


def test_policy_stays_observe_until_sample_and_day_minimums_are_met():
    decision = evaluate_method_status(make_outcomes(59, 20), prior_status=None, policy=POLICY)

    assert decision.state == "observe"
    assert decision.effective_weight == 1.0


def test_two_consecutive_failures_only_degrade_weight():
    prior = PriorStatus("active", 1.0, 1)
    decision = evaluate_method_status(
        make_outcomes(60, 20, net_return=-1.0, excess=-1.0, hit=False), prior, POLICY
    )

    assert decision.state == "degraded"
    assert decision.effective_weight == 0.75
    assert decision.failure_streak == 2


def test_automatic_policy_never_reenables_or_increases_weight():
    prior = PriorStatus("disabled", 0.0, 4)
    decision = evaluate_method_status(make_outcomes(80, 30), prior, POLICY)

    assert decision.state == "disabled"
    assert decision.effective_weight == 0.0


@dataclass(frozen=True)
class TrackedPrior:
    state: str
    effective_weight: float
    failure_streak: int
    independent_analysis_days: int


def failing(days):
    return make_outcomes(days * 3, days, net_return=-1.0, excess=-1.0, hit=False)


def test_observe_with_enough_evidence_degrades_after_two_failed_rounds():
    first = evaluate_method_status(failing(20), TrackedPrior("observe", 1.0, 0, 0), POLICY)
    second = evaluate_method_status(failing(30), TrackedPrior("observe", 1.0, first.failure_streak, 20), POLICY)

    assert (first.state, first.failure_streak) == ("observe", 1)
    assert (second.state, second.effective_weight, second.failure_streak) == ("degraded", 0.75, 2)


def test_good_evidence_never_promotes_observe_to_active():
    decision = evaluate_method_status(make_outcomes(90, 30), TrackedPrior("observe", 1.0, 0, 0), POLICY)

    assert decision.state == "observe"
    assert decision.effective_weight == 1.0


def test_degraded_needs_two_more_failed_rounds_before_disabling():
    after_one_more = evaluate_method_status(failing(30), TrackedPrior("degraded", 0.75, 2, 25), POLICY)
    after_two_more = evaluate_method_status(failing(40), TrackedPrior("degraded", 0.75, 3, 30), POLICY)

    assert (after_one_more.state, after_one_more.failure_streak) == ("degraded", 3)
    assert (after_two_more.state, after_two_more.effective_weight) == ("disabled", 0.0)


def test_the_same_evidence_does_not_count_as_a_new_round():
    prior = TrackedPrior("observe", 1.0, 1, 20)

    decision = evaluate_method_status(failing(22), prior, POLICY)

    assert decision.failure_streak == 1
    assert decision.state == "observe"
    assert decision.round_advanced is False


def test_enough_new_analysis_days_start_a_new_round():
    prior = TrackedPrior("observe", 1.0, 1, 20)

    decision = evaluate_method_status(failing(25), prior, POLICY)

    assert decision.failure_streak == 2
    assert decision.round_advanced is True