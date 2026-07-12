#!/usr/bin/env python3
"""每日選股推薦頁面：4 大選股法(因子/蔡森/謝富旭/北大) + 多策略交叉推薦。
資料來源：results/daily_picks/picks_*.json（daily_recommendations.py 每日 17:30 產生）。"""
import glob
import json
import os

import pandas as pd
import streamlit as st

PICKS_DIR = "/home/mdsadmin/Stock/tw-stock-analysis/results/daily_picks"


def _files_by_date():
    """{YYYY-MM-DD: 最新一份該日檔案}，日期新→舊。"""
    out = {}
    for f in sorted(glob.glob(f"{PICKS_DIR}/picks_*.json")):
        base = os.path.basename(f)          # picks_20260710_012453.json
        ymd = base.split("_")[1]
        d = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"
        out[d] = f                          # 後者覆蓋，保留當日最新
    return dict(sorted(out.items(), reverse=True))


def _df(rows, cols):
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    keep = [c for c in cols if c in df.columns]
    return df[keep].rename(columns=cols)


def show():
    st.title("🏛️ 每日選股推薦")
    st.caption("4 大選股法整合：因子排行 · 蔡森型態 · 謝富旭存股 · 北大風控 → 交叉比對")

    fmap = _files_by_date()
    if not fmap:
        st.warning("尚無選股結果。daily_recommendations.py 每日 17:30 產生於 results/daily_picks/。")
        return

    sel = st.selectbox("日期", list(fmap.keys()))
    data = json.load(open(fmap[sel], encoding="utf-8"))

    # ── 市場週期（北大法則）──
    pku = (data.get("pku") or {}).get("cycle") or {}
    if pku:
        st.info(f"📅 **市場週期**：{pku.get('description', '')}　"
                f"建議持股水位 **{pku.get('suggested_position', '-')}**")

    # ── 🏆 多策略共同推薦 ──
    st.subheader("🏆 多策略共同推薦")
    cr = data.get("cross_reference") or []
    if not cr:
        st.write("今日無多策略共同確認的標的。")
    else:
        for sym, info in cr:
            srcs = "、".join(info.get("sources", []))
            with st.container(border=True):
                st.markdown(f"### {sym} {info.get('name', '')}　`{srcs}` 同時選中")
                cols = st.columns(len(info.get("details", {})) or 1)
                for c, (method, det) in zip(cols, info.get("details", {}).items()):
                    with c:
                        st.caption(det.get("source", method))
                        for k, label in [("price", "股價"), ("pe", "本益比"), ("upside", "上漲空間%"),
                                         ("dy", "殖利率%"), ("fs_grade", "財報"), ("pattern", "型態"),
                                         ("tf", "週期"), ("pat_score", "型態分"), ("debt_ratio", "負債率"),
                                         ("payout_years", "連配年")]:
                            if det.get(k) is not None:
                                st.write(f"{label}：{det[k]}")

    st.markdown("---")

    # ── 三法各自清單 ──
    t1, t2, t3 = st.tabs([
        f"📊 因子排行 ({len(data.get('factor') or [])})",
        f"📈 蔡森型態 ({len(data.get('senvision') or [])})",
        f"💎 謝富旭存股 ({len(data.get('hsieh') or [])})",
    ])
    with t1:
        st.caption("綜合評分≥70、有上漲空間、財報健康的因子強勢股")
        st.dataframe(_df(data.get("factor"), {
            "sym": "代號", "name": "名稱", "price": "股價", "pe": "本益比",
            "upside": "上漲空間%", "dy": "殖利率%", "sharpe": "夏普", "fs_grade": "財報"}),
            width="stretch", hide_index=True)
    with t2:
        st.caption("技術型態突破（W底、頸線突破等），依型態分排序")
        st.dataframe(_df(data.get("senvision"), {
            "sym": "代號", "name": "名稱", "price": "股價", "pattern": "型態",
            "tf": "週期", "pat_score": "型態分", "vp_state": "量價", "sharpe": "夏普"}),
            width="stretch", hide_index=True)
    with t3:
        st.caption("深度價值存股：高殖利率、低負債、獲利穩定、連續配息")
        st.dataframe(_df(data.get("hsieh"), {
            "sym": "代號", "name": "名稱", "price": "股價", "dy": "殖利率%",
            "debt_ratio": "負債率", "current_ratio": "流動比", "payout_years": "連配年"}),
            width="stretch", hide_index=True)
