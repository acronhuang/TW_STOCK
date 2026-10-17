"""TDD: 委員重播的公告脈絡實驗——只能用截止前可見的公告，沒有脈絡的樣本提示不能變。"""

from datetime import datetime, timedelta

import pytest

from scripts import committee_replay_context as cx
from src.analysis import committee_replay as cr

pytestmark = pytest.mark.unit

CUT = datetime(2026, 9, 1, 20, 0)


def ann(days_before, title="公告標題", body="說明內容", nkey=None, captured=None, hour=10):
    when = (CUT - timedelta(days=days_before)).replace(hour=hour, minute=0)
    return {"available_at": when, "title": title, "body": body, "nkey": nkey or f"k{days_before}{title}", "captured_at": captured or datetime(2026, 10, 17)}


def test_the_cutoff_is_eight_in_the_evening_of_the_analysis_day():
    assert cx.cutoff_for("2026-09-01") == CUT


def test_only_announcements_inside_the_window_and_before_the_cutoff_are_listed():
    rows = [ann(1, "昨天"), ann(29, "二十九天前"), ann(31, "太久以前"), {**ann(0, "當日晚間"), "available_at": CUT + timedelta(minutes=1)}, {**ann(0, "剛好截止"), "available_at": CUT}]
    text, n = cx.build_context(rows, CUT)
    assert n == 3 and "昨天" in text and "二十九天前" in text and "剛好截止" in text
    assert "太久以前" not in text and "當日晚間" not in text


def test_the_window_start_is_exclusive_and_the_cutoff_is_inclusive():
    exactly_30_days = {**ann(0, "正好三十天"), "available_at": CUT - timedelta(days=30)}
    assert cx.build_context([exactly_30_days], CUT) == ("", 0)


def test_newest_first_with_the_count_and_dates_in_the_text():
    text, n = cx.build_context([ann(10, "舊"), ann(2, "新"), ann(5, "中")], CUT)
    lines = text.splitlines()
    assert n == 3 and lines[0].startswith("【近 30 天公告（截至 2026-09-01，共 3 則，列最近 3 則）】")
    assert [l.split(" ", 2)[2][:1] for l in lines[1:]] == ["新", "中", "舊"] and lines[1].startswith("- 2026-08-30 ")


def test_no_announcement_means_no_context_at_all():
    assert cx.build_context([], CUT) == ("", 0)
    assert cx.build_context([ann(40)], CUT) == ("", 0)


def test_at_most_eight_items_are_listed_but_the_total_is_reported():
    text, n = cx.build_context([ann(i, f"第{i}則") for i in range(1, 13)], CUT)
    assert n == 12 and len(text.splitlines()) == 1 + cx.MAX_ITEMS and "共 12 則，列最近 8 則" in text


def test_the_character_budget_cuts_the_list():
    rows = [ann(i, "題" * 80, "文" * 120) for i in range(1, 9)]
    text, n = cx.build_context(rows, CUT, max_chars=450)
    listed = len(text.splitlines()) - 1
    assert n == 8 and 0 < listed < 8 and f"列最近 {listed} 則" in text


def test_long_titles_and_bodies_are_shortened_to_one_line():
    text, _ = cx.build_context([ann(1, "甲\n乙" + "長" * 200, "丙\r\n丁" + "文" * 300)], CUT)
    line = text.splitlines()[1]
    assert "\n" not in line and "甲 乙" in line and "丙 丁" in line and line.count("…") == 2 and len(line) < 230


def test_a_row_without_a_body_lists_only_its_title():
    text, _ = cx.build_context([ann(1, "只有標題", body=None)], CUT)
    assert text.splitlines()[1].endswith("只有標題")


def test_a_correction_never_replaces_the_original_with_a_later_version():
    early = ann(3, "原公告", "原文", nkey="same", captured=datetime(2026, 9, 2))
    later = ann(3, "原公告", "更正後（截止後才知道）", nkey="same", captured=datetime(2026, 10, 17))
    for order in ([early, later], [later, early]):
        text, n = cx.build_context(order, CUT)
        assert n == 1 and "原文" in text and "更正後" not in text


def row(**over):
    base = {"symbol": "2330", "name": "台積電", "advisor": "評級：買進\n" + "a" * 2000, "reports": {"macro-analyst": "M", "technical-analyst": "T" * 400}}
    base.update(over)
    return base


def test_without_context_the_prompt_is_exactly_the_original_replay_prompt():
    r = row()
    assert cx.treatment_prompt(r, "") == cr.build_prompt(r["symbol"], r["name"], r["advisor"], r["reports"])


