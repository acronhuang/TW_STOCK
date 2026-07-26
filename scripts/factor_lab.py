#!/usr/bin/env python3
"""A3:正規因子評估框架(IC / 分位數 / 產業中性 z-score / 多循環)。

這是「補齊資料後的公平檢定」用的研究骨架,取代先前草率的單因子回測。
輸入任一因子(stock_factors 日頻 或 fundamental_factors PIT),輸出:
  - 產業中性 z-score(在各產業內橫斷面標準化,消除產業偏移)
  - Rank IC 時間序列 → IC 均值 / IR(=均值/標準差) / t 值 / 勝率
  - 分位數組合(N 分位)前瞻報酬 → Q_top−Q_bottom 價差 / 單調性
  - 多循環拆解(多頭/空頭,用大盤 200 日均線)分別回報

用還原價(adj_close,已修分割/減資)算前瞻報酬。月頻換手。

用法:
  factor_lab.py --factor earnings_yield --start 2018-01-01 --end 2026-06-30 --fwd 1
  factor_lab.py --factor roic --source fundamental --start 2018-01-01 --end 2026-06-30
"""
import argparse
from datetime import datetime

import numpy as np
import pandas as pd
from bson.decimal128 import Decimal128
from pymongo import MongoClient

ETF_INDUSTRIES = {"ETF", "上櫃ETF", "受益證券", "存託憑證"}


def _f(v):
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    return float(v) if isinstance(v, (int, float)) else np.nan


class FactorLab:
    def __init__(self, db):
        self.db = db
        self._sectors = None
        self._bench = None

    # ---- 產業別(排除 ETF/非普通股) ----
    def sectors(self):
        if self._sectors is None:
            m = {}
            for d in self.db.taiwan_stock_info.find(
                    {}, {"stock_id": 1, "industry_category": 1}):
                ind = d.get("industry_category")
                sid = d.get("stock_id")
                if sid and ind and ind not in ETF_INDUSTRIES:
                    m[sid] = ind
            self._sectors = m
        return self._sectors

    # ---- 月底交易日 ----
    def month_end_dates(self, start, end):
        ds = self.db.stock_price.distinct(
            "date", {"date": {"$gte": start, "$lte": end}})
        ds = sorted(ds)
        out, cur = [], None
        for i, d in enumerate(ds):
            ym = (d.year, d.month)
            if cur is not None and ym != cur:
                out.append(ds[i - 1])   # 上一交易日 = 該月最後交易日
            cur = ym
        if ds:
            out.append(ds[-1])
        return out

    # ---- 某日全市場還原收盤(dict symbol->adj_close) ----
    def _adj_close_on(self, d):
        from datetime import timedelta
        out = {}
        for r in self.db.stock_price.find(
                {"date": {"$gte": d, "$lt": d + timedelta(days=1)}},
                {"_id": 0, "symbol": 1, "adj_close": 1, "close": 1}):
            p = _f(r.get("adj_close"))
            if np.isnan(p):
                p = _f(r.get("close"))
            if not np.isnan(p) and p > 0:
                out[r["symbol"]] = p
        return out

    # ---- 某日因子值(source: stock_factors 日頻 / fundamental PIT) ----
    def _factor_on(self, d, field, source):
        out = {}
        if source == "stock_factors":
            for r in self.db.stock_factors.find(
                    {"date": d, field: {"$ne": None}},
                    {"_id": 0, "symbol": 1, field: 1}):
                v = _f(r.get(field))
                if not np.isnan(v):
                    out[r["symbol"]] = v
        else:  # fundamental_factors:取 available_from <= d 的最新一期(PIT)
            # 為效率,一次抓所有 available_from<=d 的最新期(用聚合)
            pipe = [
                {"$match": {"available_from": {"$lte": d}, field: {"$ne": None}}},
                {"$sort": {"available_from": -1}},
                {"$group": {"_id": "$stock_id", "v": {"$first": f"${field}"}}},
            ]
            for r in self.db.fundamental_factors.aggregate(pipe):
                v = _f(r.get("v"))
                if not np.isnan(v):
                    out[r["_id"]] = v
        return out

    # ---- 大盤基準(0050 還原)供循環判定 ----
    def bench(self):
        if self._bench is None:
            rows = []
            from datetime import timedelta  # noqa
            for r in self.db.stock_price.find(
                    {"symbol": "0050"}, {"_id": 0, "date": 1, "adj_close": 1, "close": 1}
            ).sort("date", 1):
                p = _f(r.get("adj_close"))
                if np.isnan(p):
                    p = _f(r.get("close"))
                if not np.isnan(p):
                    rows.append((r["date"], p))
            s = pd.Series({d: p for d, p in rows}).sort_index()
            self._bench = s
        return self._bench

    def regime_of(self, d):
        """多頭/空頭:0050 還原價 vs 其 200 交易日均線。"""
        s = self.bench()
        s2 = s[s.index <= d]
        if len(s2) < 200:
            return "unknown"
        return "多頭" if s2.iloc[-1] >= s2.iloc[-200:].mean() else "空頭"

    # ---- 建 panel ----
    def build(self, field, start, end, fwd_months=1, source="stock_factors"):
        dates = self.month_end_dates(start, end)
        sec = self.sectors()
        recs = []
        for k in range(len(dates) - fwd_months):
            d0 = dates[k]
            d1 = dates[k + fwd_months]
            fac = self._factor_on(d0, field, source)
            p0 = self._adj_close_on(d0)
            p1 = self._adj_close_on(d1)
            reg = self.regime_of(d0)
            for sym, fv in fac.items():
                if sym not in sec or sym not in p0 or sym not in p1:
                    continue
                fwd = p1[sym] / p0[sym] - 1
                recs.append((d0, sym, sec[sym], fv, fwd, reg))
        df = pd.DataFrame(recs, columns=["date", "symbol", "sector", "factor", "fwd", "regime"])
        return df

    # ---- 產業中性 z-score ----
    @staticmethod
    def sector_z(df):
        def z(g):
            m, s = g["factor"].mean(), g["factor"].std()
            g["fz"] = (g["factor"] - m) / s if s and s > 0 else 0.0
            return g
        return df.groupby(["date", "sector"], group_keys=False).apply(z)

    # ---- Rank IC ----
    @staticmethod
    def ic(df, col="fz"):
        ics = df.groupby("date")[[col, "fwd"]].apply(
            lambda g: g[col].corr(g["fwd"], method="spearman") if len(g) >= 10 else np.nan
        ).dropna()
        mean, std = ics.mean(), ics.std()
        ir = mean / std if std else np.nan
        t = ir * np.sqrt(len(ics)) if not np.isnan(ir) else np.nan
        hit = (ics > 0).mean()
        return {"n_periods": len(ics), "IC_mean": mean, "IC_std": std,
                "IR": ir, "t": t, "hit_rate": hit, "series": ics}

    # ---- 分位數(前瞻報酬橫斷面 winsorize 1%/99%,避免雞蛋水餃股暴漲扭曲均值) ----
    @staticmethod
    def quantiles(df, n=5, col="fz"):
        def qassign(g):
            try:
                g["q"] = pd.qcut(g[col].rank(method="first"), n, labels=False) + 1
            except ValueError:
                g["q"] = np.nan
            lo, hi = g["fwd"].quantile([0.01, 0.99])
            g["fwd_w"] = g["fwd"].clip(lo, hi)
            return g
        d = df.groupby("date", group_keys=False).apply(qassign).dropna(subset=["q"])
        qret = d.groupby(["date", "q"])["fwd_w"].mean().unstack()
        avg = qret.mean()   # 各分位平均月報酬
        spread = avg.get(n, np.nan) - avg.get(1, np.nan)
        mono = avg.is_monotonic_increasing or avg.is_monotonic_decreasing
        return {"q_avg": avg, "spread_top_bottom": spread, "monotonic": mono,
                "q_ret_ts": qret}


