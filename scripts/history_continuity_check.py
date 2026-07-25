#!/usr/bin/env python3
"""
歷史連續性檢查：偵測「中間缺日」與「筆數殘缺」兩型歷史破洞
============================================================
TABLE_CHECKS（twse_openapi_sync）只驗最新交易日的新鮮度，**不回頭掃歷史** —— 故某天
漏抓、隔天恢復的洞會永久隱形。實例：institutional_flow 在 2026-03 連缺 8 天（03-02~05,
03-09,03-10,03-27）＋02-26，直到 2026-07-18 手動比對交易日曆才發現、補齊。本檢查把
「回頭比對交易日曆」自動化，讓這類破洞被主動抓到而非靠碰巧。

三種破洞（互補）：
  (A) 缺日：該交易日整天無資料（date 不存在）。以 stock_price 交易日曆為基準比對。
  (B) 筆數殘缺：該日有資料但筆數異常少（< 局部中位數×THIN_RATIO）。實例：stock_price
      2026-03-10 僅 26 筆（正常 2000+），連帶 stock_factors 當日算不出 —— 缺日檢查看不到
      （date 存在），正是其盲點。筆數檢查特別涵蓋 stock_price 自己（缺日檢查的基準）。
  (C) date 欄位本身壞掉：型別非 date（字串）、或非 UTC 午夜（時區錯誤）。(A)(B) 都以
      `{"date":{"$type":"date"}}` 過濾，故字串型別的髒列**對它們完全隱形**——2026-07-19
      手動掃 DB 才發現 stock_price 有 5197 筆字串日期，此檢查從未報過。見 find_date_anomalies。

基準：stock_price（排除 TAIEX）的 distinct date = 有開市的日子（真相錨）。
範圍：預設近 --window 個交易日（歷史洞補一次即可，新洞才需持續偵測）；--full 掃全歷史。
      排除最近 2 個交易日：法人等 T+1 公布，最新日未出屬正常，不算缺。
去重：只報「新出現」的問題（記於 data_continuity_alerted），已知洞告警一次後靜默。
      → 上游真洞（如 2026-02-15 春節補班日 TWSE 無法人資料）：告警一次、判斷後即不再吵。
      → 真的漏抓：缺日用 institutional_backfill.py、殘缺用 backfill_by_date.py 補齊。

用法：
    python3 scripts/history_continuity_check.py            # 掃窗口 + 新問題告警
    python3 scripts/history_continuity_check.py --full     # 全歷史
    python3 scripts/history_continuity_check.py --status   # 只印現況，不告警、不更新 state
    python3 scripts/history_continuity_check.py --reset    # 清去重記錄（下次重新告警所有問題）
"""
from __future__ import annotations

import argparse
import os
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

from pymongo import MongoClient

# 「每交易日、全市場皆應有資料」的表（皆在 TABLE_CHECKS，lag 0 或 1）。
# stock_price 是缺日基準，不做缺日檢查；稀疏表（major_news/punished_stocks…）不適用。
CHECKED = [
    "institutional_flow", "stock_factors", "margin_purchase_short_sale",
    "day_trading_targets", "securities_lending", "after_hours_trading",
    "odd_lot_trading",
]
# 筆數殘缺偵測對象＝上述 + stock_price 自己（stock_price 亦納入缺日檢查，因日曆已改用
# trading_dates 這個外部錨，不再由 stock_price 自我推導）。
CHECKED_COUNTS = ["stock_price"] + CHECKED

# ── 收集範圍宣告（完整性的定義）────────────────────────────────────────────
# 「完整」是相對於**宣告過的範圍**，不是相對於市場上存在的一切。沒有宣告範圍，
# 完整性就只能拿「昨天有多少」當基準 → 連續漏抓時中位數自己降下去，永遠測不出來。
#
# 本系統宣告收集：上市/上櫃(twse/tpex)的 Stock / ETF / KY-Stock / PreferredStock。
# 明文**不收**：
#   • 權證（6 碼且非 00 開頭，如 700021）——來源 TPEX_OpenAPI 只供最新一個交易日，
#     窗口一關即永久無法回補；且分析鏈完全不讀（stock_factors 每日約 2003 筆，全為
#     4 碼主板，權證 0 筆）。2026-02 前更是整段歷史都沒收。
#   • 興櫃(emerging)。
# → 故權證缺席**不是缺漏，是範圍外**。這是可稽核的決定，與「調門檻讓警報閉嘴」不同：
#   把它寫在這裡，而不是偷偷改 THIN_RATIO。
_WARRANT_RE = re.compile(r"^(?!00)\d{6}$")
_COUNT_FILTER = {
    "stock_price": {"symbol": {"$ne": "TAIEX"}, "stock_id": {"$not": _WARRANT_RE}},
}

