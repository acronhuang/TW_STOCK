"""台股交易日曆 — 判定休市 vs 交易日,供盤後/新鮮度檢查共用(根治『假日誤報』)。

問題:盤後檢查/新鮮度審核以「日曆日」計落後,逢連假(如中秋 4 天)就把 stock_price
當漏抓/落後誤報。解法:以「交易日」計 —— 向 FinMind 源頭確認某日是否有資料。
"""
from __future__ import annotations

from datetime import timedelta


def is_market_open(day, token: str | None = None) -> bool | None:
    """day(date) 是否台股交易日。週末→False(免打 API);否則向 FinMind 問 2330 該日有無資料。

    回 True(交易日) / False(休市) / None(無法判定,如 API 失敗 → 呼叫端宜保守)。
    """
    if day.weekday() >= 5:                 # 週六/日
        return False
    try:
        import os
        import requests
        tok = token if token is not None else os.getenv("FINMIND_API_TOKEN", "")
        r = requests.get("https://api.finmindtrade.com/api/v4/data",
                         params={"dataset": "TaiwanStockPrice", "data_id": "2330",
                                 "start_date": day.isoformat(), "end_date": day.isoformat(),
                                 "token": tok}, timeout=20)
        if r.status_code != 200:
            return None
        return len(r.json().get("data", [])) > 0
    except Exception:
        return None


def trading_days_behind(latest_date, now, is_open_fn=None) -> int:
    """latest_date 之後、今日之前,有幾個『已收盤交易日』未入庫(休市不計)。

    只對候選『工作日』問(便宜:連假通常 0–數天)。無法判定(None)的日子**保守計入**
    (當交易日),寧可誤報也不漏真缺口。is_open_fn(date)->bool|None 可注入(測試/避 API)。
    """
    fn = is_open_fn or is_market_open
    ld = latest_date.date() if hasattr(latest_date, "date") else latest_date
    today = now.date() if hasattr(now, "date") else now
    n = 0
    d = ld + timedelta(days=1)
    while d < today:                       # 排除今日(可能尚未收盤/入庫)
        if d.weekday() < 5:
            if fn(d) is not False:          # True 或 None(保守)→ 計入
                n += 1
        d += timedelta(days=1)
    return n
