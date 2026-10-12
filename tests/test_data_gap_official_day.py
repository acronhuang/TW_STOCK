"""TDD: 官方按日期資料（TWSE rwd、TPEX www）解析為既有集合欄位，並驗證回傳的資料日。"""

from datetime import datetime

import pytest

from src.data_gap import official_day

pytestmark = pytest.mark.unit

DAY = datetime(2026, 9, 17)


def twse(fields, data, date="20260917", stat="OK"):
    return {"stat": stat, "date": date, "fields": fields, "data": data}


def tpex(fields, data, date="20260917", stat="ok"):
    return {"stat": stat, "date": date, "tables": [{"fields": fields, "data": data}]}


def test_twse_odd_lot_maps_volume_value_and_the_trade_price_as_close():
    payload = twse(["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "成交價", "最後揭示買價"],
                   [["00400A", "主動國泰動能高息", "14,044", "104", "226,918", "16.16", "16.15"],
                    ["2330", "台積電 ", "1,000", "3", "2,385,000", "2,385.00", "2,384.00"]])

    docs = official_day.parse("twse_odd", payload, DAY)

    assert docs[0] == {"stock_id": "00400A", "name": "主動國泰動能高息", "volume": 14044, "value": 226918, "close": 16.16,
                       "date": DAY, "market": "TWSE"}
    assert docs[1]["name"] == "台積電" and docs[1]["close"] == 2385.0


def test_twse_after_hours_uses_the_trade_quantity_and_amount_columns():
    payload = twse(["證券代號", "證券名稱", "成交數量", "成交筆數", "成交金額", "成交價", "最後揭示買量", "最後揭示賣量"],
                   [["00400A", "主動國泰動能高息", "45", "18", "655,650", "14.57", "0", "3,252"]])

    [doc] = official_day.parse("twse_after_hours", payload, DAY)

    assert doc == {"stock_id": "00400A", "name": "主動國泰動能高息", "volume": 45, "value": 655650, "close": 14.57,
                   "date": DAY, "market": "TWSE"}


def test_tpex_after_hours_uses_lots_and_the_fixed_price_columns():
    payload = tpex(["代號", "名稱", "委買筆數", "委買張數", "委賣筆數", "委賣張數", "成交價(元)", "成交筆數", "成交張數", "成交金額"],
                   [["00411A", "主動統一前沿科技        ", "6", "155", "4", "16", "9.91", "5", "16", "158,560"]])

    [doc] = official_day.parse("tpex_after_hours", payload, DAY)

    assert doc == {"stock_id": "00411A", "name": "主動統一前沿科技", "volume": 16, "value": 158560, "close": 9.91,
                   "date": DAY, "market": "TPEX"}


def test_tpex_odd_lot_maps_shares_amount_and_price():
    payload = tpex(["代號", "名稱", "成交股數", "成交筆數", "成交金額", "成交價格(元)"],
                   [["006201", "元大富櫃50", "220", "5", "9,752", "44.34"]])

    [doc] = official_day.parse("tpex_odd", payload, DAY)

    assert doc == {"stock_id": "006201", "name": "元大富櫃50", "volume": 220, "value": 9752, "close": 44.34,
                   "date": DAY, "market": "TPEX"}


def test_foreign_top20_keeps_rank_holdings_percentage_and_limit_despite_a_header_with_a_leading_space():
    payload = twse(["排行", "證券代號", "證券名稱", "發行股數", "外資及陸資尚可投資股數", " 全體外資及陸資持有股數",
                    "全體外資及陸資尚可投資比率", "全體外資及陸資持股比率", "法令投資上限比率"],
                   [[1, "2923", "鼎固-KY", "1,740,296,982", "8,797,363", "1,731,499,619", "0.50", "99.49", "100.00"]])

    [doc] = official_day.parse("foreign_top20", payload, DAY)

    assert doc == {"rank": 1, "stock_id": "2923", "name": "鼎固-KY", "shares_held": 1731499619, "shares_held_pct": 99.49,
                   "upper_limit": 100.0, "date": DAY}


def test_a_response_for_a_different_day_or_a_failed_status_yields_nothing():
    fields = ["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "成交價"]
    row = [["2330", "台積電", "1", "1", "1", "1"]]

    assert official_day.parse("twse_odd", twse(fields, row, date="20260918"), DAY) == []
    assert official_day.parse("twse_odd", twse(fields, row, stat="很抱歉，沒有符合條件的資料!"), DAY) == []
    assert official_day.parse("tpex_odd", {"stat": "參數輸入錯誤"}, DAY) == []


def test_rows_without_a_code_and_non_numeric_cells_are_tolerated():
    payload = twse(["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "成交價"],
                   [["", "x", "1", "1", "1", "1"], ["2330", "台積電", "--", "0", "--", "--"]])

    docs = official_day.parse("twse_odd", payload, DAY)

    assert len(docs) == 1 and docs[0]["volume"] == 0 and docs[0]["close"] == 0.0


class Collection:
    def __init__(self):
        self.ops = []

    def bulk_write(self, ops, ordered=False):
        self.ops.extend(ops)

        class Result:
            upserted_count = len(ops)
            modified_count = 0

        return Result()


def test_upsert_is_keyed_by_stock_and_date_and_stamps_utc_updated_at():
    collection = Collection()
    docs = official_day.parse("twse_odd", twse(["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "成交價"],
                                                [["2330", "台積電", "1", "1", "1", "1"]]), DAY)

    official_day.upsert(collection, docs, datetime(2026, 10, 11, 14, 0))

    op = collection.ops[0]
    assert op._filter == {"stock_id": "2330", "date": DAY} and op._upsert is True
    assert op._doc["$set"]["updated_at"] == datetime(2026, 10, 11, 14, 0)


def test_a_transient_source_failure_is_retried_once_before_the_source_is_skipped(monkeypatch):
    calls = []

    def flaky(source, day=None):
        calls.append(source)
        if source == "tpex_odd" and calls.count(source) == 1:
            raise OSError("timeout")
        fields = ["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "成交價"] if source == "twse_odd" \
            else ["代號", "名稱", "成交股數", "成交筆數", "成交金額", "成交價格(元)"]
        row = ["2330", "台積電", "1", "1", "1", "1"] if source == "twse_odd" else ["006201", "元大富櫃50", "1", "1", "1", "1"]
        return twse(fields, [row]) if source == "twse_odd" else tpex(fields, [row])

    monkeypatch.setattr(official_day, "fetch", flaky)

    docs = official_day.docs_for("odd", DAY, pause=0)

    assert sorted(d["stock_id"] for d in docs) == ["006201", "2330"] and calls.count("tpex_odd") == 2


def test_a_source_that_keeps_failing_is_skipped_so_the_other_markets_are_still_written(monkeypatch):
    def broken(source, day=None):
        if source == "tpex_odd":
            raise OSError("down")
        return twse(["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "成交價"], [["2330", "台積電", "1", "1", "1", "1"]])

    monkeypatch.setattr(official_day, "fetch", broken)

    assert [d["stock_id"] for d in official_day.docs_for("odd", DAY, pause=0)] == ["2330"]


def test_the_kind_to_collection_mapping_covers_all_five_sources():
    assert official_day.COLLECTION == {"odd": "odd_lot_trading", "after_hours": "after_hours_trading",
                                       "foreign_top20": "foreign_top20"}
    assert official_day.SOURCES == {"odd": ("twse_odd", "tpex_odd"), "after_hours": ("twse_after_hours", "tpex_after_hours"),
                                    "foreign_top20": ("foreign_top20",)}
