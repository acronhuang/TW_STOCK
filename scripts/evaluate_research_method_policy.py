#!/usr/bin/env python3
"""依成熟 outcome 對每個研究方法做單向（只降不升）的權重治理決策。"""

import argparse
import sys
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import get_db  # noqa: E402
from src.research_signal_ledger.models import MethodStatus  # noqa: E402
from src.research_signal_ledger.policy import PolicyConfig, evaluate_method_status  # noqa: E402
from src.research_signal_ledger.repository import ResearchSignalLedgerRepository  # noqa: E402

EVIDENCE_KEY_CAP = 50


class _PolicyRow:
    """policy 需要的欄位：outcome 的績效加上來自快照的分析日。"""

    def __init__(self, outcome, analysis_date):
        self.outcome_key = outcome.outcome_key
        self.revision = outcome.revision
        self.net_return_pct = outcome.net_return_pct
        self.excess_mkt_pct = outcome.excess_mkt_pct
        self.hit = outcome.hit
        self.analysis_date = analysis_date


def group_latest_outcomes(snapshots, outcomes):
    """每個快照只取最大 revision，且只納入可評估快照；依 (source, signal_kind) 分組。"""
    latest = {}
    for outcome in outcomes:
        current = latest.get(outcome.snapshot_key)
        if current is None or outcome.revision > current.revision:
            latest[outcome.snapshot_key] = outcome
    groups = defaultdict(list)
    for snapshot in snapshots:
        outcome = latest.get(snapshot.snapshot_key)
        if outcome is None or not snapshot.evaluation_enabled:
            continue
        groups[(snapshot.source, snapshot.signal_kind)].append(_PolicyRow(outcome, snapshot.analysis_date))
    return dict(groups)


def decide_all(snapshots, outcomes, load_prior, policy: PolicyConfig):
    groups = group_latest_outcomes(snapshots, outcomes)
    return {
        method: evaluate_method_status(rows, load_prior(*method), policy)
        for method, rows in groups.items()
    }


def load_snapshots_and_outcomes(repository: ResearchSignalLedgerRepository, horizon: int):
    from src.research_signal_ledger.models import ResearchSignalSnapshot

    snapshots = []
    for document in repository.snapshots.find({"evaluation_enabled": True}):
        document.pop("_id", None)
        snapshots.append(ResearchSignalSnapshot.model_validate(document))
    return snapshots, repository.list_outcomes(horizon)


def notify_transition(database, status: MethodStatus, previous_state: str) -> None:
    """只在狀態改變時通知；24h 內同方法同狀態不重複。"""
    since = datetime.now() - timedelta(hours=24)
    requirement = f"{status.source}/{status.signal_kind}/{status.state}"
    alerts = database["schedule_alerts"]
    if alerts.find_one({"source": "research_method_policy", "requirement": requirement, "ts": {"$gte": since}}):
        return
    alerts.insert_one(
        {
            "ts": datetime.now(),
            "level": "warning",
            "source": "research_method_policy",
            "requirement": requirement,
            "message": (
                f"研究方法 {status.source}/{status.signal_kind} 由 {previous_state} 轉為 {status.state}"
                f"（權重 {status.effective_weight:.2f}，樣本 {status.sample_size}，原因：{status.reason}）。"
                " 僅降權／停用，恢復需人工核准。"
            ),
            "resolved": False,
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizon", type=int, choices=(20,), default=20)
    parser.add_argument("--policy-version", default="v1")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    database = get_db()
    repository = ResearchSignalLedgerRepository(database)
    snapshots, outcomes = load_snapshots_and_outcomes(repository, args.horizon)
    groups = group_latest_outcomes(snapshots, outcomes)

    for (source, signal_kind), rows in sorted(groups.items()):
        prior = repository.load_method_status(source, signal_kind, args.policy_version)
        decision = evaluate_method_status(rows, prior, PolicyConfig())
        label = f"{source}/{signal_kind}"
        previous_state = prior.state if prior else "observe"
        changed = decision.state != previous_state
        print(
            f"{label} state={decision.state} weight={decision.effective_weight:.2f} "
            f"streak={decision.failure_streak} n={len(rows)} advanced={decision.round_advanced} "
            f"reason={decision.reason}"
        )
        if args.dry_run or not (decision.round_advanced or changed or prior is None):
            continue

        status = MethodStatus(
            source=source,
            signal_kind=signal_kind,
            policy_version=args.policy_version,
            state=decision.state,
            effective_weight=decision.effective_weight,
            evaluated_horizon=args.horizon,
            sample_size=len(rows),
            independent_analysis_days=len({str(row.analysis_date) for row in rows}),
            failure_streak=decision.failure_streak,
            reason=decision.reason,
            decided_at=datetime.now(UTC),
            evidence_outcome_keys=[row.outcome_key for row in rows][-EVIDENCE_KEY_CAP:],
        )
        repository.save_method_status(status)
        if changed:
            notify_transition(database, status, previous_state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
