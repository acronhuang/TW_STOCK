"""🔔 排程警報 —— 系統排程失敗警報查詢(取代 LINE 發送)。

來源:notify_failure.sh 寫入 schedule_alerts collection(+ logs/schedule_alerts.log)。
排程失敗(hourly 資料更新、pipeline 等)不再發 LINE,改在此頁查詢。
"""
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from pymongo import MongoClient

LEVEL_BADGE = {"error": "🔴 error", "warning": "🟠 warning", "info": "🔵 info"}


@st.cache_data(ttl=60, show_spinner=False)
def _load(days, level, source, q):
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    flt = {"ts": {"$gte": datetime.now() - timedelta(days=days)}}
    if level != "全部":
        flt["level"] = level
    if source and source != "全部":
        flt["source"] = source
    rows = []
    for d in db.schedule_alerts.find(flt).sort("ts", -1).limit(2000):
        msg = d.get("message", "")
        if q and q.strip() and q.strip().lower() not in msg.lower():
            continue
        rows.append({
            "時間": d.get("ts"),
            "嚴重度": LEVEL_BADGE.get(d.get("level"), d.get("level", "")),
            "來源": d.get("source", ""),
            "訊息": msg.replace("\n", " ／ "),
        })
    return pd.DataFrame(rows)


@st.cache_data(ttl=60, show_spinner=False)
def _sources():
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    return ["全部"] + sorted(s for s in db.schedule_alerts.distinct("source") if s)


@st.cache_data(ttl=60, show_spinner=False)
def _summary():
    db = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    c = db.schedule_alerts
    now = datetime.now()
    return {
        "total": c.estimated_document_count(),
        "d1": c.count_documents({"ts": {"$gte": now - timedelta(days=1)}}),
        "err1": c.count_documents({"ts": {"$gte": now - timedelta(days=1)}, "level": "error"}),
        "latest": (c.find_one(sort=[("ts", -1)]) or {}).get("ts"),
    }


def show():
    st.title("🔔 排程警報")
    st.caption("系統排程失敗警報(hourly 資料更新、pipeline 等)。**已改為存 DB / 此頁查詢,不再發 LINE**。"
               "來源:`notify_failure.sh` → `schedule_alerts`。")

    s = _summary()
    if not s["total"]:
        st.success("目前沒有任何排程警報紀錄 🎉")
        st.caption("(排程失敗時 notify_failure.sh 會寫入這裡;若從沒失敗過則為空。)")
        return
    k = st.columns(4)
    k[0].metric("總警報數", f"{s['total']:,}")
    k[1].metric("近 24h", s["d1"])
    k[2].metric("近 24h error", s["err1"])
    k[3].metric("最新一筆", f"{s['latest']:%m-%d %H:%M}" if s["latest"] else "—")

    c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
    days = c1.select_slider("時間範圍(天)", [1, 3, 7, 14, 30, 90], value=7)
    level = c2.selectbox("嚴重度", ["全部", "error", "warning", "info"])
    source = c3.selectbox("來源", _sources())
    q = c4.text_input("搜尋訊息內容", "")

    df = _load(days, level, source, q)
    st.caption(f"顯示 {len(df):,} 筆(近 {days} 天)")
    if df.empty:
        st.info("此條件下無警報。")
        return

    st.dataframe(
        df.style.format({"時間": lambda t: f"{t:%Y-%m-%d %H:%M:%S}" if pd.notnull(t) else "—"})
          .map(lambda v: "color:#C62F35;font-weight:600" if isinstance(v, str) and "error" in v
               else ("color:#B4841F" if isinstance(v, str) and "warning" in v else ""),
               subset=["嚴重度"]),
        hide_index=True, use_container_width=True, height=520)
    st.download_button("⬇️ 下載 CSV", df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"schedule_alerts_{datetime.now():%Y%m%d}.csv", mime="text/csv")

    with st.expander("📖 說明"):
        st.markdown("""
- 這些警報**過去透過 LINE 發送**,7 月 LINE 月額度爆掉時全部靜默 → 改為寫入 DB,在此頁查詢,不受 LINE 額度影響。
- `notify_failure.sh` 每次排程失敗會寫一筆(時間/嚴重度/來源/訊息)。
- **僅當 MongoDB 本身寫不進去(致命)** 才會 fallback 發一則 LINE,確保致命故障仍能即時通知。
- 亦有純文字備份:伺服器 `logs/schedule_alerts.log`。
""")
