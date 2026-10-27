import json
from datetime import date

import pytest

pytestmark = pytest.mark.unit

EX_FIELDS = ["資料日期", "股票代號", "股票名稱", "除權息參考價", "權值+息值", "權/息", "漲停價格", "跌停價格"]
SPLIT_FIELDS = ["恢復買賣日期", "ETF代號", "名稱", "分割(反分割)", "停止買賣前收盤價格", "恢復買賣參考價", "漲停價格", "跌停價格", "開盤競價基準"]
DAILY_FIELDS = ["日期", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌價差", "成交筆數", "註記"]
HALT_FIELDS = ["編號", "證券代號", "證券名稱", "暫停交易日期", "暫停交易時間", "恢復交易日期", "恢復交易時間"]


def exright(rows, start="20260101", end="20261231", stat="OK"):
    return {"stat": stat, "strDate": start, "endDate": end, "fields": EX_FIELDS, "data": rows}


def halts(rows, period="115/01/01 到 115/12/31"):
    return {"stat": "OK", "title": f"暫停交易證券 查詢範圍：全部上市證券 期間：{period}",
            "fields": HALT_FIELDS, "data": rows}


def price(day, open_, high, low, close, spread, volume=1000, symbol="0050"):
    return {"date": day, "symbol": symbol, "open": open_, "high": high, "low": low,
            "close": close, "spread": spread, "volume": volume}


def test_limit_prices_follow_etf_tick_and_the_seven_to_ten_percent_regime():
    from decimal import Decimal

    from src.research_workflow.tradability import limit_prices

    assert limit_prices(Decimal("188.00"), date(2025, 1, 2)) == (Decimal("206.80"), Decimal("169.20"))
    assert limit_prices(Decimal("15.24"), date(2026, 3, 31)) == (Decimal("16.76"), Decimal("13.72"))
    assert limit_prices(Decimal("51.72"), date(2026, 3, 20)) == (Decimal("56.85"), Decimal("46.55"))
    assert limit_prices(Decimal("10.00"), date(2015, 5, 29)) == (Decimal("10.70"), Decimal("9.30"))
    assert limit_prices(Decimal("10.00"), date(2015, 6, 1)) == (Decimal("11.00"), Decimal("9.00"))


def test_official_limits_validate_only_non_bond_etf_events():
    from src.research_workflow.tradability import parse_exright_limits, verify_limits

    payload = exright([
        ["115年03月20日", "00713", "元大台灣高息低波", "51.72", "0.78", "息", "56.85", "46.55"],
        ["115年03月23日", "2330", "台積電", "1,845.00", "6.0", "息", "2,020.00", "1,660.00"],
        ["115年03月24日", "0080", "富邦上証", "337.72", "1.0", "息", "9,999.95", "0.01"],
        ["115年04月02日", "00953B", "群益優選非投等債", "9.62", "0.06", "息", "9,999.95", "0.01"]])
    events = parse_exright_limits(payload, "2026-01-01", "2026-12-31")
    assert [event["symbol"] for event in events] == ["00713", "0080"]
    assert [event["no_limit"] for event in events] == [False, True]
    assert verify_limits(events) == {"events": 1, "mismatches": [], "unvalidated_class_events": 0, "no_limit_events": 1}
    events[0]["upper_limit"] = 56.9
    check = verify_limits(events)
    assert check["events"] == 1 and check["mismatches"][0]["symbol"] == "00713"
    events[0]["upper_limit"] = 56.85
    events[1]["no_limit"] = False
    assert verify_limits(events)["mismatches"][0]["symbol"] == "0080"
    partial = exright([["115年03月24日", "0080", "富邦上証", "337.72", "1.0", "息", "9,999.95", "300.00"]])
    assert not parse_exright_limits(partial, "2026-01-01", "2026-12-31")[0]["no_limit"]


@pytest.mark.parametrize("change", ["stat", "start", "schema"])
def test_official_limit_table_rejects_failed_stale_or_changed_responses(change):
    from src.research_workflow.tradability import parse_exright_limits

    payload = exright([])
    if change == "stat":
        payload["stat"] = "查詢失敗"
    elif change == "start":
        payload["strDate"] = "20250101"
    else:
        payload["fields"] = [name for name in EX_FIELDS if name != "除權息參考價"]
    with pytest.raises(ValueError):
        parse_exright_limits(payload, "2026-01-01", "2026-12-31")


def test_halt_history_is_validated_against_the_requested_period_and_symbols():
    from src.research_workflow.tradability import parse_halts

    payload = halts([[1, "0050", "元大台灣50", "115/02/03", "8:00", "115/02/04", "8:00"],
                     [2, "2330", "台積電", "115/02/03", "8:00", "115/02/04", "8:00"],
                     [3, "00631L", "元大台灣50正2", "115/05/06", "9:00", "", ""]])
    got = parse_halts(payload, ["0050", "00631L"], "2026-01-01", "2026-12-31")
    assert [(row["symbol"], row["start"], row["resume"]) for row in got] == [
        ("0050", "2026-02-03T08:00:00", "2026-02-04T08:00:00"), ("00631L", "2026-05-06T09:00:00", None)]
    stale = halts([], period="115/01/01 到 115/06/30")
    with pytest.raises(ValueError):
        parse_halts(stale, ["0050"], "2026-01-01", "2026-12-31")
    with pytest.raises(ValueError):
        parse_halts({**payload, "stat": "查詢日期小於100年10月3日，請重新查詢!"}, ["0050"], "2026-01-01", "2026-12-31")


def derive(rows, references=None, stops=None, calendar=None, official=None):
    from src.research_workflow.tradability import derive_tradability

    return derive_tradability(rows, references or {}, stops or [], "2026-01-01", calendar, official)


CALENDAR = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]


