"""TDD: 委員重播評測的統計與抽樣；提示必須與 live 合議第一輪盲投一致，否則比較沒有意義。"""

import pytest

from src.analysis import committee_replay as cr
from src.moe import consensus

pytestmark = pytest.mark.unit


def test_prompt_is_the_same_text_live_consensus_sends_in_round_one():
    reports = {"technical-analyst": "T" * 400, "macro-analyst": "M", "chip-analyst": ""}
    advisor = "評級：買進\n" + "a" * 2000
    expected = consensus._round1_prompt("2330", "台積電", advisor[:1500], "【總經】M\n【技術】" + "T" * 300)
    assert cr.build_prompt("2330", "台積電", advisor, reports) == expected


def test_data_summary_skips_empty_roles_and_cuts_each_report_at_300_chars():
    text = cr.data_summary({"risk-manager": "R" * 500, "value-analyst": None})
    assert text == "【風險】" + "R" * 300


@pytest.mark.parametrize(
    "votes, draft, expected",
    [
        (["買進", "買進", "賣出"], "持有", "買進"),
        (["買進", "賣出", "持有"], "賣出", "賣出"),
        (["買進", "賣出", "持有"], "買進", "買進"),
        (["買進", "賣出"], "持有", "持有"),
        (["買進", "持有"], "賣出", "持有"),
        (["買進", "賣出"], None, "持有"),
        ([None, None], "買進", "買進"),
        ([None, None], None, "持有"),
        (["買進", None, None], "賣出", "買進"),
    ],
)
def test_final_follows_the_live_tie_rules(votes, draft, expected):
    assert cr.final_from_votes(votes, draft) == expected


def test_final_matches_live_finalize_on_the_same_votes():
    for votes in (["買進", "買進", "賣出"], ["買進", "賣出", "持有"], ["持有", "持有", "賣出"], ["賣出", "賣出", "賣出"]):
        live = consensus._finalize([{"vote": v, "reason": "x" * 20} for v in votes], "評級：持有")[0]
        assert cr.final_from_votes(votes, "持有") == live


def test_sampling_is_deterministic_stratified_by_date_and_sorted():
    pool = [{"date": f"2026-09-{d:02d}", "symbol": f"{s:04d}"} for d in range(1, 11) for s in range(30)]
    a, b = cr.sample_rows(pool, 50, seed=7), cr.sample_rows(pool, 50, seed=7)
    assert a == b and a == sorted(a, key=lambda r: (r["date"], r["symbol"]))
    assert len(a) == 50 and {r["date"] for r in a} == {r["date"] for r in pool}
    assert all(sum(1 for r in a if r["date"] == d) == 5 for d in {r["date"] for r in a})
    assert cr.sample_rows(pool, 50, seed=8) != a


def test_sampling_caps_the_number_of_dates_and_keeps_both_ends():
    pool = [{"date": f"d{i:03d}", "symbol": "1"} for i in range(100)]
    picked = cr.sample_rows(pool, 40, seed=1, max_dates=10)
    dates = [r["date"] for r in picked]
    assert len(set(dates)) == 10 and dates[0] == "d000" and dates[-1] == "d099"


def test_vote_distribution_separates_abstentions_from_valid_votes():
    dist = cr.vote_distribution(["買進", "買進", "賣出", None])
    assert dist["買進"] == pytest.approx(2 / 3) and dist["賣出"] == pytest.approx(1 / 3)
    assert dist["持有"] == 0 and dist["abstain"] == 0.25


def test_outcome_stats_spread_and_hits():
    rows = [
        {"vote": "買進", "excess": 0.10}, {"vote": "買進", "excess": -0.02}, {"vote": "買進", "excess": None},
        {"vote": "賣出", "excess": -0.04}, {"vote": "賣出", "excess": 0.02}, {"vote": "持有", "excess": 0.5},
    ]
    s = cr.outcome_stats(rows)
    assert s["n_buy"] == 2 and s["n_sell"] == 2
    assert s["mean_buy"] == pytest.approx(0.04) and s["mean_sell"] == pytest.approx(-0.01)
    assert s["spread"] == pytest.approx(0.05) and s["hit_buy"] == 0.5 and s["hit_sell"] == 0.5


