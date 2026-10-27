import json
from datetime import date, datetime

import pytest

pytestmark = pytest.mark.unit


def isin_page(rows):
    body = "".join(f"<tr><td>{code}　{name}</td><td>X</td><td>{listed}</td><td>{market}</td><td></td><td>ESVUFR</td></tr>"
                   for code, name, listed, market in rows)
    return ("<table><tr><th>有價證券代號及名稱</th><th>國際證券辨識號碼(ISIN Code)</th><th>上市日</th><th>市場別</th>"
            f"<th>產業別</th><th>CFICode</th></tr>{body}</table>")


def build(symbols, listings=None, first=None, delistings=None, start="2025-01-01", end="2026-09-18"):
    from src.research_workflow.membership import build_membership

    return build_membership(symbols, start, end, listings or {}, first or {}, delistings or [], "2026-10-27T12:00:00+08:00")


def spans(result, symbol):
    return [(row["start"], row["end"], row["eligible"], row["reason"]) for row in result["membership"] if row["symbol"] == symbol]


@pytest.mark.parametrize("symbol,allowed", [("2330", True), ("0050", True), ("00631L", True), ("006208", True),
                                            ("2881A", False), ("030025", False), ("0999", False), ("91001", False)])
def test_registered_instruments_are_ordinary_four_digit_stocks_and_etfs_only(symbol, allowed):
    from src.research_workflow.membership import instrument_allowed

    assert instrument_allowed(symbol) is allowed


def test_listed_symbol_is_eligible_from_its_listing_date_and_ineligible_before_it():
    got = build(["00631L"], listings={"00631L": date(2025, 3, 3)})
    assert spans(got, "00631L") == [("2025-01-01", "2025-03-02", False, "before_listing"),
                                    ("2025-03-03", "2026-09-18", True, "listed")]
    row = got["membership"][1]
    assert row["listed_on"] == "2025-03-03" and row["basis"] == "isin_listing_date"
    assert row["available_at"] == "2025-03-03T00:00:00" and row["source"]


def test_listing_before_the_window_gives_one_eligible_span():
    got = build(["0050"], listings={"0050": date(2003, 6, 30)})
    assert spans(got, "0050") == [("2025-01-01", "2026-09-18", True, "listed")]


def test_delisting_ends_eligibility_the_day_before_the_delisting_date():
    got = build(["2478"], listings={"2478": date(2000, 1, 3)},
                delistings=[{"symbol": "2478", "delisted_on": "2026-03-10", "source": "TaiwanStockDelisting"}])
    assert spans(got, "2478") == [("2025-01-01", "2026-03-09", True, "listed"), ("2026-03-10", "2026-09-18", False, "delisted")]


def test_unknown_listing_date_falls_back_to_the_first_observed_price_as_a_lower_bound():
    got = build(["2478"], first={"2478": date(2013, 1, 2)},
                delistings=[{"symbol": "2478", "delisted_on": "2026-03-10", "source": "TaiwanStockDelisting"}])
    assert got["membership"][0]["basis"] == "first_observed_price_lower_bound"
    assert got["membership"][0]["listed_on"] == "2013-01-02"
    assert got["basis_counts"] == {"first_observed_price_lower_bound": 1}


@pytest.mark.parametrize("case", ["no_dates", "two_delistings", "delisted_before_listed"])
def test_ambiguous_symbols_are_left_unresolved_without_any_membership_rows(case):
    kwargs = {"listings": {"2478": date(2000, 1, 3)}}
    if case == "no_dates":
        kwargs = {}
    elif case == "two_delistings":
        kwargs["delistings"] = [{"symbol": "2478", "delisted_on": "2025-03-10"}, {"symbol": "2478", "delisted_on": "2026-03-10"}]
    else:
        kwargs["delistings"] = [{"symbol": "2478", "delisted_on": "1999-03-10"}]
    got = build(["2478"], **kwargs)
    assert not got["membership"] and got["unresolved"][0]["symbol"] == "2478"


def test_delisting_on_the_listing_day_is_ambiguous():
    got = build(["2478"], listings={"2478": date(2000, 1, 3)}, delistings=[{"symbol": "2478", "delisted_on": "2000-01-03"}])
    assert not got["membership"] and got["unresolved"][0]["reason"] == "delisting_not_after_listing"


def test_instruments_outside_the_registered_universe_are_never_eligible():
    got = build(["2881A"], listings={"2881A": date(2010, 1, 4)})
    assert spans(got, "2881A") == [("2025-01-01", "2026-09-18", False, "instrument_not_in_registered_universe")]


