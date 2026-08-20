#!/usr/bin/env python3
"""💬 每日決策問答（多來源檢索）

顯示當日團隊 verdict,並用自然語言問決策。LLM 依問題檢索多來源後作答:
  ① 當日整體決策(team_analysis)
  ② 問到的個股：歷史 verdict + 即時 DB(收盤/factor/法人/財報)—全市場任一檔皆可
  ③ 專案知識庫 RAG(報告/文件/回測結論)
LLM = Ollama .28 qwen2.5-14b;明令只據檢索到的資料回答、不編造。網頁無 LINE 額度限制。
"""
import glob
import json
import os
import re
import sys
from collections import Counter

import pandas as pd
import requests
import streamlit as st
from bson.decimal128 import Decimal128
from pymongo import MongoClient

sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis/scripts")
sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis")

OLLAMA = "http://172.16.9.28:11434"
MODEL = "qwen2.5-14b:latest"
ROOT = "/home/mdsadmin/Stock/tw-stock-analysis"


def _db():
    return MongoClient("localhost", 27017)["tw_stock_analysis"]


def _f(v):
    if isinstance(v, Decimal128):
        return float(v.to_decimal())
    return float(v) if isinstance(v, (int, float)) else None


@st.cache_data(ttl=300, show_spinner="載入當日分析…")
def load_today():
    db = _db()
    last = db.team_analysis.find_one(sort=[("date", -1)], projection={"date": 1})
    if not last:
        return None, []
    d = last["date"]
    docs = list(db.team_analysis.find(
        {"date": d},
        {"symbol": 1, "name": 1, "final_verdict": 1, "consensus.tally": 1,
         "advisor": 1, "evidence": 1}))
    return d, docs


@st.cache_data(ttl=300, show_spinner=False)
def dailypick_syms():
    files = sorted(glob.glob(os.path.join(ROOT, "results", "daily_picks", "picks_*.json")))
    if not files:
        return []
    try:
        d = json.load(open(files[-1], encoding="utf-8"))
    except Exception:
        return []
    syms, seen = [], set()
    for item in (d.get("cross_reference") or []):
        if isinstance(item, (list, tuple)) and len(item) == 2:
            s = str(item[0])
            srcs = (item[1] or {}).get("sources", []) or []
            if len(srcs) >= 2 and s not in seen:
                seen.add(s)
                syms.append(s)
    for key in ("factor", "senvision", "hsieh"):
        for r in (d.get(key) or []):
            s = str(r.get("sym"))
            if s and s != "None" and s not in seen:
                seen.add(s)
                syms.append(s)
    return syms[:8]


def _ev_str(ev):
    if not isinstance(ev, list):
        return ""
    return " ".join(f"{e.get('metric')}{e.get('flag', '')}" for e in ev if isinstance(e, dict))


def _row(d):
    t = (d.get("consensus") or {}).get("tally") or {}
    return {
        "代號": d.get("symbol"), "名稱": d.get("name"),
        "定案": d.get("final_verdict") or "—",
        "合議": f"買{t.get('買進', 0)}/持{t.get('持有', 0)}/賣{t.get('賣出', 0)}",
        "佐證": _ev_str(d.get("evidence")),
    }


def stock_history(db, code):
    rows = list(db.team_analysis.find(
        {"symbol": code}, {"date": 1, "final_verdict": 1, "consensus.tally": 1}
    ).sort("date", -1).limit(6))
    out = []
    for r in rows:
        t = (r.get("consensus") or {}).get("tally") or {}
        out.append(f"{str(r.get('date'))[:10]} {r.get('final_verdict') or '—'}"
                   f"(買{t.get('買進', 0)}/持{t.get('持有', 0)}/賣{t.get('賣出', 0)})")
    return "；".join(out) if out else "無團隊分析紀錄"


def stock_snapshot(db, code):
    ti = db.taiwan_stock_info.find_one({"stock_id": code}, {"stock_name": 1, "industry_category": 1}) or {}
    name, ind = ti.get("stock_name", ""), ti.get("industry_category", "")
    px = db.stock_price.find_one({"symbol": code}, sort=[("date", -1)]) or {}
    close, pxd = _f(px.get("close")), str(px.get("date"))[:10]
    f = db.stock_factors.find_one({"symbol": code}, sort=[("date", -1)]) or {}
    pe, pb = _f(f.get("pe_ratio")), _f(f.get("pb_ratio"))
    roe, r3, r6, r12, rsi = (_f(f.get(k)) for k in ("roe", "return_3m", "return_6m", "return_12m", "rsi_14"))
    inst = list(db.institutional_flow.find(
        {"stock_id": code}, {"foreign_net": 1, "total_net": 1}).sort("date", -1).limit(10))
    fnet = sum((_f(x.get("foreign_net")) or 0) for x in inst) / 1000.0
    tnet = sum((_f(x.get("total_net")) or 0) for x in inst) / 1000.0
    ff = db.fundamental_factors.find_one({"stock_id": code}, sort=[("period_end", -1)]) or {}

    parts = [f"{code} {name}（{ind}）", f"歷史verdict: {stock_history(db, code)}"]
    snap = f"即時: 收盤{close}({pxd})"
    if roe is not None:
        snap += f" | roe{roe:.1f}"
    if r3 is not None:
        snap += f" 近3月{r3:+.1f}% 近半年{r6:+.1f}% 近1年{r12:+.1f}%"
    if rsi is not None:
        snap += f" rsi{rsi:.0f}"
    snap += " | PE" + (("%.1f" % pe) if pe else "n/a(當日因子未算)")
    snap += " PB" + (("%.2f" % pb) if pb else "n/a")
    fv = _f(f.get("fair_value"))
    mos = _f(f.get("margin_of_safety"))
    if fv:
        snap += " | DCF合理價%.1f" % fv + ((" 安全邊際%+.0f%%" % mos) if mos is not None else "")
    snap += f" | 法人近10日淨: 外資{fnet:+.0f}張 三大法人{tnet:+.0f}張"
    parts.append(snap)
    if ff:
        roe_ff, dr, pm = _f(ff.get("roe")), _f(ff.get("debt_ratio")), _f(ff.get("profit_margin"))
        parts.append(f"財報({str(ff.get('period_end'))[:10]}): roe{roe_ff:.1f} 負債比{dr:.1f}% 淨利率{pm:.1f}%")
    try:
        from src.analysis.value_profile import value_profile_text
        vp = value_profile_text(db, code)
        if vp and vp != "四維價值資料不足":
            parts.append("四維價值: " + vp)
    except Exception:
        pass
    return "\n  ".join(parts)


