import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

pytestmark = pytest.mark.unit

FIELDS = ["資料日期", "股票代號", "股票名稱", "除權息前收盤價", "除權息參考價", "權值+息值", "權/息", "漲停價格", "跌停價格"]
ROWS = [["115年03月17日", "2330", "台積電", "1,845.00", "1,839.00", "6.0", "息", "2,020.00", "1,655.00"],
        ["115年03月20日", "00713", "元大台灣高息低波", "52.50", "51.72", "0.78", "息", "56.85", "46.55"],
        ["115年04月01日", "9999", "怪事件", "10.00", "30.00", "0", "權", "33.00", "27.00"],
        ["115年04月02日", "8888", "無價格", "--", "--", "0", "權", "--", "--"]]


def table(rows=None, start="20260101", end="20261231", stat="OK"):
    return {"stat": stat, "strDate": start, "endDate": end, "fields": FIELDS, "data": ROWS if rows is None else rows}


START, END = datetime(2026, 1, 1), datetime(2026, 12, 31)


def test_factor_is_the_official_reference_price_over_the_prior_close_and_odd_rows_are_skipped_not_guessed():
    from src.data_gap.exright_factors import parse_exright_factors

    got = parse_exright_factors(table(), START, END)
    events = {event["stock_id"]: event for event in got["events"]}
    assert set(events) == {"2330", "00713"}
    assert events["2330"]["factor"] == pytest.approx(1839 / 1845) and events["2330"]["ex_date"] == datetime(2026, 3, 17)
    assert events["2330"]["prev_close"] == 1845.0 and events["2330"]["ref_price"] == 1839.0 and events["2330"]["kind"] == "息"
    assert {item["stock_id"]: item["reason"] for item in got["skipped"]} == {"9999": "factor_out_of_range", "8888": "unreadable_price"}


@pytest.mark.parametrize("change", ["stat", "start", "schema", "outside", "duplicate", "date"])
def test_official_exright_table_rejects_failed_stale_changed_or_misdated_responses(change):
    from src.data_gap.exright_factors import parse_exright_factors

    payload = table()
    if change == "stat":
        payload["stat"] = "查詢失敗"
    elif change == "start":
        payload["strDate"] = "20250101"
    elif change == "schema":
        payload["fields"] = [name for name in FIELDS if name != "除權息參考價"]
    elif change == "outside":
        payload["data"] = [["114年03月17日", "2330", "台積電", "1,845.00", "1,839.00", "6.0", "息", "2,020.00", "1,655.00"]]
    elif change == "duplicate":
        payload["data"] = [ROWS[0], ROWS[0]]
    else:
        payload["data"] = [["03-17", "2330", "台積電", "1,845.00", "1,839.00", "6.0", "息", "2,020.00", "1,655.00"]]
    with pytest.raises(ValueError):
        parse_exright_factors(payload, START, END)


def test_only_priced_symbols_without_a_factor_are_reported_missing():
    from src.data_gap.exright_factors import missing_factors, parse_exright_factors

    events = parse_exright_factors(table(), START, END)["events"]
    have = {("2330", datetime(2026, 3, 17))}
    assert [e["stock_id"] for e in missing_factors(events, have, {"2330", "00713"})] == ["00713"]
    assert missing_factors(events, have, {"2330"}) == []


def test_agreement_summarises_how_close_the_official_formula_is_to_existing_factors():
    from src.data_gap.exright_factors import agreement, parse_exright_factors

    events = parse_exright_factors(table(), START, END)["events"]
    assert agreement(events, {}) == {"overlap": 0, "median_abs_diff": None, "over_half_percent": 0}
    got = agreement(events, {("2330", datetime(2026, 3, 17)): 1839 / 1845 + 0.001, ("00713", datetime(2026, 3, 20)): 51.72 / 52.5 + 0.01})
    assert got["overlap"] == 2 and got["over_half_percent"] == 1 and got["median_abs_diff"] == pytest.approx(0.0055)


class Reply:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class Collection:
    def __init__(self, rows=None, symbols=()):
        self.rows, self.symbols, self.batches = rows or [], symbols, []

    def find(self, query, projection=None):
        return self.rows

    def distinct(self, field):
        return list(self.symbols)

    def bulk_write(self, operations, ordered=False):
        self.batches.append(operations)


def test_filler_inserts_only_missing_events_without_touching_existing_factors(monkeypatch):
    import fill_exright_factors as filler

    class Session:
        def get(self, url, params=None, **kwargs):
            assert url.endswith("/exRight/TWT49U")
            return Reply(table(start=params["startDate"], end=params["endDate"]))

    factors = Collection([{"stock_id": "2330", "ex_date": datetime(2026, 3, 17), "factor": 0.9967}])
    db = {"adjustment_factors": factors, "stock_price": Collection(symbols=["2330", "00713"])}
    now = datetime(2026, 10, 27)
    dry = filler.run(db, Session(), START, END, apply=False, pause=0, now=now)
    assert dry["missing"] == 1 and not factors.batches and dry["agreement_with_existing"]["overlap"] == 1
    done = filler.run(db, Session(), START, END, apply=True, pause=0, now=now)
    operations = [op for batch in factors.batches for op in batch]
    assert done["applied"] is True and len(operations) == 1
    operation = operations[0]
    assert operation._filter == {"stock_id": "00713", "ex_date": datetime(2026, 3, 20)} and operation._upsert
    assert "$set" not in operation._doc and operation._doc["$setOnInsert"]["source"] == "TWSE_TWT49U"
    assert operation._doc["$setOnInsert"]["updated_at"] == now
