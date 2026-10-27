import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

pytestmark = pytest.mark.unit

FIELDS = ["恢復買賣日期", "ETF代號", "名稱", "分割(反分割)", "停止買賣前收盤價格", "恢復買賣參考價", "漲停價格", "跌停價格", "開盤競價基準"]
ROWS = [["113/12/11", "00632R", "元大台灣50反1", "反分割", "3.28", "22.96", "25.25", "20.67", "22.96"],
        ["114/06/18", "0050", "元大台灣50", "分割", "188.65", "47.16", "51.85", "42.45", "47.16"],
        ["115/03/31", "00631L", "元大台灣50正2", "", "443.15", "20.14", "24.16", "16.12", "20.14"],
        ["114/10/22", "00673R", "期元大S&P原油反1", "反分割", "7.02", "28.08", "9,999.95", "0.01", "28.08"]]


def table(rows=None, stat="OK"):
    return {"stat": stat, "fields": FIELDS, "data": ROWS if rows is None else rows}


def test_official_table_becomes_corporate_actions_with_price_ratios_and_blank_kinds_inferred():
    from src.data_gap.etf_splits import parse_split_table

    events = parse_split_table(table())
    assert [(e["symbol"], e["event_date"].date().isoformat(), e["type"]) for e in events] == [
        ("00632R", "2024-12-11", "反分割"), ("0050", "2025-06-18", "分割"),
        ("00673R", "2025-10-22", "反分割"), ("00631L", "2026-03-31", "分割")]
    by_symbol = {e["symbol"]: e for e in events}
    assert by_symbol["00631L"]["ratio"] == pytest.approx(20.14 / 443.15, abs=1e-6) and by_symbol["00631L"]["type"] == "分割"
    assert by_symbol["0050"]["ratio"] == pytest.approx(0.249986, abs=1e-6)
    assert by_symbol["00632R"]["ratio"] == pytest.approx(7.0, abs=1e-6) and by_symbol["00632R"]["type"] == "反分割"
    assert by_symbol["00631L"]["event_date"] == datetime(2026, 3, 31) and by_symbol["00631L"]["source"] == "TWSE_TWTCAU"
    assert [e["event_date"] for e in events] == sorted(e["event_date"] for e in events)


@pytest.mark.parametrize("change", ["stat", "schema", "kind", "ratio", "duplicate", "price", "date"])
def test_official_table_rejects_failed_changed_or_implausible_rows(change):
    from src.data_gap.etf_splits import parse_split_table

    payload = table()
    if change == "stat":
        payload["stat"] = "查詢失敗"
    elif change == "schema":
        payload["fields"] = [name for name in FIELDS if name != "恢復買賣參考價"]
    elif change == "kind":
        payload["data"] = [["114/06/18", "0050", "元大台灣50", "反分割", "188.65", "47.16", "51.85", "42.45", "47.16"]]
    elif change == "ratio":
        payload["data"] = [["114/06/18", "0050", "元大台灣50", "反分割", "1.00", "25.00", "9,999.95", "0.01", "25.00"]]
    elif change == "duplicate":
        payload["data"] = [ROWS[1], ROWS[1]]
    elif change == "price":
        payload["data"] = [["114/06/18", "0050", "元大台灣50", "分割", "0", "47.16", "51.85", "42.45", "47.16"]]
    else:
        payload["data"] = [["2025-06-18", "0050", "元大台灣50", "分割", "188.65", "47.16", "51.85", "42.45", "47.16"]]
    with pytest.raises(ValueError):
        parse_split_table(payload)


def test_missing_actions_lists_official_events_without_a_corporate_action_record():
    from src.data_gap.etf_splits import missing_actions, parse_split_table

    events = parse_split_table(table())
    have = {("0050", datetime(2025, 6, 18)), ("00632R", datetime(2024, 12, 11))}
    assert [e["symbol"] for e in missing_actions(events, have)] == ["00673R", "00631L"]
    assert missing_actions(events, {(e["symbol"], e["event_date"]) for e in events}) == []


class Reply:
    def __init__(self, payload):
        import json

        self.content = json.dumps(payload, ensure_ascii=False).encode()

    def raise_for_status(self):
        pass

    def json(self):
        import json

        return json.loads(self.content)


def test_collector_reads_the_official_table_for_the_whole_history_and_the_adjuster_accepts_the_events():
    import backfill_adj_close
    import collect_corporate_actions as cca

    calls = []

    class Session:
        def get(self, url, params=None, **kwargs):
            calls.append((url, params))
            return Reply(table())

    events = cca.fetch_etf_splits(Session(), today=datetime(2026, 10, 27))
    assert len(events) == 4 and calls[0][0].endswith("/split/TWTCAU")
    assert calls[0][1]["startDate"] == "20110101" and calls[0][1]["endDate"] == "20261027"

    class Collection:
        def find(self, query, projection):
            return [{"event_date": e["event_date"], "ratio": e["ratio"]} for e in events if e["symbol"] == query["symbol"]]

    class Db:
        corporate_actions = Collection()

    assert [round(ratio, 6) for _, ratio in backfill_adj_close._corp_events(Db(), "00631L")] == [round(20.14 / 443.15, 6)]
    assert [round(ratio, 3) for _, ratio in backfill_adj_close._corp_events(Db(), "00632R")] == [7.0]


def test_audit_reports_official_split_events_missing_from_corporate_actions():
    import price_coverage_audit as audit

    from src.data_gap.etf_splits import parse_split_table

    events = parse_split_table(table())

    class Actions:
        def __init__(self, rows):
            self.rows = rows

        def find(self, query, projection):
            assert query == {"type": {"$in": ["分割", "反分割"]}}
            return self.rows

    ok, message = audit.run_splits(events, {"corporate_actions": Actions([{"symbol": "0050", "event_date": datetime(2025, 6, 18)}])})
    assert ok is False and "缺 corporate_actions 3 筆" in message and "00631L(2026-03-31)" in message
    everything = [{"symbol": e["symbol"], "event_date": e["event_date"]} for e in events]
    ok, message = audit.run_splits(events, {"corporate_actions": Actions(everything)})
    assert ok is True and "4 筆都已在" in message