def test_missing_spread_is_corroborated_only_by_an_adjacent_trading_day_and_conflicts_stay_withheld():
    first = price("2026-01-05", 59.9, 60.2, 59.8, 60.0, None)
    second = price("2026-01-06", 60.5, 60.8, 60.0, 60.4, None)
    got = derive([first, second], calendar=CALENDAR)
    assert got["tradability"][0]["basis"] == "prior_close_adjacent_trading_day"
    gap = derive([price("2026-01-02", 59.9, 60.2, 59.8, 60.0, None), second], calendar=CALENDAR)
    assert not gap["tradability"] and gap["withheld"][-1]["reason"] == "prior_close_not_corroborated"
    conflict = derive([first, {**second, "spread": 1.4}], calendar=CALENDAR)
    assert not conflict["tradability"] and conflict["withheld"][-1]["reason"] == "prior_close_not_corroborated"
    no_calendar = derive([first, second])
    assert not no_calendar["tradability"] and no_calendar["withheld"][-1]["reason"] == "prior_close_not_corroborated"
    outside = derive([first, price("2026-01-08", 60.5, 60.8, 60.0, 60.4, None)], calendar=CALENDAR)
    assert outside["withheld"][-1]["reason"] == "date_not_in_trading_calendar"


def test_normal_days_are_tradable_and_available_before_the_open():
    got = derive([price("2026-01-05", 59.9, 60.2, 59.8, 60.0, 0.1),
                  price("2026-01-06", 60.5, 60.8, 60.0, 60.4, 0.4)])
    assert got["withheld"][0]["reason"] == "no_prior_row"
    entry = got["tradability"][0]
    assert (entry["symbol"], entry["date"], entry["can_buy"], entry["can_sell"]) == ("0050", "2026-01-06", True, True)
    assert entry["available_at"] == "2026-01-06T00:00:00"
    assert entry["upper_limit"] == 66.0 and entry["lower_limit"] == 54.0
    assert entry["basis"] == "prior_close_corroborated_by_spread" and entry["source"]


def test_open_at_a_limit_blocks_only_the_side_that_cannot_trade():
    up = derive([price("2026-01-05", 59.9, 60.2, 59.8, 60.0, 0.1), price("2026-01-06", 66.0, 66.0, 66.0, 66.0, 6.0)])
    down = derive([price("2026-01-05", 59.9, 60.2, 59.8, 60.0, 0.1), price("2026-01-06", 54.0, 54.0, 54.0, 54.0, -6.0)])
    assert (up["tradability"][0]["can_buy"], up["tradability"][0]["can_sell"]) == (False, True)
    assert (down["tradability"][0]["can_buy"], down["tradability"][0]["can_sell"]) == (True, False)


