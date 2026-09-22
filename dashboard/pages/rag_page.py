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
from src.analysis.international_news import generate_analysis
from src.analysis.evidence_guard import guard_analysis
from src.analysis.web_search import (NEWS_MODE_REGIONS, google_news_search,
                                     needs_web_supplement, safe_external_url,
                                     sanitize_markdown_text, search_news_by_mode)  # noqa: E402

KIND_LABEL = {"report": "📄 報告", "doc": "📘 文件", "result": "📊 分析結果"}
EVENT_TYPES = ["貨幣政策／利率", "科技供應鏈／AI", "能源／原物料", "地緣政治／貿易", "國際景氣／市場"]


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
    web_on = st.sidebar.toggle(
        "網路補充", value=False,
        help="本機沒有足夠相關段落時，查詢 Google News RSS 並在下方獨立列出外部來源",
    )
    international_on = st.sidebar.toggle(
        "國際新聞分析", value=False,
        help="依選擇的事件類型，僅根據 Google News RSS 結果產生可能影響與不確定性分析",
    )
    event_type = st.sidebar.selectbox("國際事件類型", EVENT_TYPES, disabled=not international_on)
    news_mode = st.sidebar.selectbox(
        "國際新聞來源", list(NEWS_MODE_REGIONS), disabled=not international_on,
        help="英文模式優先搜尋 Reuters、Bloomberg、CNBC、Financial Times；綜合模式分列繁中與英文來源。",
    )

    st.sidebar.caption(
        "⚠️ 根目錄報告有不少結論已被推翻。時間加權讓新文件排前面,"
        "但**若正確的新文件不存在,加權也救不了** —— 那是語料問題,不是排序問題。")

    q = st.text_input("問題", placeholder="例:adj_close 還原價是否正確?除權息係數怎麼算?")
    analyze_international = international_on and st.sidebar.button("分析外部新聞")
    if not q:
        if analyze_international:
            st.warning("請先輸入問題，再執行國際新聞分析。")
        st.info("輸入問題開始檢索。可在側邊欄關閉時間加權,比對新舊文件的說法差異。")
        return

    hl = half_life if decay_on else 10**9
    with st.spinner("檢索中…"):
        rows = search(q, docs, mat, k=k,
                      kind=None if kind == "全部" else kind, half_life=hl)

    if not rows:
        st.warning("查無結果。試著換個說法,或放寬文件類型。")

    if rows and gen_on:
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

    web_results = []
    if web_on and needs_web_supplement(rows):
        with st.spinner("查詢網路補充資料…"):
            web_results = google_news_search(q)
        st.markdown("### 網路補充")
        st.caption("以下為即時外部搜尋結果，非專案語料，未納入上方受限的知識庫答案。")
        if web_results:
            for result in web_results:
                published_at = f" · {result['published_at']}" if result["published_at"] else ""
                title = sanitize_markdown_text(result["title"])
                url = safe_external_url(result["url"])
                src = sanitize_markdown_text(result["source"])
                line = f"- [{title}]({url})" if url else f"- {title}"
                st.markdown(f"{line}  \n  {src}{published_at}")
        else:
            st.info("這次沒有取得可用的外部結果。")
        st.divider()

    if analyze_international:
        with st.spinner("查詢國際新聞並分析中…"):
            grouped_results = search_news_by_mode(f"{q} {event_type}", news_mode)
            international_results = [article for articles in grouped_results.values() for article in articles]
            try:
                analysis, elapsed = generate_analysis(q, event_type, international_results)
            except Exception as error:
                analysis, elapsed = f"國際新聞分析失敗:{error}", 0.0
        st.markdown("### 國際新聞分析")
        st.caption(
            f"事件類型：{event_type}；新聞來源：{news_mode}。分析只根據下列 {len(international_results)} 筆 Google News RSS 標題，"
            "不是投資建議。")
        st.markdown(analysis)
        st.caption(f"{MODEL} 分析耗時 {elapsed:.1f}s。")
        # EvidenceGuard：驗證輸出是否逆出外部證據（未引用/超範圍/腌補台股標的）。
        _evidence_text = " ".join(a.get("title", "") for a in international_results)
        _guard = guard_analysis(analysis, n_sources=len(international_results), evidence_text=_evidence_text)
        if _guard["flagged"]:
            st.warning("⚠️ 證據守門：本分析可能超出外部新聞證據，請謹慎對待。\n\n"
                       + "\n".join(f"- {r}" for r in _guard["reasons"]))
        if international_results:
            st.markdown("#### 外部證據")
            index = 1
            for source_group, articles in grouped_results.items():
                st.markdown(f"**{sanitize_markdown_text(source_group)}**")
                for result in articles:
                    published_at = f" · {result['published_at']}" if result["published_at"] else ""
                    title = sanitize_markdown_text(result["title"])
                    url = safe_external_url(result["url"])
                    src = sanitize_markdown_text(result["source"])
                    link = f"[{title}]({url})" if url else title
                    st.markdown(f"[{index}] {link}  \n{src}{published_at}")
                    index += 1
        st.divider()

    if rows:
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