THIN_RATIO = 0.5       # 某日筆數 < 局部中位數×此值 → 判殘缺（殘缺日通常少一個數量級，門檻寬鬆亦可抓）
THIN_LOCAL_K = 10      # 局部中位數取前後各 K 個交易日。用「局部」而非全窗口中位數的原因：
                       # stock_price 筆數隨納入標的增加而長期上升（2016 約 280 → 2026 約 6000），
                       # 全窗口單一中位數會把「早期正常但較少」誤判殘缺；局部中位數隨水位漸變、
                       # 只揪「相對鄰近日突然掉一個數量級」的真殘缺（如 03-10 的 26 vs 鄰居 2300）。
T1_BUFFER = 2          # 排除最近 N 個交易日（T+1 公布緩衝，避免把正常未出當缺）
DEFAULT_WINDOW = 120   # 預設檢查窗口（交易日）


def _date_set(db, coll: str, extra: dict | None = None) -> set[str]:
    """該表所有 date（YYYYMMDD 字串集合）。只取 $type:date —— stock_price 混有 str 型別
    髒日期（見 charts.py 同款過濾），不濾會與 datetime 產出不同格式而全數對不上、假缺口。"""
    q = {"date": {"$type": "date"}}
    if extra:
        q.update(extra)
    return {d.strftime("%Y%m%d") for d in db[coll].distinct("date", q)}


def _trading_calendar(db, upto_ymd: str) -> list[str]:
    """權威交易日曆（YYYYMMDD 升冪）＝ trading_dates 集合，取 <= upto_ymd 的日子。

    **為何不再用 stock_price.distinct(date) 自我推導**：那是循環參照——用「我有資料的
    日子」定義「應該有資料的日子」，於是「整天沒下載」永遠測不出來（缺的那天不在自己
    推導的日曆裡）。反之髒資料會憑空長出交易日：實例 2026-02-15(週日) 有 1339 筆舊格式
    列（date 存 UTC 16:00＝台北隔日午夜），舊邏輯據此判定週日是交易日，再回頭告警
    institutional_flow「缺 2026-02-15」——純屬虛構。

    trading_dates：1999-01-05 ~ 2026-12-31，每年 242~243 天，正確排除週末與國定假日，
    已被 backtest.py / factor_calculator.py 等使用。實測與 stock_price 實得日在
    2016-01-11~2026-07-17 的 2562 天中僅差 1 天（2026-07-10 颱風停市，見 _closure_days）。
    注意 trading_dates.date 是**字串** "YYYY-MM-DD"（非 Date 型別，用 datetime 查會全空）。
    """
    return sorted(x["date"].replace("-", "")
                  for x in db.trading_dates.find(
                      {"date": {"$lte": upto_ymd[:4] + "-" + upto_ymd[4:6] + "-" + upto_ymd[6:]}},
                      {"date": 1}))


def find_date_anomalies(db) -> dict[str, dict]:
    """(C) date 欄位本身壞掉：型別非 date、或時間部分非 UTC 午夜。

    **為何需要獨立這一項**：本檔其餘所有檢查（含 _date_set）都用 `{"date": {"$type": "date"}}`
    過濾——那是為了避開混型別排序錯誤，代價是**字串型別的髒列對每個檢查都是隱形的**。
    2026-07-19 手動掃全 DB 才發現 stock_price 有 5197 筆字串日期（橫跨 1214 個日期、
    2021~2026），完整性檢查從未報過它們一次。這一項就是補這個洞。

    兩種病灶（皆為 2026-02 的一次性事故，已清理，此處為防復發）：
      • 字串日期："2026-02-23" 而非 ISODate —— 對 date 查詢完全不可見
      • 非午夜：ISODate 帶 16:00（台北午夜寫成 UTC）—— 精確日期查詢會查不到

    註：stock_price 已於 2026-07-19 加上 validator（$expr 午夜約束 + validationAction:error）
    從寫入端擋掉；其餘表仍是 warn，故此偵測仍有必要。
    """
    report = {}
    for coll in CHECKED_COUNTS:
        c = db[coll]
        if not c.find_one({"date": {"$exists": True}}):
            continue
        bad_type = c.count_documents({"date": {"$exists": True, "$not": {"$type": "date"}}})
        # $dateTrunc 遇非 date 型別會拋例外，故先以 $type 過濾再比對
        non_mid = c.count_documents({
            "date": {"$type": "date"},
            "$expr": {"$ne": [{"$dateTrunc": {"date": "$date", "unit": "day"}}, "$date"]}})
        if bad_type or non_mid:
            report[coll] = {"bad_type": bad_type, "non_midnight": non_mid}
    return report


