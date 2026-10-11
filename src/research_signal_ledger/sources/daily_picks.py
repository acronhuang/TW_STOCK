"""將 daily_recommendations 的版本化 JSON 報告轉為帳本快照。"""

import hashlib
import json
from datetime import UTC, date, datetime, time
from pathlib import Path

from src.research_signal_ledger.models import ResearchSignalSnapshot, SignalDirection
from src.research_signal_ledger.sources.base import (
    TAIPEI,
    SourceCollectionResult,
    as_taipei_aware,
    build_snapshot_key,
)


class DailyPicksSource:
    name = "daily_picks"
    rule_version = "daily_recommendations_v1"
    _strategies = {
        "factor": "factor_rank",
        "senvision": "senvision",
        "hsieh": "hsieh_value",
    }

    def __init__(self, reports_dir: Path):
        self.reports_dir = reports_dir

    def collect(self, as_of: date) -> SourceCollectionResult:
        report = self._report_for(as_of)
        if report is None:
            return SourceCollectionResult(self.name, [], "no_output", "no daily picks report")

        path, payload = report
        report_time = self._report_time(payload.get("date"), as_of)
        source_event_id = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}:{as_of.isoformat()}"
        snapshots: list[ResearchSignalSnapshot] = []
        for strategy, signal_kind in self._strategies.items():
            for row in payload.get(strategy, []):
                snapshot = self._normalize_row(
                    row, signal_kind, as_of, report_time, source_event_id
                )
                if snapshot is not None:
                    snapshots.append(snapshot)
        status = "captured" if snapshots else "no_output"
        return SourceCollectionResult(self.name, snapshots, status)

    def _report_for(self, as_of: date) -> tuple[Path, dict] | None:
        for path in sorted(self.reports_dir.glob("picks_*.json"), reverse=True):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            report_time = self._report_time(payload.get("date"), as_of)
            if report_time.date() == as_of:
                return path, payload
        return None

    @staticmethod
    def _report_time(value: object, as_of: date) -> datetime:
        if isinstance(value, str):
            try:
                return as_taipei_aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
            except ValueError:
                pass
        return datetime.combine(as_of, time.min, tzinfo=TAIPEI)

    def _normalize_row(
        self,
        row: object,
        signal_kind: str,
        analysis_date: date,
        available_at: datetime,
        source_event_id: str,
    ) -> ResearchSignalSnapshot | None:
        if not isinstance(row, dict):
            return None
        symbol = row.get("symbol", row.get("sym"))
        price = row.get("price")
        if not isinstance(symbol, str) or not isinstance(price, (int, float)) or price <= 0:
            return None
        score = row.get("total_score", row.get("score"))
        normalized_score = float(score) if isinstance(score, (int, float)) and 0 <= score <= 100 else None
        return ResearchSignalSnapshot(
            snapshot_key=build_snapshot_key(
                source=self.name,
                source_event_id=source_event_id,
                symbol=symbol,
                analysis_date=analysis_date,
                signal_kind=signal_kind,
                direction=SignalDirection.LONG,
                rule_version=self.rule_version,
            ),
            source=self.name,
            source_event_id=source_event_id,
            symbol=symbol,
            analysis_date=analysis_date,
            available_at=available_at,
            captured_at=datetime.now(UTC),
            signal_kind=signal_kind,
            direction=SignalDirection.LONG,
            evaluation_enabled=True,
            score=normalized_score,
            rule_version=self.rule_version,
            price_at_signal=float(price),
            source_payload=row,
            benchmark_profile="market_equal_weight_liquid_tw_v1",
        )