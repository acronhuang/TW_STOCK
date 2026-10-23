"""TDD: 買賣計畫審查——每個檢查的邊界、缺資料不猜、輸出不含預測或保證。"""

import pytest

from src.analysis import plan_review as pr

pytestmark = pytest.mark.unit

RISK = {"current_price": 100.0, "position_sizing": {"max_position_pct": 3.9}, "atr": {"n": 2.0, "stop_2n": 96.0}}
CALM = {"close": 100.0, "ma_bias_20": 1.0, "rsi_14": 50.0, "return_1m": 2.0}


def plan(**kw):
    base = {"symbol": "2330", "action": "買進", "entry": 100.0, "stop": 96.0, "shares": 1000, "capital": 1_000_000.0}
    base.update(kw)
    return base


def status(result, item):
    return next(c for c in result["checks"] if c["item"] == item)["status"]


def detail(result, item):
    return next(c for c in result["checks"] if c["item"] == item)["detail"]


# ---- normalize ----
def test_normalize_accepts_aliases_strings_and_lots():
    got, err = pr.normalize({"symbol": "2330", "action": "BUY", "entry": "2,385", "lots": 3, "capital": "1000000"})
    assert err == "" and got == {"symbol": "2330", "action": "買進", "entry": 2385.0, "shares": 3000, "capital": 1_000_000.0}


@pytest.mark.parametrize("args", [
    {"symbol": "23", "action": "買進"}, {"symbol": "../x", "action": "買進"}, {"symbol": "2330", "action": "下單"},
    {"symbol": "2330", "action": "買進", "entry": 0}, {"symbol": "2330", "action": "買進", "entry": "abc"},
    {"symbol": "2330", "action": "買進", "stop": -1}, {"symbol": "2330", "action": "買進", "stop_pct": 100},
    {"symbol": "2330", "action": "買進", "stop": 90, "stop_pct": 5}, {"symbol": "2330", "action": "買進", "shares": 1.5},
    {"symbol": "2330", "action": "買進", "shares": 1000, "lots": 1}, {"symbol": "2330", "action": "買進", "entry": True},
    None, "x",
])
def test_normalize_rejects_bad_input(args):
    got, err = pr.normalize(args)
    assert got is None and err


# ---- 止損 ----
def test_no_stop_is_a_failure_and_names_the_atr_reference():
    result = pr.review({k: v for k, v in plan().items() if k != "stop"}, RISK, CALM, [])
    assert status(result, "止損") == pr.FAIL and "沒有止損" in detail(result, "止損") and "96" in detail(result, "止損")
    assert result["verdict"].startswith(pr.FAIL)


def test_stop_not_below_entry_fails():
    assert status(pr.review(plan(stop=100.0), RISK, CALM, []), "止損") == pr.FAIL
    assert status(pr.review(plan(stop=105.0), RISK, CALM, []), "止損") == pr.FAIL


def test_stop_at_two_n_passes_and_states_the_multiple():
    result = pr.review(plan(stop=96.0), RISK, CALM, [])
    assert status(result, "止損") == pr.PASS and "2 倍 N" in detail(result, "止損")


@pytest.mark.parametrize("stop, expected", [(99.0, pr.WARN), (98.0, pr.PASS), (94.0, pr.PASS), (93.9, pr.WARN)])
def test_stop_distance_boundaries_in_n(stop, expected):  # 距離 1N=2 元、3N=6 元
    assert status(pr.review(plan(stop=stop), RISK, CALM, []), "止損") == expected


def test_stop_without_atr_passes_with_a_note():
    result = pr.review(plan(), {**RISK, "atr": None}, CALM, [])
    assert status(result, "止損") == pr.PASS and "ATR 資料不足" in detail(result, "止損")


def test_stop_pct_is_converted_with_the_entry():
    p = {k: v for k, v in plan().items() if k != "stop"} | {"stop_pct": 4.0}
    assert status(pr.review(p, RISK, CALM, []), "止損") == pr.PASS and "96" in detail(pr.review(p, RISK, CALM, []), "止損")