@pytest.mark.parametrize("case,reason", [
    ("spread", "prior_close_not_corroborated"),
    ("outside", "observed_price_outside_derived_limits"),
    ("outside_low", "observed_price_outside_derived_limits"),
    ("no_trade", "no_trade_or_invalid_price"),
    ("halt", "official_halt_overlaps_session")])
def test_rows_that_cannot_be_verified_are_withheld_instead_of_guessed(case, reason):
    base = price("2026-01-06", 60.5, 60.8, 60.0, 60.4, 0.4)
    stops = []
    if case == "spread":
        base["spread"] = 1.4
    elif case == "outside":
        base["high"] = 66.5
    elif case == "outside_low":
        base["low"] = 53.5
    elif case == "no_trade":
        base["volume"] = 0
    else:
        stops = [{"symbol": "0050", "start": "2026-01-06T08:00:00", "resume": "2026-01-07T08:00:00"}]
    got = derive([price("2026-01-05", 59.9, 60.2, 59.8, 60.0, 0.1), base], stops=stops)
    assert not got["tradability"] and got["withheld"][-1]["reason"] == reason


def test_session_boundaries_and_row_consistency_are_exact():
    rows = [price("2026-01-05", 59.9, 60.2, 59.8, 60.0, 0.1), price("2026-01-06", 60.5, 60.8, 60.0, 60.4, 0.4)]
    resumes_at_open = [{"symbol": "0050", "start": "2026-01-05T08:00:00", "resume": "2026-01-06T09:00:00"}]
    starts_after_close = [{"symbol": "0050", "start": "2026-01-06T13:30:00", "resume": "2026-01-07T09:00:00"}]
    assert derive(rows, stops=resumes_at_open)["tradability"]
    assert derive(rows, stops=starts_after_close)["tradability"]
    off_by_a_cent = [rows[0], {**rows[1], "spread": 0.39}]
    assert derive(off_by_a_cent)["withheld"][-1]["reason"] == "prior_close_not_corroborated"
    open_above_limit = [rows[0], price("2026-01-06", 67.0, 66.0, 60.0, 60.4, 0.4)]
    assert derive(open_above_limit)["withheld"][-1]["reason"] == "observed_price_outside_derived_limits"


def test_a_halt_that_resumes_before_the_session_does_not_overlap():
    stops = [{"symbol": "0050", "start": "2026-01-05T08:00:00", "resume": "2026-01-06T08:00:00"}]
    got = derive([price("2026-01-05", 59.9, 60.2, 59.8, 60.0, 0.1), price("2026-01-06", 60.5, 60.8, 60.0, 60.4, 0.4)], stops=stops)
    assert got["tradability"][0]["date"] == "2026-01-06"
    still = [{"symbol": "0050", "start": "2026-01-05T08:00:00", "resume": None}]
    got = derive([price("2026-01-05", 59.9, 60.2, 59.8, 60.0, 0.1), price("2026-01-06", 60.5, 60.8, 60.0, 60.4, 0.4)], stops=still)
    assert not got["tradability"]


def test_official_reference_price_sets_limits_on_ex_days_and_stocks_are_unsupported():
    row = price("2026-01-06", 59.9, 60.2, 59.5, 60.0, -0.5)
    got = derive([price("2026-01-05", 60.0, 60.2, 59.8, 60.5, 0.1), row], references={("0050", "2026-01-06"): 59.95})
    entry = got["tradability"][0]
    assert entry["basis"] == "official_reference_price" and entry["upper_limit"] == pytest.approx(65.9)
    stocks = derive([price("2026-01-05", 1, 1, 1, 1, 0, symbol="2330"), price("2026-01-06", 1, 1, 1, 1, 0, symbol="2330")])
    assert not stocks["tradability"]
    assert {item["reason"] for item in stocks["withheld"]} == {"unsupported_instrument"}
    unlimited = derive([price("2026-01-05", 60.0, 60.2, 59.8, 60.5, 0.1), row], references={("0050", "2026-01-06"): None})
    assert not unlimited["tradability"] and unlimited["withheld"][-1]["reason"] == "official_no_price_limit"


