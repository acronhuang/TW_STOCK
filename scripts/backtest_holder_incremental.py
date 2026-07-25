#!/usr/bin/env python3
"""
大戶集中度的「增量價值」檢定（Fama-MacBeth）
=============================================
問題：backtest_holder_conc.py 已證實 |big_chg|（大戶佔比變動幅度）單獨看很強
      （4 週超額 +1.00%、t=5.87）。但它可能只是「這檔股票最近很熱鬧」的代理——
      而 chip_score_scan 的 resonance() 早就在用 volume_ratio（量比）。
      若兩者重複，接進評分只增加複雜度、不增加資訊。
      故本檢定問的是：**控制住量與波動之後，|big_chg| 還剩下什麼？**

方法：每個快照期跑一次橫斷面迴歸（Fama-MacBeth），再對 167 期的係數做 t 檢定。
      特徵一律轉成橫斷面百分位排名（0~1 後置中），使係數可直接互相比較、
      且不受離群值影響。被解釋變數為進場後 4 週報酬。

  fwd_ret ~ |big_chg| + volume_ratio + realized_vol + turnover(量) + 動能

進場時機同 backtest_holder_conc.py：資料日後第一個週二收盤（避免未來函數）。

**為什麼不控制法人/融資（誠實揭露）**
  institutional_flow 僅 2026-02-24 起（約 20 週）、stock_factors 的 volume_ratio/
  obv_slope 僅 2026-05-29 起（約 7 週）—— 樣本太少，多變數迴歸結論會是雜訊。
  故本檢定只能回答「是否為量/波動的代理」，無法回答「在法人訊號之上是否加值」。
  後者要等 institutional_flow 累積足夠歷史（或另行回補）才測得了。
  量比在此由 stock_price 自行計算（定義與 src/factors/volume_factors.py 一致：
  當日量 / 前 20 日均量，不含當日），以取得完整三年。

用法：
    python3 scripts/backtest_holder_incremental.py
    python3 scripts/backtest_holder_incremental.py --horizon 10   # 改測 2 週
"""
from __future__ import annotations

import argparse
import os
from datetime import timedelta

import numpy as np
import pandas as pd
from pymongo import MongoClient

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from backtest_holder_conc import entry_day, load_holders, load_prices   # noqa: E402

VOL_MA_WINDOW = 20      # 與 src/factors/volume_factors.py 的 VOL_MA_WINDOW 一致


def rank01(s: pd.Series) -> pd.Series:
    """橫斷面百分位排名，置中到 [-0.5, +0.5]。係數＝由最低到最高的報酬差。"""
    return s.rank(pct=True) - 0.5


