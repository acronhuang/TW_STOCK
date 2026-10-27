import sys
from datetime import date, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import backfill_delisted_prices as bdp

pytestmark = pytest.mark.unit

START = date(2013, 1, 1)


def fact(symbol, day):
    return {"symbol": symbol, "delisted_on": date.fromisoformat(day)}


def test_plan_covers_delisted_stocks_with_no_prices_or_a_history_that_ends_too_early():
    from src.data_gap.delisted import plan_history

    facts = [fact("2361", "2015-12-28"), fact("4415", "2019-05-02"), fact("1258", "2023-06-09"), fact("2881A", "2020-01-02"),
             fact("1111", "2012-06-01"), fact("3333", "2018-01-01"), fact("3333", "2021-01-01")]
    last = {"2361": date(2013, 1, 8), "1258": date(2023, 6, 1)}
    assert plan_history(facts, last, START) == [
        {"symbol": "2361", "from": date(2013, 1, 9), "to": date(2015, 12, 28)},
        {"symbol": "4415", "from": START, "to": date(2019, 5, 2)}]
    assert plan_history([fact("1258", "2023-06-09")], {"1258": date(2023, 5, 1)}, START, grace_days=14)[0]["from"] == date(2023, 5, 2)


class Reply:
    def __init__(self, status=200, rows=None):
        self.status_code = status
        self.rows = rows or []

    def json(self):
        return {"data": self.rows}


def finmind_row(day, close="1.94"):
    return {"date": day, "open": 1.9, "max": 1.94, "min": 1.9, "close": close, "Trading_Volume": 100,
            "Trading_money": 190, "Trading_turnover": 5, "spread": 0.01}


class Prices:
    def __init__(self):
        self.batches = []

    def aggregate(self, pipeline):
        assert pipeline[0]["$match"]["symbol"]["$in"]
        return [{"_id": "2361", "last": datetime(2013, 1, 8)}]

    def bulk_write(self, operations, ordered=False):
        self.batches.append(operations)


def session(responses):
    calls = []

    class Fake:
        def get(self, url, params=None, headers=None, **kwargs):
            calls.append((params, headers))
            return responses.pop(0)

    return Fake(), calls


FACTS = [fact("2361", "2015-12-28"), fact("4415", "2019-05-02")]


def test_apply_inserts_only_priced_rows_inside_the_listing_window_and_never_rewrites_existing_rows():
    prices = Prices()
    fake, calls = session([Reply(rows=[finmind_row("2013-01-09"), finmind_row("2014-06-03"), finmind_row("2014-06-04", close=0),
                                       finmind_row("2016-01-04")]), Reply(rows=[])])
    now = datetime(2026, 10, 27)
    got = bdp.run({"stock_price": prices}, FACTS, "token", (10, 600), START, apply=True, session=fake, now=now)
    assert got["status"] == "ok" and got["planned"] == 2 and got["rows"] == 2 and got["empty"] == ["4415"]
    operations = [op for batch in prices.batches for op in batch]
    assert [op._filter["date"].date().isoformat() for op in operations] == ["2013-01-09", "2014-06-03"]
    assert all(op._upsert and "$set" not in op._doc for op in operations)
    inserted = operations[0]._doc["$setOnInsert"]
    assert inserted["adj_close"] == inserted["close"] and inserted["updated_at"] == now and "adjustment_factor" not in inserted
    assert calls[0][0]["start_date"] == "2013-01-09" and calls[0][0]["end_date"] == "2015-12-28"
    assert calls[1][0]["start_date"] == "2013-01-01" and calls[0][1] == {"Authorization": "Bearer token"}


def test_dry_run_reads_but_does_not_write():
    prices = Prices()
    fake, _ = session([Reply(rows=[finmind_row("2014-06-03")]), Reply()])
    got = bdp.run({"stock_price": prices}, FACTS, "token", (0, 600), START, apply=False, session=fake)
    assert got["rows"] == 1 and got["applied"] is False and not prices.batches


@pytest.mark.parametrize("usage", [None, (590, 600), (0, 21)])
def test_unknown_or_insufficient_quota_aborts_before_any_request(usage):
    fake, calls = session([])
    got = bdp.run({"stock_price": Prices()}, FACTS, "token", usage, START, apply=True, session=fake)
    assert got["status"] == "aborted" and not calls


def test_a_non_200_response_stops_the_run_and_keeps_what_was_already_fetched():
    prices = Prices()
    fake, calls = session([Reply(rows=[finmind_row("2014-06-03")]), Reply(status=402)])
    got = bdp.run({"stock_price": prices}, FACTS, "token", (0, 600), START, apply=True, session=fake)
    assert got["status"] == "stopped" and got["stopped"] == {"symbol": "4415", "http_status": 402} and got["rows"] == 1
    assert len(prices.batches) == 1 and len(calls) == 2
