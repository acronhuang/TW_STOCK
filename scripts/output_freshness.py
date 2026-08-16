#!/usr/bin/env python3
"""FR-OUT-001 —— 對外產出是否如期產生。

用法:
  output_freshness.py            檢查全部登記的產出
  output_freshness.py --list     只列清單與預期節奏，不做判定

為什麼與資料新鮮度分開（ADR-0012）
----------------------------------
`data_freshness_audit` 納管 38 個 collection，**其中屬於「對外產出」的只有
`team_analysis` 一個**，其餘 37 個全是原始資料。也就是說監控在盯「資料有沒有進來」，
幾乎不盯「產出有沒有出去」。後者失效時完全靜默：頁面照常顯示、API 照常回應，
只是內容是舊的。

兩者的嚴重性與處理方式也不同：原始資料遲到通常是上游 API 的問題，等一下就好；
產出沒生出來是自己的排程壞了，且會靜默污染所有下游判斷。

⚠️「預期節奏」必須是清單上的明確參數，不能靠目視
--------------------------------------------------
2026-08-16 的誤判實例：`verdict_detail` 最新分析日 2026-08-06，目視「與今天差 10 天」
而誤判為嚴重落後；實際上 window=5 需要分析日之後有 5 個交易日，理論最新值就是 08-07，
**只落後 1 個分析日**。同時誤判其每日 cron「從未執行」為失效——實則該 cron
於週六加入、排程為平日，首次執行本就在週一。兩個誤判都源於缺少寫下來的節奏參數。

可失敗性證據（ADR-0002 條件 1，可重跑）:
  正向  output_freshness.py                 -> 結束碼 0
  反向  OUTPUT_MAX_LAG=0 output_freshness.py -> 結束碼 1（容許落後歸零，必有產出被判遲到）
"""
import os
import sys
import argparse
import datetime

from pymongo import MongoClient

DB = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]

# 全域容許倍率：測試可用 OUTPUT_MAX_LAG=0 讓所有容許歸零，證明本檢查會失敗。
LAG_SCALE = float(os.getenv("OUTPUT_MAX_LAG", "1"))

# 產出清單（FR-OUT-001 的納管對象）
#   field          判定用的日期欄位
#   lag_trading    **內建**落後幾個交易日（前瞻視窗等結構性落差，非遲到）
#   tol_days       在內建落差之上，還容許遲到幾個日曆天
#   why            為什麼是這個節奏 —— 沒寫理由的參數會被下一個人改掉
OUTPUTS = [
    dict(id="team_analysis", name="團隊合議定案", coll="team_analysis",
         field="date", lag_trading=0, tol_days=4,
         why="週跑跨數日，最新分析日可能停在開跑那天"),
    dict(id="verdict_detail_5", name="判斷準確度逐筆(5日)", coll="verdict_detail",
         field="date", lag_trading=5, tol_days=4, filt={"window": 5},
         why="前瞻 5 交易日，分析日之後要滿 5 天才算得出來；cron 為平日"),
    dict(id="verdict_detail_20", name="判斷準確度逐筆(20日)", coll="verdict_detail",
         field="date", lag_trading=20, tol_days=4, filt={"window": 20},
         why="同上，前瞻 20 交易日"),
    dict(id="verdict_performance", name="判斷準確度快照", coll="verdict_performance",
         field="ts", lag_trading=0, tol_days=4,
         why="每日 07:30 隨 verdict_detail 累積一併產生"),
    dict(id="core_watchlist", name="核心池每日追蹤", coll="core_watchlist",
         field="updated_at", lag_trading=0, tol_days=4,
         why="平日 21:30 刷新；週末不跑故容許跨週末"),
    dict(id="requirement_status", name="需求狀態板", coll="requirement_status",
         field="checked_at", lag_trading=0, tol_days=2,
         why="每日 07:47；它自己遲到代表整個需求體系失明"),
]


def trading_days():
    return sorted(d for d in DB.trading_dates.distinct("date") if d)


def latest_of(o):
    """回該產出的最新日期（date 物件）。查無回 None。"""
    q = dict(o.get("filt") or {})
    q[o["field"]] = {"$exists": True, "$ne": None}
    d = DB[o["coll"]].find_one(q, sort=[(o["field"], -1)])
    if not d:
        return None
    v = d.get(o["field"])
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, str) and len(v) >= 10:
        try:
            return datetime.date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="只列清單與節奏")
    a = ap.parse_args()

    if a.list:
        print("%-22s %-24s %8s %8s %s" % ("id", "名稱", "內建落後", "容許遲到", "理由"))
        for o in OUTPUTS:
            print("%-22s %-24s %6d 交易日 %6d 天 %s"
                  % (o["id"], o["name"], o["lag_trading"], o["tol_days"], o["why"]))
        return 0

    tds = trading_days()
    today = datetime.date.today()
    past = [d for d in tds if d <= str(today)]
    if not past:
        print("⚪ 無資料：trading_dates 中查無今日以前的交易日")
        return 2

    print("%-22s %-22s %-12s %-12s %6s %s" %
          ("產出", "名稱", "實際最新", "應不早於", "落後", "判定"))
    print("-" * 104)
    n_fail = n_nodata = 0
    for o in OUTPUTS:
        got = latest_of(o)
        # 應不早於 = 扣掉內建落差後的那個交易日，再往前放寬 tol_days
        idx = len(past) - 1 - o["lag_trading"]
        base = datetime.date.fromisoformat(past[idx]) if idx >= 0 else None
        tol = int(o["tol_days"] * LAG_SCALE)
        floor = (base - datetime.timedelta(days=tol)) if base else None
        if got is None:
            n_nodata += 1
            print("%-22s %-22s %-12s %-12s %6s ⚪無資料"
                  % (o["id"], o["name"], "-", str(floor or "-"), "-"))
            continue
        lag = (base - got).days if base else 0
        ok = floor is None or got >= floor
        if not ok:
            n_fail += 1
        print("%-22s %-22s %-12s %-12s %5d天 %s"
              % (o["id"], o["name"], str(got), str(floor), lag,
                 "✅通過" if ok else "🔴遲到"))

    print()
    print(f"達標 {len(OUTPUTS) - n_fail - n_nodata} / 遲到 {n_fail} / 無資料 {n_nodata}"
          f"　（共 {len(OUTPUTS)} 項，容許倍率 {LAG_SCALE}）")
    if n_fail:
        return 1
    if n_nodata:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
