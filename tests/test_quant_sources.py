from datetime import datetime

import pytest

pytestmark = pytest.mark.unit


def response(rows=None):
    return {"stat": "OK", "strDate": "20260101", "endDate": "20260918",
            "fields": ["資料日期", "股票代號", "股票名稱", "除權息前收盤價", "權值+息值", "權/息", "漲停價格", "跌停價格"],
            "data": rows if rows is not None else [
                ["115年03月17日", "2330", "台積電", "1,845.00", "6.000035", "息", "2,020.00", "1,660.00"],
                ["115年01月06日", "2442", "新美齊", "24.80", "0.671598", "權", "27.25", "21.75"]]}


def test_official_parser_uses_field_names_and_keeps_non_cash_events_unresolved():
    from src.research_workflow.sources import parse_exright

    payload = response()
    payload["fields"].reverse()
    payload["data"] = [list(reversed(row)) for row in payload["data"]]
    got = parse_exright(payload, ["2330", "2442"], "2026-01-01", "2026-09-18")
    assert got["events"][0]["date"] == "2026-03-17"
    assert got["events"][0]["cash_amount"] == pytest.approx(6.000035)
    assert got["unresolved"][0]["symbol"] == "2442"
    assert not got["coverage"]


@pytest.mark.parametrize("change", ["date", "schema", "status"])
def test_stale_dates_schema_drift_and_error_status_are_rejected(change):
    from src.research_workflow.sources import parse_exright

    payload = response()
    if change == "date":
        payload["strDate"] = "20250101"
    elif change == "schema":
        payload["fields"][4] = "未知金額欄位"
    else:
        payload["stat"] = "查詢失敗"
    with pytest.raises(ValueError):
        parse_exright(payload, ["2330"], "2026-01-01", "2026-09-18")


def test_cash_event_requires_matching_dividend_and_actual_payment_date():
    from src.research_workflow.sources import reconcile_cash

    rows = [{"stock_id": "2330", "cash_ex_dividend_date": "2026-03-17",
             "cash_earnings_distribution": "6.0", "cash_statutory_surplus": "0.0",
             "cash_dividend_payment_date": datetime(2026, 4, 9)}]
    event = {"symbol": "2330", "date": "2026-03-17", "cash_amount": 6.000035,
             "source": "TWSE_TWT49U"}
    good = reconcile_cash([event], rows)
    assert good["actions"][0]["cash_dividend"] == 6.0
    assert good["actions"][0]["cash_payment_date"] == "2026-04-09"
    assert good["actions"][0]["share_ratio"] == 1.0
    assert not good["coverage"]
    rows[0]["cash_earnings_distribution"] = "5.0"
    assert not reconcile_cash([event], rows)["actions"]
    assert reconcile_cash([event], rows)["unresolved"]
    rows[0]["cash_earnings_distribution"] = "6.0"
    rows[0]["cash_dividend_payment_date"] = ""
    assert not reconcile_cash([event], rows)["actions"]


def test_current_isin_listing_facts_do_not_become_historical_membership():
    from src.research_workflow.sources import parse_isin

    html = """<table><tr><th>有價證券代號及名稱</th><th>上市日</th><th>市場別</th><th>產業別</th></tr>
    <tr><td>2330　台積電</td><td>1994/09/05</td><td>上市</td><td>半導體業</td></tr>
    <tr><td>00635U　期元大S&amp;P黃金</td><td>2015/04/15</td><td>上市</td><td></td></tr></table>"""
    got = parse_isin(html, ["2330", "00635U"], "2026-10-26")
    assert got["listing_facts"][0]["listed_on"] == "1994-09-05"
    assert got["listing_facts"][1]["symbol"] == "00635U"
    assert not got["membership"]
    assert got["historical_membership_certified"] is False


def test_unconfirmed_listing_and_payment_conflicts_are_not_resolved_by_guessing():
    from src.research_workflow.sources import reconcile_cash

    event = {"symbol": "2330", "date": "2026-03-17", "cash_amount": 6.0, "source": "TWSE_TWT49U"}
    base = {"stock_id": "2330", "cash_ex_dividend_date": "2026-03-17", "cash_earnings_distribution": 6,
            "cash_statutory_surplus": 0, "cash_dividend_payment_date": "2026-04-09"}
    result = reconcile_cash([event], [base, {**base, "cash_dividend_payment_date": "2026-04-10"}])
    assert not result["actions"] and result["unresolved"]