def _closure_days(db, missing: set[str]) -> set[str]:
    """從缺漏日中挑出「疑似休市」＝該日**所有**受檢表皆 0 筆。

    trading_dates 是預先產生的國定假日曆，**無法預知天災停市**（颱風/地震停班停課時
    證交所同步休市）。實例 2026-07-10 臺北市停止上班上課、全表 0 筆，但仍在 trading_dates
    中。這類日子每年約 1~3 天，特徵極明確（全表皆 0，而非某表少幾筆），故獨立歸類：
    報一次請人確認，不逐表各報一次（否則一個颱風假會產生 8 則缺日告警）。
    """
    out = set()
    for ymd in missing:
        start = datetime.strptime(ymd, "%Y%m%d")
        end = start.replace(hour=23, minute=59, second=59)
        if all(db[c].count_documents({"date": {"$gte": start, "$lte": end}}) == 0
               for c in CHECKED_COUNTS):
            out.add(ymd)
    return out


def _line(msg: str):
    """發 LINE（與其他腳本一致：補 sys.path + load_dotenv，否則 token 靜默遺失）。"""
    try:
        root = Path(__file__).parent.parent
        sys.path.insert(0, str(root))
        from dotenv import load_dotenv
        load_dotenv(str(root / ".env"))
        from src.alerts.line_notifier import LineNotifier
        n = LineNotifier()
        if n.enabled:
            n.send(msg)
        else:
            print("  LINE 未設定，跳過告警")
    except Exception as e:      # noqa: BLE001
        print(f"  LINE 發送失敗：{e}")


def find_gaps(db, window_cal: list[str]) -> dict[str, list[str]]:
    """(A) 缺日：回 {collection: [缺漏交易日 YYYYMMDD, ...]}。僅查各表最早日之後的窗口。"""
    win = set(window_cal)
    report = {}
    # stock_price 亦納入（日曆已改用 trading_dates 外部錨，它不再是自己的基準）。
    # 套用 _COUNT_FILTER：只有「範圍外標的」的日子（如僅剩權證）應視為缺，而非算它有。
    for coll in CHECKED_COUNTS:
        have = _date_set(db, coll, _COUNT_FILTER.get(coll))
        if not have:
            continue                       # 表為空 → 非連續性問題，跳過
        tmin = min(have)
        gaps = sorted(d for d in win if d >= tmin and d not in have)
        if gaps:
            report[coll] = gaps
    return report


def find_thin_days(db, window_cal: list[str]) -> dict[str, list]:
    """(B) 筆數殘缺：回 {collection: [(缺量日, 筆數, 局部中位數), ...]}。
    某日筆數 >0 但 < 前後各 THIN_LOCAL_K 個交易日中位數×THIN_RATIO → 殘缺（筆數 0＝缺日，另由 find_gaps 抓）。"""
    win = set(window_cal)
    since = datetime.strptime(window_cal[0], "%Y%m%d")     # 只掃窗口起點後，用到 date 索引
    report = {}
    for coll in CHECKED_COUNTS:
        match = {"date": {"$type": "date", "$gte": since}}
        match.update(_COUNT_FILTER.get(coll, {}))
        counts = {}
        for g in db[coll].aggregate([{"$match": match},
                                     {"$group": {"_id": "$date", "n": {"$sum": 1}}}]):
            ymd = g["_id"].strftime("%Y%m%d")
            if ymd in win:
                counts[ymd] = g["n"]
        if len(counts) < THIN_LOCAL_K + 2:                # 樣本太少無法定義局部水位
            continue
        items = sorted(counts.items())                    # [(ymd, n), ...] 按日期
        vals = [n for _, n in items]
        thin = []
        for i, (d, c) in enumerate(items):
            left = vals[max(0, i - THIN_LOCAL_K):i]       # 前鄰居＝穩定的歷史水位基準
            right = vals[i + 1:i + 1 + THIN_LOCAL_K]
            # 需前鄰居足夠才判：窗口最前 K 天略過（它們在上週窗口居中、早被查過），否則
            # 水位跳變點的低側（如 2026-01-13 卡在 2300→6000 跳變）只有後鄰居→誤判殘缺。
            # 尾部（近期，最需即時偵測）後鄰居可不足，用前鄰居當基準即可。
            if len(left) < THIN_LOCAL_K:
                continue
            med = int(statistics.median(left + right))
            if 0 < c < med * THIN_RATIO:
                thin.append((d, c, med))
        if thin:
            report[coll] = thin
    return report