def test_membership_evidence_closes_only_listing_and_eligibility_gaps():
    import pandas as pd

    from src.research_workflow.evidence import enrich

    frame = pd.DataFrame([{"date": "2026-01-06", "symbol": "00631L", "open": 1.0, "close": 1.0, "volume": 10},
                          {"date": "2025-01-06", "symbol": "00631L", "open": 1.0, "close": 1.0, "volume": 10}])
    got = enrich(frame, {"membership": build(["00631L"], listings={"00631L": date(2025, 3, 3)})["membership"]})
    by_date = got.set_index("date")
    assert bool(by_date.loc["2026-01-06", "eligible"]) is True and bool(by_date.loc["2025-01-06", "eligible"]) is False
    assert (got["listed_on"] == "2025-03-03").all()
    assert got["can_buy"].isna().all() and got["cash_dividend"].isna().all()


class Reply:
    def __init__(self, text):
        self.content = text.encode("cp950")

    def raise_for_status(self):
        pass


def fake_session(twse=None, tpex=None):
    pages = {"2": isin_page(twse if twse is not None else [("0050", "元大台灣50", "2003/06/30", "上市"),
                                                          ("00631L", "元大台灣50正2", "2014/10/31", "上市")]),
             "4": isin_page(tpex if tpex is not None else [("6488", "環球晶", "2015/09/25", "上櫃")])}

    class Session:
        def get(self, url, params=None, **kwargs):
            assert url == "https://isin.twse.com.tw/isin/C_public.jsp"
            return Reply(pages[params["strMode"]])

    return Session()


class Prices:
    def aggregate(self, pipeline, **kwargs):
        assert pipeline[0]["$match"]["symbol"]["$in"]
        assert pipeline[1]["$group"]["first"] == {"$min": "$date"}
        return [{"_id": "2478", "first": datetime(2013, 1, 2)}, {"_id": "0050", "first": datetime(2013, 1, 2)}]


def stored_snapshot(snapshot_id, symbols, start, end, db=None):
    return {"delisting_facts": [{"symbol": "2478", "delisted_on": "2026-03-10", "source": "TaiwanStockDelisting"}],
            "source_snapshot": {"id": "x" * 64}}


def test_collect_membership_archives_isin_pages_and_stays_partial(tmp_path, monkeypatch):
    from src.research_workflow import membership

    monkeypatch.setattr(membership, "load_snapshot", stored_snapshot)
    out = tmp_path / "membership"
    got = membership.collect_membership(out, ["0050", "00631L", "2478"], "2025-01-01", "2026-09-18", "a" * 64,
                                        session=fake_session(), db={"stock_price": Prices()})
    assert got["status"] == "partial_evidence" and got["certified_complete"] is False and got["unresolved"] == 0
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["certified_complete"] is False and manifest["basis_counts"] == {
        "first_observed_price_lower_bound": 1, "isin_listing_date": 2}
    assert {item["path"] for item in manifest["artifacts"]} >= {"raw/isin_twse.html", "raw/isin_tpex.html", "raw/first_prices.json"}
    assert manifest["limitations"] and "eligibility_rule" in manifest
    evidence = json.loads((out / "evidence.json").read_text(encoding="utf-8"))
    assert {row["symbol"] for row in evidence["membership"]} == {"0050", "00631L", "2478"}
    assert evidence["actions"] == [] and evidence["tradability"] == [] and evidence["coverage"] == []
    with pytest.raises(FileExistsError):
        membership.collect_membership(out, ["0050"], "2025-01-01", "2026-09-18", "a" * 64, session=fake_session(), db={"stock_price": Prices()})


def test_collect_membership_rejects_a_symbol_listed_on_both_markets(tmp_path, monkeypatch):
    from src.research_workflow import membership

    monkeypatch.setattr(membership, "load_snapshot", stored_snapshot)
    both = fake_session(tpex=[("0050", "元大台灣50", "2010/01/04", "上櫃")])
    got = membership.collect_membership(tmp_path / "m", ["0050"], "2025-01-01", "2026-09-18", "a" * 64,
                                        session=both, db={"stock_price": Prices()})
    assert got["unresolved"] == 1
    assert json.loads((tmp_path / "m" / "evidence.json").read_text(encoding="utf-8"))["membership"] == []


def test_cli_exposes_the_membership_command(tmp_path, monkeypatch):
    from scripts import quant_workflow

    seen = {}

    def fake(out, symbols, start, end, snapshot):
        seen.update(out=out, symbols=symbols, start=start, end=end, snapshot=snapshot)
        return {"status": "partial_evidence"}

    monkeypatch.setattr("src.research_workflow.membership.collect_membership", fake)
    assert quant_workflow.main(["membership", "--symbols", "0050,00631L", "--snapshot", "a" * 64, "--out", str(tmp_path / "m")]) == 2
    assert seen["symbols"] == ["0050", "00631L"] and seen["snapshot"] == "a" * 64 and seen["start"] == "2014-01-01"
