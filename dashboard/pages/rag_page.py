#!/usr/bin/env python3
"""專案知識庫檢索(RAG)

語料:專案內 markdown 報告、docs/、results/ JSON,以 bge-m3(1024維)嵌入。
排序:向量 + 字面 兩路 RRF × 時間衰減。

⚠️ 時間衰減不是裝飾:根目錄 124 份報告彼此矛盾,不少結論已被推翻
   (例:2026-02 的報告說 adj_close 覆蓋率 100% ✅,但 2026-07-20 已證實那是假的)。
   關掉衰減就會拿到舊的錯誤答案 —— 側邊欄可切換兩種排序自行比對。
"""
from datetime import datetime

import streamlit as st

import sys
sys.path.insert(0, "/home/mdsadmin/Stock/tw-stock-analysis/scripts")
from stockrag_search import load, search      # noqa: E402
from stockrag_answer import generate, MODEL   # noqa: E402

KIND_LABEL = {"report": "📄 報告", "doc": "📘 文件", "result": "📊 分析結果"}


@st.cache_resource(show_spinner="載入知識庫向量…")
def _corpus():
    """整個語料載進記憶體(約 15MB)。cache_resource 讓多次查詢共用同一份。"""
    return load()


def show():
    st.title("🔎 專案知識庫檢索")
    st.markdown("對專案內的報告、文件與分析結果做語意檢索。")

    docs, mat = _corpus()
    if not docs:
        st.error("語料庫是空的 —— 請先執行 `scripts/stockrag_ingest.py`。")
        return

    kinds = sorted({d.get("kind") for d in docs if d.get("kind")})
    paths = {d["path"] for d in docs}
    newest = max((d["doc_date"] for d in docs if isinstance(d.get("doc_date"), datetime)),
                 default=None)

    c1, c2, c3 = st.columns(3)
    c1.metric("語料塊數", f"{len(docs):,}")
    c2.metric("文件份數", f"{len(paths):,}")
    c3.metric("最新文件", newest.strftime("%Y-%m-%d") if newest else "—")

    st.sidebar.markdown("### 檢索設定")
    kind = st.sidebar.selectbox("文件類型", ["全部"] + kinds,
                                format_func=lambda k: KIND_LABEL.get(k, k))
    k = st.sidebar.slider("回傳筆數", 3, 20, 6)
    decay_on = st.sidebar.toggle("時間加權", value=True,
                                 help="關閉後舊報告會浮上來 —— 可用來比對哪些結論已過時")
    half_life = st.sidebar.slider("半衰期(天)", 30, 720, 180, 30,
                                  disabled=not decay_on,
                                  help="文件每經過這麼多天,權重減半")

    gen_on = st.sidebar.toggle("LLM 生成答案", value=True,
                               help=f"用 {MODEL} 依檢索結果作答並附出處。關閉則只列原文段落")

    st.sidebar.caption(
        "⚠️ 根目錄報告有不少結論已被推翻。時間加權讓新文件排前面,"
        "但**若正確的新文件不存在,加權也救不了** —— 那是語料問題,不是排序問題。")

    q = st.text_input("問題", placeholder="例:adj_close 還原價是否正確?除權息係數怎麼算?")
    if not q:
        st.info("輸入問題開始檢索。可在側邊欄關閉時間加權,比對新舊文件的說法差異。")
        return

    hl = half_life if decay_on else 10**9
    with st.spinner("檢索中…"):
        rows = search(q, docs, mat, k=k,
                      kind=None if kind == "全部" else kind, half_life=hl)

    if not rows:
        st.warning("查無結果。試著換個說法,或放寬文件類型。")
        return

    if gen_on:
        with st.spinner(f"{MODEL} 作答中…"):
            try:
                ans, elapsed = generate(q, rows)
            except Exception as e:
                ans, elapsed = f"生成失敗:{e}", 0.0
        st.markdown("### 回答")
        st.markdown(ans)
        st.caption(
            f"由 {MODEL} 依下列 {len(rows)} 段資料生成,耗時 {elapsed:.1f}s。"
            "**答案僅來自這些段落,請對照原文查證** —— 語料含已被推翻的舊報告。")
        st.divider()

    st.markdown("### 依據的段落")
    st.caption(f"共 {len(rows)} 筆" + ("(已套用時間加權)" if decay_on else "(未加權,依相關度)"))

    for i, r in enumerate(rows, 1):
        dd = r.get("doc_date")
        ds = dd.strftime("%Y-%m-%d") if isinstance(dd, datetime) else "?"
        age = r.get("age_days", 0)
        stale = "  🕐 較舊" if age > 120 else ""
        with st.expander(
                f"**{i}. {r['title'][:60]}**　·　{ds}({age} 天前){stale}", expanded=(i <= 2)):
            m1, m2, m3 = st.columns(3)
            m1.metric("綜合分數", f"{r['score']:.4f}")
            m2.metric("語意相似度", f"{r['vec_sim']:.3f}")
            m3.metric("類型", KIND_LABEL.get(r.get("kind"), r.get("kind", "—")))
            st.code(f"{r['path']} #chunk{r['chunk_idx']}", language=None)
            st.markdown(r["content"])

    st.divider()
    st.caption(
        "檢索 = 向量(bge-m3)與字面(字元 bigram)兩路 RRF 融合,再乘時間衰減。"
        "繁中無分詞,MongoDB 文字索引與 PostgreSQL `to_tsvector` 都切不出詞,"
        "故字面這路用 n-gram 重疊率而非全文檢索。")
