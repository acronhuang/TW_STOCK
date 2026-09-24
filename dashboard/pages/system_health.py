"""系統健康頁 —— 資料品質 + AI verdict 命中率（改善建議 #1/#3 的呈現層）。

讀取 data_health_history（資料健康）與 verdict_metrics（AI 命中率）最新紀錄，
唯讀呈現。集合為空時顯示提示，不報錯。
"""
from datetime import datetime

import streamlit as st

from src.config import get_db
from src.domain.collections import (
    COLL_DATA_HEALTH_HISTORY,
    COLL_SCHEDULE_ALERTS,
    COLL_VERDICT_AB_METRICS,
    COLL_VERDICT_METRICS,
)
from src.audit.ab_verdict import build_trend_series, window_delta
from src.monitoring.data_quality import summarize_open_alerts


def _fmt_pct(v):
    return f"{v:.1%}" if isinstance(v, (int, float)) else "N/A"


def _pass_rate(counts: dict):
    """prod_data 通過率 = passed /（passed+failed+error）;分母 0 回 None（不列入趨勢）。"""
    denom = counts.get("passed", 0) + counts.get("failed", 0) + counts.get("error", 0)
    return counts.get("passed", 0) / denom if denom else None


def show():
    st.header("🩺 系統健康")
    db = get_db()

    # ── 未解決告警 ───────────────────────────────────
    open_docs = list(db[COLL_SCHEDULE_ALERTS].find({"resolved": {"$ne": True}}))
    summ = summarize_open_alerts(open_docs)
    if summ["total"]:
        src_txt = "、".join(f"{k} ×{v}" for k, v in sorted(summ["by_source"].items()))
        st.error(f"🔴 未解決告警 {summ['total']} 項（{src_txt}）")
        for a in summ["latest"]:
            ts = a.get("ts")
            when = ts.strftime("%m-%d %H:%M") if isinstance(ts, datetime) else ""
            col_msg, col_btn = st.columns([9, 1])
            col_msg.warning(f"[{when}] {a.get('source', '?')}：{a.get('message', '')}")
            if a.get("_id") is not None and col_btn.button("✅ 已解決", key=f"res_{a['_id']}"):
                db[COLL_SCHEDULE_ALERTS].update_one(
                    {"_id": a["_id"]},
                    {"$set": {"resolved": True, "resolved_at": datetime.now(),
                              "resolved_reason": "manual: dashboard"}},
                )
                st.rerun()
        st.caption("點「✅ 已解決」可手動消警；指標回穩時下次評估會自動消警。")
    else:
        st.success("✅ 目前無未解決告警")

    st.divider()

    # ── AI verdict 命中率 ──────────────────────────────────────────
    st.subheader("🎯 AI 判斷命中率（事後歸因）")
    st.caption("verdict → N 日後實際報酬的命中率；換模型/節點/prompt 的 A/B 客觀依據。")
    vm = db[COLL_VERDICT_METRICS].find_one({}, sort=[("ts", -1)])
    if not vm:
        st.info("尚無 verdict_metrics 資料。請先跑 `scripts/verdict_attribution.py`（建議每日排程）。")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("整體命中率", _fmt_pct(vm.get("hit_rate")))
        c2.metric("平均報酬", _fmt_pct(vm.get("avg_return")))
        c3.metric("樣本數", vm.get("n", 0))
        by = vm.get("by_verdict", {})
        if by:
            st.markdown("**分票別命中率**")
            rows = [{"票別": k, "樣本": v.get("n", 0), "命中率": _fmt_pct(v.get("hit_rate"))}
                    for k, v in sorted(by.items())]
            st.dataframe(rows, hide_index=True, use_container_width=True)
        ts = vm.get("ts")
        horizon = vm.get("horizon_days", "?")
        st.caption(f"評估期：{horizon} 日　·　更新："
                   f"{ts.strftime('%Y-%m-%d %H:%M') if isinstance(ts, datetime) else ts}")

    st.divider()

    # ── 趨勢追蹤 ─────────────────────────────────────
    st.subheader("📈 趨勢追蹤（命中率 / Ollama↔規則 一致率）")
    st.caption("讀歷史快照：verdict_metrics（命中率）與 verdict_ab_metrics（一致率）隨時間變化。")

    hist = list(db[COLL_VERDICT_METRICS].find(
        {}, {"ts": 1, "hit_rate": 1}).sort("ts", 1).limit(180))
    hr_series = build_trend_series(hist, "hit_rate")
    if len(hr_series) >= 2:
        st.markdown("**AI 命中率趨勢**")
        st.line_chart(
            {"命中率": [v for _, v in hr_series]})
        st.caption(f"{hr_series[0][0]:%Y-%m-%d} ～ {hr_series[-1][0]:%Y-%m-%d}（{len(hr_series)} 點）")
        d = window_delta(hr_series, k=7)
        if d:
            st.metric("命中率（近7期均）", _fmt_pct(d["recent"]),
                      delta=f"{d['delta']:+.1%} vs 前7期")
    else:
        st.info("命中率歷史不足 2 點；每日排程 `scripts/verdict_attribution.py` 累積後即顯現趨勢。")

    ab_hist = list(db[COLL_VERDICT_AB_METRICS].find(
        {}, {"ts": 1, "agreement_rate": 1}).sort("ts", 1).limit(180))
    ag_series = build_trend_series(ab_hist, "agreement_rate")
    if len(ag_series) >= 2:
        st.markdown("**Ollama vs 規則 一致率趨勢**")
        st.line_chart({"一致率": [v for _, v in ag_series]})
        st.caption(f"{ag_series[0][0]:%Y-%m-%d} ～ {ag_series[-1][0]:%Y-%m-%d}（{len(ag_series)} 點）；"
                   "一致率越低，代表 Ollama 與規則的判斷歧異越大。")
        d = window_delta(ag_series, k=7)
        if d:
            st.metric("一致率（近7期均）", _fmt_pct(d["recent"]),
                      delta=f"{d['delta']:+.1%} vs 前7期", delta_color="off")
    else:
        st.info("一致率歷史不足 2 點；排程 `scripts/verdict_ab_eval.py --persist` 累積後即顯現趨勢。")

    st.divider()

    # ── 資料健康 ──────────────────────────────────────────────────
    st.subheader("📦 資料健康（新鮮度 / 覆蓋率 / 備份）")
    st.caption("由 `scripts/data_health_check.py` 排程寫入；異常同步進排程警報。")
    dh = db[COLL_DATA_HEALTH_HISTORY].find_one({}, sort=[("ts", -1)])
    if not dh:
        st.info("尚無 data_health_history 資料。請先跑 `scripts/data_health_check.py`（建議每日排程）。")
    else:
        ok = dh.get("ok")
        st.metric("整體狀態", "✅ 正常" if ok else f"🔴 {len(dh.get('alerts', []))} 項異常")
        c1, c2, c3 = st.columns(3)
        c1.metric("過期集合", dh.get("stale_count", 0))
        c2.metric("覆蓋不足", dh.get("low_coverage_count", 0))
        c3.metric("備份", "✅" if dh.get("backup_ok") else "🔴")
        for a in dh.get("alerts", []):
            st.warning(a)
        ts = dh.get("ts")
        st.caption(f"更新：{ts.strftime('%Y-%m-%d %H:%M') if isinstance(ts, datetime) else ts}")

    st.divider()

    # ── prod_data 真實庫驗證（世界事實不變式）─────────────────────────
    st.subheader("🧪 prod_data 真實庫驗證（世界事實不變式）")
    st.caption("prod_data 測試不進 CI（合成種子造假違 ADR-0011）；由 "
               "`scripts/prod_data_health_report.py` 在 .166 排程對 live 庫定期驗證。")
    pd_coll = db["prod_data_health_history"]
    pdh = pd_coll.find_one({}, sort=[("ts", -1)])
    if not pdh:
        st.info("尚無 prod_data_health_history 資料。請先跑 "
                "`scripts/prod_data_health_report.py --alert`（建議每日排程）。")
    else:
        c = pdh.get("counts", {})
        ok = pdh.get("ok")
        st.metric("整體狀態", "✅ 全通過" if ok else
                  f"🔴 {c.get('failed', 0)} failed / {c.get('error', 0)} error")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("total", c.get("total", 0))
        m2.metric("passed", c.get("passed", 0))
        m3.metric("failed+error", c.get("failed", 0) + c.get("error", 0))
        m4.metric("skipped", c.get("skipped", 0))
        for f in pdh.get("failures", []):
            st.warning(f"🔴 {f.get('test', '?')}：{f.get('detail', '')}")
        ts = pdh.get("ts")
        st.caption(f"标記：{pdh.get('marker', 'prod_data')}　·　更新："
                   f"{ts.strftime('%Y-%m-%d %H:%M') if isinstance(ts, datetime) else ts}")

        # 趨勢：通過率（passed /（passed+failed+error））
        hist = list(pd_coll.find({}, {"ts": 1, "counts": 1}).sort("ts", 1).limit(180))
        series = [(d["ts"], _pass_rate(d.get("counts", {}))) for d in hist
                  if isinstance(d.get("ts"), datetime) and _pass_rate(d.get("counts", {})) is not None]
        if len(series) >= 2:
            st.markdown("**通過率趨勢**")
            st.line_chart({"通過率": [v for _, v in series]})
            st.caption(f"{series[0][0]:%Y-%m-%d} ～ {series[-1][0]:%Y-%m-%d}（{len(series)} 點）")
        else:
            st.info("通過率歷史不足 2 點；排程累積後即顯現趨勢。")
