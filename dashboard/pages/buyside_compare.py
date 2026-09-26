"""M5 買方改良對照頁 — v1(現行買進)vs v2(影子:降級追高)命中/超額。

影子模式:純讀 verdict_detail 的 buy_v2,不動 live。空資料→st.info 不報錯。
"""
from datetime import datetime

import streamlit as st

from src.config import get_db
from src.analysis.buyside.backtest_compare import compare


def _pct(v):
    return f"{v*100:.1f}%" if isinstance(v, (int, float)) else "N/A"


def _ex(v):
    return f"{v*100:+.2f}%" if isinstance(v, (int, float)) else "N/A"


def show():
    st.header("📈 買方改良對照（v1 vs shadow）")
    st.caption("影子模式:不動 live verdict;比較買方 v1(現行)與 shadow 版之命中率/均超額。"
               "升級 live 前須 out-of-sample 回測佐證(見 docs/plans/verdict_buyside_v1.md)。")
    db = get_db()
    ver = st.radio("shadow 版本", ["v3.1 純品質(buy_v3c)", "v2 混合(buy_v2)"],
                   horizontal=True, key="bs_ver", label_visibility="collapsed")
    field = "buy_v3c" if "v3.1" in ver else "buy_v2"
    res = compare(db, window=20, field=field)
    v1, v2 = res["v1"], res["v2"]

    if not v1["n"]:
        st.info("尚無 verdict_detail 買進資料。請先跑回測(verdict_orthogonality_backtest)"
                "與影子寫入(buyside.shadow_writer)。")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("v1 買進命中", _pct(v1["hit_rate"]))
    dh = res.get("delta_hit")
    c2.metric(f"{ver.split()[0]} 買進命中", _pct(v2["hit_rate"]),
              delta=(f"{dh*100:+.1f}pp" if isinstance(dh, (int, float)) else None))
    c3.metric("v1 均超額", _ex(v1["mean_excess"]))
    c4.metric("降級數", f"{res['downgraded']} / {v1['n']}")

    st.markdown(f"**v1 vs {ver.split()[0]} 對照**")
    st.dataframe([
        {"版本": "v1(全買進)", "樣本": v1["n"], "命中率": _pct(v1["hit_rate"]), "均超額": _ex(v1["mean_excess"])},
        {"版本": f"{ver.split()[0]}(移除降級)", "樣本": v2["n"], "命中率": _pct(v2["hit_rate"]), "均超額": _ex(v2["mean_excess"])},
    ], hide_index=True, use_container_width=True)

    de = res.get("delta_excess")
    verdict = ("🟢 v2 改善" if (isinstance(dh, (int, float)) and dh > 0) else "🔴 v2 未改善")
    st.caption(f"{verdict}(Δ命中 {dh*100:+.1f}pp、Δ均超額 {de*100:+.2f}% 若有值)。"
               f"⚠️ 單一區間 in-sample,泛化未證;更新:{datetime.now():%Y-%m-%d %H:%M}"
               if isinstance(dh, (int, float)) else "資料不足以比較。")
