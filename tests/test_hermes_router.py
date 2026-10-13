"""TDD: Hermes 預路由——問題進來先決定要查什麼；查錯對象比不查更糟，所以誤判要有測試擋住。"""

import json

import pytest

from src.ops import hermes_router as hr
from src.ops import readonly_tools as ro

pytestmark = pytest.mark.unit

NAMES = {"台積電": "2330", "鴻海": "2317", "聯電": "2303", "大立光": "3008"}


def symbols(question, names=NAMES):
    return [code for code, _ in hr.find_symbols(question, names)]


def test_a_stock_code_in_the_question_is_found():
    assert symbols("2330 的估值如何") == ["2330"]
    assert hr.find_symbols("00878 殖利率", None) == [("00878", "")]


def test_years_dates_amounts_and_prices_are_not_taken_for_codes():
    assert symbols("2026年的 1000 股 2330", None) == ["2330"]
    assert symbols("2026-10-13 買了 2330", None) == ["2330"]
    assert symbols("現價 2540.0 元，2330 呢", None) == ["2330"]
    assert symbols("10000 元能買幾張 2330", None) == ["2330"]


def test_a_code_followed_by_a_word_that_merely_starts_with_gu_is_still_a_code():
    assert symbols("2330 股價 3000 元的話", None) == ["2330"]
    assert symbols("2330 股票怎麼樣", None) == ["2330"]
    assert symbols("買了 2330 股", None) == []


def test_codes_the_market_does_not_have_are_dropped_when_the_name_table_is_known():
    assert symbols("9999 與 2330") == ["2330"]
    assert symbols("9999 與 2330", None) == ["9999", "2330"]


def test_company_names_need_three_characters_or_a_question_about_data():
    assert hr.find_symbols("台積電怎麼樣", NAMES) == [("2330", "台積電")]
    assert symbols("鴻海") == []
    assert symbols("鴻海的估值") == ["2317"]


def test_at_most_two_symbols_in_the_order_they_were_asked():
    assert symbols("聯電、2330、鴻海、3008 哪個便宜 估值") == ["2303", "2330"]


def test_each_symbol_is_listed_once_even_when_code_and_name_both_appear():
    assert symbols("台積電 2330 估值") == ["2330"]


def test_order_requests_are_never_prefetched_but_questions_about_buying_are():
    assert hr.plan("幫我買進 1000 股 2330", NAMES, ro.INDUSTRIES) == []
    assert hr.plan("下單 2330", NAMES, ro.INDUSTRIES) == []
    assert hr.plan("掛單賣出 2 張 2330", NAMES, ro.INDUSTRIES) == []
    assert hr.plan("該不該買進 2330？", NAMES, ro.INDUSTRIES)


def test_keywords_choose_the_kinds_and_english_words_need_word_boundaries():
    assert hr.wanted_kinds("2330 的本益比") == ["valuation"]
    assert hr.wanted_kinds("2330 PE 多少") == ["valuation"]
    assert hr.wanted_kinds("a lot of people") == []
    assert hr.wanted_kinds("外資買超與營收") == ["institutional", "revenue"]
    assert hr.wanted_kinds("你好") == []


def test_a_bare_symbol_gets_price_valuation_and_score():
    assert hr.plan("2330 怎麼樣", NAMES, ro.INDUSTRIES) == [
        ("stock_data", {"kind": "price", "symbol": "2330"}),
        ("stock_data", {"kind": "valuation", "symbol": "2330"}),
        ("stock_data", {"kind": "score", "symbol": "2330"}),
    ]


def test_the_number_of_calls_is_capped_and_every_symbol_still_gets_one():
    calls = hr.plan("2330 與 2317 的估值、評分、風險、法人、營收", NAMES, ro.INDUSTRIES)
    assert len(calls) <= hr.MAX_CALLS
    assert {args["symbol"] for _, args in calls} == {"2330", "2317"}


