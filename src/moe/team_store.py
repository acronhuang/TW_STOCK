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


def upsert_analyses(db, analyses: list, date: datetime, meta: dict = None,
                    source_file: str = "") -> tuple[int, int]:
    """批量 upsert；保留既有 verify 欄位與 created_at（$setOnInsert）。"""
    meta = meta or {}
    ops = []
    now = datetime.now()
    for a in analyses:
        sym = a.get("symbol")
        if not sym:
            continue
        name = (meta.get(sym) or {}).get("name", "") if meta else ""
        doc = to_doc(a, date, name, source_file)
        ops.append(UpdateOne(
            {"symbol": sym, "date": date},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        ))
    if not ops:
        return 0, 0
    res = db["team_analysis"].bulk_write(ops, ordered=False)
    return res.upserted_count, res.modified_count