def test_collector_archives_responses_and_never_claims_complete_coverage(tmp_path):
    import json

    from src.research_workflow.sources import collect

    class Reply:
        def __init__(self, content):
            self.content = content

        def raise_for_status(self):
            pass

    class Session:
        def get(self, url, **kwargs):
            assert url.startswith(("https://www.twse.com.tw/", "https://isin.twse.com.tw/"))
            if "TWT49U" in url:
                return Reply(json.dumps(response(), ensure_ascii=False).encode())
            return Reply("<table><tr><td>有價證券代號及名稱</td><td>上市日</td><td>市場別</td></tr><tr><td>2330 台積電</td><td>1994/09/05</td><td>上市</td></tr></table>".encode("cp950"))

    class Collection:
        def find(self, query, projection):
            return [{"stock_id": "2330", "cash_ex_dividend_date": "2026-03-17",
                     "cash_earnings_distribution": 6, "cash_statutory_surplus": 0,
                     "cash_dividend_payment_date": "2026-04-09"}]

    output = tmp_path / "sources"
    got = collect(output, ["2330"], "2026-01-01", "2026-09-18", session=Session(), db={"dividend_detail": Collection()})
    assert got["status"] == "partial_evidence"
    assert got["actions"] == 1
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["artifacts"] and not manifest["certified_complete"]
    evidence = json.loads((output / "evidence.json").read_text())
    assert evidence["coverage"] == [] and evidence["membership"] == [] and evidence["tradability"] == []
    assert len(evidence["actions"]) == 1
    with pytest.raises(FileExistsError):
        collect(output, ["2330"], "2026-01-01", "2026-09-18", session=Session(), db={"dividend_detail": Collection()})


def test_listing_facts_only_enrich_listing_date_not_historical_eligibility():
    import pandas as pd

    from src.research_workflow.evidence import enrich

    frame = pd.DataFrame({"date": ["2020-01-02"], "symbol": ["2330"]})
    evidence = {"listing_facts": [{"symbol": "2330", "listed_on": "1994-09-05",
                                  "source": "TWSE_ISIN_current_directory", "observed_on": "2026-10-26"}]}
    result = enrich(frame, evidence)
    assert result["listed_on"].iloc[0] == "1994-09-05"
    assert pd.isna(result["eligible"].iloc[0])
    assert "industry" not in result