def _pct(v):
    return f"{v*100:+.3f}%" if v is not None and not (isinstance(v, float) and np.isnan(v)) else "n/a"


def evaluate(db, field, start, end, fwd, source, n_q=5):
    lab = FactorLab(db)
    print(f"\n=== 因子評估:{field} | {start:%Y-%m}~{end:%Y-%m} | 前瞻{fwd}月 | 來源{source} ===")
    df = lab.build(field, start, end, fwd, source)
    if df.empty:
        print("無資料"); return
    print(f"樣本:{len(df):,} 檔·期,{df['date'].nunique()} 個換手日,{df['symbol'].nunique()} 檔")
    dfz = lab.sector_z(df)
    # 全體 IC
    r = lab.ic(dfz)
    print(f"\n[產業中性 Rank IC] 期數{r['n_periods']} | IC均值 {r['IC_mean']:+.4f} | "
          f"IR {r['IR']:+.3f} | t {r['t']:+.2f} | 勝率 {r['hit_rate']*100:.0f}%")
    q = lab.quantiles(dfz, n_q)
    print(f"[分位數月報酬] " + " ".join(f"Q{int(i)}={_pct(v)}" for i, v in q['q_avg'].items()))
    print(f"  Q{n_q}−Q1 價差={_pct(q['spread_top_bottom'])}/月 | 單調={'✅' if q['monotonic'] else '❌'}")
    # 多循環拆解
    print("[多循環拆解]")
    for reg in ["多頭", "空頭"]:
        sub = dfz[dfz["regime"] == reg]
        if sub["date"].nunique() >= 6:
            rr = lab.ic(sub)
            print(f"  {reg}:期數{rr['n_periods']} IC均值{rr['IC_mean']:+.4f} IR{rr['IR']:+.3f} 勝率{rr['hit_rate']*100:.0f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--factor", required=True)
    ap.add_argument("--source", choices=["stock_factors", "fundamental"], default="stock_factors")
    ap.add_argument("--start", default="2018-01-01")
    ap.add_argument("--end", default="2026-06-30")
    ap.add_argument("--fwd", type=int, default=1)
    ap.add_argument("--nq", type=int, default=5)
    a = ap.parse_args()
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    evaluate(db, a.factor,
             datetime.strptime(a.start, "%Y-%m-%d"),
             datetime.strptime(a.end, "%Y-%m-%d"),
             a.fwd, a.source, a.nq)


if __name__ == "__main__":
    main()