def main():
    ap = argparse.ArgumentParser(description="歷史連續性檢查（缺日 + 筆數殘缺）")
    ap.add_argument("--window", type=int, default=DEFAULT_WINDOW, help=f"檢查窗口交易日數（預設 {DEFAULT_WINDOW}）")
    ap.add_argument("--full", action="store_true", help="掃全歷史（忽略 --window）")
    ap.add_argument("--status", action="store_true", help="只印現況，不告警、不更新 state")
    ap.add_argument("--reset", action="store_true", help="清去重記錄後結束")
    ap.add_argument("--db-uri", default=os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    args = ap.parse_args()

    db = MongoClient(args.db_uri)[os.getenv("MONGODB_DATABASE", "tw_stock_analysis")]

    if args.reset:
        n = db.data_continuity_alerted.delete_many({}).deleted_count
        print(f"已清去重記錄 {n} 筆")
        return

    # 權威交易日曆＝trading_dates（外部錨），去掉最近 T1_BUFFER 天（T+1 緩衝）。
    # 夾到「實際開始有資料」之後：日曆自 1999 起，而 stock_price 自 2016-01-11 起，
    # 不夾會把 2016 年之前每一天都判成缺漏。
    cal = _trading_calendar(db, datetime.now().strftime("%Y%m%d"))
    have_sp = _date_set(db, "stock_price", _COUNT_FILTER["stock_price"])
    if not have_sp:
        print("stock_price 無資料，略過"); return
    cal = [d for d in cal if d >= min(have_sp)]
    if len(cal) <= T1_BUFFER:
        print("交易日曆過短，略過"); return
    cal = cal[:-T1_BUFFER]

    # 反向檢查（舊邏輯做不到）：有資料、但日曆說不是交易日 → 髒資料或日曆錯。
    # 實例 2026-02-15(週日) 1339 筆舊格式列。此為資料品質問題，獨立報告不進去重表。
    orphan = sorted(d for d in have_sp if d not in set(cal) and d >= cal[0] and d <= cal[-1])
    window_cal = cal if args.full else cal[-args.window:]
    scope = "全歷史" if args.full else f"近 {len(window_cal)} 交易日"
    print(f"歷史連續性檢查｜{scope}（{window_cal[0]} ~ {window_cal[-1]}）｜{datetime.now():%F %T}")

    gap_report = find_gaps(db, window_cal)          # 缺日：date 完全不存在
    thin_report = find_thin_days(db, window_cal)    # 缺量：date 存在但筆數異常少

    # 疑似休市（天災停市）先抽出來：一個颱風假會讓每張表都缺同一天，若不獨立歸類，
    # 8 張表就產生 8 則缺日告警，指向同一件事。抽出後不再計入各表缺日。
    all_missing = {d for ds in gap_report.values() for d in ds}
    closures = _closure_days(db, all_missing) if all_missing else set()
    if closures:
        gap_report = {c: [d for d in ds if d not in closures] for c, ds in gap_report.items()}
        gap_report = {c: ds for c, ds in gap_report.items() if ds}

    # date 欄位健康（與缺日/缺量互補：那兩者只看「日期對不對」，這裡看「date 欄位本身壞沒壞」）
    date_bad = find_date_anomalies(db)

    def _fmt(g):
        return f"{g[:4]}-{g[4:6]}-{g[6:]}"

    if not gap_report and not thin_report and not closures and not orphan and not date_bad:
        print("  ✅ 各表交易日連續、筆數正常、date 欄位健康")
    for coll, d in date_bad.items():
        parts = []
        if d["bad_type"]:
            parts.append(f"型別非 date {d['bad_type']} 筆（對日期查詢隱形）")
        if d["non_midnight"]:
            parts.append(f"非 UTC 午夜 {d['non_midnight']} 筆（時區錯誤）")
        print(f"  🕐 {coll}: date 欄位異常 — " + "；".join(parts))
    if closures:
        print(f"  🌀 疑似休市 {len(closures)} 天（全表 0 筆，日曆未含天災停市）→ "
              + ", ".join(_fmt(d) for d in sorted(closures)))
    if orphan:
        print(f"  🧹 非交易日卻有資料 {len(orphan)} 天（髒資料/時區錯誤）→ "
              + ", ".join(_fmt(d) for d in orphan[:10]))
    for coll, gaps in gap_report.items():
        shown = ", ".join(_fmt(g) for g in gaps[:10])
        more = f" …共 {len(gaps)} 天" if len(gaps) > 10 else ""
        print(f"  ⚠️ {coll}: 缺 {len(gaps)} 個交易日 → {shown}{more}")
    for coll, thin in thin_report.items():
        shown = ", ".join(f"{_fmt(d)}({c}/鄰{m})" for d, c, m in thin[:10])
        more = f" …共 {len(thin)} 天" if len(thin) > 10 else ""
        print(f"  ⚠️ {coll}: {len(thin)} 天筆數殘缺（<局部中位×{THIN_RATIO:g}）→ {shown}{more}")

    if args.status:
        print("  (--status：不告警、不更新 state)")
        return

    # 去重：只報「新出現」的問題（缺日與缺量各自的 key，互不干擾）
    alerted = {d["_id"] for d in db.data_continuity_alerted.find({}, {"_id": 1})}
    new_gaps = {c: [g for g in gs if f"{c}:{g}" not in alerted] for c, gs in gap_report.items()}
    new_gaps = {c: gs for c, gs in new_gaps.items() if gs}
    new_thin = {c: [(d, n, m) for d, n, m in th if f"{c}:{d}:thin" not in alerted]
                for c, th in thin_report.items()}
    new_thin = {c: v for c, v in new_thin.items() if v}
    # date 欄位異常：key 含「筆數」→ 數量變動會重新告警，維持原狀則靜默。
    # 這類是「當下狀態」而非「某天的事件」，故不能只用 collection 當 key。
    new_date_bad = {c: d for c, d in date_bad.items()
                    if f"{c}:dateanom:{d['bad_type']}:{d['non_midnight']}" not in alerted}
    n_new = (sum(len(v) for v in new_gaps.values()) + sum(len(v) for v in new_thin.values())
             + len(new_date_bad))

    # 心跳（供 watchdog 確認本檢查有跑）
    db.system_heartbeat.update_one(
        {"_id": "continuity"},
        {"$set": {"last_run": datetime.now(), "status": "ok",
                  "gap_colls": len(gap_report), "thin_colls": len(thin_report), "new_issues": n_new}},
        upsert=True)

    if not n_new:
        print("  （無新問題，未告警）" if (gap_report or thin_report) else "")
        return

    lines = [f"🕳️ {datetime.now():%m-%d %H:%M} 歷史資料完整性偵測", f"發現 {n_new} 個新問題："]
    for coll, gaps in new_gaps.items():
        ds = ", ".join(f"{g[4:6]}/{g[6:]}" for g in gaps[:8])
        more = f" …共{len(gaps)}天" if len(gaps) > 8 else ""
        lines.append(f"• {coll} 缺日: {ds}{more}")
    for coll, thin in new_thin.items():
        ds = ", ".join(f"{d[4:6]}/{d[6:]}({n})" for d, n, m in thin[:8])
        more = f" …共{len(thin)}天" if len(thin) > 8 else ""
        lines.append(f"• {coll} 筆數殘缺: {ds}{more}")
    for coll, d in new_date_bad.items():
        bits = []
        if d["bad_type"]:
            bits.append(f"型別非date {d['bad_type']}筆")
        if d["non_midnight"]:
            bits.append(f"非午夜 {d['non_midnight']}筆")
        lines.append(f"• {coll} date 欄位異常: " + "、".join(bits))
    lines.append("\n→ 上游真無資料則忽略（本問題不再告警）；漏抓則補：")
    lines.append("  缺日 institutional_backfill.py、殘缺 backfill_by_date.py --date --apply")
    if new_date_bad:
        lines.append("  date 欄位異常：非資料缺漏，是寫入器 bug（時區/型別），須修寫入端")
    _line("\n".join(lines))
    print(f"  🚨 已告警 {n_new} 個新問題")

    # 標記為已告警（下次不再吵）
    docs = [{"_id": f"{c}:{g}", "ts": datetime.now()} for c, gs in new_gaps.items() for g in gs]
    docs += [{"_id": f"{c}:{d}:thin", "ts": datetime.now()} for c, th in new_thin.items() for d, n, m in th]
    docs += [{"_id": f"{c}:dateanom:{d['bad_type']}:{d['non_midnight']}", "ts": datetime.now()}
             for c, d in new_date_bad.items()]
    if docs:
        db.data_continuity_alerted.insert_many(docs)


if __name__ == "__main__":
    main()
