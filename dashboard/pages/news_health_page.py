"""📰 新聞抓取健康 —— Google News RSS 成功率/空回/被擋趨勢 + 快取新鮮度 + verdict 消息面覆蓋。

資料來源：
  - news_health_history（scripts/news_health_check.py 每交易日 19:30 寫入的探針快照）
  - team_analysis（news_count/catalyst 結構化欄位，看新聞實際覆蓋到多少 verdict）
把 google_titles() 的靜默 fail-open 變成可觀測：新聞源悄悄壞掉時這裡會先紅。非投資建議。
"""
import sys

import pandas as pd
import streamlit as st
from pymongo import MongoClient

sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")


def _db():
    return MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]


@st.cache_data(ttl=600, show_spinner="讀新聞健康快照…")
def _load_history(limit: int = 30):
    db = _db()
    rows = []
    for h in db.news_health_history.find().sort("date", -1).limit(limit):
        p = h.get("probe", {})
        c = h.get("cache", {})
        intl = h.get("intl", {})
        rows.append({
            "日期": h["date"].date(),
            "成功率%": round(p.get("success_rate", 0) * 100, 0),
            "空回%": round(p.get("empty_rate", 0) * 100, 0),
            "被擋%": round(p.get("blocked_rate", 0) * 100, 0),
            "p95(s)": p.get("lat_p95"),
            "國際成功率%": round(intl.get("success_rate", 0) * 100, 0) if intl else None,
            "快取新鮮%": round(c.get("media_fresh_rate", 0) * 100, 0),
            "快取最新(天)": c.get("cache_age_days"),
            "官方14d": c.get("major_news_14d"),
        })
    return list(reversed(rows))


@st.cache_data(ttl=600, show_spinner="讀 verdict 新聞覆蓋…")
def _load_coverage(days: int = 5):
    db = _db()
    dates = sorted(db.team_analysis.distinct("date"), reverse=True)[:days]
    rows = []
    for d in dates:
        cur = list(db.team_analysis.find(
            {"date": d}, {"catalyst": 1, "news_count": 1, "final_verdict": 1}))
        if not cur:
            continue
        n = len(cur)
        with_news = sum(1 for x in cur if x.get("catalyst"))
        avg_cnt = round(sum((x.get("news_count") or 0) for x in cur) / n, 1)
        rows.append({
            "日期": d.date() if hasattr(d, "date") else d,
            "分析檔數": n,
            "有新聞檔數": with_news,
            "新聞覆蓋%": round(with_news / n * 100, 0),
            "平均新聞則數": avg_cnt,
        })
    return rows


def show():
    st.header("📰 新聞抓取健康")
    st.caption("team 合議推播前即時抓 Google News 餵分析角色；本頁把其死活變成可觀測。")

    hist = _load_history()
    if not hist:
        st.info("尚無新聞健康快照（scripts/news_health_check.py --snapshot 累積中）。")
        return

    latest = hist[-1]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Google 成功率", f"{latest['成功率%']:.0f}%")
    c2.metric("被擋(429/403)", f"{latest['被擋%']:.0f}%",
              delta=None if latest["被擋%"] == 0 else "限流中", delta_color="inverse")
    c3.metric("快取新鮮", f"{latest['快取新鮮%']:.0f}%",
              help=f"media_news 最新 {latest['快取最新(天)']} 天前")
    c4.metric("官方重大訊息(14d)", f"{latest['官方14d']}")

    df = pd.DataFrame(hist).set_index("日期")
    st.subheader("成功率 / 空回 / 被擋 趨勢")
    st.line_chart(df[["成功率%", "空回%", "被擋%"]])

    st.subheader("每日快照")
    st.dataframe(df, use_container_width=True)

    st.subheader("🎩 verdict 新聞覆蓋（結構化 catalyst 欄位）")
    cov = _load_coverage()
    if cov:
        st.caption("有多少比例的團隊合議標的，實際被餵到新聞佐證。覆蓋率長期偏低＝新聞源可能默默失效。")
        st.dataframe(pd.DataFrame(cov).set_index("日期"), use_container_width=True)
    else:
        st.info("team_analysis 尚無 catalyst 欄位（部署後新跑的合議才會有）。")