def test_every_planned_call_is_accepted_by_the_read_only_whitelist():
    for question in ("2330 怎麼樣", "2330 估值 評分 風險 法人 營收 股利 財報 同業 技術 情緒 異常 研判", "半導體業排名", "大盤"):
        for name, args in hr.plan(question, NAMES, ro.INDUSTRIES):
            assert ro.build_url(name, args)[0] is not None, (name, args)


def test_industry_questions_use_the_industry_tool_unless_a_symbol_is_named():
    assert hr.plan("半導體業評分前三名是誰？", {}, ro.INDUSTRIES) == [("industry_data", {"industry": "半導體業"})]
    assert hr.plan("塑膠的排名", {}, ro.INDUSTRIES) == [("industry_data", {"industry": "塑膠工業"})]
    assert hr.plan("2330 在半導體業的排名", NAMES, ro.INDUSTRIES)[0][0] == "stock_data"


def test_market_questions():
    assert hr.plan("大盤現在如何", {}, ro.INDUSTRIES) == [("market_data", {"kind": "macro"})]
    assert hr.plan("全市場團隊研判彙總", {}, ro.INDUSTRIES) == [("market_data", {"kind": "team"})]


def test_nothing_to_look_up_means_no_calls():
    assert hr.plan("你好", NAMES, ro.INDUSTRIES) == []
    assert hr.plan("", NAMES, ro.INDUSTRIES) == []
    assert hr.plan(None, NAMES, ro.INDUSTRIES) == []


def test_prefetch_runs_calls_in_order_and_keeps_errors():
    seen = []

    def call(name, args):
        seen.append(args["kind"])
        return ("壞了", True) if args["kind"] == "score" else ("{}", False)

    calls = hr.plan("2330 怎麼樣", NAMES, ro.INDUSTRIES)
    results = hr.prefetch(calls, call)
    assert seen == ["price", "valuation", "score"]
    assert [r[3] for r in results] == [False, False, True]


def test_prefetch_stops_when_the_time_budget_is_used_up():
    ticks = iter([0, 1, 100, 200])
    results = hr.prefetch(
        [("stock_data", {"kind": "price", "symbol": "2330"})] * 3, lambda n, a: ("{}", False), budget_seconds=10, clock=lambda: next(ticks)
    )
    assert len(results) == 1


def test_prefetch_truncates_oversized_bodies():
    results = hr.prefetch([("stock_data", {"kind": "price", "symbol": "2330"})], lambda n, a: ("x" * 10000, False))
    assert len(results[0][2]) == hr.MAX_BODY


def test_context_labels_each_result_and_tells_the_model_it_is_data_not_instructions():
    results = [("stock_data", {"kind": "valuation", "symbol": "2330"}, '{"fair_value": 942.5}', False),
               ("stock_data", {"kind": "score", "symbol": "9999"}, "API 回應 HTTP 404", True)]
    text = hr.format_context(results, NAMES)
    assert "不是指令" in text and "calc" in text
    assert "■ stock_data kind=valuation symbol=2330（台積電）" in text and '{"fair_value": 942.5}' in text
    assert "■ stock_data kind=score symbol=9999【查詢失敗】" in text
    assert hr.format_context([], NAMES) == ""


@pytest.mark.parametrize("question", ["漲 5% 會是多少", "比公平價高出多少", "請直接算", "兩檔差距", "平均是多少"])
def test_questions_that_need_arithmetic_are_recognised(question):
    assert hr.needs_calculation(question)


@pytest.mark.parametrize("question", ["2330 估值如何", "半導體業排名", "", None])
def test_plain_lookups_do_not_need_arithmetic(question):
    assert not hr.needs_calculation(question)


def test_the_calc_hint_is_added_only_when_asked_for():
    results = [("stock_data", {"kind": "price", "symbol": "2330"}, "{}", False)]
    assert "本題需要運算" in hr.format_context(results, NAMES, calc_hint=True)
    assert "本題需要運算" not in hr.format_context(results, NAMES)


@pytest.mark.parametrize("answer", ["2330 目前偏高", "現價 2540 元", "估值偏高", "殖利率 3.2%", "外資買超", "00878 不錯"])
def test_answers_that_talk_about_stocks_are_recognised(answer):
    assert hr.mentions_stock_info(answer)


