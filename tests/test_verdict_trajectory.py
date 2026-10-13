"""TDD: 合議軌跡評估——缺角色、角色失敗、票數不足、空洞投票都要被抓到，正常的紀錄不能被誤報。"""

import pytest

from src.analysis import verdict_trajectory as vt

pytestmark = pytest.mark.unit


def healthy(symbol="2330", votes=3, rounds=1):
    return {"symbol": symbol,
            "reports": {role: f"{role} 的意見" for role in vt.EXPECTED_ROLES},
            "consensus": {"n": votes, "rounds_run": rounds, "dissent": [], "final_source": "facilitator"},
            "shadow_lint": {"flags": []}}


def test_a_healthy_record_has_no_violations():
    run = vt.trajectory(healthy())

    assert run["violations"] == [] and run["role_hit_rate"] == 1.0 and run["votes"] == 3


def test_a_missing_role_lowers_the_hit_rate_and_is_named():
    doc = healthy()
    del doc["reports"]["chip-analyst"]

    run = vt.trajectory(doc)

    assert run["missing_roles"] == ["chip-analyst"] and run["role_hit_rate"] == pytest.approx(5 / 6)
    assert any("缺角色" in v for v in run["violations"])


def test_a_role_whose_report_is_an_error_string_or_empty_counts_as_failed_not_as_present_and_fine():
    doc = healthy()
    doc["reports"]["value-analyst"] = "分析失敗: timeout"
    doc["reports"]["macro-analyst"] = "   "

    run = vt.trajectory(doc)

    assert run["failed_roles"] == ["macro-analyst", "value-analyst"]
    assert any("角色失敗" in v for v in run["violations"])


def test_fewer_votes_than_expected_is_a_violation_but_a_record_without_consensus_is_not_judged_on_votes():
    assert any("票數" in v for v in vt.trajectory(healthy(votes=2))["violations"])

    no_consensus = healthy()
    no_consensus["consensus"] = {}
    run = vt.trajectory(no_consensus)
    assert run["has_consensus"] is False and run["violations"] == []


def test_a_hollow_vote_flag_from_the_shadow_lint_is_counted():
    doc = healthy()
    doc["shadow_lint"]["flags"] = ["合議壞票×1:llama3.1:8b", "風報比<1(0.8)"]

    run = vt.trajectory(doc)

    assert run["hollow_votes"] == 1 and any("空洞投票" in v for v in run["violations"])


def test_the_summary_counts_each_kind_and_lists_only_the_violating_records():
    bad = healthy("2317", votes=2, rounds=2)
    bad["reports"]["risk-manager"] = "分析失敗: x"
    docs = [healthy("2330"), healthy("2454", rounds=2), bad]

    summary = vt.summarize(docs)

    assert summary["records"] == 3 and summary["records_with_failed_role"] == 1 and summary["vote_shortfall"] == 1
    assert summary["two_round_share"] == pytest.approx(2 / 3)
    assert [r["symbol"] for r in summary["violating"]] == ["2317"]


def test_an_empty_input_gives_no_rates_rather_than_a_fake_perfect_score():
    summary = vt.summarize([])

    assert summary["records"] == 0 and summary["role_hit_rate"] is None and summary["two_round_share"] is None