def test_context_is_appended_after_the_key_data_and_the_rest_is_unchanged():
    r = row()
    base = cr.build_prompt(r["symbol"], r["name"], r["advisor"], r["reports"])
    prompt = cx.treatment_prompt(r, "【近 30 天公告】\n- x")
    assert prompt != base and "【近 30 天公告】\n- x" in prompt
    assert prompt.index("【關鍵數據】") < prompt.index("【近 30 天公告】") < prompt.index("規則：")
    assert prompt.replace("\n\n【近 30 天公告】\n- x", "") == base


def test_missing_reports_or_advisor_do_not_break_the_prompt():
    assert "規則：" in cx.treatment_prompt(row(reports=None, advisor=None), "")


def items(pairs):
    return [{"date": f"2026-08-{i // 2 + 1:02d}", "base": b, "treat": t, "excess": e} for i, (b, t, e) in enumerate(pairs)]


def test_paired_difference_is_the_change_in_spread_and_is_reproducible():
    # 附公告後把會賠的買進改成持有、把會漲的賣出改成買進 → 價差變大
    data = items([("買進", "持有", -0.05), ("買進", "買進", 0.03), ("賣出", "買進", 0.04), ("賣出", "賣出", -0.02)] * 6)
    first = cx.paired_spread_diff(data, iters=500)
    assert first == cx.paired_spread_diff(data, iters=500)
    diff, lo, hi, p = first
    assert diff > 0 and lo <= diff <= hi and 0.5 < p <= 1.0


def test_no_change_in_votes_gives_exactly_zero_difference():
    data = items([("買進", "買進", 0.02), ("賣出", "賣出", -0.01), ("買進", "買進", -0.03), ("賣出", "賣出", 0.01)] * 5)
    diff, lo, hi, _ = cx.paired_spread_diff(data, iters=300)
    assert diff == lo == hi == 0


def test_a_single_date_or_a_missing_side_gives_no_interval():
    one_day = [{"date": "d", "base": "買進", "treat": "買進", "excess": 0.01}, {"date": "d", "base": "賣出", "treat": "賣出", "excess": -0.01}]
    assert cx.paired_spread_diff(one_day) is None
    no_sells = items([("買進", "買進", 0.01)] * 6)
    assert cx.paired_spread_diff(no_sells) is None


def test_the_interval_is_wider_when_the_dates_disagree():
    agree = items([("買進", "買進", 0.02), ("賣出", "賣出", -0.02)] * 10)
    mixed = items([("買進", "買進", 0.02), ("賣出", "買進", 0.02), ("買進", "賣出", -0.05), ("賣出", "賣出", 0.04)] * 5)
    a, m = cx.paired_spread_diff(agree, iters=400), cx.paired_spread_diff(mixed, iters=400)
    assert a is not None and m is not None and a[2] - a[1] == 0 and (m[2] - m[1]) > 0


def test_the_interval_brackets_the_point_estimate_with_real_tails():
    mixed = items([("買進", "買進", 0.02), ("賣出", "買進", 0.02), ("買進", "賣出", -0.05), ("賣出", "賣出", 0.04)] * 5)
    diff, lo, hi, _ = cx.paired_spread_diff(mixed, iters=1000)
    assert lo < diff - 0.001 and hi > diff + 0.001


def test_the_default_window_keeps_the_original_file_names(monkeypatch):
    monkeypatch.setattr(cx, "DAYS", 30)
    assert cx.plan_path("d").name == "ctx_plan.json" and cx.results_path("d").name == "ctx_results.jsonl"


def test_other_windows_use_separate_files_so_runs_never_mix(monkeypatch):
    monkeypatch.setattr(cx, "DAYS", 180)
    assert cx.plan_path("d").name == "ctx_plan_180.json" and cx.results_path("d").name == "ctx_results_180.jsonl"


def test_the_days_option_sets_the_window(monkeypatch):
    monkeypatch.setattr(cx, "DAYS", 30)
    monkeypatch.setattr(cx, "remaining", lambda: 0)
    assert cx.main(["status", "--days", "180"]) == 0 and cx.DAYS == 180
    assert cx.main(["status"]) == 0 and cx.DAYS == 30


def test_a_longer_window_reaches_older_announcements_and_says_so():
    old = ann(100, "一百天前")
    assert cx.build_context([old], CUT) == ("", 0)
    text, n = cx.build_context([old], CUT, days=180)
    assert n == 1 and "近 180 天公告" in text and "一百天前" in text
