#!/usr/bin/env python3
"""📬 每日快訊（LINE 內容鏡像 + 完整明細）

收盤 pipeline 產生的通知會落地到 digest_history:
  - full_sections: **完整未濃縮**內容(依主題分區)→ 網頁預設顯示全文,無字數限制。
  - messages: LINE 實際推播的濃縮版(受 5000 字限)→ 收在摺疊區。
LINE 月額度用盡(429)時,這裡仍可完整查閱。
"""
from datetime import datetime

import streamlit as st
from pymongo import MongoClient


def _db():
    return MongoClient("localhost", 27017)["tw_stock_analysis"]


@st.cache_data(ttl=60, show_spinner=False)
def _load(limit=60):
    db = _db()
    return list(db.digest_history.find({}, {"_id": 0}).sort("date", -1).limit(limit))


def show():
    st.title("📬 每日快訊")
    st.caption("收盤彙整通知的**完整內容**。LINE 額度用盡時,這裡仍可查閱全文(網頁無字數限制,不會被截)。")

    docs = _load()
    if not docs:
        st.info("尚無快訊紀錄。今晚收盤 pipeline（evening_pipeline）跑過 evening_digest 後即會出現。")
        return

    dates = [d.get("date_str", str(d.get("date", ""))[:10]) for d in docs]
    c1, c2 = st.columns([2, 3])
    with c1:
        pick = st.selectbox("選擇日期", dates, index=0)
    doc = next((d for d in docs if d.get("date_str", str(d.get("date", ""))[:10]) == pick), docs[0])

    msgs = doc.get("messages", [])
    full = doc.get("full_sections", [])
    gen = doc.get("generated_at")
    gen_s = gen.strftime("%Y-%m-%d %H:%M") if isinstance(gen, datetime) else str(gen or "")
    sent = doc.get("sent_ok")
    meta = f"🕒 產生於 {gen_s} ｜ 來源 {doc.get('entry_count', '?')} 則"
    if sent is None:
        meta += " ｜ LINE：未發送（僅落地）"
    elif sent == len(msgs):
        meta += f" ｜ LINE：✅ 全發送 {sent}/{len(msgs)}"
    else:
        meta += f" ｜ LINE：⚠️ 僅發送 {sent}/{len(msgs)}（額度不足，內容仍在此）"
    with c2:
        st.caption(meta)

    # ---- 完整內容(預設,依主題分區,不濃縮) ----
    if full:
        for sec in full:
            st.markdown(f"#### {sec.get('theme', '')}")
            for body in sec.get("sources", []):
                with st.container(border=True):
                    st.text(body)
    else:
        # 舊資料無 full_sections → 退回顯示濃縮訊息
        st.info("此日為舊格式紀錄,僅有濃縮版(新資料會顯示完整內容)。")
        for m in msgs:
            with st.container(border=True):
                st.text(m.get("text", ""))

    # ---- LINE 實際推播的濃縮版(摺疊) ----
    if msgs:
        with st.expander(f"📱 LINE 實際推播版（濃縮 {len(msgs)} 則,受 5000 字限）", expanded=False):
            for m in msgs:
                st.caption(f"訊息 {m.get('seq', '')}／{len(msgs)}　·　{m.get('chars', 0)} 字")
                st.text(m.get("text", ""))

    st.divider()
    st.caption("📎 明細來源頁：🛡️ 持倉風控｜🏛️ 每日選股推薦｜🗳️ 團隊分析｜🧲 大戶籌碼×量價勢")


if __name__ == "__main__":
    show()