def test_without_entry_uses_the_current_price():
    p = {k: v for k, v in plan().items() if k != "entry"}
    assert status(pr.review(p, RISK, CALM, []), "止損") == pr.PASS
    assert status(pr.review(p, None, {"close": 100.0, **CALM}, []), "止損") == pr.PASS  # 風險取不到就用因子的收盤價
    assert status(pr.review(p, None, None, []), "止損") == pr.MISSING


# ---- 單筆風險 ----
@pytest.mark.parametrize("shares, stop, expected", [
    (1000, 96.0, pr.PASS),     # 損失 4,000 = 0.4%
    (5000, 96.0, pr.PASS),     # 20,000 = 2%（邊界含）
    (5001, 96.0, pr.WARN),
    (12500, 96.0, pr.WARN),    # 50,000 = 5%（邊界含）
    (12501, 96.0, pr.FAIL),
])
def test_risk_thresholds(shares, stop, expected):
    assert status(pr.review(plan(shares=shares, stop=stop), RISK, CALM, []), "單筆風險") == expected


def test_risk_suggests_lots_for_one_percent():
    assert "約 2 張" in detail(pr.review(plan(shares=10000), RISK, CALM, []), "單筆風險")  # 1% = 10,000 元 ÷ 4 元 = 2,500 股 → 2 張


def test_risk_is_missing_without_capital_or_shares():
    no_capital = {k: v for k, v in plan().items() if k != "capital"}
    no_shares = {k: v for k, v in plan().items() if k != "shares"}
    assert status(pr.review(no_capital, RISK, CALM, []), "單筆風險") == pr.MISSING
    assert "總資金" in detail(pr.review(no_capital, RISK, CALM, []), "單筆風險")
    assert status(pr.review(no_shares, RISK, CALM, []), "單筆風險") == pr.MISSING


# ---- 倉位占比 ----
@pytest.mark.parametrize("shares, expected", [(300, pr.PASS), (390, pr.PASS), (400, pr.WARN), (3000, pr.WARN), (3100, pr.FAIL)])
def test_position_size_thresholds(shares, expected):  # 單檔上限 3.9%、集中度 30%；進場 100 元、資金 100 萬
    assert status(pr.review(plan(shares=shares, stop=96.0), RISK, CALM, []), "倉位占比") == expected


def test_position_size_without_system_cap_only_checks_concentration():
    risk = {**RISK, "position_sizing": {}}
    assert status(pr.review(plan(shares=2000), risk, CALM, []), "倉位占比") == pr.PASS
    assert status(pr.review(plan(shares=4000), risk, CALM, []), "倉位占比") == pr.FAIL


def test_position_size_is_missing_without_inputs():
    assert status(pr.review({k: v for k, v in plan().items() if k != "capital"}, RISK, CALM, []), "倉位占比") == pr.MISSING


# ---- 攤平 ----
HELD = [{"symbol": "2330", "shares": 2000, "avg_cost": 105.0}]


def test_buying_below_average_cost_is_flagged_as_averaging_down():
    result = pr.review(plan(entry=100.0), RISK, CALM, HELD)
    assert status(result, "攤平") == pr.WARN and "向下攤平" in detail(result, "攤平") and "105" in detail(result, "攤平")


def test_buying_above_average_cost_is_not_averaging_down():
    assert status(pr.review(plan(entry=110.0, stop=104.0), RISK, CALM, HELD), "攤平") == pr.PASS


def test_a_new_position_is_not_averaging_down():
    assert status(pr.review(plan(), RISK, CALM, []), "攤平") == pr.PASS
    assert status(pr.review(plan(), RISK, CALM, [{"symbol": "2317", "shares": 1000, "avg_cost": 200.0}]), "攤平") == pr.PASS


def test_average_cost_is_weighted_across_lots():
    held = [{"symbol": "2330", "shares": 1000, "avg_cost": 100.0}, {"symbol": "2330", "shares": 3000, "avg_cost": 120.0}]  # 加權 115
    assert "115" in detail(pr.review(plan(entry=110.0), RISK, CALM, held), "攤平")


