import json
from datetime import date
from decimal import Decimal

import pytest

pytestmark = pytest.mark.unit

FIELDS = ["恢復買賣日期", "ETF代號", "名稱", "分割(反分割)", "停止買賣前收盤價格", "恢復買賣參考價", "漲停價格", "跌停價格", "開盤競價基準"]
ROWS = [["114/06/18", "0050", "元大台灣50", "分割", "188.65", "47.16", "51.85", "42.45", "47.16"],
        ["115/03/31", "00631L", "元大台灣50正2", "", "443.15", "20.14", "24.16", "16.12", "20.14"],
        ["113/12/11", "00632R", "元大台灣50反1", "反分割", "3.28", "22.96", "25.25", "20.67", "22.96"],
        ["115/04/22", "00674R", "期元大S&P黃金反1", "反分割", "5.18", "25.90", "9,999.95", "0.01", "25.90"]]
ANNOUNCEMENT = """<html><body><table><tr><td>主旨</td><td>公告本公司經理之「元大ETF傘型證券投資信託基金之
台灣50單日正向2倍證券投資信託基金」(以下簡稱本基金，證券代碼00631L)分割後單位數及每受益權單位參考價。</td></tr>
<tr><td>說明</td><td>3.因應措施:
一、本次辦理分割受益憑證比例、價格：
(1)辦理受益憑證：分割。
分割比率（分割後受益權單位數/分割前受益權單位數）：22
（即分割後受益權單位數：分割前受益權單位數 = 22：1）
(3)分割/反分割後單位數：3,664,848,000
三、分割作業時程：
(1)受益憑證最後交易日期：115年3月24日
(6)新受益憑證上市(櫃)買賣日：115年3月31日
二、本基金分割後之每受益權單位參考價(即恢復買賣參考價)為20.14元。
分割前受益憑證最後交易日(115年3月
24日)之收盤價(443.15元)除上分割比率(22倍)計算得出(443.15/22=20.14)。
</td></tr></table></body></html>"""


def table(rows=None, stat="OK"):
    return {"stat": stat, "title": "ETF分割(反分割)恢復買賣參考價格", "fields": FIELDS, "data": ROWS if rows is None else rows}


def test_official_split_table_is_parsed_by_header_and_marks_unlimited_resumptions():
    from src.research_workflow.splits import parse_split_table

    events = parse_split_table(table(), "2011-01-01", "2026-12-31")
    by_symbol = {event["symbol"]: event for event in events}
    assert [event["date"] for event in events] == ["2024-12-11", "2025-06-18", "2026-03-31", "2026-04-22"]
    assert by_symbol["00631L"] == {"symbol": "00631L", "date": "2026-03-31", "kind": "", "prior_close": 443.15,
                                   "reference_price": 20.14, "upper_limit": 24.16, "lower_limit": 16.12, "no_limit": False}
    assert by_symbol["00674R"]["no_limit"] is True
    half = table([["115/04/22", "00674R", "x", "反分割", "5.18", "25.90", "9,999.95", "20.00", "25.90"]])
    assert parse_split_table(half, "2011-01-01", "2026-12-31")[0]["no_limit"] is False


@pytest.mark.parametrize("change", ["stat", "schema", "outside", "duplicate"])
def test_split_table_rejects_failed_changed_out_of_range_or_duplicated_responses(change):
    from src.research_workflow.splits import parse_split_table

    payload = table()
    if change == "stat":
        payload["stat"] = "查詢失敗"
    elif change == "schema":
        payload["fields"] = [name for name in FIELDS if name != "恢復買賣參考價"]
    elif change == "outside":
        payload["data"] = [ROWS[1]]
        with pytest.raises(ValueError):
            parse_split_table(payload, "2026-04-01", "2026-12-31")
        return
    else:
        payload["data"] = [ROWS[1], ROWS[1]]
    with pytest.raises(ValueError):
        parse_split_table(payload, "2011-01-01", "2026-12-31")


@pytest.mark.parametrize("prior,reference,expected", [
    ("443.15", "20.14", Decimal(22)), ("188.65", "47.16", Decimal(4)), ("245.30", "35.04", Decimal(7)),
    ("170.15", "24.30", Decimal(7)), ("3.28", "22.96", Decimal(1) / Decimal(7)), ("2.04", "12.23", Decimal(1) / Decimal(6)),
    ("100", "100", None), ("443.15", "21.00", None), ("443.15", "20.19", None), ("0.20", "0.02", None)])
def test_ratio_is_derived_only_when_the_official_formula_has_one_integer_solution(prior, reference, expected):
    from src.research_workflow.splits import derive_ratio

    assert derive_ratio(Decimal(prior), Decimal(reference)) == expected


def test_issuer_announcement_gives_explicit_ratio_dates_and_prices():
    from src.research_workflow.splits import parse_split_announcement

    assert parse_split_announcement(ANNOUNCEMENT) == {
        "symbol": "00631L", "ratio": Decimal(22), "last_trading_day": "2026-03-24", "resume_day": "2026-03-31",
        "reference_price": Decimal("20.14"), "prior_close": Decimal("443.15")}
    with pytest.raises(ValueError):
        parse_split_announcement(ANNOUNCEMENT.replace("22\n", "\n", 1).replace("分割比率", "比例"))