def test_outcome_stats_without_both_sides_has_no_spread():
    assert cr.outcome_stats([{"vote": "買進", "excess": 0.1}])["spread"] is None
    assert cr.outcome_stats([])["hit_buy"] is None


def test_bootstrap_resamples_dates_not_rows_and_is_reproducible():
    rows = []
    for day in range(12):
        rows += [{"date": f"d{day}", "vote": "買進", "excess": 0.03}] * 5 + [{"date": f"d{day}", "vote": "賣出", "excess": -0.03}] * 5
    low, high = cr.cluster_bootstrap_spread(rows, iters=200, seed=3)
    assert low == pytest.approx(0.06) and high == pytest.approx(0.06)
    assert cr.cluster_bootstrap_spread(rows, iters=200, seed=3) == (low, high)


def test_bootstrap_interval_is_wide_when_days_disagree():
    # 10 天裡 6 天價差 +10pp、4 天 -10pp：每天有很多筆，只有以日為單位重抽才看得出不穩
    rows = []
    for day in range(10):
        sign = 1 if day < 6 else -1
        rows += [{"date": f"d{day}", "vote": "買進", "excess": 0.05 * sign}] * 5
        rows += [{"date": f"d{day}", "vote": "賣出", "excess": -0.05 * sign}] * 5
    low, high = cr.cluster_bootstrap_spread(rows, iters=1000, seed=1)
    assert low < 0 < high and high - low > 0.08


def test_bootstrap_needs_at_least_two_days():
    assert cr.cluster_bootstrap_spread([{"date": "d", "vote": "買進", "excess": 1.0}], iters=10) is None


def test_agreement_uses_only_keys_both_voted_on():
    a = {1: "買進", 2: "賣出", 3: None, 4: "持有"}
    b = {1: "買進", 2: "持有", 3: "賣出", 5: "賣出"}
    same, corr = cr.agreement(a, b)
    assert same == 0.5 and corr is not None


def test_agreement_perfect_and_opposite():
    a = {1: "買進", 2: "賣出", 3: "持有"}
    assert cr.agreement(a, dict(a)) == (1.0, pytest.approx(1.0))
    flipped = {1: "賣出", 2: "買進", 3: "持有"}
    assert cr.agreement(a, flipped)[1] == pytest.approx(-1.0)


def test_agreement_with_no_overlap_or_no_variance():
    assert cr.agreement({1: None}, {1: "買進"}) == (None, None)
    assert cr.agreement({1: "買進", 2: "買進"}, {1: "賣出", 2: "持有"})[1] is None


@pytest.mark.parametrize(
    "response, vote, hollow",
    [
        ("買進\n技術面突破且法人買超，估值偏低。", "買進", False),
        ("賣出\n短", "賣出", True),
        ("持有\n我是投資決策委員會的成員，我將根據提供的資訊獨立判斷後投票。", "持有", True),
        ("不知道", None, False),
        ("ERR:timeout", None, False),
    ],
)
def test_parse_vote_flags_hollow_reasons_like_live(response, vote, hollow):
    got_vote, _, got_hollow = cr.parse_vote(response)
    assert (got_vote, got_hollow) == (vote, hollow)


def test_dir_option_redirects_report_to_another_folder(tmp_path, monkeypatch, capsys):
    import json

    from scripts import committee_replay as script

    for name in ("OUT", "SAMPLES", "RESULTS"):
        monkeypatch.setattr(script, name, getattr(script, name))
    sample = {"date": "2026-01-02", "symbol": "2330", "name": "x", "advisor": "評級：買進", "reports": {},
              "advisor_rating": "買進", "live_votes": {}, "excess": 0.01, "fwd_ret": 0.02}
    (tmp_path / "samples.json").write_text(json.dumps([sample]), encoding="utf-8")
    record = {"model": "zz-model", "date": "2026-01-02", "symbol": "2330", "vote": "買進", "reason": "r", "hollow": False, "ms": 1000}
    (tmp_path / "results.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["committee_replay.py", "--dir", str(tmp_path), "report"])
    script.main()
    assert "zz-model" in capsys.readouterr().out
