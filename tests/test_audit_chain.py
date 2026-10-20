"""TDD: 防篡改指紋鏈——登記、核對、被改／刪／重寫都要被抓到，且未動過的帳本要通過。"""

import json
from datetime import datetime
from decimal import Decimal

import pytest
from bson.decimal128 import Decimal128

from src.ops import audit_chain as chain

pytestmark = pytest.mark.integration

LEDGER = "chain_test_ledger"
NOW = datetime(2026, 10, 13, 9, 0)


@pytest.fixture
def db(write_db):
    for name in (LEDGER, chain.CHAIN):
        write_db[name].drop()
    write_db[LEDGER].insert_many([
        {"symbol": "2330", "price": Decimal128("1100.5"), "date": datetime(2026, 10, 9)},
        {"symbol": "2317", "price": Decimal128("210.0"), "date": datetime(2026, 10, 9)},
        {"symbol": "2454", "price": Decimal128("1500"), "date": datetime(2026, 10, 12)},
    ])
    return write_db


def build(db):
    return chain.register(db, LEDGER, NOW)


def check(db, head_file=None):
    return chain.verify(db, (LEDGER,), head_file)


def test_the_digest_ignores_key_order_and_the_id_and_reads_decimals_and_dates():
    a = {"b": Decimal128("1.5"), "a": datetime(2026, 10, 9), "_id": 1}
    b = {"a": datetime(2026, 10, 9), "b": Decimal128("1.5"), "_id": 2}

    assert chain.digest(a) == chain.digest(b)
    assert chain.digest(a) != chain.digest({**a, "b": Decimal128("1.6")})
    assert Decimal("1.5") == Decimal(chain.canonical(a).split('"b":"')[1].split('"')[0])


def test_registering_links_each_entry_to_the_previous_one_and_a_rerun_adds_nothing(db):
    assert build(db) == 3 and build(db) == 0

    entries = list(db[chain.CHAIN].find().sort("seq", 1))
    assert [e["seq"] for e in entries] == [1, 2, 3]
    assert entries[0]["prev"] == chain.GENESIS and entries[1]["prev"] == entries[0]["hash"]


def test_an_untouched_ledger_passes_and_new_rows_extend_the_chain(db):
    build(db)
    assert check(db)["ok"]

    db[LEDGER].insert_one({"symbol": "2603", "price": Decimal128("200")})
    assert build(db) == 1 and check(db)["ok"] and check(db)["entries"] == 4


def test_a_changed_field_is_reported_as_modified(db):
    build(db)
    db[LEDGER].update_one({"symbol": "2330"}, {"$set": {"price": Decimal128("999")}})

    result = check(db)

    assert not result["ok"] and len(result["modified"]) == 1 and result["missing"] == []


def test_a_deleted_row_is_reported_as_missing(db):
    build(db)
    db[LEDGER].delete_one({"symbol": "2317"})

    result = check(db)

    assert not result["ok"] and len(result["missing"]) == 1


def test_editing_a_chain_entry_or_removing_one_in_the_middle_breaks_the_links(db):
    build(db)
    db[chain.CHAIN].update_one({"seq": 2}, {"$set": {"digest": "f" * 64}})
    assert check(db)["broken_links"]

    build_again = db[chain.CHAIN].delete_one({"seq": 2})
    assert build_again.deleted_count == 1 and any("不連續" in p for p in check(db)["broken_links"])


def test_a_chain_rewritten_end_to_end_is_caught_by_the_saved_head(db, tmp_path):
    build(db)
    head_file = tmp_path / "head.json"
    chain.write_head(db, head_file, NOW)
    assert check(db, head_file)["ok"]

    db[LEDGER].update_one({"symbol": "2330"}, {"$set": {"price": Decimal128("999")}})
    db[chain.CHAIN].drop()
    build(db)                                      # 竄改者重建一條自洽的鏈

    result = check(db, head_file)
    assert result["modified"] == [] and result["broken_links"] == []   # 鏈本身看不出問題
    assert result["anchor"] and not result["ok"]                       # 只有鏈頭備份抓得到


def test_a_truncated_chain_is_caught_by_the_saved_head(db, tmp_path):
    build(db)
    head_file = tmp_path / "head.json"
    chain.write_head(db, head_file, NOW)
    db[chain.CHAIN].delete_one({"seq": 3})

    assert any("截斷" in p for p in check(db, head_file)["anchor"])
    assert json.loads(head_file.read_text(encoding="utf-8"))["seq"] == 3