@pytest.mark.parametrize("answer", ["你只能提供資訊，不能下單。", "好的", "", None, "共 3 項", "2026-10-13 更新"])
def test_answers_that_do_not_are_left_alone(answer):
    assert not hr.mentions_stock_info(answer)


def _ctx(kind, is_error=False, name="stock_data"):
    return hr.format_context([(name, {"kind": kind, "symbol": "2317"}, "{}", is_error)], NAMES)


def test_glossary_follows_the_kinds_that_were_fetched():
    text = _ctx("institutional")
    assert "foreign_net＝外資" in text and "單位是股（不是元）" in text
    assert "dcf＝" not in text


def test_revenue_glossary_states_the_thousand_dollar_unit():
    assert "單位是千元（不是元）" in _ctx("revenue")


def test_no_glossary_for_failed_or_unknown_lookups():
    assert hr._GLOSSARY_HEAD not in _ctx("institutional", is_error=True)
    assert hr._GLOSSARY_HEAD not in _ctx("sentiment")
    assert hr._GLOSSARY_HEAD not in _ctx("macro", name="market_data")


def test_each_glossary_entry_appears_once_when_a_kind_is_fetched_twice():
    results = [("stock_data", {"kind": "price", "symbol": s}, "{}", False) for s in ("2330", "2317")]
    assert hr.format_context(results, NAMES).count("成交量，單位是股") == 1


def test_glossary_adds_no_digits_so_it_cannot_launder_numbers():
    assert not any(ch.isdigit() for text in hr.GLOSSARY.values() for ch in text)


def test_every_glossary_kind_is_a_kind_the_tool_accepts():
    kinds = ro.TOOLS[0]["inputSchema"]["properties"]["kind"]["enum"]
    assert set(hr.GLOSSARY) <= set(kinds)


@pytest.mark.parametrize(
    "answer, expected",
    [
        ("請查询资料。", "簡體字"),
        ("外銷資金淨買超 100 股", "外銷資金"),
        ("信託資金買超", "信託資金"),
        ("百萬股評價區間為 1564.95 至 2157.0", "本益比區間"),
        ("外資買賣超為 -19,577,989 元", "單位是股"),
        ("2026-10-13 日投信買超 765,000 元", "單位是股"),
        ("2330 月營收 511,857,399 元", "千元"),
    ],
)
def test_language_slips_are_reported(answer, expected):
    assert any(expected in issue for issue in hr.language_issues(answer))


@pytest.mark.parametrize(
    "answer",
    [
        "外資買賣超為 -19,577,989 股，月營收 511,857,399 千元。",
        "現價 2540.0 元，DCF 公平價 942.5 元。",
        "營收年增 54.6%，法人買超 3 天。",
        "",
        None,
    ],
)
def test_correct_wording_is_not_reported(answer):
    assert hr.language_issues(answer) == []


def test_list_style_glossaries_say_the_newest_row_is_last():
    for kind in ("institutional", "revenue", "price"):
        assert "最新一筆在最後" in hr.GLOSSARY[kind]
    assert "最新一筆在最後" not in hr.GLOSSARY["valuation"]


@pytest.mark.parametrize("answer", ["投信買超：634,78 股", "合計 1,2345 股", "金額 12,34,567 元", "成交 1234,567 股"])
def test_misgrouped_thousands_are_reported(answer):
    assert any("千分位" in issue for issue in hr.language_issues(answer))


@pytest.mark.parametrize("answer", ["合計 13,383,722 股", "第 1,2,3 名", "共 6,347 股", "價 2540.0 元", "代號 2330"])
def test_well_grouped_or_small_numbers_are_not_reported_as_misgrouped(answer):
    assert not any("千分位" in issue for issue in hr.language_issues(answer))


INSTITUTIONAL = '[{"date":"2026-10-05","foreign_net":13072342.0,"trust_net":-63478.0,"dealer_net":374858.0}]'


def test_a_buy_label_on_a_negative_figure_is_reported():
    issues = hr.language_issues("投信買超：63,478 股", INSTITUTIONAL)
    assert any("負值" in issue for issue in issues)


