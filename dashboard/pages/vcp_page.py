"""🌀 VCP 波動收縮候選 —— Minervini VCP 每日掃描結果 + 單股即時檢視。

讀取收盤後管線 vcp_scan.py 寫入的 vcp_candidates；亦可即時對單一個股跑 detect_vcp。
"""
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.domain.collections import COLL_STOCK_PRICE, COLL_VCP_CANDIDATES  # noqa: E402
from src.morphology.vcp import detect_vcp  # noqa: E402


def _db():
    return MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]


def _f(v):
    return float(v.to_decimal()) if hasattr(v, "to_decimal") else (float(v) if v is not None else None)


@st.cache_data(ttl=300, show_spinner=False)
def _candidates():
    db = _db()
    rows = list(db[COLL_VCP_CANDIDATES].find({}, {"_id": 0}).sort("score", -1))
    return rows


def _load_df(sym: str, days: int = 400):
    db = _db()
    cutoff_doc = db[COLL_STOCK_PRICE].find_one({"symbol": sym}, sort=[("date", -1)])
    if not cutoff_doc:
        return None
    cutoff = cutoff_doc["date"] - timedelta(days=days)
    rows = list(db[COLL_STOCK_PRICE].find(
        {"symbol": sym, "date": {"$gte": cutoff}},
        {"_id": 0, "date": 1, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1},
    ).sort("date", 1))
    if len(rows) < 60:
        return None
    df = pd.DataFrame(rows)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = df[c].map(_f)
    return df


def show():
    st.subheader("🌀 VCP 波動收縮候選")
    st.caption("Minervini 趨勢樣板(8條) × 逐次收斂回檔 × 量能枯竭 × 樞紐突破點。"
               "清單由收盤後管線 `vcp_scan.py` 每日產生。")

    rows = _candidates()
    if rows:
        scan_date = rows[0].get("scan_date")
        d = scan_date.strftime("%Y-%m-%d") if hasattr(scan_date, "strftime") else str(scan_date)[:10]
        st.markdown(f"**掃描日：{d}　候選 {len(rows)} 檔**")
        df = pd.DataFrame([{
            "代號": r["symbol"], "名稱": r.get("name", ""),
            "分數": r["score"], "現價": r["price"], "樞紐價": r["pivot"],
            "突破在即": "★" if r.get("near_pivot") else "",
            "整理深度%": r.get("base_depth_pct"),
            "收斂": " → ".join(f"{c:g}" for c in r.get("contractions", [])),
            "量縮": "✓" if r.get("volume_dryup") else "",
            "趨勢樣板": f"{r.get('trend_template_passed', 0)}/8",
        } for r in rows])
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("尚無候選資料（管線未跑或今日 0 檔）。可於下方即時檢視單一個股。")

    st.markdown("---")
    st.markdown("#### 🔎 單股即時檢視")
    sym = st.text_input("股票代號（4 碼）", value="2330", max_chars=4)
    if st.button("分析 VCP", type="primary"):
        df = _load_df(sym.strip())
        if df is None:
            st.error("查無足夠資料（需 ≥60 日）。")
            return
        res = detect_vcp(df)
        c1, c2, c3 = st.columns(3)
        c1.metric("VCP 成立", "✅ 是" if res["is_vcp"] else "❌ 否")
        c2.metric("評分", f"{res['score']}/100")
        c3.metric("樞紐買點", f"{res['pivot']:g}")
        tt = res["trend_template"]
        st.markdown(f"**趨勢樣板：{tt['passed']}/8**　**收斂段：{res['contractions']}**　"
                    f"**整理深度：{res['base_depth_pct']}%**　"
                    f"**量縮：{'✓' if res['volume_dryup'] else '✗'}**　"
                    f"**貼近突破：{'✓' if res['near_pivot'] else '✗'}**")
        (st.success if res["is_vcp"] else st.warning)(f"判定：{res['reason']}")
        with st.expander("趨勢樣板 8 條細項"):
            st.json({k: v for k, v in tt.items() if k not in ("passed", "total", "ok")})