def save_anchor(db, directory, name, now=NOW):
    directory.mkdir(exist_ok=True)
    chain.write_head(db, directory / f"audit_chain_head_{name}.json", now)
    return directory


def test_an_old_offsite_anchor_stays_valid_while_the_chain_grows(db, tmp_path):
    build(db)
    anchors = save_anchor(db, tmp_path / "anchors", "20261013")
    db[LEDGER].insert_one({"symbol": "2603", "price": Decimal128("200"), "date": datetime(2026, 10, 13)})
    build(db)

    result = chain.verify(db, (LEDGER,), anchors=chain.anchor_files(anchors))

    assert result["ok"] and result["anchors_checked"] == 1


def test_a_chain_rewritten_even_with_a_refreshed_local_head_is_caught_by_an_offsite_anchor(db, tmp_path):
    build(db)
    anchors = save_anchor(db, tmp_path / "anchors", "20261013")
    db[LEDGER].update_one({"symbol": "2330"}, {"$set": {"price": Decimal128("999")}})
    db[chain.CHAIN].drop()
    build(db)
    local_head = tmp_path / "head.json"
    chain.write_head(db, local_head, NOW)                       # 竄改者連同機鏈頭檔一起改

    result = chain.verify(db, (LEDGER,), local_head, chain.anchor_files(anchors))

    assert not result["ok"]
    assert result["anchor"] == ["audit_chain_head_20261013.json：第 3 筆的雜湊與鏈頭備份不同（鏈被重寫）"]


def test_an_offsite_anchor_pointing_past_a_truncated_chain_is_named_in_the_report(db, tmp_path):
    build(db)
    anchors = save_anchor(db, tmp_path / "anchors", "20261015")
    db[chain.CHAIN].delete_one({"seq": 3})

    result = chain.verify(db, (LEDGER,), anchors=chain.anchor_files(anchors))

    assert any(p.startswith("audit_chain_head_20261015.json：") and "截斷" in p for p in result["anchor"])


def test_an_unreadable_anchor_file_is_reported_instead_of_crashing(db, tmp_path):
    build(db)
    anchors = tmp_path / "anchors"
    anchors.mkdir()
    (anchors / "audit_chain_head_20261016.json").write_text("{not json", encoding="utf-8")

    result = chain.verify(db, (LEDGER,), anchors=chain.anchor_files(anchors))

    assert result["anchor"] == ["audit_chain_head_20261016.json：錨點檔無法讀取"] and not result["ok"]


def test_anchor_files_lists_only_matching_names_in_order_and_tolerates_a_missing_folder(tmp_path):
    for name in ("audit_chain_head_20261018.json", "audit_chain_head_20261013.json", "notes.txt", "other.json"):
        (tmp_path / name).write_text("{}", encoding="utf-8")

    assert [p.name for p in chain.anchor_files(tmp_path)] == ["audit_chain_head_20261013.json", "audit_chain_head_20261018.json"]
    assert chain.anchor_files(tmp_path / "nope") == [] and chain.anchor_files(None) == []


def test_the_verify_command_fails_on_a_bad_anchor_and_says_so_when_there_are_none(db, tmp_path, capsys, monkeypatch):
    from scripts import audit_chain as command

    monkeypatch.setattr(command, "HEAD_FILE", tmp_path / "no_local_head.json")

    assert command.run_verify(db, False, anchors_dir=tmp_path / "nope") == 0
    assert "沒有異機錨點檔" in capsys.readouterr().out

    (tmp_path / "audit_chain_head_20261017.json").write_text(json.dumps({"seq": 5, "hash": "x"}), encoding="utf-8")
    assert command.run_verify(db, False, anchors_dir=tmp_path) == 1
    out = capsys.readouterr().out
    assert "鏈頭不符" in out and "異機錨點 1 份已核對" in out


def test_the_command_line_reads_the_anchors_dir_option(db, tmp_path, capsys, monkeypatch):
    from scripts import audit_chain as command

    monkeypatch.setattr(command, "get_db", lambda: db)
    monkeypatch.setattr(command, "HEAD_FILE", tmp_path / "no_local_head.json")
    (tmp_path / "audit_chain_head_20261017.json").write_text(json.dumps({"seq": 5, "hash": "x"}), encoding="utf-8")

    assert command.main(["verify", "--anchors-dir", str(tmp_path)]) == 1
    assert "異機錨點 1 份已核對" in capsys.readouterr().out