def test_collect_cli_exposes_partial_evidence_as_non_success_status(tmp_path, monkeypatch, capsys):
    import json

    from scripts.quant_workflow import main
    from src.research_workflow import sources

    def fake_collect(output, symbols, start, end):
        assert symbols == ["2330", "0050"]
        return {"status": "partial_evidence", "actions": 1, "certified_complete": False}

    monkeypatch.setattr(sources, "collect", fake_collect)
    assert main(["collect", "--symbols", "2330,0050", "--start", "2026-01-01", "--end", "2026-09-18", "--out", str(tmp_path / "intake")]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "partial_evidence"


def test_issuer_browser_capture_only_accepts_common_share_twd_and_matching_events():
    from src.research_workflow.sources import reconcile_tsmc_capture

    capture = {"url": "https://investor.tsmc.com/english/dividends", "captured_at": "2026-10-26T00:00:00Z",
               "capture_method": "integrated_browser_rendered_DOM", "tables": [
                   {"headers": [["Period", "Per Common Share", "Cash Dividend", "Ex-Dividend Date", "Record Date", "Distribution Date", "Shareholders' Meeting"]],
                    "rows": [["3Q25", "-", "NT$6.00003573", "2026/03/17", "2026/03/23", "2026/04/09", "-"]]},
                   {"headers": [["Period", "Per ADS", "Cash Dividend", "Ex-Dividend Date", "Record Date", "Distribution Date", "Shareholders' Meeting"]],
                    "rows": [["3Q25", "-", "US$0.9389720", "2026/03/17", "2026/03/17", "2026/04/09", "-"]]}]}
    events = [{"symbol": "2330", "date": "2026-03-17", "cash_amount": 6.000035, "source": "TWSE_TWT49U"}]
    result = reconcile_tsmc_capture(events, capture)
    assert len(result["actions"]) == 1 and not result["unresolved"]
    assert result["actions"][0]["cash_dividend"] == pytest.approx(6.00003573)
    assert result["actions"][0]["cash_payment_date"] == "2026-04-09"
    assert result["actions"][0]["payment_date_source"] == capture["url"]
    events[0]["cash_amount"] = 5.0
    assert not reconcile_tsmc_capture(events, capture)["actions"]
    capture["url"] = "https://example.com/not-official"
    with pytest.raises(ValueError, match="issuer"):
        reconcile_tsmc_capture(events, capture)


@pytest.fixture
def finmind_receipts(tmp_path):
    import hashlib
    import json

    directory = tmp_path / "receipts"
    directory.mkdir()
    split = {"date": "2019-09-09", "stock_id": "6548", "type": "面額變更",
             "before_price": 312, "after_price": 31.2, "max_price": 34.3,
             "min_price": 28.1, "open_price": 31.2}
    par = {"date": "2019-09-09", "stock_id": "6548", "stock_name": "長科",
           "before_close": 312, "after_ref_close": 31.2, "after_ref_max": 34.3,
           "after_ref_min": 28.1, "after_ref_open": 31.2}
    rows = {"TaiwanStockDelisting": [
        {"date": "2020-01-02", "stock_id": "1230", "stock_name": "例子"},
        {"date": "2026-10-16", "stock_id": "1231", "stock_name": "截止後"}],
        "TaiwanStockSplitPrice": [split, {**split, "date": "2025-06-18", "stock_id": "0050",
                                         "type": "分割", "before_price": 188.65, "after_price": 47.16,
                                         "max_price": 51.85, "min_price": 42.45, "open_price": 47.16}],
        "TaiwanStockParValueChange": [par]}

    def write(change=None):
        if change:
            change(rows)
        checks = []
        for dataset, data in rows.items():
            content = json.dumps({"status": 200, "msg": "success", "data": data}, ensure_ascii=False).encode()
            (directory / f"{dataset}.response.json").write_bytes(content)
            checks.append({"dataset": dataset, "request": {"dataset": dataset}, "http_status": 200,
                           "raw_sha256": hashlib.sha256(content).hexdigest(), "rows": len(data)})
        (directory / "result.json").write_text(json.dumps({"captured_at": "2026-10-26T12:00:00+00:00",
                                                         "checks": checks}), encoding="utf-8")
        return directory

    return write


def test_finmind_import_filters_cutoff_and_merges_reference_events_without_entitlements(tmp_path, finmind_receipts):
    import json

    from src.research_workflow.sources import import_finmind

    output = tmp_path / "imported"
    result = import_finmind(output, finmind_receipts(), "2014-01-01", "2026-09-18")
    evidence = json.loads((output / "evidence.json").read_text(encoding="utf-8"))
    assert result["status"] == "partial_evidence"
    assert result["delisting_facts"] == 1 and result["reference_events"] == 2
    assert evidence["delisting_facts"][0]["delisted_on"] == "2020-01-02"
    assert evidence["delisting_facts"][0]["symbol"] == "1230"
    shared = next(row for row in evidence["reference_events"] if row["symbol"] == "6548")
    assert shared["sources"] == ["TaiwanStockParValueChange", "TaiwanStockSplitPrice"]
    assert shared["before_price"] == 312 and shared["after_price"] == 31.2
    assert all("share_ratio" not in row and "eligible" not in row for row in evidence["reference_events"])
    assert all(not evidence[key] for key in ("actions", "coverage", "membership", "tradability"))
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert not manifest["certified_complete"] and len(manifest["artifacts"]) == 4
    with pytest.raises(FileExistsError):
        import_finmind(output, output, "2014-01-01", "2026-09-18")


@pytest.mark.parametrize("defect", ["hash", "conflict", "duplicate", "schema", "date", "amount", "status", "kind"])
def test_finmind_import_rejects_untrusted_or_conflicting_receipts(tmp_path, finmind_receipts, defect):
    from src.research_workflow.sources import import_finmind

    def change(rows):
        if defect == "conflict":
            rows["TaiwanStockParValueChange"][0]["after_ref_max"] = 99
        elif defect == "duplicate":
            rows["TaiwanStockSplitPrice"].append(dict(rows["TaiwanStockSplitPrice"][0]))
        elif defect == "schema":
            del rows["TaiwanStockSplitPrice"][0]["open_price"]
        elif defect == "date":
            rows["TaiwanStockDelisting"][0]["date"] = "2020-02-30"
        elif defect == "amount":
            rows["TaiwanStockSplitPrice"][0]["after_price"] = -1
        elif defect == "kind":
            rows["TaiwanStockSplitPrice"][0]["type"] = "unrecognized"

    receipts = finmind_receipts(change)
    if defect in ("hash", "status"):
        path = receipts / "TaiwanStockDelisting.response.json"
        if defect == "hash":
            path.write_bytes(path.read_bytes() + b" ")
        else:
            import hashlib
            import json

            content = b'{"status":400,"msg":"permission denied","data":[]}'
            path.write_bytes(content)
            summary = json.loads((receipts / "result.json").read_text())
            summary["checks"][0]["raw_sha256"] = hashlib.sha256(content).hexdigest()
            (receipts / "result.json").write_text(json.dumps(summary))
    with pytest.raises((ValueError, TypeError)):
        import_finmind(tmp_path / "bad", receipts, "2014-01-01", "2026-09-18")


def test_finmind_import_empty_receipts_are_not_complete_coverage(tmp_path, finmind_receipts):
    from src.research_workflow.sources import import_finmind

    result = import_finmind(tmp_path / "empty", finmind_receipts(lambda rows: [data.clear() for data in rows.values()]),
                            "2014-01-01", "2026-09-18")
    assert result["status"] == "no_data" and not result["certified_complete"]


def test_finmind_import_cli_runs_without_network_or_database(tmp_path, finmind_receipts, capsys):
    import json

    from scripts.quant_workflow import main

    status = main(["import-finmind", "--receipts", str(finmind_receipts()), "--out", str(tmp_path / "cli"),
                   "--start", "2014-01-01", "--end", "2026-09-18"])
    assert status == 2
    assert json.loads(capsys.readouterr().out)["reference_events"] == 2


def test_finmind_import_retains_blank_event_types_as_unresolved(tmp_path, finmind_receipts):
    import json

    from src.research_workflow.sources import import_finmind

    def change(rows):
        rows["TaiwanStockSplitPrice"].append({"date": "2026-03-31", "stock_id": "00631L", "type": "",
            "before_price": 443.15, "after_price": 20.14, "max_price": 24.16, "min_price": 16.12, "open_price": 20.14})

    output = tmp_path / "blank"
    result = import_finmind(output, finmind_receipts(change), "2014-01-01", "2026-09-18")
    evidence = json.loads((output / "evidence.json").read_text(encoding="utf-8"))
    assert result["reference_events"] == 2 and result["unresolved"] == 1
    assert evidence["unresolved"][0]["symbol"] == "00631L"
    assert evidence["unresolved"][0]["kind"] == ""
    assert evidence["unresolved"][0]["before_price"] == 443.15
    assert "share_ratio" not in evidence["unresolved"][0]
    assert not evidence["actions"] and not evidence["coverage"]


def test_snapshot_dry_run_and_insert_only_idempotency(tmp_path, finmind_receipts, monkeypatch):
    import copy
    from types import SimpleNamespace

    from src import config
    from src.research_workflow.persistence import persist_snapshot
    from src.research_workflow.sources import import_finmind

    directory = tmp_path / "validated"
    import_finmind(directory, finmind_receipts(), "2014-01-01", "2026-09-18")
    monkeypatch.setattr(config, "get_db", lambda: pytest.fail("dry-run opened database"))
    dry = persist_snapshot(directory)
    assert dry["status"] == "dry_run" and not dry["certified_complete"]

    class Collection:
        def __init__(self):
            self.records = {}

        def update_one(self, query, update, upsert):
            assert upsert and set(update) == {"$setOnInsert"}
            key = query["_id"]
            inserted = key not in self.records
            if inserted:
                self.records[key] = copy.deepcopy(update["$setOnInsert"])
            return SimpleNamespace(upserted_id=key if inserted else None)

    collection = Collection()
    db = {"quant_source_evidence": collection}
    first = persist_snapshot(directory, db=db, apply=True)
    original = copy.deepcopy(collection.records)
    second = persist_snapshot(directory, db=db, apply=True)
    assert first["status"] == "stored" and second["status"] == "already_present"
    assert first["snapshot_id"] == dry["snapshot_id"] == second["snapshot_id"]
    assert collection.records == original and len(collection.records) == 1
    document = next(iter(collection.records.values()))
    assert not document["evidence"]["coverage"] and not document["certified_complete"]


@pytest.mark.parametrize("defect", ["normalized_evidence", "raw_receipt", "empty"])
def test_snapshot_refuses_modified_or_empty_evidence(tmp_path, finmind_receipts, defect):
    import json

    from src.research_workflow.persistence import persist_snapshot
    from src.research_workflow.sources import import_finmind

    receipts = finmind_receipts(lambda rows: [data.clear() for data in rows.values()] if defect == "empty" else None)
    directory = tmp_path / "validated"
    import_finmind(directory, receipts, "2014-01-01", "2026-09-18")
    if defect == "normalized_evidence":
        path = directory / "evidence.json"
        evidence = json.loads(path.read_text(encoding="utf-8"))
        evidence["coverage"] = [{"certified_complete": True}]
        path.write_text(json.dumps(evidence), encoding="utf-8")
    elif defect == "raw_receipt":
        path = directory / "raw" / "TaiwanStockSplitPrice.response.json"
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError):
        persist_snapshot(directory, db={}, apply=True)