class Reply:
    def __init__(self, payload):
        self.content = json.dumps(payload, ensure_ascii=False).encode()

    def raise_for_status(self):
        pass


def fake_session(official_limit="56.85", daily=None, splits=None, broken_months=(), flaky_months=()):
    attempts = {}

    class Session:
        def get(self, url, params=None, **kwargs):
            assert url.startswith("https://www.twse.com.tw/rwd/zh/")
            if "TWT49U" in url:
                rows = [["115年03月20日", "00713", "元大台灣高息低波", "51.72", "0.78", "息", official_limit, "46.55"]] if params["startDate"].startswith("2026") else []
                return Reply(exright(rows, params["startDate"], params["endDate"]))
            if url.endswith("/split/TWTCAU"):
                return Reply({"stat": "OK", "fields": SPLIT_FIELDS, "data": splits or []})
            if "STOCK_DAY" in url:
                month = params["date"][:6]
                if month in flaky_months and not attempts.get(month):
                    attempts[month] = 1
                    raise __import__("requests").ConnectionError("blip")
                if month in broken_months:
                    raise __import__("requests").ConnectionError("down")
                return Reply((daily or {}).get((params["stockNo"], month), {"stat": "很抱歉，沒有符合條件的資料!"}))
            return Reply(halts([], period="115/01/01 到 115/09/18"))

    return Session()


class Calendar:
    def find(self, query, projection):
        return [{"date": "2026-01-05"}, {"date": "2026-01-06"}]


class Prices:
    def find(self, query, projection):
        assert query["symbol"] == {"$in": ["0050"]}
        return [{"symbol": "0050", "date": __import__("datetime").datetime(2026, 1, 5), "open": 59.9, "high": 60.2,
                 "low": 59.8, "close": 60.0, "spread": 0.1, "volume": 10},
                {"symbol": "0050", "date": __import__("datetime").datetime(2026, 1, 6), "open": 60.5, "high": 60.8,
                 "low": 60.0, "close": 60.4, "spread": 0.4, "volume": 10}]


def database():
    return {"stock_price": Prices(), "trading_dates": Calendar()}


