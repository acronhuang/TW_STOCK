#!/usr/bin/env python3
"""VCP 波動收縮形態偵測 (Minervini Volatility Contraction Pattern)。
================================================================
作為 morphology 形態庫的一員，判斷個股是否處於 VCP 突破前整理：
1. Trend Template（Minervini 8 條趨勢樣板）作為前置過濾。
2. 一連串逐次收斂的回檔（後一次回檔比前一次淺）。
3. 量能逐步枯竭（dry-up），突破樞紐價(pivot)前成交量萎縮。

輸入 DataFrame 需含 open/high/low/close/volume（日線，日期升冪）。

Usage:
    from src.morphology.vcp import detect_vcp
    result = detect_vcp(df)          # 單檔判斷（dict）
    # 全市場掃描：python -m src.morphology.vcp
"""
from __future__ import annotations

import numpy as np
import pandas as pd

REQUIRED_COLS = ("open", "high", "low", "close", "volume")


def _find_swings(close: np.ndarray, order: int = 5) -> tuple[list[int], list[int]]:
    """以局部極值找轉折高/低點索引（order=左右比較窗）。"""
    highs, lows = [], []
    n = len(close)
    for i in range(order, n - order):
        window = close[i - order:i + order + 1]
        if close[i] == window.max() and close[i] > close[i - 1]:
            highs.append(i)
        if close[i] == window.min() and close[i] < close[i - 1]:
            lows.append(i)
    return highs, lows


def _trend_template(df: pd.DataFrame) -> dict:
    """Minervini 趨勢樣板 8 條（資料不足的條件記為 False）。"""
    close = df["close"].astype(float)
    price = float(close.iloc[-1])
    ma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else np.nan
    ma150 = close.rolling(150).mean().iloc[-1] if len(close) >= 150 else np.nan
    ma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else np.nan
    ma200_22ago = close.rolling(200).mean().iloc[-23] if len(close) >= 223 else np.nan

    win = close.iloc[-252:] if len(close) >= 252 else close
    low_52w = float(win.min())
    high_52w = float(win.max())

    checks = {
        "price_above_ma150_ma200": bool(price > ma150 and price > ma200) if not np.isnan(ma150) and not np.isnan(ma200) else False,
        "ma150_above_ma200": bool(ma150 > ma200) if not np.isnan(ma150) and not np.isnan(ma200) else False,
        "ma200_trending_up": bool(ma200 > ma200_22ago) if not np.isnan(ma200) and not np.isnan(ma200_22ago) else False,
        "ma50_above_ma150_ma200": bool(ma50 > ma150 and ma50 > ma200) if not np.isnan(ma50) and not np.isnan(ma150) and not np.isnan(ma200) else False,
        "price_above_ma50": bool(price > ma50) if not np.isnan(ma50) else False,
        "price_30pct_above_52w_low": bool(price >= low_52w * 1.30),
        "price_within_25pct_52w_high": bool(price >= high_52w * 0.75),
        "price_near_52w_high": bool(price >= high_52w * 0.85),
    }
    checks["passed"] = sum(checks.values())
    checks["total"] = 8
    checks["ok"] = checks["passed"] >= 7
    return checks