def test_announcement_must_agree_with_the_official_table_before_it_confirms_a_ratio():
    from src.research_workflow.splits import parse_split_announcement, parse_split_table, reconcile_announcement

    event = next(e for e in parse_split_table(table(), "2011-01-01", "2026-12-31") if e["symbol"] == "00631L")
    announced = parse_split_announcement(ANNOUNCEMENT)
    assert reconcile_announcement(event, announced) == Decimal(22)
    for field, value in (("ratio", Decimal(21)), ("resume_day", "2026-04-01"), ("reference_price", Decimal("20.15")),
                         ("prior_close", Decimal("443.1")), ("symbol", "0050")):
        with pytest.raises(ValueError):
            reconcile_announcement(event, {**announced, field: value})


class Reply:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        pass


def session_for(table_payload=None, page=ANNOUNCEMENT):
    class Session:
        def get(self, url, params=None, **kwargs):
            if url.endswith("/split/TWTCAU"):
                return Reply(json.dumps(table_payload or table(), ensure_ascii=False).encode())
            assert "ETFortune/announcement" in url
            return Reply(page.encode())

    return Session()


def test_collect_splits_emits_explicit_actions_archives_raw_pages_and_never_certifies_coverage(tmp_path):
    from src.research_workflow.splits import collect_splits

    out = tmp_path / "splits"
    url = "https://www.twse.com.tw/zh/ETFortune/announcement?company=A00005&date=20260330&seq=1&fund=00631L&type=all"
    got = collect_splits(out, ["0050", "00631L"], "2014-01-01", "2026-09-18", announcements={"00631L": url}, session=session_for())
    assert got["status"] == "partial_evidence" and got["certified_complete"] is False
    assert got["actions"] == 2 and got["unresolved"] == 0 and got["announcement_confirmed"] == 1
    evidence = json.loads((out / "evidence.json").read_text(encoding="utf-8"))
    by_symbol = {row["symbol"]: row for row in evidence["actions"]}
    assert by_symbol["00631L"]["share_ratio"] == 22.0 and by_symbol["00631L"]["date"] == "2026-03-31"
    assert by_symbol["00631L"]["cash_dividend"] == 0.0 and by_symbol["00631L"]["basis"] == "issuer_announcement_confirmed"
    assert by_symbol["0050"]["share_ratio"] == 4.0 and by_symbol["0050"]["basis"] == "official_reference_price_formula"
    assert evidence["coverage"] == [] and evidence["membership"] == [] and evidence["tradability"] == []
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["certified_complete"] is False and manifest["earliest_table_event"] == "2024-12-11"
    assert {item["path"] for item in manifest["artifacts"]} == {"raw/twtcau.json", "raw/announcement_00631L.html"}
    with pytest.raises(FileExistsError):
        collect_splits(out, ["0050"], "2014-01-01", "2026-09-18", session=session_for())


def test_collect_splits_leaves_events_unresolved_when_announcement_or_formula_disagree(tmp_path):
    from src.research_workflow.splits import collect_splits

    url = "https://www.twse.com.tw/zh/ETFortune/announcement?company=A00005&date=20260330&seq=1&fund=00631L&type=all"
    got = collect_splits(tmp_path / "bad", ["00631L"], "2014-01-01", "2026-09-18", announcements={"00631L": url},
                         session=session_for(page=ANNOUNCEMENT.replace("20.14元", "20.15元")))
    assert got["actions"] == 0 and got["unresolved"] == 1
    odd = table([["115/03/31", "00631L", "元大台灣50正2", "", "443.15", "21.00", "24.16", "16.12", "21.00"]])
    got = collect_splits(tmp_path / "odd", ["00631L"], "2014-01-01", "2026-09-18", session=session_for(odd))
    assert got["actions"] == 0 and got["unresolved"] == 1


def test_split_actions_enter_the_panel_without_filling_other_days():
    import pandas as pd

    from src.research_workflow.evidence import enrich

    frame = pd.DataFrame([{"date": day, "symbol": "00631L", "open": 1.0, "close": 1.0, "volume": 10}
                          for day in ("2026-03-24", "2026-03-31")])
    action = {"symbol": "00631L", "date": "2026-03-31", "cash_dividend": 0.0, "share_ratio": 22.0, "source": "TWSE_TWTCAU"}
    got = enrich(frame, {"actions": [action]}).set_index("date")
    assert got.loc["2026-03-31", "share_ratio"] == 22.0 and got["share_ratio"].isna().sum() == 1


def test_cli_exposes_the_splits_command(tmp_path, monkeypatch):
    from scripts import quant_workflow

    seen = {}

    def fake(out, symbols, start, end, announcements=None):
        seen.update(symbols=symbols, announcements=announcements, start=start)
        return {"status": "partial_evidence"}

    monkeypatch.setattr("src.research_workflow.splits.collect_splits", fake)
    assert quant_workflow.main(["splits", "--symbols", "0050,00631L", "--announcement", "00631L=https://x/y", "--out", str(tmp_path / "s")]) == 2
    assert seen["symbols"] == ["0050", "00631L"] and seen["announcements"] == {"00631L": "https://x/y"} and seen["start"] == "2014-01-01"
    assert date.fromisoformat(seen["start"])
