"""研究訊號成效帳本的 append-only MongoDB 儲存庫。"""

from dataclasses import dataclass

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

from src.domain.collections import (
    COLL_RESEARCH_BENCHMARK_SNAPSHOTS,
    COLL_RESEARCH_SIGNAL_CAPTURE_RUNS,
    COLL_RESEARCH_SIGNAL_OUTCOMES,
    COLL_RESEARCH_SIGNAL_SNAPSHOTS,
    COLL_RESEARCH_METHOD_STATUS,
    COLL_RESEARCH_METHOD_STATUS_HISTORY,
)
from src.research_signal_ledger.models import (
    CaptureRun,
    MethodStatus,
    ResearchBenchmarkSnapshot,
    ResearchSignalOutcome,
    ResearchSignalSnapshot,
)


@dataclass(frozen=True)
class CaptureWriteResult:
    inserted: int = 0
    duplicates: int = 0


class ResearchSignalLedgerRepository:
    """將不可變快照與結果以 insert-only 的方式寫入 MongoDB。"""

    def __init__(self, database):
        self.snapshots = database[COLL_RESEARCH_SIGNAL_SNAPSHOTS]
        self.benchmarks = database[COLL_RESEARCH_BENCHMARK_SNAPSHOTS]
        self.outcomes = database[COLL_RESEARCH_SIGNAL_OUTCOMES]
        self.capture_runs = database[COLL_RESEARCH_SIGNAL_CAPTURE_RUNS]
        self.method_status = database[COLL_RESEARCH_METHOD_STATUS]
        self.method_status_history = database[COLL_RESEARCH_METHOD_STATUS_HISTORY]
        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        self.snapshots.create_index(
            [("snapshot_key", ASCENDING)], unique=True, name="uq_snapshot_key"
        )
        self.snapshots.create_index(
            [("analysis_date", ASCENDING), ("source", ASCENDING), ("symbol", ASCENDING)],
            name="analysis_source_symbol",
        )
        self.snapshots.create_index(
            [("source", ASCENDING), ("signal_kind", ASCENDING), ("analysis_date", ASCENDING)],
            name="source_kind_analysis_date",
        )
        self.benchmarks.create_index(
            [("benchmark_key", ASCENDING)], unique=True, name="uq_benchmark_key"
        )
        self.outcomes.create_index(
            [("snapshot_key", ASCENDING), ("horizon_trading_days", ASCENDING), ("revision", ASCENDING)],
            unique=True,
            name="uq_outcome_revision",
        )
        self.outcomes.create_index(
            [("snapshot_key", ASCENDING), ("horizon_trading_days", ASCENDING), ("revision", DESCENDING)],
            name="latest_outcome_revision",
        )
        self.outcomes.create_index(
            [("horizon_trading_days", ASCENDING), ("evaluated_at", ASCENDING)],
            name="horizon_evaluated_at",
        )
        self.capture_runs.create_index(
            [("run_id", ASCENDING), ("source", ASCENDING)],
            unique=True,
            name="uq_capture_run_source",
        )
        self.method_status.create_index(
            [("source", ASCENDING), ("signal_kind", ASCENDING), ("policy_version", ASCENDING)],
            unique=True,
            name="uq_method_status",
        )
        self.method_status_history.create_index(
            [
                ("source", ASCENDING),
                ("signal_kind", ASCENDING),
                ("policy_version", ASCENDING),
                ("decided_at", ASCENDING),
            ],
            unique=True,
            name="uq_method_status_history",
        )

    def insert_snapshots(self, snapshots: list[ResearchSignalSnapshot]) -> CaptureWriteResult:
        inserted = 0
        duplicates = 0
        for snapshot in snapshots:
            try:
                self.snapshots.insert_one(snapshot.model_dump(mode="json"))
            except DuplicateKeyError:
                duplicates += 1
            else:
                inserted += 1
        return CaptureWriteResult(inserted=inserted, duplicates=duplicates)

    def insert_benchmark(self, snapshot: ResearchBenchmarkSnapshot) -> bool:
        try:
            self.benchmarks.insert_one(snapshot.model_dump(mode="json"))
        except DuplicateKeyError:
            return False
        return True

    def append_outcome(self, outcome: ResearchSignalOutcome) -> bool:
        try:
            self.outcomes.insert_one(outcome.model_dump(mode="json"))
        except DuplicateKeyError:
            return False
        return True

    def latest_outcome(self, snapshot_key: str, horizon: int) -> ResearchSignalOutcome | None:
        document = self.outcomes.find_one(
            {"snapshot_key": snapshot_key, "horizon_trading_days": horizon},
            sort=[("revision", DESCENDING)],
        )
        if document is None:
            return None
        document.pop("_id", None)
        return ResearchSignalOutcome.model_validate(document)

    def list_outcomes(self, horizon: int) -> list[ResearchSignalOutcome]:
        outcomes = []
        for document in self.outcomes.find({"horizon_trading_days": horizon}):
            document.pop("_id", None)
            outcomes.append(ResearchSignalOutcome.model_validate(document))
        return outcomes

    def record_capture_run(self, run: CaptureRun) -> None:
        self.capture_runs.insert_one(run.model_dump(mode="json"))

    def save_method_status(self, status: MethodStatus) -> None:
        """歷程先 append，再覆寫現態：中途失敗時寬寬留下可追溯紀錄，而非無紀錄的狀態變更。"""
        document = status.model_dump(mode="json")
        try:
            self.method_status_history.insert_one(dict(document))
        except DuplicateKeyError:
            pass  # 同一決策重存：冪等。
        # 本模組唯一的覆寫：現態本就是「目前值」，歷史在 history。
        self.method_status.replace_one(
            {
                "source": status.source,
                "signal_kind": status.signal_kind,
                "policy_version": status.policy_version,
            },
            document,
            upsert=True,
        )

    def load_method_status(
        self, source: str, signal_kind: str, policy_version: str
    ) -> MethodStatus | None:
        document = self.method_status.find_one(
            {"source": source, "signal_kind": signal_kind, "policy_version": policy_version}
        )
        if document is None:
            return None
        document.pop("_id", None)
        return MethodStatus.model_validate(document)