def test_daily_capture_preserves_authenticated_raw_receipts_without_leaking_token(tmp_path, finmind_receipts):
    from src.research_workflow.persistence import capture_finmind
    from src.research_workflow.sources import import_finmind

    receipts = finmind_receipts()

    class Session:
        def get(self, url, *, params, headers, timeout):
            from types import SimpleNamespace

            assert url == "https://api.finmindtrade.com/api/v4/data"
            assert "token" not in params and headers["Authorization"] == "Bearer test-secret"
            assert timeout > 0
            return SimpleNamespace(status_code=200, content=(receipts / f"{params['dataset']}.response.json").read_bytes())

    output = tmp_path / "capture"
    capture_finmind(output, "test-secret", session=Session(), usage_fn=lambda token: (0, 600))
    assert "test-secret" not in (output / "result.json").read_text()
    result = import_finmind(tmp_path / "imported", output, "2014-01-01", "2026-09-18")
    assert result["reference_events"] == 2 and result["delisting_facts"] == 1


@pytest.mark.parametrize("usage", [None, (590, 600)])
def test_daily_capture_stops_before_requests_when_quota_is_unknown_or_low(tmp_path, usage):
    from src.research_workflow.persistence import capture_finmind

    class Session:
        def get(self, *args, **kwargs):
            pytest.fail("data API called without reserved quota")

    output = tmp_path / "quota"
    with pytest.raises(ValueError):
        capture_finmind(output, "test-secret", session=Session(), usage_fn=lambda token: usage)
    assert not output.exists()