def test_a_sell_label_on_a_positive_figure_is_reported():
    issues = hr.language_issues("外資賣超 13072342 股", INSTITUTIONAL)
    assert any("正值" in issue for issue in issues)


def test_a_buy_label_with_a_minus_sign_is_reported_even_without_context():
    assert any("負值" in issue for issue in hr.language_issues("投信買超 -63478 股"))


@pytest.mark.parametrize("answer", ["外資買超 13,072,342 股", "投信賣超 63,478 股", "投信賣超 -63,478 股", "自營商買超：374858 股"])
def test_direction_that_matches_the_sign_is_not_reported(answer):
    assert hr.language_issues(answer, INSTITUTIONAL) == []


def test_direction_is_not_judged_for_a_figure_the_context_does_not_have():
    assert hr.language_issues("外資買超 99999 股", INSTITUTIONAL) == []


@pytest.mark.parametrize("question", ["台積電營收換算成億元", "營收多少億", "765000 股是幾張", "換成萬元"])
def test_conversion_questions_are_recognised(question):
    assert hr.needs_conversion(question)


@pytest.mark.parametrize("question", ["台積電估值如何", "法人買賣超", "", None])
def test_other_questions_are_not_conversion_questions(question):
    assert not hr.needs_conversion(question)


def test_convert_hint_is_added_only_when_asked_for():
    results = [("stock_data", {"kind": "revenue", "symbol": "2330"}, "{}", False)]
    assert "本題需要換算單位" in hr.format_context(results, NAMES, convert_hint=True)
    assert "本題需要換算單位" not in hr.format_context(results, NAMES)


def test_revenue_and_institutional_glossaries_point_to_the_conversion_tool():
    assert "convert_unit" in hr.GLOSSARY["revenue"] and "convert_unit" in hr.GLOSSARY["institutional"]


def test_english_field_names_in_an_answer_are_reported():
    issues = hr.language_issues("foreign_net：-19,577,989 股，來自 mom_growth")
    assert any("foreign_net" in i and "mom_growth" in i for i in issues)


@pytest.mark.parametrize("answer", ["外資買超 13,072,342 股", "資料來自 stock_data 的法人資料", "kind=institutional", "foreign_netx"])
def test_chinese_names_and_tool_names_are_not_reported_as_field_names(answer):
    assert not any("英文欄位名" in i for i in hr.language_issues(answer))


def test_every_field_name_the_glossary_teaches_is_detected():
    assert "foreign_net" in hr._FIELD_NAMES and "annual_volatility" in hr._FIELD_NAMES
    for name in hr._FIELD_NAMES:
        assert any("英文欄位名" in i for i in hr.language_issues(f"數值 {name} 如下"))


def test_the_word_for_converting_alone_is_enough_to_ask_for_the_tool():
    assert hr.needs_conversion("請幫我換算這個數字")


def test_a_field_name_inside_a_longer_identifier_is_not_reported():
    assert not any("英文欄位名" in i for i in hr.language_issues("my_foreign_net 與 xforeign_net"))


@pytest.mark.parametrize(
    "number, context, expected",
    [
        ("19577989", '{"foreign_net":-19577989.0}', "neg"),
        ("19,577,989", '{"foreign_net":-19577989.0}', "neg"),
        ("-19577989", '{"foreign_net":-19577989.0}', "neg"),
        ("63478", '{"a":63478.0}', "pos"),
        ("63478", '{"a":63478.0,"b":-63478.0}', "both"),
        ("63478", '{"a":634780.0}', None),
        ("63478", "", None),
    ],
)
def test_sign_in_context_tells_how_the_figure_appears_in_the_data(number, context, expected):
    assert hr.sign_in_context(number, context) == expected


def test_the_combined_label_buy_sell_surplus_is_not_read_as_a_sell_label():
    assert hr.language_issues("外資買賣超是 19577.989 張", "19577989 股 = 19577.989 張") == []


RAW_FLOW = '{"foreign_net":-19577989.0}'
RAW_REVENUE = '[{"year_month":"2026-09","revenue":511857399.0}]'


