import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import backfill_by_date as bbd
import twse_daily_update as tdu

pytestmark = pytest.mark.unit


class FakeResp:
    def __init__(self, payload):
        self.content = json.dumps(payload).encode()
        self.headers = {"Content-Length": str(len(self.content))}

    def raise_for_status(self):
        pass

    def json(self):
        return json.loads(self.content)


@pytest.mark.parametrize("code,expected", [
    ("2330", True), ("0050", True), ("006208", True), ("030025", True),
    ("00631L", True), ("00679B", True), ("00400A", True), ("00625K", True),
    ("2881A", False), ("03033X", False), ("00A", False), ("0063", True), ("", False), ("ABC", False)])
def test_price_codes_include_digit_codes_and_letter_etfs_but_not_preferred_shares_or_warrants(code, expected):
    from src.data_gap.codes import is_price_code

    assert is_price_code(code) is expected


def test_daily_twse_update_keeps_letter_etfs_and_still_skips_preferred_shares_and_unpriced_rows(monkeypatch):
    rows = [{"Date": "1151022", "Code": code, "Name": code, "ClosingPrice": close, "OpeningPrice": "1", "HighestPrice": "1",
             "LowestPrice": "1", "TradeVolume": "10", "TradeValue": "10", "Change": "0", "Transaction": "1"}
            for code, close in (("0050", "106.9"), ("00631L", "35.61"), ("2881A", "60"), ("1538", ""))]
    monkeypatch.setattr(tdu.requests, "get", lambda url, **kw: FakeResp(rows))
    assert [rec["stock_id"] for rec in tdu.fetch_twse()] == ["0050", "00631L"]


def test_daily_tpex_update_keeps_letter_etfs_but_not_other_letter_codes(monkeypatch):
    rows = [{"Date": "1151022", "SecuritiesCompanyCode": code, "CompanyName": code, "Close": "10", "Open": "10",
             "High": "10", "Low": "10", "TradingShares": "1", "Change": "0"}
            for code in ("6488", "00679B", "70001P", "2881A")]
    monkeypatch.setattr(tdu, "_get_tpex_json", lambda url: rows)
    assert [rec["stock_id"] for rec in tdu.fetch_tpex()] == ["6488", "00679B"]


def test_date_backfill_parsers_keep_letter_etfs_too(monkeypatch):
    def line(code):
        return [code, "名", "100", "5", "1,000", "1", "10", "10", "10", "10"]

    table = {"title": "個股日成交資訊", "data": [line("0050"), line("00631L"), line("2881A")]}
    monkeypatch.setattr(bbd.requests, "get", lambda url, **kw: FakeResp({"stat": "OK", "tables": [table]}))
    assert [rec["stock_id"] for rec in bbd.fetch_twse("20260731")] == ["0050", "00631L"]
    otc = [["6488", "名", "10", "0", "10", "10", "10", "10", "100", "1000", "5"],
           ["00679B", "名", "10", "0", "10", "10", "10", "10", "100", "1000", "5"],
           ["70001P", "名", "10", "0", "10", "10", "10", "10", "100", "1000", "5"]]
    monkeypatch.setattr(bbd.requests, "get", lambda url, **kw: FakeResp({"tables": [{"data": otc}]}))
    monkeypatch.setattr(bbd.requests, "post", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("down")))
    assert [rec["stock_id"] for rec in bbd.fetch_tpex("20260731")] == ["6488", "00679B"]


class Collection:
    def __init__(self, found=None):
        self.found, self.batches = found or [], []

    def find(self, query, projection=None):
        return self.found

    def bulk_write(self, operations, ordered=False):
        self.batches.append(operations)

        class Result:
            upserted_count = len(operations)

        return Result()


def record(code, day):
    return {"stock_id": code, "symbol": code, "date": datetime.fromisoformat(day), "close": 1, "adj_close": 1}


def test_letter_etf_backfill_inserts_only_missing_rows_and_never_rewrites_existing_prices():
    prices = Collection()
    db = {"stock_price": prices, "trading_dates": Collection([{"date": "2026-08-03"}, {"date": "2026-07-31"}])}
    seen = []

    def twse(day):
        seen.append(day)
        return [record("0050", "2026-07-31"), record("00631L", "2026-07-31")]

    def tpex(day):
        raise RuntimeError("TPEX down")

    result = bbd.backfill_letter_etfs(db, "20260731", "20260803", apply=True, twse=twse, tpex=tpex, pause=0)
    assert seen == ["20260731", "20260803"]
    operations = [op for batch in prices.batches for op in batch]
    assert [op._filter["stock_id"] for op in operations] == ["00631L", "00631L"]
    assert all("$set" not in op._doc and "$setOnInsert" in op._doc and op._upsert for op in operations)
    assert result["inserted_candidates"] == 2 and result["applied"] is True
    assert [item["market"] for item in result["failures"]] == ["tpex", "tpex"]


def test_letter_etf_backfill_is_a_dry_run_unless_applied():
    prices = Collection()
    db = {"stock_price": prices, "trading_dates": Collection([{"date": "2026-07-31"}])}
    result = bbd.backfill_letter_etfs(db, "20260731", "20260731", apply=False,
                                      twse=lambda day: [record("00631L", "2026-07-31")], tpex=lambda day: [], pause=0)
    assert not prices.batches and result["inserted_candidates"] == 1 and result["applied"] is False


def test_coverage_gaps_list_official_priced_codes_missing_from_the_price_table():
    from src.data_gap.coverage import missing_rows

    official = [record("0050", "2026-10-22"), record("00631L", "2026-10-22"), record("2881A", "2026-10-22"),
                record("2330", "2026-10-22")]
    present = {"2026-10-22": {"0050", "2330"}}
    assert missing_rows(official, present) == [("2026-10-22", "00631L")]
    assert missing_rows(official, {}) == [("2026-10-22", "0050"), ("2026-10-22", "00631L"), ("2026-10-22", "2330")]
    assert missing_rows([], present) == []


def test_audit_script_fails_with_a_readable_message_only_when_rows_are_missing():
    import price_coverage_audit as audit

    class Prices:
        def distinct(self, field, query):
            return ["0050"]

    ok = audit.run([record("0050", "2026-10-22")], {"stock_price": Prices()})
    assert ok == (True, "官方當日有收盤價的 1 檔都已在價格表")
    ok, message = audit.run([record("0050", "2026-10-22"), record("00631L", "2026-10-22")], {"stock_price": Prices()})
    assert ok is False and "00631L" in message and "1 檔" in message
