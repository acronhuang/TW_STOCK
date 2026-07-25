#!/usr/bin/env python3
"""
大戶集中度訊號回測（shareholding.big_pct 週變化 → 未來報酬）
==============================================================
問題：「千張大戶佔比週增」對未來股價有沒有預測力？值不值得進 chip_score_scan 的評分？

**進場時機（本腳本最重要的設計，勿改）**
  集保「資料日」D 與「我們知道 D」之間有數日落差：資料表只存 D，不存公布日。
  用 D 當天收盤進場 = 未來函數（look-ahead）—— 那天根本還不知道大戶佔比變化，
  回測會漂亮得很有說服力，實盤則不會。籌碼類回測最常見的作假就在這裡。
  故進場一律設在「D 之後的第一個週二」收盤：那正是 cron（`0 9 * * 2`）真正把資料
  寫進 DB 的時刻，也是第一個可據以下單的價格。這不只是保守，是「可實現」。
  實證（本專案自身觀測）：資料日 07-03(五) 由 07-07(二) cron 取得；07-09(四) 由
  07-14(二) 取得 —— 落差 4–5 天，次週二假設與兩次觀測皆相容。
  --entry-lag-weeks 可再往後推，用來檢驗結論是否依賴這個假設。

方法：
  每個快照日 D 計算 big_chg = big_pct(D) − big_pct(前一快照)，橫斷面分 5 組（Q1 最賣、
  Q5 最買），比較各組進場後 1/2/4 週（以交易日 5/10/20 計）的報酬。
  同時報「原始報酬」與「超額報酬」（減去當週母體等權平均，去除大盤方向）。

已知限制（誠實，勿在結論中忽略）：
  - 歷史僅 2023-03 起（norway 回補上限），約 3 年、涵蓋單一多頭段 → 空頭有效性未知。
  - 母體為「今日仍在」的股票 → 存活者偏誤，報酬偏樂觀。
  - 歷史列來自 norway、近期列來自 TDCC，同日互差 ~0.01pp（四捨五入），對分組無實質影響。

用法：
    python3 scripts/backtest_holder_conc.py
    python3 scripts/backtest_holder_conc.py --entry-lag-weeks 1   # 敏感度：再晚一週進場
    python3 scripts/backtest_holder_conc.py --include-etf --min-price 0
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from _adj_price import ADJ_PROJ, use_adjusted_df  # noqa: E402
from bson import Decimal128
from pymongo import MongoClient

HORIZONS = {"1週": 5, "2週": 10, "4週": 20}   # 交易日
N_GROUPS = 5

# --combo 的四象限（大戶佔比 × 總股東人數，各取橫斷面三分位後交集）
COMBO_LABELS = {
    1: "吸籌 大戶↑股東↓",
    2: "     大戶↑股東↑",
    3: "     大戶↓股東↓",
    4: "出貨 大戶↓股東↑",
}


def _f(x):
    if x is None:
        return np.nan
    if isinstance(x, Decimal128):
        return float(x.to_decimal())
    try:
        return float(x)
    except (ValueError, TypeError):
        return np.nan


def load_holders(db) -> pd.DataFrame:
    """回傳 long-form: date, stock_id, big_pct, total_holders。

    total_holders（總股東人數）是「散戶動向」在三年歷史上唯一可得的代理：
    retail_pct（散戶佔股數比例）只有 TDCC 起算後的兩期，norway 不提供該級距；
    但總股東人數 norway 全期都有（340007 列，100% 覆蓋）。人數增加＝籌碼分散。
    """
    rows = list(db.shareholding.find(
        {"big_pct": {"$ne": None}},
        {"_id": 0, "date": 1, "stock_id": 1, "big_pct": 1, "total_holders": 1}))
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["big_pct"] = df["big_pct"].map(_f)
    df["total_holders"] = df["total_holders"].map(_f)
    return df.dropna(subset=["big_pct"])


def load_prices(db, symbols, start) -> tuple[pd.DataFrame, pd.DataFrame]:
    """回傳 (close_pivot, volume_pivot)，index=交易日, columns=股票。"""
    cur = db.stock_price.find(
        {"symbol": {"$in": list(symbols)}, "date": {"$gte": start}},
        {"_id": 0, "symbol": 1, "date": 1, "close": 1, "volume": 1, **ADJ_PROJ})
    df = pd.DataFrame(list(cur))
    df["date"] = pd.to_datetime(df["date"])
    df = use_adjusted_df(df)   # 用還原價,否則除權息=假跌
    df["close"] = df["close"].map(_f)
    df["volume"] = df["volume"].map(_f)
    df = df.dropna(subset=["close"])
    df = df[df["close"] > 0]
    close = df.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").sort_index()
    vol = df.pivot_table(index="date", columns="symbol", values="volume", aggfunc="last").sort_index()
    return close, vol


def entry_day(snapshot: pd.Timestamp, trading_days: list, lag_weeks: int):
    """D 之後第一個週二（＝cron 實際取得資料的時刻）對應的交易日收盤。
    該週二若休市，順延至其後第一個交易日。lag_weeks 可再往後推整週（敏感度檢驗）。"""
    days_ahead = (1 - snapshot.weekday()) % 7 or 7      # 下一個週二（嚴格大於 D）
    target = snapshot + timedelta(days=days_ahead + 7 * lag_weeks)
    for d in trading_days:
        if d >= target:
            return d
    return None


def main():
    ap = argparse.ArgumentParser(description="大戶集中度訊號回測")
    ap.add_argument("--entry-lag-weeks", type=int, default=0,
                    help="在『次週二』基礎上再往後推幾週（敏感度檢驗，預設 0）")
    ap.add_argument("--min-price", type=float, default=10.0, help="進場日最低收盤價")
    ap.add_argument("--min-lots", type=float, default=100, help="進場日最低成交張數")
    ap.add_argument("--include-etf", action="store_true", help="納入 ETF（代號 00 開頭）")
    ap.add_argument("--abs", action="store_true",
                    help="改以 |big_chg| 分組。用於檢定『兩端都好』的 U 形：若成立，"
                         "訊號代表的是變動幅度（關注度/波動度代理），而非方向。")
    ap.add_argument("--combo", action="store_true",
                    help="檢定雙重確認：大戶佔比↑ 且 總股東人數↓ = 主力吸籌（反之為出貨）。"
                         "兩訊號各取橫斷面三分位，交集成四象限。單一訊號無效不代表組合無效。")
    ap.add_argument("--db-uri", default=os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    args = ap.parse_args()

    db = MongoClient(args.db_uri)[os.getenv("MONGODB_DATABASE", "tw_stock_analysis")]

    print("載入大戶持股 …")
    h = load_holders(db)
    if not args.include_etf:
        h = h[~h["stock_id"].str.startswith("00")]
    piv = h.pivot_table(index="date", columns="stock_id", values="big_pct", aggfunc="last").sort_index()
    chg = piv.diff()                                    # 對「前一個快照」的變化（百分點）
    # 股東人數用「相對變化」：2330 有 291 萬股東、小型股僅數千，絕對人數不可橫斷面比較
    hpiv = h.pivot_table(index="date", columns="stock_id", values="total_holders",
                         aggfunc="last").sort_index()
    hchg = hpiv.pct_change()
    snapshots = [d for d in chg.index if chg.loc[d].notna().sum() >= 100]
    print(f"  快照 {len(piv)} 期（可用 {len(snapshots)} 期）｜股票 {piv.shape[1]} 檔"
          f"｜{piv.index[0]:%Y-%m-%d} ~ {piv.index[-1]:%Y-%m-%d}")

    print("載入股價 …")
    close, vol = load_prices(db, piv.columns, piv.index[0] - timedelta(days=10))
    tds = list(close.index)
    print(f"  交易日 {len(tds)} 天｜股票 {close.shape[1]} 檔")

    recs = []
    for snap in snapshots:
        e = entry_day(snap, tds, args.entry_lag_weeks)
        if e is None:
            continue
        ei = tds.index(e)
        row = chg.loc[snap].dropna()
        if args.abs:
            row = row.abs()
        px = close.loc[e].reindex(row.index)
        vl = vol.loc[e].reindex(row.index) / 1000.0     # 股 → 張
        keep = px.notna() & (px >= args.min_price) & (vl >= args.min_lots)
        row, px = row[keep], px[keep]
        if len(row) < N_GROUPS * 10:
            continue

        if args.combo:
            # 雙重確認：兩訊號各取橫斷面三分位，交集成四象限。
            # 只用正負號會被雜訊淹沒（多數股票每週變動極小），故用相對強弱。
            hr = hchg.loc[snap].reindex(row.index).dropna()
            r2 = row.reindex(hr.index)
            if len(hr) < 90:
                continue
            try:
                bt = pd.qcut(r2.rank(method="first"), 3, labels=False)    # 0=大戶減 2=大戶增
                ht = pd.qcut(hr.rank(method="first"), 3, labels=False)    # 0=股東減 2=股東增
            except ValueError:
                continue
            grp = pd.Series(0, index=r2.index)          # 0 = 其他（不納入比較）
            grp[(bt == 2) & (ht == 0)] = 1              # 吸籌：大戶增 + 股東減
            grp[(bt == 2) & (ht == 2)] = 2              # 大戶增 + 股東增
            grp[(bt == 0) & (ht == 0)] = 3              # 大戶減 + 股東減
            grp[(bt == 0) & (ht == 2)] = 4              # 出貨：大戶減 + 股東增
            row = r2
            px = px.reindex(r2.index)
        else:
            try:                                        # 同值過多時 qcut 會失敗
                grp = pd.qcut(row.rank(method="first"), N_GROUPS, labels=False) + 1
            except ValueError:
                continue
        for label, k in HORIZONS.items():
            if ei + k >= len(tds):
                continue
            fwd = close.loc[tds[ei + k]].reindex(row.index) / px - 1
            ok = fwd.notna()
            if ok.sum() < N_GROUPS * 10:
                continue
            ex = fwd - fwd[ok].mean()                   # 超額：減當期母體等權平均
            for g in range(1, N_GROUPS + 1):
                m = ok & (grp == g)
                if m.sum():
                    recs.append({"snapshot": snap, "entry": e, "horizon": label, "group": g,
                                 "n": int(m.sum()), "ret": fwd[m].mean(), "excess": ex[m].mean(),
                                 "chg": row[m].mean()})

    if not recs:
        print("❌ 無足夠樣本")
        return
    r = pd.DataFrame(recs)

    lag_note = "" if args.entry_lag_weeks == 0 else f"（+{args.entry_lag_weeks} 週）"
    print(f"\n{'='*76}\n大戶佔比週變化 → 未來報酬｜進場＝資料日後第一個週二收盤{lag_note}"
          f"\n樣本 {r['snapshot'].nunique()} 期｜{r['entry'].min():%Y-%m-%d} ~ {r['entry'].max():%Y-%m-%d}\n{'='*76}")

    for label in HORIZONS:
        sub = r[r["horizon"] == label]
        if sub.empty:
            continue
        print(f"\n【{label}後】")
        print(f"  {'組別':<22}{'平均大戶變化':>12}{'平均報酬':>10}{'超額報酬':>10}{'樣本/期':>9}")
        for g in range(1, N_GROUPS + 1):
            s = sub[sub["group"] == g]
            if s.empty:
                continue
            if args.combo:
                tag = COMBO_LABELS[g]
            elif args.abs:
                tag = {1: "Q1 變動最小", N_GROUPS: f"Q{N_GROUPS} 變動最大"}.get(g, f"Q{g}")
            else:
                tag = {1: "Q1 大戶減最多", N_GROUPS: f"Q{N_GROUPS} 大戶增最多"}.get(g, f"Q{g}")
            print(f"  {tag:<22}{s['chg'].mean():>+11.2f}%{s['ret'].mean()*100:>9.2f}%"
                  f"{s['excess'].mean()*100:>+9.2f}%{s['n'].mean():>9.0f}")
        # 價差：以「每期價差」為樣本做 t 檢定（期間內獨立性假設，非 Newey-West）
        hi, lo, name = (1, 4, "→ 吸籌−出貨 價差") if args.combo else (N_GROUPS, 1, "→ Q5−Q1 價差")
        w = sub.pivot_table(index="snapshot", columns="group", values="excess")
        if hi in w and lo in w:
            sp = (w[hi] - w[lo]).dropna()
            t = sp.mean() / (sp.std(ddof=1) / np.sqrt(len(sp))) if len(sp) > 1 and sp.std(ddof=1) else np.nan
            win = (sp > 0).mean() * 100
            print(f"  {name:<22}{'':>12}{'':>10}{sp.mean()*100:>+9.2f}%"
                  f"   t={t:>5.2f}  勝率 {win:.0f}%（{len(sp)} 期）")

    print(f"\n{'='*76}")
    print("限制：3 年單一多頭段；母體為今日仍在的股票（存活者偏誤）→ 結論僅供參考，非證明。")
    print(f"敏感度：另跑 --entry-lag-weeks 1 檢驗結論是否依賴進場時機假設。")


if __name__ == "__main__":
    main()