def test_daily_capture_stops_on_permission_error_and_redacts_response(tmp_path):
    from types import SimpleNamespace

    from src.research_workflow.persistence import capture_finmind

    class Session:
        calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            return SimpleNamespace(status_code=400, content=b'{"status":400,"msg":"test-secret"}')

    session = Session()
    output = tmp_path / "denied"
    with pytest.raises(ValueError):
        capture_finmind(output, "test-secret", session=session, usage_fn=lambda token: (0, 600))
    assert session.calls == 1
    assert b"test-secret" not in (output / "TaiwanStockDelisting.response.json").read_bytes()


def test_source_sync_cli_dry_runs_do_not_call_network_or_database(tmp_path, finmind_receipts, monkeypatch, capsys):
    import json

    from scripts import quant_source_sync
    from src import config
    from src.research_workflow.sources import import_finmind

    monkeypatch.setattr(quant_source_sync, "capture_finmind", lambda *args, **kwargs: pytest.fail("dry-run fetched data"))
    monkeypatch.setattr(config, "get_db", lambda *args, **kwargs: pytest.fail("dry-run opened database"))
    assert quant_source_sync.main(["--collect"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "dry_run"
    directory = tmp_path / "validated"
    import_finmind(directory, finmind_receipts(), "2014-01-01", "2026-09-18")
    assert quant_source_sync.main(["--evidence", str(directory)]) == 0
    assert json.loads(capsys.readouterr().out)["certified_complete"] is False


def test_source_sync_cli_refuses_concurrent_apply_before_capture(tmp_path, monkeypatch, capsys):
    import json

    fcntl = pytest.importorskip("fcntl")
    from scripts import quant_source_sync

    monkeypatch.setattr(quant_source_sync, "ROOT", tmp_path)
    monkeypatch.setattr(quant_source_sync, "capture_finmind", lambda *args, **kwargs: pytest.fail("lock bypassed"))
    (tmp_path / "logs").mkdir()
    with (tmp_path / "logs" / ".quant_source_sync.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert quant_source_sync.main(["--collect", "--apply"]) == 2
    assert json.loads(capsys.readouterr().err)["error"] == "BlockingIOError"


@pytest.fixture
def stored_source_snapshot(tmp_path, finmind_receipts):
    import copy
    from types import SimpleNamespace

    from src.research_workflow.persistence import persist_snapshot
    from src.research_workflow.sources import import_finmind

    class Collection:
        document = None

        def update_one(self, query, update, upsert):
            self.document = copy.deepcopy(update["$setOnInsert"])
            return SimpleNamespace(upserted_id=query["_id"])

        def find_one(self, query):
            return copy.deepcopy(self.document) if query == {"_id": self.document["_id"]} else None

    directory = tmp_path / "stored"
    import_finmind(directory, finmind_receipts(), "2014-01-01", "2026-09-18")
    collection = Collection()
    db = {"quant_source_evidence": collection}
    result = persist_snapshot(directory, db=db, apply=True)
    return db, result["snapshot_id"]


def test_snapshot_reader_selects_explicit_version_symbols_and_dates_without_eligibility(stored_source_snapshot):
    from src.research_workflow.persistence import load_snapshot

    db, snapshot_id = stored_source_snapshot
    evidence = load_snapshot(snapshot_id, ["0050", "1230"], "2020-01-01", "2026-09-18", db=db)
    assert [row["symbol"] for row in evidence["reference_events"]] == ["0050"]
    assert [row["symbol"] for row in evidence["delisting_facts"]] == ["1230"]
    assert not evidence["membership"] and not evidence["tradability"] and not evidence["coverage"]
    assert evidence["source_snapshot"]["id"] == snapshot_id
    assert evidence["source_snapshot"]["observed_at"] == "2026-10-26T12:00:00+00:00"
    assert evidence["source_snapshot"]["certified_complete"] is False
    narrowed = load_snapshot(snapshot_id, ["0050"], "2026-01-01", "2026-09-18", db=db)
    assert not narrowed["reference_events"] and not narrowed["delisting_facts"]


@pytest.mark.parametrize("defect", ["tamper", "missing", "outside", "id"])
def test_snapshot_reader_rejects_untrusted_or_unavailable_versions(stored_source_snapshot, defect):
    from src.research_workflow.persistence import load_snapshot

    db, snapshot_id = stored_source_snapshot
    start, end = "2014-01-01", "2026-09-18"
    if defect == "tamper":
        db["quant_source_evidence"].document["evidence"]["reference_events"][0]["after_price"] = 999
    elif defect == "missing":
        snapshot_id = "0" * 64
    elif defect == "outside":
        end = "2026-10-26"
    else:
        snapshot_id = "latest"
    with pytest.raises(ValueError):
        load_snapshot(snapshot_id, ["0050"], start, end, db=db)


def test_snapshot_export_keeps_audit_blocked_and_preserves_selected_source_evidence(tmp_path, stored_source_snapshot, monkeypatch, capsys):
    import json

    import pandas as pd

    from scripts.quant_workflow import main
    from src import config

    db, snapshot_id = stored_source_snapshot
    monkeypatch.setattr(config, "get_db", lambda **kwargs: db)
    prices = tmp_path / "prices.csv"
    pd.DataFrame({"date": ["2025-06-18"], "symbol": ["0050"], "open": [47.16], "close": [48.0], "volume": [1000]}).to_csv(prices, index=False)
    output = tmp_path / "export.csv"
    assert main(["export", "--prices", str(prices), "--snapshot", snapshot_id, "--out", str(output)]) == 2
    audit = json.loads(capsys.readouterr().out)
    assert audit["status"] == "blocked" and audit["source_snapshot"]["id"] == snapshot_id
    evidence = json.loads(output.with_suffix(".evidence.json").read_text(encoding="utf-8"))
    assert evidence["reference_events"][0]["symbol"] == "0050"
    assert evidence["reference_events"][0]["date"] == "2025-06-18"
    assert not evidence["actions"] and not evidence["coverage"]