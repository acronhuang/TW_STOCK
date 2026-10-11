"""將 team_analysis 合議結論正規化為研究訊號快照。"""

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta

from src.domain.collections import COLL_TEAM_ANALYSIS
from src.research_signal_ledger.models import ResearchSignalSnapshot, SignalDirection
from src.research_signal_ledger.sources.base import (
    TAIPEI,
    SourceCollectionResult,
    as_taipei_aware,
    build_snapshot_key,
)


class TeamAnalysisSource:
    name = "team_analysis"
    rule_version = "team_analysis_v1"
    _long_verdicts = {"強力買進", "買進"}
    _risk_verdicts = {"減碼", "賣出"}

    def __init__(self, database):
        self.collection = database[COLL_TEAM_ANALYSIS]

    def collect(self, as_of: date) -> SourceCollectionResult:
        snapshots = []
        start = datetime.combine(as_of, time.min)
        query = {"date": {"$gte": start, "$lt": start + timedelta(days=1)}}
        for document in self.collection.find(query):
            if self._as_date(document.get("date")) != as_of:
                continue
            snapshot = self._normalize(document, as_of)
            if snapshot is not None:
                snapshots.append(snapshot)
        return SourceCollectionResult(
            self.name,
            snapshots,
            "captured" if snapshots else "no_output",
        )

    def _normalize(self, document: dict, as_of: date) -> ResearchSignalSnapshot | None:
        symbol = document.get("symbol")
        price = document.get("price_at_analysis")
        verdict = document.get("final_verdict")
        if not isinstance(symbol, str) or not isinstance(price, (int, float)) or price <= 0:
            return None
        # 合議尚未完成不是訊號；週五全市場批次要到約 5 天後才全部完成。
        if not verdict:
            return None
        # updated_at 才是結論可用的時間；沒有就略過，不能退回批次日（那會是 look-ahead）。
        if not isinstance(document.get("updated_at"), datetime):
            return None
        direction = self._direction(verdict)
        event_payload = {
            "document_id": str(document.get("_id", "")),
            "verdict": verdict,
            "models": document.get("models") or {},
            "price": price,
        }
        payload_hash = hashlib.sha256(
            json.dumps(event_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        source_event_id = f"mongo:{event_payload['document_id']}:sha256:{payload_hash}"
        available_at = self._as_datetime(document.get("updated_at"), as_of)
        consensus = document.get("consensus") or {}
        source_payload = {
            "final_verdict": verdict,
            "models": document.get("models") or {},
            "consensus_tally": consensus.get("tally") or {},
        }
        # 新聞佐證是 verdict 的切面（news_value_backtest 用 catalyst 分組），保存才能日後重切。
        for field in ("catalyst", "news_count", "news_official", "news_media"):
            if field in document:
                source_payload[field] = document[field]
        return ResearchSignalSnapshot(
            snapshot_key=build_snapshot_key(
                source=self.name,
                source_event_id=source_event_id,
                symbol=symbol,
                analysis_date=as_of,
                signal_kind="final_verdict",
                direction=direction,
                rule_version=self.rule_version,
            ),
            source=self.name,
            source_event_id=source_event_id,
            symbol=symbol,
            analysis_date=as_of,
            available_at=available_at,
            captured_at=datetime.now(UTC),
            signal_kind="final_verdict",
            direction=direction,
            evaluation_enabled=direction not in (SignalDirection.HOLD, SignalDirection.OBSERVE),
            price_at_signal=float(price),
            source_payload=source_payload,
            benchmark_profile="analysis_pool_v1",
            rule_version=self.rule_version,
        )

    def _direction(self, verdict: object) -> SignalDirection:
        if verdict in self._long_verdicts:
            return SignalDirection.LONG
        if verdict in self._risk_verdicts:
            return SignalDirection.RISK_REDUCE
        return SignalDirection.HOLD

    @staticmethod
    def _as_date(value: object) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value).date()
            except ValueError:
                return None
        return None

    @staticmethod
    def _as_datetime(value: object, fallback_date: date) -> datetime:
        if isinstance(value, datetime):
            return as_taipei_aware(value)
        if isinstance(value, str):
            try:
                return as_taipei_aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
            except ValueError:
                pass
        return datetime.combine(fallback_date, time.min, tzinfo=TAIPEI)