@st.cache_resource(show_spinner="載入知識庫向量…")
def _rag_corpus():
    from stockrag_search import load
    return load()


def rag_hits(question, k=4):
    try:
        from stockrag_search import search
        docs, mat = _rag_corpus()
        if not docs:
            return []
        rows = search(question, docs, mat, k=k)
        out = []
        for r in rows:
            title = str(r.get("title", ""))[:50]
            dd = str(r.get("doc_date"))[:10]
            content = str(r.get("content", ""))[:280].replace("\n", " ")
            out.append(f"[{title}]({dd}) {content}")
        return out
    except Exception as e:
        return [f"(知識庫檢索略過: {e})"]


def answer_question(question, today_docs):
    db = _db()
    lines = []
    for d in today_docs:
        t = (d.get("consensus") or {}).get("tally") or {}
        lines.append(f"{d.get('symbol')} {d.get('name')}:{d.get('final_verdict') or '—'}"
                     f"(買{t.get('買進', 0)}/持{t.get('持有', 0)}/賣{t.get('賣出', 0)})")
    ctx = ["【今日整體決策 %d 檔】" % len(today_docs), "\n".join(lines)]
    codes = []
    for c in re.findall(r"\d{4}", question):
        if c not in codes:
            codes.append(c)
    if codes:
        ctx.append("\n【問到的個股詳情】")
        for c in codes[:6]:
            ctx.append("▼ " + stock_snapshot(db, c))
    hits = rag_hits(question)
    if hits:
        ctx.append("\n【知識庫相關段落】")
        ctx.append("\n".join(hits))
    context = "\n".join(ctx)

    prompt = (
        "你是台股投資決策助理。以下是多來源檢索到的資料(今日團隊決策、問到個股的歷史與即時數據、"
        "知識庫段落)。**只根據這些資料回答**,不要編造;資料沒有的就明說沒有。注意 ⚠️背離 與"
        "『當日因子未算』等提示。用繁體中文簡潔作答,涉及個股標代號。\n\n" + context +
        "\n\n【使用者問題】\n" + question + "\n\n【回答】\n")
    r = requests.post(
        f"{OLLAMA}/api/generate",
        json={"model": MODEL, "prompt": prompt, "stream": False,
              "options": {"num_predict": 800, "temperature": 0.3, "num_ctx": 8192}},
        timeout=600)
    r.raise_for_status()
    return r.json().get("response", "").strip(), context


def show():
    st.title("💬 每日決策問答")
    st.caption("當日團隊 verdict + 資料佐證;問答會檢索『當日決策 + 個股歷史/即時DB + 知識庫』作答,"
               "只據檢索資料、不編造。網頁無 LINE 額度限制。")

    date_d, docs = load_today()
    if not docs:
        st.warning("team_analysis 尚無資料。請先跑 team_daily_verified.py。")
        return
    dstr = date_d.strftime("%Y-%m-%d") if hasattr(date_d, "strftime") else str(date_d)[:10]
    dp = set(dailypick_syms())

    cc = Counter(d.get("final_verdict") for d in docs if d.get("final_verdict"))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("分析日期", dstr)
    c2.metric("分析檔數", len(docs))
    c3.metric("🟢買進", cc.get("買進", 0))
    c4.metric("🔴賣出", cc.get("賣出", 0))

    st.markdown("### 🎯 今日量化精選(dailypicks)")
    dp_docs = [d for d in docs if d.get("symbol") in dp]
    if dp_docs:
        st.dataframe(pd.DataFrame([_row(d) for d in dp_docs]), hide_index=True, width="stretch")
    else:
        st.info("今日 picks 尚未有對應團隊分析。")

    with st.expander(f"📋 全部當日分析（{len(docs)} 檔）"):
        st.dataframe(pd.DataFrame([_row(d) for d in docs]), hide_index=True, width="stretch", height=400)

    st.markdown("---")
    st.markdown("### 💬 問決策（多來源檢索）")
    st.caption("例:5515 為什麼買進、法人買不買? / 2330 現在 PE 和近一年報酬? / 這週哪些買進? / 動能策略回測結論?")
    q = st.text_input("問題", key="dq_q", placeholder="可問任一檔(含未分析的)、歷史、或策略/回測")
    if st.button("詢問", key="dq_ask", type="primary") and q.strip():
        with st.spinner(f"{MODEL} 檢索+作答中…（首次載知識庫較久）"):
            try:
                ans, ctx = answer_question(q.strip(), docs)
                st.markdown(ans or "(無回應)")
                with st.expander("🔍 這次檢索到的資料(佐證)"):
                    st.text(ctx[:6000])
            except Exception as e:
                st.error(f"查詢失敗: {e}")
    st.caption(f"LLM: {MODEL} @ {OLLAMA}｜來源: 當日team_analysis + 個股歷史/即時DB + 知識庫RAG")
