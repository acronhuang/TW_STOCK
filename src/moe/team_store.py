#!/usr/bin/env python3
"""
team_analysis 持久層（共用模組）
================================
定義 team_daily_verified 分析結果在 MongoDB 的文件形狀、索引、與 upsert 邏輯。
migration / 雙寫 / 復驗三者共用此模組，確保 schema 一致。

集合: tw_stock_analysis.team_analysis
文件唯一鍵: (symbol, date)
"""
from __future__ import annotations

from datetime import datetime

from pymongo import ASCENDING, MongoClient, UpdateOne

VERDICTS = ("強力買進", "買進", "持有", "觀望", "中立", "減碼", "賣出")


def get_db(uri: str = "mongodb://localhost:27017"):
    return MongoClient(uri)["tw_stock_analysis"]


def ensure_indexes(db):
    col = db["team_analysis"]
    col.create_index([("symbol", ASCENDING), ("date", ASCENDING)], unique=True, name="uq_symbol_date")
    col.create_index([("date", ASCENDING), ("final_verdict", ASCENDING)], name="date_verdict")
    col.create_index([("date", ASCENDING), ("verify.status", ASCENDING)], name="date_verifystatus")
    return col


def _evidence_close(analysis: dict):
    """分析當下佐證表中的收盤價（供復驗基準）。"""
    for e in analysis.get("evidence") or []:
        if e.get("metric") == "收盤價":
            try:
                return float(e.get("db"))
            except (TypeError, ValueError):
                return None
    return None


def _final_verdict(analysis: dict):
    """定案：優先合議 final，其次顧問草案『評級：X』，皆無則 None。"""
    c = analysis.get("consensus")
    if c and c.get("final"):
        return c["final"]
    adv = analysis.get("advisor") or ""
    import re
    m = re.search(r"評級[:：]\s*(強力買進|買進|持有|觀望|中立|減碼|賣出)", adv)
    return m.group(1) if m else None


def to_doc(analysis: dict, date: datetime, name: str = "", source_file: str = "") -> dict:
    """把單筆 analysis 轉為 team_analysis 文件（不含 _id）。"""
    now = datetime.now()
    return {
        "symbol": analysis["symbol"],
        "name": name or "",
        "date": date,
        "reports": analysis.get("reports") or {},
        # ADR-0005：每份角色報告的產生模型與節點。沒有它，關於模型的主張無法被檢查。
        "models": analysis.get("models") or {},
        # ADR-0004：可執行性是屬性不是過濾條件，供執行層自行決定門檻。
        "median_turnover": analysis.get("median_turnover"),
        "evidence": analysis.get("evidence") or [],
        "advisor": analysis.get("advisor"),
        "consensus": analysis.get("consensus"),
        "senvision": analysis.get("senvision"),
        "extra": analysis.get("extra"),
        "final_verdict": _final_verdict(analysis),
        "price_at_analysis": _evidence_close(analysis),
        "source_file": source_file,
        "updated_at": now,
    }


# 這些欄位「有值」比「沒值」珍貴，來源缺這些欄位時不得覆蓋既有值。
# 2026-08-15 實測踩過：流水線改造後 phase2 只寫 DB 不寫 JSON，
# 而 phase3 的 migrate_team_to_db 仍把 JSON(只有 phase1 資料)同步回 DB，
# 於是用 advisor=None 蓋掉了 phase2 剛寫入的顧問整合與合議定案 ——
# 8 檔全滅，log 卻一路顯示成功（合議定案都印出來了），只有查 DB 才看得見。
# 對照組：不在該 JSON 內的另外 49 檔完全不受影響，證實是覆蓋而非寫入失敗。
_PRECIOUS = ("advisor", "consensus", "final_verdict", "reports", "models",
             "median_turnover", "evidence", "senvision", "extra", "price_at_analysis")


def upsert_analyses(db, analyses: list, date: datetime, meta: dict = None,
                    source_file: str = "") -> tuple[int, int]:
    """批量 upsert；保留既有 verify 欄位與 created_at（$setOnInsert）。

    空值不覆蓋：來源沒有的欄位（None／空 dict／空 list）不會寫進 $set，
    因此「只有 phase1 資料的來源」不會抹掉「phase2 已寫入的成果」。
    要清空某欄位請直接操作 DB，不要靠這支。
    """
    meta = meta or {}
    ops = []
    now = datetime.now()
    for a in analyses:
        sym = a.get("symbol")
        if not sym:
            continue
        name = (meta.get(sym) or {}).get("name", "") if meta else ""
        doc = to_doc(a, date, name, source_file)
        doc = {k: v for k, v in doc.items()
               if k not in _PRECIOUS or v not in (None, {}, [], "")}
        ops.append(UpdateOne(
            {"symbol": sym, "date": date},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        ))
    if not ops:
        return 0, 0
    res = db["team_analysis"].bulk_write(ops, ordered=False)
    return res.upserted_count, res.modified_count