def detect_vcp(
    df: pd.DataFrame,
    min_contractions: int = 3,
    max_base_depth: float = 0.30,
    pivot_proximity: float = 0.08,
    swing_order: int = 5,
) -> dict:
    """偵測 VCP。

    Args:
        df: 日線 DataFrame（升冪），含 open/high/low/close/volume。
        min_contractions: 最少收斂次數（典型 2~4，預設 3 較選別）。
        max_base_depth: 整理區間（base）允許的最大深度（0.30=30%）。
        pivot_proximity: 現價距樞紐價多近才算「貼近突破」（0.08=8%）。
        swing_order: 轉折點偵測窗。

    Returns:
        dict：is_vcp、contractions（逐次回檔深度%）、pivot（樞紐價）、
              volume_dryup、trend_template、score(0~100)、reason。
    """
    if not all(c in df.columns for c in REQUIRED_COLS):
        raise ValueError(f"DataFrame 必須包含 {REQUIRED_COLS}")

    df = df.dropna(subset=list(REQUIRED_COLS)).reset_index(drop=True)
    if len(df) < 60:
        return {"is_vcp": False, "reason": "資料不足(<60 日)", "score": 0}

    close = df["close"].astype(float).to_numpy()
    volume = df["volume"].astype(float).to_numpy()
    price = float(close[-1])

    tt = _trend_template(df)

    # 只看近 ~1 季整理區找收斂
    base = df.iloc[-70:].reset_index(drop=True)
    base_close = base["close"].astype(float).to_numpy()
    highs, lows = _find_swings(base_close, order=swing_order)

    # 配對（高→其後最近的低）量出每段回檔深度
    contractions: list[float] = []
    for h in highs:
        later_lows = [l for l in lows if l > h]
        if not later_lows:
            continue
        l = later_lows[0]
        depth = (base_close[h] - base_close[l]) / base_close[h]
        if depth > 0:
            contractions.append(round(depth * 100, 2))

    # 收斂判定：至少 min_contractions 段，且整體呈遞減（容許 1 次反彈）
    contracting = False
    if len(contractions) >= min_contractions:
        recent = contractions[-max(min_contractions, 3):]
        decreasing = sum(recent[i] >= recent[i + 1] for i in range(len(recent) - 1))
        contracting = decreasing >= (len(recent) - 2) and recent[-1] <= recent[0]

    base_depth = (base_close.max() - base_close.min()) / base_close.max()
    base_ok = base_depth <= max_base_depth

    # 量能枯竭：近 10 日均量 < 前 50 日均量
    vol_recent = float(volume[-10:].mean())
    vol_prior = float(volume[-60:-10].mean()) if len(volume) >= 60 else float(volume.mean())
    vol_ratio = vol_recent / vol_prior if vol_prior > 0 else 1.0
    volume_dryup = bool(vol_prior > 0 and vol_ratio < 0.85)

    # 樞紐價 = 整理區最後一段高點（突破買點）
    pivot = float(base_close[highs[-1]]) if highs else float(base_close.max())
    pivot_dist = (pivot - price) / pivot if pivot > 0 else 1.0
    near_pivot = bool(0 <= pivot_dist <= pivot_proximity and price <= pivot * 1.02)

    # 連續評分 0~100（著重 VCP 專有品質，讓 is_vcp 候選排得開）
    def _clamp(x: float) -> float:
        return max(0.0, min(1.0, x))

    final_depth = contractions[-1] if contractions else 100.0
    ratio = (contractions[-1] / contractions[0]) if len(contractions) >= 2 and contractions[0] > 0 else 1.0
    score = (
        (tt["passed"] / 8) * 15                              # 趨勢樣板 0~15
        + (min(len(contractions), 4) / 4) * 15               # 收斂段數 0~15（3+ 為佳）
        + _clamp((15 - final_depth) / 12) * 25               # 最後一段越淺越好 0~25
        + _clamp(1.0 - ratio) * 15                           # 收斂比（last/first）越小越好 0~15
        + _clamp((max_base_depth - base_depth) / max_base_depth) * 10  # 整理越緊越好 0~10
        + _clamp((0.85 - vol_ratio) / 0.35) * 10             # 量縮程度 0~10
        + _clamp((pivot_proximity - pivot_dist) / pivot_proximity) * 10  # 貼近樞紐 0~10
    )
    score = round(min(max(score, 0.0), 100.0), 1)

    is_vcp = bool(tt["ok"] and contracting and base_ok and len(contractions) >= min_contractions)

    reasons = []
    if not tt["ok"]:
        reasons.append(f"趨勢樣板僅 {tt['passed']}/8")
    if not contracting:
        reasons.append("回檔未逐次收斂")
    if not base_ok:
        reasons.append(f"整理深度過大 {base_depth*100:.0f}%")
    if len(contractions) < min_contractions:
        reasons.append(f"收斂段數不足({len(contractions)})")

    return {
        "is_vcp": is_vcp,
        "score": score,
        "price": round(price, 2),
        "pivot": round(pivot, 2),
        "near_pivot": near_pivot,
        "contractions": contractions,
        "n_contractions": len(contractions),
        "base_depth_pct": round(base_depth * 100, 2),
        "volume_dryup": volume_dryup,
        "trend_template": tt,
        "reason": "；".join(reasons) if reasons else "符合 VCP",
    }


def screen_vcp_market(
    mongo_uri: str = "mongodb://localhost:27017/",
    db_name: str = "tw_stock_analysis",
    min_score: int = 70,
    lookback_days: int = 400,
    limit_symbols: int | None = None,
    require_vcp: bool = True,
) -> list[dict]:
    """全市場 VCP 掃描；回傳符合条件的清單（分數降冪）。

    require_vcp=True（預設）：以 is_vcp 為硬門檻（趨勢樣板 + 逐次收斂 + 整理深度），
    再以 score>=min_score 排序；避免「強趨勢但未收斂」的個股混入。"""
    from datetime import datetime, timedelta

    from pymongo import MongoClient

    from src.domain.collections import COLL_STOCK_PRICE

    client = MongoClient(mongo_uri)
    db = client[db_name]
    cutoff = datetime.now() - timedelta(days=lookback_days)

    symbols = db[COLL_STOCK_PRICE].distinct("symbol")
    symbols = [s for s in symbols if isinstance(s, str) and s.isdigit() and len(s) == 4]
    if limit_symbols:
        symbols = symbols[:limit_symbols]

    results: list[dict] = []
    for sym in symbols:
        rows = list(db[COLL_STOCK_PRICE].find(
            {"symbol": sym, "date": {"$gte": cutoff}},
            {"_id": 0, "date": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
        ).sort("date", 1))
        if len(rows) < 60:
            continue
        df = pd.DataFrame(rows)
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].map(lambda v: float(v.to_decimal()) if hasattr(v, "to_decimal") else v)
        try:
            res = detect_vcp(df)
        except ValueError:
            continue
        if require_vcp and not res.get("is_vcp"):
            continue
        if res.get("score", 0) >= min_score:
            res["symbol"] = sym
            results.append(res)

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def _main() -> None:
    hits = screen_vcp_market(min_score=70)
    print(f"VCP 候選 {len(hits)} 檔：")
    for r in hits[:40]:
        flag = "★突破在即" if r["near_pivot"] else ""
        print(f"  {r['symbol']}  score={r['score']:>3}  pivot={r['pivot']:>8}  "
              f"收斂={r['contractions']}  {flag}")


if __name__ == "__main__":
    _main()