def test_collect_archives_raw_responses_validates_rule_and_never_certifies_completeness(tmp_path):
    from src.research_workflow.tradability import collect_tradability

    out = tmp_path / "tradability"
    got = collect_tradability(out, ["0050"], "2026-01-01", "2026-09-18", session=fake_session(), db=database(), pause=0)
    assert got["status"] == "partial_evidence" and got["certified_complete"] is False
    assert got["tradability"] == 1 and got["withheld"] == 1 and got["official_limit_events"] == 1
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["certified_complete"] is False and manifest["artifacts"]
    assert any(item["path"].startswith("raw/exright_") for item in manifest["artifacts"])
    assert any(item["path"] == "raw/trading_dates.json" for item in manifest["artifacts"])
    evidence = json.loads((out / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["tradability"][0]["date"] == "2026-01-06"
    assert evidence["actions"] == [] and evidence["coverage"] == [] and evidence["membership"] == []
    with pytest.raises(FileExistsError):
        collect_tradability(out, ["0050"], "2026-01-01", "2026-09-18", session=fake_session(), db=database(), pause=0)


def test_collect_requires_a_trading_calendar(tmp_path):
    from src.research_workflow.tradability import collect_tradability

    class Empty:
        def find(self, query, projection):
            return []

    with pytest.raises(ValueError, match="calendar"):
        collect_tradability(tmp_path / "t", ["0050"], "2026-01-01", "2026-09-18", session=fake_session(),
                            db={"stock_price": Prices(), "trading_dates": Empty()}, pause=0)


def test_collect_refuses_to_emit_flags_when_the_rule_disagrees_with_the_official_table(tmp_path):
    from src.research_workflow.tradability import collect_tradability

    out = tmp_path / "tradability"
    with pytest.raises(ValueError, match="official limit"):
        collect_tradability(out, ["0050"], "2026-01-01", "2026-09-18", session=fake_session("56.90"), db=database(), pause=0)
    assert not (out / "evidence.json").exists() and (out / "failure.json").exists()


def test_collect_rejects_unsupported_instruments_before_any_request(tmp_path):
    from src.research_workflow.tradability import collect_tradability

    class Forbidden:
        def get(self, *args, **kwargs):
            raise AssertionError("no request expected")

    for symbols in (["2330"], ["00679B"], ["0050", "2330"]):
        with pytest.raises(ValueError, match="verified ETF"):
            collect_tradability(tmp_path / "-".join(symbols), symbols, "2026-01-01", "2026-09-18", session=Forbidden(), db={})


def test_evidence_files_merge_by_concatenating_lists_and_rejecting_conflicting_scalars():
    from src.research_workflow.evidence import merge_evidence

    merged = merge_evidence([{"actions": [{"a": 1}], "tradability": [], "source_snapshot": {"id": "x"}},
                             {"actions": [{"a": 2}], "tradability": [{"t": 1}]}])
    assert merged["actions"] == [{"a": 1}, {"a": 2}] and merged["tradability"] == [{"t": 1}]
    assert merged["source_snapshot"] == {"id": "x"}
    with pytest.raises(ValueError):
        merge_evidence([{"source_snapshot": {"id": "x"}}, {"source_snapshot": {"id": "y"}}])


def test_cli_merges_repeated_evidence_files_and_exposes_the_tradability_command(tmp_path, capsys, monkeypatch):
    import pandas as pd

    from scripts import quant_workflow

    source = tmp_path / "prices.csv"
    pd.DataFrame([{"date": "2026-01-06", "symbol": "0050", "open": 60.5, "close": 60.4, "volume": 10}]).to_csv(source, index=False)
    flags = tmp_path / "flags.json"
    flags.write_text(json.dumps({"tradability": [{"symbol": "0050", "date": "2026-01-06", "can_buy": True, "can_sell": True,
                                                  "available_at": "2026-01-06T00:00:00", "source": "derived_price_limit"}]}))
    actions = tmp_path / "actions.json"
    actions.write_text(json.dumps({"actions": []}))
    assert quant_workflow.main(["audit", "--prices", str(source), "--evidence", str(flags), "--evidence", str(actions)]) == 2
    assert "can_buy" not in json.loads(capsys.readouterr().out)["missing_values"]
    seen = {}

    def fake(out, symbols, start, end):
        seen.update(out=out, symbols=symbols, start=start, end=end)
        return {"status": "partial_evidence"}

    monkeypatch.setattr("src.research_workflow.tradability.collect_tradability", fake)
    assert quant_workflow.main(["tradability", "--symbols", "0050,00631L", "--out", str(tmp_path / "t")]) == 2
    assert seen["symbols"] == ["0050", "00631L"] and seen["start"] == "2014-01-01"


def test_tradability_evidence_enriches_flags_without_unlocking_the_other_gaps():
    import pandas as pd

    from src.research_workflow.evidence import enrich

    frame = pd.DataFrame([{"date": "2026-01-06", "symbol": "0050", "open": 60.5, "close": 60.4, "volume": 10}])
    entry = {"symbol": "0050", "date": "2026-01-06", "can_buy": True, "can_sell": False,
             "available_at": "2026-01-06T00:00:00", "source": "derived_price_limit"}
    got = enrich(frame, {"tradability": [entry]})
    assert bool(got["can_buy"].iloc[0]) is True and bool(got["can_sell"].iloc[0]) is False
    assert got["eligible"].isna().all() and got["listed_on"].isna().all() and got["cash_dividend"].isna().all()


def official_days(rows, months=((2025, 12), (2026, 1))):
    from decimal import Decimal

    days = {day: {"open": Decimal(o), "high": Decimal(h), "low": Decimal(low), "close": Decimal(c)} for day, (o, h, low, c) in rows.items()}
    return {"0050": {"days": days, "months": set(months)}}


OFFICIAL = {"2025-12-31": ("59.5", "60.0", "59.4", "59.9"), "2026-01-05": ("59.9", "60.2", "59.8", "60.0"),
            "2026-01-06": ("60.5", "60.8", "60.0", "60.4")}


def test_split_resumption_day_uses_the_official_limits_instead_of_the_ten_percent_rule():
    first = price("2026-01-05", 59.9, 60.2, 59.8, 60.0, 0.1)
    wide = price("2026-01-06", 19.67, 23.5, 19.0, 19.26, None)
    got = derive([first, wide], references={("0050", "2026-01-06"): (20.14, 24.16, 16.12)})
    entry = got["tradability"][0]
    assert entry["basis"] == "official_split_resumption_limits" and entry["upper_limit"] == 24.16 and entry["lower_limit"] == 16.12
    assert entry["base_price"] == 20.14 and entry["can_buy"] is True
    beyond = derive([first, {**wide, "high": 24.5}], references={("0050", "2026-01-06"): (20.14, 24.16, 16.12)})
    assert not beyond["tradability"] and beyond["withheld"][-1]["reason"] == "observed_price_outside_derived_limits"
    locked = derive([first, price("2026-01-06", 24.16, 24.16, 24.16, 24.16, None)], references={("0050", "2026-01-06"): (20.14, 24.16, 16.12)})
    assert locked["tradability"][0]["can_buy"] is False


def test_official_daily_table_rescues_conflicting_spreads_and_vets_the_row_against_the_official_prices():
    rows = [price("2026-01-05", 59.9, 60.2, 59.8, 60.0, 9.9), price("2026-01-06", 60.5, 60.8, 60.0, 60.4, 9.9)]
    got = derive(rows, official=official_days(OFFICIAL))
    assert [(e["date"], e["basis"], e["base_price"]) for e in got["tradability"]] == [
        ("2026-01-05", "prior_close_official_daily_table", 59.9), ("2026-01-06", "prior_close_official_daily_table", 60.0)]
    wrong = derive(rows, official=official_days({**OFFICIAL, "2026-01-06": ("60.5", "60.8", "60.0", "60.5")}))
    assert [e["date"] for e in wrong["tradability"]] == ["2026-01-05"]
    assert wrong["withheld"][-1]["reason"] == "official_daily_mismatch"
    partial = derive(rows, official=official_days({day: OFFICIAL[day] for day in ("2026-01-05", "2026-01-06")}))
    assert [e["date"] for e in partial["tradability"]] == ["2026-01-06"]
    assert partial["withheld"][0]["reason"] == "no_prior_row"
    first_row = derive(rows[:1], official=official_days(OFFICIAL))
    assert first_row["tradability"][0]["basis"] == "prior_close_official_daily_table"


def daily(symbol, ym, rows):
    year = int(ym[:4])
    return {"stat": "OK", "date": ym + "01", "title": f"{year - 1911}年{ym[4:]}月 {symbol} 元大台灣50 各日成交資訊",
            "fields": DAILY_FIELDS, "data": [[roc, "1,000", "60,000", o, h, low, c, "+0.10", "10", ""] for roc, o, h, low, c in rows]}


def test_official_daily_table_is_parsed_by_header_and_skips_days_without_prices():
    from decimal import Decimal

    from src.research_workflow.tradability import parse_daily_table

    payload = daily("0050", "202601", [("115/01/05", "59.90", "60.20", "59.80", "60.00"), ("115/01/06", "--", "--", "--", "--"),
                                       ("115/01/07", "1,060.50", "1,060.80", "1,060.00", "1,060.40")])
    assert parse_daily_table(payload, "0050", (2026, 1)) == [
        {"date": "2026-01-05", "open": Decimal("59.90"), "high": Decimal("60.20"), "low": Decimal("59.80"), "close": Decimal("60.00")},
        {"date": "2026-01-07", "open": Decimal("1060.50"), "high": Decimal("1060.80"), "low": Decimal("1060.00"), "close": Decimal("1060.40")}]
    assert parse_daily_table({"stat": "很抱歉，沒有符合條件的資料!"}, "0050", (2026, 1)) == []


@pytest.mark.parametrize("change", ["stat", "symbol", "schema", "month"])
def test_official_daily_table_rejects_failed_foreign_changed_or_misdated_responses(change):
    from src.research_workflow.tradability import parse_daily_table

    payload = daily("0050", "202601", [("115/01/05", "59.90", "60.20", "59.80", "60.00")])
    if change == "stat":
        payload["stat"] = "系統忙碌中"
    elif change == "symbol":
        payload["title"] = "115年01月 2330 台積電 各日成交資訊"
    elif change == "schema":
        payload["fields"] = [name for name in DAILY_FIELDS if name != "收盤價"]
    else:
        payload["data"][0][0] = "115/02/03"
    with pytest.raises(ValueError):
        parse_daily_table(payload, "0050", (2026, 1))


class PriceRows:
    def __init__(self, rows):
        self.rows = rows

    def find(self, query, projection):
        return self.rows


def stored(day, o, h, low, c, spread):
    return {"symbol": "0050", "date": __import__("datetime").datetime.fromisoformat(day), "open": o, "high": h,
            "low": low, "close": c, "spread": spread, "volume": 10}


def test_collect_fetches_official_months_only_for_withheld_rows_and_rescues_them(tmp_path):
    from src.research_workflow.tradability import collect_tradability

    rows = [stored("2026-01-05", 59.9, 60.2, 59.8, 60.0, 9.9), stored("2026-01-06", 60.5, 60.8, 60.0, 60.4, 9.9)]
    months = {("0050", "202512"): daily("0050", "202512", [("114/12/31", "59.50", "60.00", "59.40", "59.90")]),
              ("0050", "202601"): daily("0050", "202601", [("115/01/05", "59.90", "60.20", "59.80", "60.00"),
                                                           ("115/01/06", "60.50", "60.80", "60.00", "60.40")])}
    out = tmp_path / "official"
    got = collect_tradability(out, ["0050"], "2026-01-01", "2026-09-18", session=fake_session(daily=months),
                              db={"stock_price": PriceRows(rows), "trading_dates": Calendar()}, pause=0)
    assert got["tradability"] == 2 and got["withheld"] == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    paths = {item["path"] for item in manifest["artifacts"]}
    assert {"raw/stock_day_0050_202512.json", "raw/stock_day_0050_202601.json", "raw/twtcau.json"} <= paths
    assert manifest["validation"]["official_daily_months"] == 2 and manifest["validation"]["rescued_by_official_daily"] == 2
    assert manifest["validation"]["split_events"] == 0
    evidence = json.loads((out / "evidence.json").read_text(encoding="utf-8"))
    assert {e["basis"] for e in evidence["tradability"]} == {"prior_close_official_daily_table"}


def test_collect_uses_official_split_limits_and_tolerates_a_failing_official_month(tmp_path):
    from src.research_workflow.tradability import collect_tradability

    rows = [stored("2026-01-05", 59.9, 60.2, 59.8, 60.0, 0.1), stored("2026-01-06", 60.5, 60.8, 60.0, 60.4, 0.4)]
    split = [["115/01/06", "0050", "元大台灣50", "分割", "240.00", "60.00", "72.00", "48.00", "60.00"]]
    out = tmp_path / "split"
    got = collect_tradability(out, ["0050"], "2026-01-01", "2026-09-18", session=fake_session(splits=split, broken_months=("202512",)),
                              db={"stock_price": PriceRows(rows), "trading_dates": Calendar()}, pause=0)
    assert got["status"] == "partial_evidence" and got["tradability"] == 1 and got["withheld"] == 1
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["validation"]["split_events"] == 1
    assert manifest["validation"]["official_daily_failures"] == [{"symbol": "0050", "month": "202512"}]
    evidence = json.loads((out / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["tradability"][0]["basis"] == "official_split_resumption_limits" and evidence["tradability"][0]["upper_limit"] == 72.0

def test_only_a_conflicting_spread_row_is_enough_to_trigger_the_official_month_and_a_blip_is_retried(tmp_path):
    from src.research_workflow.tradability import collect_tradability

    rows = [stored("2025-12-31", 59.5, 60.0, 59.4, 59.9, 0.1), stored("2026-01-05", 59.9, 60.2, 59.8, 60.0, 9.9)]
    months = {("0050", "202512"): daily("0050", "202512", [("114/12/31", "59.50", "60.00", "59.40", "59.90")]),
              ("0050", "202601"): daily("0050", "202601", [("115/01/05", "59.90", "60.20", "59.80", "60.00")])}
    out = tmp_path / "conflict"
    got = collect_tradability(out, ["0050"], "2026-01-01", "2026-09-18", session=fake_session(daily=months, flaky_months=("202601",)),
                              db={"stock_price": PriceRows(rows), "trading_dates": Calendar()}, pause=0)
    assert got["tradability"] == 1 and got["withheld"] == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["validation"]["official_daily_failures"] == [] and manifest["validation"]["rescued_by_official_daily"] == 1


def test_official_daily_rows_without_positive_prices_are_ignored():
    from src.research_workflow.tradability import parse_daily_table

    payload = daily("0050", "202601", [("115/01/05", "59.90", "60.20", "59.80", "60.00"), ("115/01/06", "0.00", "0.00", "0.00", "0.00")])
    assert [row["date"] for row in parse_daily_table(payload, "0050", (2026, 1))] == ["2026-01-05"]

def test_official_prior_close_needs_every_month_in_between_to_have_been_fetched():
    rows = [price("2026-01-05", 59.9, 60.2, 59.8, 60.0, 0.1), price("2026-03-02", 60.5, 60.8, 60.0, 60.4, 0.4)]
    table = {"2025-12-31": ("59.5", "60.0", "59.4", "59.9"), "2026-03-02": ("60.5", "60.8", "60.0", "60.4")}
    gap = derive(rows, official=official_days(table, months=((2025, 12), (2026, 3))))
    assert gap["tradability"][0]["basis"] == "prior_close_corroborated_by_spread"
    contiguous = derive(rows, official=official_days(table, months=((2025, 12), (2026, 1), (2026, 2), (2026, 3))))
    assert contiguous["tradability"][0]["basis"] == "prior_close_official_daily_table" and contiguous["tradability"][0]["base_price"] == 59.9


def test_leveraged_and_futures_etfs_only_get_flags_inside_the_minimum_band():
    first = price("2026-01-05", 59.9, 60.2, 59.8, 60.0, 0.1, symbol="00631L")
    inside = price("2026-01-06", 63.0, 70.0, 62.0, 66.0, 6.0, symbol="00631L")
    got = derive([first, inside])
    entry = got["tradability"][0]
    assert (entry["limit_rule"], entry["can_buy"], entry["can_sell"]) == ("minimum_band_only", True, True)
    for opened in (66.0, 48.0):
        locked = derive([first, {**inside, "open": opened}])
        assert not locked["tradability"] and locked["withheld"][-1]["reason"] == "possible_limit_lock_unverified"
    ordinary = derive([{**first, "symbol": "0050"}, {**inside, "symbol": "0050"}])
    assert ordinary["withheld"][-1]["reason"] == "observed_price_outside_derived_limits"
    official = derive([first, price("2026-01-06", 19.67, 23.5, 19.0, 19.26, None, symbol="00631L")],
                      references={("00631L", "2026-01-06"): (20.14, 24.16, 16.12)})
    assert official["tradability"][0]["limit_rule"] == "official_limits"


def test_only_ordinary_etf_events_validate_the_ten_percent_rule():
    from src.research_workflow.tradability import verify_limits

    leveraged = {"symbol": "00631L", "date": "2026-03-31", "reference_price": 20.14, "upper_limit": 24.16, "lower_limit": 16.12, "no_limit": False}
    assert verify_limits([leveraged]) == {"events": 0, "mismatches": [], "unvalidated_class_events": 1, "no_limit_events": 0}