def test_average_down_is_missing_when_positions_unavailable():
    assert status(pr.review(plan(), RISK, CALM, None), "攤平") == pr.MISSING


# ---- 追高 ----
@pytest.mark.parametrize("factors, expected", [
    ({"ma_bias_20": 9.0, "rsi_14": 50, "return_1m": 1}, pr.WARN),
    ({"ma_bias_20": 8.9, "rsi_14": 50, "return_1m": 1}, pr.PASS),
    ({"ma_bias_20": 1, "rsi_14": 72.0, "return_1m": 1}, pr.WARN),
    ({"ma_bias_20": 1, "rsi_14": 71.9, "return_1m": 1}, pr.PASS),
    ({"ma_bias_20": 1, "rsi_14": 50, "return_1m": 14.0}, pr.WARN),
    ({"ma_bias_20": 1, "rsi_14": 50, "return_1m": 13.9}, pr.PASS),
])
def test_chase_thresholds(factors, expected):
    assert status(pr.review(plan(), RISK, factors, []), "追高") == expected


def test_chase_lists_every_triggered_signal():
    text = detail(pr.review(plan(), RISK, {"ma_bias_20": 12.0, "rsi_14": 80.0, "return_1m": 20.0}, []), "追高")
    assert "高出 20 日均線 12%" in text and "RSI 80" in text and "近一月已漲 20%" in text


def test_chase_is_missing_without_factor_data():
    assert status(pr.review(plan(), RISK, None, []), "追高") == pr.MISSING
    assert status(pr.review(plan(), RISK, {"close": 100}, []), "追高") == pr.MISSING


# ---- 賣出 ----
def test_selling_something_not_held_fails():
    assert status(pr.review(plan(action="賣出"), RISK, CALM, []), "持倉") == pr.FAIL


def test_selling_more_than_held_fails_and_within_held_passes_with_pnl():
    over = pr.review(plan(action="賣出", shares=3000, entry=110.0), RISK, CALM, HELD)
    ok = pr.review(plan(action="減碼", shares=1000, entry=110.0), RISK, CALM, HELD)
    assert status(over, "持倉") == pr.FAIL and "超過持有數量" in detail(over, "持倉")
    assert status(ok, "持倉") == pr.PASS and "4.76%" in detail(ok, "持倉")  # (110−105)/105


def test_sell_plans_do_not_get_buy_side_checks():
    assert [c["item"] for c in pr.review(plan(action="賣出"), RISK, CALM, HELD)["checks"]] == ["持倉"]


# ---- 結論與輸出 ----
def test_verdict_precedence_and_missing_note():
    assert pr.verdict([{"status": pr.PASS}, {"status": pr.WARN}, {"status": pr.FAIL}]) == pr.FAIL
    assert pr.verdict([{"status": pr.PASS}, {"status": pr.WARN}]) == pr.WARN
    assert pr.verdict([{"status": pr.PASS}]) == pr.PASS
    assert pr.verdict([{"status": pr.PASS}, {"status": pr.MISSING}]) == "通過（另有 1 項資料不足，未能檢查）"


def test_a_clean_plan_passes_overall():
    result = pr.review(plan(shares=300), RISK, CALM, [])
    assert result["verdict"] == pr.PASS


def test_risk_error_payload_is_treated_as_missing_data():
    result = pr.review({k: v for k, v in plan().items() if k != "entry"}, {"symbol": "2330", "error": "價格資料不足"}, None, None)
    assert status(result, "止損") == pr.MISSING


def test_render_has_disclaimer_plan_verdict_and_numbered_items_without_none():
    text = pr.render(pr.review(plan(shares=300), RISK, CALM, HELD))
    lines = text.splitlines()
    assert "不預測漲跌、不保證報酬、不代為下單" in lines[0]
    assert lines[1].startswith("我理解的計畫：2330 買進；進場價 100 元；止損價 96 元；300 股；總資金 1000000 元")
    assert lines[2].startswith("結論：") and lines[3].startswith("1. 止損：") and lines[-1].startswith("5. 追高：")
    assert "None" not in text


