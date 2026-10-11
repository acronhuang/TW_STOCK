"""📒 研究訊號成效帳本 —— 唯讀。顯示各研究方法的 5/10/20 日成本後績效與治理狀態。

資料來源是 research_signal_* 帳本（append-only 快照 + 成熟結果），不是 results/*.json。
與「📈 命中率回看」不同：這裡以訊號實際可用時間之後的首個交易日進場、使用還原價、
扣除台股 round-trip 成本，並與保存的流動性個股等權基準比較，所以兩邊數字不同是正常的。
此頁沒有任何修改權重或門檻的控制；降權／停用只由 evaluate_research_method_policy 決定。
非投資建議，僅供研究驗證。
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import date

HORIZONS = (5, 10, 20)
# 與 policy.PolicyConfig.min_sample_size 同一個「證據不足」標準。
THIN_SAMPLE = 60

_STATUS_LABELS = {
    "observe": "觀察中",
    "active": "正常",
    "degraded": "已降權",
    "disabled": "已停用",
}


def status_label(state: str | None) -> str:
    if state is None:
        return "尚無狀態（觀察中）"
    return _STATUS_LABELS.get(state, state)


@dataclass(frozen=True)
class SummaryRow:
    """一筆成熟結果加上其快照的方法識別與分析日。"""

    source: str
    signal_kind: str
    rule_version: str
    analysis_date: date
    gross_return_pct: float
    net_return_pct: float
    excess_mkt_pct: float | None
    hit: bool | None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def method_summary(rows) -> list[dict]:
    """依 (source, signal_kind) 彙總；樣本少於 THIN_SAMPLE 標記 thin，避免被過度解讀。"""
    groups = defaultdict(list)
    for item in rows:
        groups[(item.source, item.signal_kind)].append(item)
    summary = []
    for (source, signal_kind), items in sorted(groups.items()):
        measurable = [item.hit for item in items if item.hit is not None]
        excess = [item.excess_mkt_pct for item in items if item.excess_mkt_pct is not None]
        summary.append(
            {
                "source": source,
                "signal_kind": signal_kind,
                "rule_versions": sorted({item.rule_version for item in items}),
                "samples": len(items),
                "analysis_days": len({item.analysis_date for item in items}),
                "mean_gross_pct": _mean([item.gross_return_pct for item in items]),
                "mean_net_pct": _mean([item.net_return_pct for item in items]),
                "mean_excess_pct": _mean(excess),
                "hit_rate_pct": (sum(measurable) / len(measurable) * 100) if measurable else None,
                "thin": len(items) < THIN_SAMPLE,
            }
        )
    return summary


def ledger_read_model(repository, horizon: int) -> list[dict]:
    """每個 snapshot 僅呈現指定 horizon 的最大 outcome revision。"""
    latest = {}
    for outcome in repository.list_outcomes(horizon):
        previous = latest.get(outcome.snapshot_key)
        if previous is None or outcome.revision > previous.revision:
            latest[outcome.snapshot_key] = outcome
    return [
        {
            "snapshot_key": outcome.snapshot_key,
            "gross_return_pct": outcome.gross_return_pct,
            "net_return_pct": outcome.net_return_pct,
            "excess_mkt_pct": outcome.excess_mkt_pct,
        }
        for outcome in latest.values()
    ]


def joined_rows(snapshots, outcomes) -> list[SummaryRow]:
    """每個快照取最大 revision 的 outcome，並只納入可評估快照。"""
    latest = {}
    for outcome in outcomes:
        previous = latest.get(outcome.snapshot_key)
        if previous is None or outcome.revision > previous.revision:
            latest[outcome.snapshot_key] = outcome
    rows = []
    for snapshot in snapshots:
        outcome = latest.get(snapshot["snapshot_key"])
        if outcome is None or not snapshot.get("evaluation_enabled"):
            continue
        rows.append(
            SummaryRow(
                source=snapshot["source"],
                signal_kind=snapshot["signal_kind"],
                rule_version=snapshot["rule_version"],
                analysis_date=date.fromisoformat(str(snapshot["analysis_date"])[:10]),
                gross_return_pct=outcome.gross_return_pct,
                net_return_pct=outcome.net_return_pct,
                excess_mkt_pct=outcome.excess_mkt_pct,
                hit=outcome.hit,
            )
        )
    return rows


def show():
    """Streamlit 頁面；全程唯讀。"""
    import streamlit as st
    from pymongo import MongoClient

    from src.research_signal_ledger.repository import ResearchSignalLedgerRepository

    st.title("📒 研究訊號成效帳本")
    st.caption(
        "追蹤各研究方法的事後表現：次一交易日進場、還原價、扣台股成本，並與流動性個股等權基準比較。"
        "數字與「📈 命中率回看」不同是正常的。此頁唯讀，不能改權重。非投資建議。"
    )

    database = MongoClient("mongodb://localhost:27017/")["tw_stock_analysis"]
    repository = ResearchSignalLedgerRepository(database)

    snapshots = list(
        repository.snapshots.find(
            {}, {"_id": 0, "snapshot_key": 1, "source": 1, "signal_kind": 1, "rule_version": 1,
                 "analysis_date": 1, "evaluation_enabled": 1}
        )
    )
    last_run = repository.capture_runs.find_one({}, {"_id": 0, "recorded_at": 1}, sort=[("recorded_at", -1)])
    total = len(snapshots)
    days = len({str(s["analysis_date"])[:10] for s in snapshots})
    st.metric("累計快照", f"{total:,}", f"{days} 個分析日")
    st.caption(f"最近一次 capture：{(last_run or {}).get('recorded_at', '尚無')}")

    horizon = st.radio("前瞻視窗（交易日）", HORIZONS, index=2, horizontal=True, key="ledger_horizon")
    rows = joined_rows(snapshots, repository.list_outcomes(horizon))
    if not rows:
        st.info(
            f"尚無 {horizon} 日成熟結果。首批快照要等進場後滿 {horizon} 個交易日才會成熟；"
            "在此之前方法狀態一律為「觀察中」。"
        )
        return

    summary = method_summary(rows)
    for entry in summary:
        status = repository.load_method_status(entry["source"], entry["signal_kind"], "v1")
        entry["status"] = status_label(status.state if status else None)
        entry["weight"] = status.effective_weight if status else 1.0
    st.dataframe(
        [
            {
                "來源": e["source"], "訊號": e["signal_kind"], "樣本": e["samples"],
                "分析日": e["analysis_days"], "毛報酬%": e["mean_gross_pct"],
                "淨報酬%": e["mean_net_pct"], "超額%": e["mean_excess_pct"],
                "勝率%": e["hit_rate_pct"], "狀態": e["status"], "權重": e["weight"],
                "⚠️樣本單薄": "是" if e["thin"] else "",
            }
            for e in summary
        ],
        width="stretch",
    )
    st.caption(
        f"⚠️ 樣本少於 {THIN_SAMPLE} 筆者標示「樣本單薄」，同日同標的可在多個來源重複出現，"
        "樣本並非完全獨立；持倉風控每日僅約 16 檔，獨立性最差。"
    )