@pytest.mark.parametrize(
    "answer, context",
    [
        ("外資 -19,577,989張", RAW_FLOW),
        ("外資賣超 19577989 張", RAW_FLOW),
        ("營收 511,857,399 億元", RAW_REVENUE),
        ("營收 511857399億", RAW_REVENUE),
        ("營收 511857399 萬元", RAW_REVENUE),
    ],
)
def test_a_raw_figure_relabelled_without_conversion_is_reported(answer, context):
    assert any("不能只改單位" in i for i in hr.language_issues(answer, context))


@pytest.mark.parametrize(
    "answer, context",
    [
        ("外資 -19577.989 張", RAW_FLOW + "\n-19577989 股 = -19577.989 張"),
        ("營收 5,118.57399 億元", RAW_REVENUE + "\n511857399 千元 = 5118.57399 億元"),
        ("營收 5118.57399 億", RAW_REVENUE + "\n511857399 千元 = 5118.57399 億元"),
        ("共 3 張", '{"a":3}'),
        ("營收 511,857,399 千元", RAW_REVENUE),
        ("外資 99999 張", RAW_FLOW),
    ],
)
def test_converted_small_or_unrelated_figures_are_not_reported_as_relabelled(answer, context):
    assert not any("不能只改單位" in i for i in hr.language_issues(answer, context))


FLOW_ROWS = json.dumps(
    [
        {"date": "2026-10-13", "foreign_net": -19577989.0, "trust_net": 765000.0, "dealer_net": 371097.0, "total_net": -18441892.0},
        {"date": "2026-10-12", "foreign_net": -25348402.0, "trust_net": 78100.0, "dealer_net": 28880.0, "total_net": -25241422.0},
    ]
)
REVENUE_ROWS = json.dumps([{"year_month": "2026-08", "revenue": 514805337.0}, {"year_month": "2026-09", "revenue": 511857399.0}])
PRICE_ROWS = json.dumps([{"date": "2026-10-13", "close": 2490.0, "volume": 21131357.0}])


def derived(kind, body, question, symbol="2317", is_error=False):
    return hr.derive_conversions([("stock_data", {"kind": kind, "symbol": symbol}, body, is_error)], ro.convert_unit, question)


def test_institutional_flows_are_converted_to_lots_from_the_newest_row():
    lines = derived("institutional", FLOW_ROWS, "鴻海外資最新買賣超幾張")
    assert lines[0] == "外資買賣超（2317 2026-10-13）：-19577989.0 股 = -19577.989 張"
    assert len(lines) == 4 and all("2026-10-13" in line for line in lines)
    assert "三大法人合計買賣超（2317 2026-10-13）：-18441892.0 股 = -18441.892 張" in lines


def test_the_newest_row_is_chosen_by_date_not_by_position():
    rows = json.dumps(json.loads(FLOW_ROWS)[::-1])
    assert "2026-10-13" in derived("institutional", rows, "外資幾張")[0]


def test_revenue_is_converted_to_hundred_million_by_default_and_to_ten_thousand_when_asked():
    assert derived("revenue", REVENUE_ROWS, "營收多少億", "2330") == ["月營收（2330 2026-09）：511857399.0 千元 = 5118.57399 億元"]
    assert derived("revenue", REVENUE_ROWS, "營收換成萬元", "2330") == ["月營收（2330 2026-09）：511857399.0 千元 = 51185739.9 萬元"]


def test_trading_volume_is_converted_to_lots():
    assert derived("price", PRICE_ROWS, "成交量幾張", "2330") == ["成交量（2330 2026-10-13）：21131357.0 股 = 21131.357 張"]


@pytest.mark.parametrize("question", ["鴻海外資買賣超如何", "營收如何", "", None])
def test_nothing_is_converted_unless_the_question_asks_for_it(question):
    assert derived("institutional", FLOW_ROWS, question) == []


