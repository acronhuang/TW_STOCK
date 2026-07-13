#!/usr/bin/env python3
"""團隊分析頁面：全市場 7 角色 + .27 合議定案表格瀏覽 + 單檔明細 + 復驗狀態。"""
import streamlit as st
import pandas as pd
from pymongo import MongoClient

ROLE_ICON = {
    "macro-analyst": "🎯 總經", "technical-analyst": "📈 技術",
    "fundamental-analyst": "💰 基本面", "value-analyst": "💎 價值",
    "risk-manager": "🛡️ 風險", "chip-analyst": "🏦 籌碼",
}
STATUS_LABEL = {"fresh": "✅ 新鮮", "stale": "⚠️ 過期", "unknown": "❓ 未知"}


@st.cache_resource
def _db():
    return MongoClient("mongodb://localhost:27017")["tw_stock_analysis"]


def show():
    st.title("🗳️ 團隊分析（7 角色 + .27 合議）")
    db = _db()
    col = db["team_analysis"]

    dates = sorted({d.strftime("%Y-%m-%d") for d in col.distinct("date")}, reverse=True)
    if not dates:
        st.warning("team_analysis 尚無資料。請先跑 team_daily_verified.py 或 migrate_team_to_db.py。")
        return

    c1, c2, c3 = st.columns([1, 1, 1])
    sel_date = c1.selectbox("分析日期", dates)
    dt = pd.Timestamp(sel_date).to_pydatetime()

    docs = list(col.find({"date": dt}, {
        "symbol": 1, "name": 1, "final_verdict": 1, "consensus.tally": 1,
        "price_at_analysis": 1, "verify.status": 1, "verify.truth_close": 1, "_id": 0}))
    if not docs:
        st.info("此日無資料"); return

    # 摘要
    verdicts = [d.get("final_verdict") for d in docs]
    n_verdict = sum(1 for v in verdicts if v)
    stats = {}
    for d in docs:
        s = (d.get("verify") or {}).get("status", "unknown")
        stats[s] = stats.get(s, 0) + 1
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("標的數", len(docs))
    m2.metric("有定案", n_verdict, help="有合議/顧問評級的檔數（phase2 未跑時為 0）")
    m3.metric("✅ 新鮮", stats.get("fresh", 0))
    m4.metric("⚠️ 過期", stats.get("stale", 0), help="分析當下用了過期股價，建議重跑")

    # 篩選
    all_verdicts = sorted({v for v in verdicts if v})
    fv = c2.multiselect("定案篩選", all_verdicts, default=all_verdicts)
    fs = c3.multiselect("復驗狀態", list(STATUS_LABEL), default=list(STATUS_LABEL),
                        format_func=lambda x: STATUS_LABEL.get(x, x))

    rows = []
    for d in docs:
        v = d.get("final_verdict")
        s = (d.get("verify") or {}).get("status", "unknown")
        if (all_verdicts and fv and v not in fv and v is not None) or (s not in fs):
            continue
        t = (d.get("consensus") or {}).get("tally") or {}
        rows.append({
            "代號": d["symbol"], "名稱": d.get("name", ""),
            "定案": v or "—",
            "買": t.get("買進", ""), "持": t.get("持有", ""), "賣": t.get("賣出", ""),
            "分析收盤": d.get("price_at_analysis"),
            "權威收盤": (d.get("verify") or {}).get("truth_close"),
            "復驗": STATUS_LABEL.get(s, s),
        })
    df = pd.DataFrame(rows)
    st.caption(f"符合 {len(df)} / {len(docs)} 檔")
    st.dataframe(df, width='stretch', height=430, hide_index=True)

    st.markdown("---")
    st.subheader("🔍 單檔明細")
    syms = [d["symbol"] for d in docs]
    pick = st.selectbox("選擇代號", syms,
                        format_func=lambda s: f"{s} {next((d.get('name','') for d in docs if d['symbol']==s), '')}")
    full = col.find_one({"symbol": pick, "date": dt})
    if not full:
        return
    vf = full.get("verify") or {}
    st.write(f"**復驗狀態**：{STATUS_LABEL.get(vf.get('status'), vf.get('status'))}　"
             f"分析收盤 `{full.get('price_at_analysis')}`　權威收盤 `{vf.get('truth_close')}`")
    fm = vf.get("finmind")
    if fm:
        ok = "✅ 一致" if fm.get("match") else "⚠️ 背離"
        st.write(f"**FinMind 複核**：DB `{fm.get('db_close')}` vs FinMind `{fm.get('finmind_close')}` → {ok}")

    cons = full.get("consensus")
    if cons:
        t = cons.get("tally") or {"買進": 0, "持有": 0, "賣出": 0}
        src = cons.get("final_source")
        src_tag = {"facilitator": "　（🧠 主持人綜合）",
                   "majority": "　（多數決）"}.get(src, "")
        st.success(f"🗳️ 合議定案：**{cons.get('final')}**{src_tag}　"
                   f"（買{t.get('買進', 0)}/持{t.get('持有', 0)}/賣{t.get('賣出', 0)}）")

        round_tallies = cons.get("round_tallies")
        if round_tallies:
            # ── 序列討論記錄（discuss()）——舊盲投記錄無此欄位 ──
            title = f"🧠 討論過程（{cons.get('rounds_run', len(round_tallies))} 輪"
            if cons.get("changed"):
                title += f"，{cons['changed']} 位委員討論後改票"
            title += "）"
            with st.expander(title, expanded=True):
                st.markdown("**各輪票數演變**（委員讀到彼此發言後可改票）")
                for i, rt in enumerate(round_tallies):
                    mark = "　← 定案" if i == len(round_tallies) - 1 else ""
                    st.write(f"- 第 {i+1} 輪：買 {rt.get('買進',0)} / 持 {rt.get('持有',0)} "
                             f"/ 賣 {rt.get('賣出',0)}{mark}")
                if cons.get("transcript"):
                    st.markdown("**末輪委員發言**（餵回給下一輪 / 主持人的逐字稿）")
                    st.code(cons["transcript"], language=None)
                if cons.get("facilitator"):
                    st.markdown("**🧠 主持人綜合定案理由**")
                    st.info(cons["facilitator"])
                if cons.get("dissent"):
                    st.caption(f"⚠️ 仍有 {len(cons['dissent'])} 位委員持異議：" +
                               "、".join(f"{x['model']}→{x['vote']}" for x in cons["dissent"]))
        else:
            # ── 舊盲投記錄（deliberate()）：只列委員票 ──
            for vote in cons.get("votes", []):
                st.write(f"- `{vote['model']}` → **{vote['vote']}**：{vote.get('reason', '')}")
    if full.get("advisor"):
        with st.expander("🎩 投資顧問整合"):
            st.write(full["advisor"])

    for role, txt in (full.get("reports") or {}).items():
        with st.expander(ROLE_ICON.get(role, role)):
            st.write(txt)

    ev = full.get("evidence") or []
    if ev:
        st.markdown("**佐證數據**")
        st.dataframe(pd.DataFrame(ev), width='stretch', hide_index=True)