def main():
    ap = argparse.ArgumentParser(description="大戶集中度增量價值檢定（Fama-MacBeth）")
    ap.add_argument("--horizon", type=int, default=20, help="持有交易日數（預設 20＝4週）")
    ap.add_argument("--min-price", type=float, default=10.0)
    ap.add_argument("--min-lots", type=float, default=100)
    ap.add_argument("--with-inst", action="store_true",
                    help="加入法人淨買佔量%%、外資佔量%% 為控制變數（需 institutional_flow 回補至 2023-03；"
                         "回補前跑此旗標會因樣本不足自動縮短區間）。")
    ap.add_argument("--db-uri", default=os.getenv("MONGODB_URI", "mongodb://localhost:27017"))
    args = ap.parse_args()

    db = MongoClient(args.db_uri)[os.getenv("MONGODB_DATABASE", "tw_stock_analysis")]

    print("載入資料 …")
    h = load_holders(db)
    h = h[~h["stock_id"].str.startswith("00")]
    piv = h.pivot_table(index="date", columns="stock_id", values="big_pct", aggfunc="last").sort_index()
    chg = piv.diff()
    close, vol = load_prices(db, piv.columns, piv.index[0] - timedelta(days=60))
    tds = list(close.index)
    ret1d = close.pct_change()
    volma = vol.rolling(VOL_MA_WINDOW).mean().shift(1)      # 前 20 日均量（不含當日）
    print(f"  快照 {len(piv)} 期｜交易日 {len(tds)} 天｜股票 {close.shape[1]} 檔")

    ip = fp = None
    if args.with_inst:
        from backtest_holder_conc import _f as _fnum
        inst = pd.DataFrame(list(db.institutional_flow.find(
            {}, {"_id": 0, "stock_id": 1, "date": 1, "total_net": 1, "foreign_net": 1})))
        inst["date"] = pd.to_datetime(inst["date"])
        for c in ("total_net", "foreign_net"):
            inst[c] = inst[c].map(_fnum)
        ip = inst.pivot_table(index="date", columns="stock_id", values="total_net", aggfunc="last").sort_index()
        fp = inst.pivot_table(index="date", columns="stock_id", values="foreign_net", aggfunc="last").sort_index()
        print(f"  法人資料 {ip.index[0]:%Y-%m-%d} ~ {ip.index[-1]:%Y-%m-%d}（{len(ip)} 天）"
              f" → 進場日不在此範圍者自動跳過")

    FEATURES = ["|大戶變化|", "量比", "波動30d", "成交量", "動能20d"]
    if args.with_inst:
        FEATURES += ["法人佔量%", "外資佔量%"]
    coefs, ts_n, solo, corrs = [], [], [], []
    for snap in [d for d in chg.index if chg.loc[d].notna().sum() >= 100]:
        e = entry_day(snap, tds, 0)
        if e is None:
            continue
        ei = tds.index(e)
        if ei + args.horizon >= len(tds) or ei < 30:
            continue
        row = chg.loc[snap].dropna().abs()
        px = close.loc[e].reindex(row.index)
        vl = vol.loc[e].reindex(row.index)
        keep = px.notna() & (px >= args.min_price) & (vl / 1000.0 >= args.min_lots)
        idx = row.index[keep.fillna(False)]
        if len(idx) < 100:
            continue

        fwd = (close.loc[tds[ei + args.horizon]].reindex(idx) / px.reindex(idx) - 1)
        vr = (vol.loc[e].reindex(idx) / volma.loc[e].reindex(idx))
        rv = ret1d.iloc[ei - 30:ei + 1].reindex(columns=idx).std()
        mom = (close.loc[e].reindex(idx) / close.loc[tds[ei - 20]].reindex(idx) - 1)

        feat = {
            "|大戶變化|": rank01(row.reindex(idx)),
            "量比": rank01(vr), "波動30d": rank01(rv),
            "成交量": rank01(vl.reindex(idx)), "動能20d": rank01(mom),
        }
        if args.with_inst:
            if e not in ip.index:            # 進場日無法人資料（回補未涵蓋）→ 跳過該期
                continue
            vl_shares = vol.loc[e].reindex(idx)
            feat["法人佔量%"] = rank01(ip.loc[e].reindex(idx) / vl_shares)
            feat["外資佔量%"] = rank01(fp.loc[e].reindex(idx) / vl_shares)
        X = pd.DataFrame(feat)
        d = pd.concat([fwd.rename("y"), X], axis=1).dropna()
        if len(d) < 100:
            continue
        A = np.column_stack([np.ones(len(d))] + [d[f].values for f in FEATURES])
        try:
            beta, *_ = np.linalg.lstsq(A, d["y"].values, rcond=None)
        except np.linalg.LinAlgError:
            continue
        coefs.append(beta[1:])
        ts_n.append(len(d))
        # 單變數對照（同一批股票、同一期）：|大戶變化| 未控制其他特徵時的係數
        A1 = np.column_stack([np.ones(len(d)), d["|大戶變化|"].values])
        b1, *_ = np.linalg.lstsq(A1, d["y"].values, rcond=None)
        solo.append(b1[1])
        # 與其他特徵的橫斷面相關（排名相關）：高＝測的是同一件事
        corrs.append([d["|大戶變化|"].corr(d[f]) for f in FEATURES[1:]])

    if len(coefs) < 20:
        print(f"❌ 有效期數僅 {len(coefs)}，樣本不足")
        return
    C = pd.DataFrame(coefs, columns=FEATURES)

    hz = {5: "1週", 10: "2週", 20: "4週"}.get(args.horizon, f"{args.horizon}日")
    print(f"\n{'='*70}\nFama-MacBeth 增量檢定｜持有 {hz}｜{len(C)} 期｜每期約 {int(np.mean(ts_n))} 檔"
          f"\n係數＝該特徵由最低排到最高，對應的報酬差（已控制其他特徵）\n{'='*70}")
    print(f"  {'特徵':<14}{'平均係數':>10}{'t 值':>8}{'顯著':>6}")
    for f in FEATURES:
        m = C[f].mean()
        t = m / (C[f].std(ddof=1) / np.sqrt(len(C)))
        print(f"  {f:<14}{m*100:>+9.2f}%{t:>8.2f}{'  ✓' if abs(t) >= 2 else '   ':>6}")

    # 關鍵對照：同一批股票、同一期，控制前 vs 控制後
    s = pd.Series(solo)
    t_solo = s.mean() / (s.std(ddof=1) / np.sqrt(len(s)))
    m_multi = C["|大戶變化|"].mean()
    t_multi = m_multi / (C["|大戶變化|"].std(ddof=1) / np.sqrt(len(C)))
    keep_pct = (m_multi / s.mean() * 100) if s.mean() else float("nan")
    print(f"\n  【|大戶變化| 控制前後對照（同批股票、同期）】")
    print(f"  {'單獨迴歸（不控制）':<20}{s.mean()*100:>+8.2f}%   t={t_solo:>5.2f}")
    print(f"  {'控制量/波動/動能後':<20}{m_multi*100:>+8.2f}%   t={t_multi:>5.2f}"
          f"   → 殘存 {keep_pct:.0f}%")

    R = pd.DataFrame(corrs, columns=FEATURES[1:])
    print(f"\n  【|大戶變化| 與其他特徵的橫斷面相關（各期平均）】")
    print("  相關高＝兩者測的是同一件事，接進評分只是換個名字再算一次")
    for f in FEATURES[1:]:
        print(f"  {'vs ' + f:<20}{R[f].mean():>+8.2f}")

    print(f"\n{'='*70}")
    if args.with_inst:
        print("已控制法人淨買佔量%、外資佔量%（institutional_flow 已回補至 2023-03）。")
        print("殘存係數＝在既有法人×量價訊號之上，|大戶變化| 額外貢獻的部分。")
    else:
        print("未控制法人 —— 加 --with-inst 納入法人佔量%（institutional_flow 已回補至 2023-03）。")


if __name__ == "__main__":
    main()