def test_failed_unknown_or_unreadable_lookups_are_not_converted():
    assert derived("institutional", FLOW_ROWS, "幾張", is_error=True) == []
    assert derived("valuation", FLOW_ROWS, "幾張") == []
    assert derived("institutional", FLOW_ROWS[:60], "幾張") == []
    assert derived("institutional", "[]", "幾張") == []
    assert derived("institutional", '{"foreign_net": 1}', "幾張") == []


def test_a_field_that_is_missing_or_null_is_skipped_and_the_rest_still_converted():
    rows = json.dumps([{"date": "2026-10-13", "foreign_net": None, "trust_net": 765000.0}])
    assert derived("institutional", rows, "幾張") == ["投信買賣超（2317 2026-10-13）：765000.0 股 = 765 張"]


def test_a_conversion_the_tool_refuses_is_skipped():
    rows = json.dumps([{"date": "2026-10-13", "foreign_net": 1e30}])
    assert derived("institutional", rows, "幾張") == []


def test_converted_lines_appear_in_the_context_under_their_own_heading():
    results = [("stock_data", {"kind": "revenue", "symbol": "2330"}, REVENUE_ROWS, False)]
    lines = derived("revenue", REVENUE_ROWS, "營收多少億", "2330")
    text = hr.format_context(results, NAMES, convert_hint=True, conversions=lines)
    assert hr._CONVERTED_HEAD in text and lines[0] in text
    assert hr._CONVERTED_HEAD not in hr.format_context(results, NAMES)
    assert "程式已精確換算" in hr._CONVERT_HINT


DAYS = json.dumps(
    [
        {"date": "2026-10-08", "close": 2550.0, "volume": 23145193.0},
        {"date": "2026-10-12", "close": 2540.0, "volume": 23555768.0},
        {"date": "2026-10-13", "close": 2490.0, "volume": 40796261.0},
    ]
)


def on_day(question, today, body=DAYS):
    results = [("stock_data", {"kind": "price", "symbol": "2330"}, body, False)]
    return hr.derive_conversions(results, ro.convert_unit, question, today)


def test_yesterday_picks_the_row_dated_yesterday_and_says_so():
    assert on_day("昨天成交量幾張", "2026-10-13") == ["成交量（2330 2026-10-12，昨日）：23555768.0 股 = 23555.768 張"]
    assert on_day("昨日成交量幾張", "2026-10-14") == ["成交量（2330 2026-10-13，昨日）：40796261.0 股 = 40796.261 張"]


def test_yesterday_without_a_row_for_that_day_falls_back_to_the_previous_trading_day_and_says_so():
    line = on_day("昨天成交量幾張", "2026-10-13", json.dumps(json.loads(DAYS)[:1] + json.loads(DAYS)[2:]))[0]
    assert "2026-10-08，上一個交易日（昨天沒有資料）" in line


def test_yesterday_with_only_todays_row_converts_nothing():
    assert on_day("昨天成交量幾張", "2026-10-13", json.dumps(json.loads(DAYS)[2:])) == []


def test_today_picks_the_newest_row_and_flags_when_it_is_not_today():
    assert "2026-10-13，今日" in on_day("今天成交量幾張", "2026-10-13")[0]
    assert "2026-10-13，最新資料日（今天沒有資料）" in on_day("今天成交量幾張", "2026-10-14")[0]


def test_without_a_relative_day_word_the_newest_row_is_used_untagged():
    line = on_day("成交量幾張", "2026-10-13")[0]
    assert line == "成交量（2330 2026-10-13）：40796261.0 股 = 40796.261 張"


def test_relative_days_are_ignored_when_today_is_unknown_or_malformed():
    assert "2026-10-13）" in on_day("昨天成交量幾張", None)[0]
    assert "2026-10-13）" in on_day("昨天成交量幾張", "不是日期")[0]


def test_relative_day_words_do_not_apply_to_monthly_rows():
    results = [("stock_data", {"kind": "revenue", "symbol": "2330"}, REVENUE_ROWS, False)]
    assert hr.derive_conversions(results, ro.convert_unit, "昨天營收多少億", "2026-10-13") == [
        "月營收（2330 2026-09）：511857399.0 千元 = 5118.57399 億元"
    ]
