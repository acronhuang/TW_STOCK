"""缺口回補政策：每個集合的缺口能不能自動補、用哪支既有工具。"""
from dataclasses import dataclass

_LATEST_ONLY = "來源 OpenAPI 只提供最新交易日，沒有按日期的端點，現有工具無法回補"


@dataclass(frozen=True)
class Recovery:
    mode: str                      # backfill | unrecoverable | derived | review
    reason: str = ""
    commands: tuple[tuple[str, ...], ...] = ()


_UNRECOVERABLE = ("day_trading_targets", "securities_lending", "after_hours_trading", "odd_lot_trading")
_PRIORITY = {"stock_price": 0}   # 其他表的回補以 stock_price 的交易日曆為基準，必須先補價格


def priority(collection: str) -> int:
    return _PRIORITY.get(collection, 1)


def recovery_for(collection: str, day: str) -> Recovery:
    iso = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    if collection == "stock_price":
        return Recovery("backfill", commands=(("backfill_by_date.py", "--date", day, "--apply"),))
    if collection == "institutional_flow":
        return Recovery("backfill", commands=(("institutional_backfill.py", "--start", iso, "--end", iso),))
    if collection == "margin_purchase_short_sale":
        # 殘缺日看不出缺的是上市還是上櫃，兩邊都補（皆為冪等 upsert）
        return Recovery("backfill", commands=(("backfill_margin_by_date.py", "--date", day, "--apply"),
                                              ("tpex_margin_sync.py", "--date", day)))
    if collection == "stock_factors_valuation":
        return Recovery("backfill", commands=(("backfill_valuation_by_date.py", "--date", day, "--apply"),))
    if collection == "monthly_revenue":
        # OpenAPI 只給最新公告月；公告期內重抓即可，過期後補不回會在三次嘗試後轉 failed 告警
        return Recovery("backfill", commands=(("sync_revenue_openapi.py",),))
    if collection in _UNRECOVERABLE:
        return Recovery("unrecoverable", reason=_LATEST_ONLY)
    if collection == "foreign_holding":
        return Recovery("backfill", commands=(("twse_foreign_holding_sync.py", "--date", day),))
    if collection == "risk_analysis":
        return Recovery("snapshot", reason="持倉風控合議是當日決策快照（含當時持倉與模型判斷），不能事後重建")
    if collection == "stock_factors":
        return Recovery("derived", reason="由 stock_price 等原始表計算的衍生表，請在原始表補齊後重算因子，不在此直接回補")
    return Recovery("review", reason="政策表沒有這個集合，需人工判斷能否回補")