def test_the_output_never_promises_or_predicts():
    text = pr.render(pr.review(plan(), RISK, {"ma_bias_20": 30, "rsi_14": 90, "return_1m": 60}, HELD))
    assert not any(word in text for word in ("保證獲利", "一定賺", "會漲", "會跌", "目標價", "買進訊號"))


def test_wrong_typed_inputs_are_treated_as_missing_not_as_empty():
    result = pr.review(plan(), RISK, ["not", "a", "dict"], {"error": "x"})
    assert status(result, "攤平") == pr.MISSING and status(result, "追高") == pr.MISSING


def test_buying_exactly_at_the_average_cost_is_not_averaging_down():
    assert status(pr.review(plan(entry=105.0, stop=101.0), RISK, CALM, HELD), "攤平") == pr.PASS


def test_selling_exactly_the_held_shares_is_allowed():
    assert status(pr.review(plan(action="賣出", shares=2000), RISK, CALM, HELD), "持倉") == pr.PASS


def test_an_error_payload_from_the_risk_api_is_ignored_even_if_it_carries_a_price():
    p = {k: v for k, v in plan().items() if k != "entry"}
    assert status(pr.review(p, {"error": "價格資料不足", "current_price": 100.0}, None, None), "止損") == pr.MISSING


def test_risk_advice_says_so_when_even_one_lot_is_too_much():
    text = detail(pr.review(plan(shares=1000, capital=100_000.0), RISK, CALM, []), "單筆風險")
    assert "連 1 張都超過（可改用零股）" in text and "不足" not in text


def test_a_zero_half_kelly_cap_is_explained_instead_of_saying_exceeds_zero_percent():
    risk = {**RISK, "position_sizing": {"max_position_pct": 0.0}}
    text = detail(pr.review(plan(shares=300), risk, CALM, []), "倉位占比")
    assert status(pr.review(plan(shares=300), risk, CALM, []), "倉位占比") == pr.WARN
    assert "半凱利上限為 0%" in text and "超過系統風控" not in text


# ---- 同價位受阻 ----
def with_resistance(resistance, **kw):
    return pr.review(plan(**kw), RISK, CALM, [], resistance)


@pytest.mark.parametrize("count, expected", [(0, pr.PASS), (2, pr.PASS), (3, pr.WARN), (7, pr.WARN)])
def test_resistance_threshold(count, expected):
    assert status(with_resistance({"failed_touches": count, "window": 30, "zone_high": 105.0}), "同價位受阻") == expected


def test_resistance_warning_names_the_zone_and_admits_the_effect_is_small():
    text = detail(with_resistance({"failed_touches": 3, "window": 30, "zone_high": 105.0}), "同價位受阻")
    assert "105 元附近" in text and "3 次衝高失敗" in text and "小於一次來回交易成本" in text and "不是進出場訊號" in text


@pytest.mark.parametrize("bad", [None, {"error": "價格資料不足"}, {"window": 30}, ["x"], {"failed_touches": "abc"}])
def test_resistance_missing_or_invalid_data_is_missing_not_passed(bad):
    assert status(with_resistance(bad), "同價位受阻") == pr.MISSING


def test_resistance_is_only_checked_when_given_and_only_for_buys():
    assert "同價位受阻" not in [c["item"] for c in pr.review(plan(), RISK, CALM, [])["checks"]]
    assert "同價位受阻" not in [c["item"] for c in pr.review(plan(action="賣出"), RISK, CALM, HELD, {"failed_touches": 5})["checks"]]


def test_a_resistance_warning_alone_makes_the_verdict_a_warning():
    assert with_resistance({"failed_touches": 3, "window": 30}, shares=300)["verdict"] == pr.WARN


def test_the_plan_review_threshold_matches_the_validated_rule():
    from src.analysis import signal_rules

    assert pr.RESIST_BLOCK == signal_rules.PARAMS["resist_block"]
