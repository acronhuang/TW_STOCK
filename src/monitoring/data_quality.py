"""資料品質監控 —— 新鮮度 / 覆蓋率 / 文件驗證。

背景：分析再強，餵爛資料一樣爛。本模組提供輕量、可測（fake db）的健康檢查，
供排程呼叫後寫入 data_health_history 與 schedule_alerts，讓資料落後/髒資料
在網頁上看得見，而非事後才發現（如 2706 EPS 漂移、被推翻的舊報告）。

設計：純函式 + 注入 db，無外部相依；預設不寫入，由呼叫端決定持久化。
"""
from __future__ import annotations

from datetime import datetime

from src.domain.collections import (
    COLL_SCHEDULE_ALERTS,
)

# ── 單一真相源:資料健康門檻 ──────────────────────────────────────
# 新鮮度/覆蓋率門檻的唯一權威來源。scripts/data_health_check.py(排程監控)
# 與 tests/test_data_integrity.py(真實庫測試)均從此 import,避免兩處門檻各自
# 漂移(曾發生:data_health 4 天 vs test_data_integrity 5 天)。
DEFAULT_HEALTH_CONFIG = {
    "freshness": {
        "stock_price": {"date_field": "date", "max_age_days": 4},
        "stock_factors": {"date_field": "date", "max_age_days": 4},
        "institutional_flow": {"date_field": "date", "max_age_days": 4},
        "quarterly_earnings": {"date_field": "updated_at", "max_age_days": 120},
        "monthly_revenue": {"date_field": "updated_at", "max_age_days": 40},
        "macro_indicators": {"date_field": "updated_at", "max_age_days": 40},
    },
    "coverage": {
        "taiwan_stock_info": 1000,
    },
}


def _coerce_dt(value):
    """將值轉為 datetime：支援 datetime 與 ISO 字串（'2026-09-22'、'2026-08'）。無法解析回 None。"""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        v = value.strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y%m%d"):
            try:
                return datetime.strptime(v, fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            return None
    return None


def _latest_date(db, collection: str, date_field: str):
    """取集合最新日期（依 date_field desc）。空集合回 None。"""
    doc = db[collection].find({}, {date_field: 1}).sort([(date_field, -1)]).limit(1)
    docs = list(doc)
    if not docs:
        return None
    return docs[0].get(date_field)


def check_freshness(db, specs: dict, now: datetime | None = None) -> list[dict]:
    """檢查各集合新鮮度。

    specs: {collection: {'date_field': str, 'max_age_days': int}}
    回傳 [{collection, latest, age_days, max_age_days, stale}]
    """
    now = now or datetime.now()
    out = []
    for collection, spec in specs.items():
        field = spec.get("date_field", "date")
        max_age = int(spec.get("max_age_days", 3))
        latest = _latest_date(db, collection, field)
        if latest is None:
            out.append({"collection": collection, "latest": None,
                        "age_days": None, "max_age_days": max_age, "stale": True})
            continue
        latest_dt = _coerce_dt(latest)
        age = (now - latest_dt).days if latest_dt else None
        stale = age is None or age > max_age
        out.append({"collection": collection, "latest": latest,
                    "age_days": age, "max_age_days": max_age, "stale": stale})
    return out


def check_coverage(db, collection: str, min_count: int) -> dict:
    """檢查集合文件數是否達門檻。"""
    count = db[collection].count_documents({})
    return {"collection": collection, "count": count,
            "min_count": min_count, "ok": count >= min_count}


def validate_document(doc: dict, rules: dict) -> list[str]:
    """驗證單一文件欄位是否在合理範圍。

    rules: {field: (min, max)} 或 {field: callable(value)->bool}
    回傳違規描述清單（空 = 通過）。
    """
    violations = []
    for field, rule in rules.items():
        if field not in doc or doc[field] is None:
            violations.append(f"缺欄位 {field}")
            continue
        value = doc[field]
        if callable(rule):
            if not rule(value):
                violations.append(f"{field}={value} 未通過驗證")
        else:
            lo, hi = rule
            if not (lo <= value <= hi):
                violations.append(f"{field}={value} 超出範圍 [{lo}, {hi}]")
    return violations


def run_health_check(db, config: dict, now: datetime | None = None) -> dict:
    """整合新鮮度 + 覆蓋率 → 健康報告。

    config: {'freshness': {...specs}, 'coverage': {collection: min_count}}
    回傳 {ok, ts, freshness, coverage, stale_count, low_coverage_count, alerts}
    """
    now = now or datetime.now()
    freshness = check_freshness(db, config.get("freshness", {}), now=now)
    coverage = [check_coverage(db, c, n) for c, n in config.get("coverage", {}).items()]

    alerts = []
    for f in freshness:
        if f["stale"]:
            alerts.append(f"[新鮮度] {f['collection']} 落後 "
                          f"{f['age_days'] if f['age_days'] is not None else '無資料'} 天"
                          f"（上限 {f['max_age_days']}）")
    for c in coverage:
        if not c["ok"]:
            alerts.append(f"[覆蓋率] {c['collection']} 僅 {c['count']} 筆（期望 ≥ {c['min_count']}）")

    return {
        "ok": not alerts,
        "ts": now,
        "freshness": freshness,
        "coverage": coverage,
        "stale_count": sum(1 for f in freshness if f["stale"]),
        "low_coverage_count": sum(1 for c in coverage if not c["ok"]),
        "alerts": alerts,
    }


def summarize_open_alerts(docs, latest_n: int = 8):
    """彙整未解決告警（純函式，可測）。

    docs: schedule_alerts 中 resolved!=True 的紀錄。回：
      {total, by_source: {source: count}, latest: [依 ts 由新到舊，最多 latest_n 筆]}
    """
    docs = list(docs or [])
    by_source: dict = {}
    for d in docs:
        src = d.get("source", "unknown")
        by_source[src] = by_source.get(src, 0) + 1
    latest = sorted(docs, key=lambda d: d.get("ts") or datetime.min, reverse=True)[:latest_n]
    return {"total": len(docs), "by_source": by_source, "latest": latest}


def auto_resolve_alerts(db, source: str, now=None, reason: str = "指標回到門檻上方"):
    """自動消警：把指定 source 的未解決告警標記 resolved（指標回穩時呼叫）。

    回傳被標記的筆數（modified_count）。db 需提供 schedule_alerts.update_many。
    """
    now = now or datetime.now()
    res = db[COLL_SCHEDULE_ALERTS].update_many(
        {"source": source, "resolved": {"$ne": True}},
        {"$set": {"resolved": True, "resolved_at": now,
                  "resolved_reason": f"auto: {reason}"}},
    )
    return getattr(res, "modified_count", 0)
