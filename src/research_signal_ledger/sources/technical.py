"""將可持久化技術型態輸出正規化為研究訊號快照。"""

import hashlib
import json
from datetime import UTC, date, datetime, time

from src.domain.collections import COLL_VCP_CANDIDATES
from src.research_signal_ledger.models import ResearchSignalSnapshot, SignalDirection
from src.research_signal_ledger.sources.base import (
    TAIPEI,
    SourceCollectionResult,
    build_snapshot_key,
)


class TechnicalSource:
    name = "technical"
    rule_version = "vcp_v1"

    def __init__(self, database):
        self.collection = database[COLL_VCP_CANDIDATES]

    def collect(self, as_of: date) -> SourceCollectionResult:
        snapshots = []
        for document in self.collection.find({}):
            if self._as_date(document.get("scan_date")) != as_of:
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
        price = document.get("price")
        if not isinstance(symbol, str) or not isinstance(price, (int, float)) or price <= 0:
            return None
        payload = {
            key: document.get(key)
            for key in ("score", "pivot", "near_pivot", "contractions", "base_depth_pct", "volume_dryup")
        }
        event_payload = {"document_id": str(document.get("_id", "")), **payload}
        content_hash = hashlib.sha256(
            json.dumps(event_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        source_event_id = f"mongo:{event_payload['document_id']}:sha256:{content_hash}"
        score = payload["score"]
        normalized_score = float(score) if isinstance(score, (int, float)) and 0 <= score <= 100 else None
        return ResearchSignalSnapshot(
            snapshot_key=build_snapshot_key(
                source=self.name,
                source_event_id=source_event_id,
                symbol=symbol,
                analysis_date=as_of,
                signal_kind="vcp",
                direction=SignalDirection.LONG,
                rule_version=self.rule_version,
            ),
            source=self.name,
            source_event_id=source_event_id,
            symbol=symbol,
            analysis_date=as_of,
            available_at=datetime.combine(as_of, time.min, tzinfo=TAIPEI),
            captured_at=datetime.now(UTC),
            signal_kind="vcp",
            direction=SignalDirection.LONG,
            evaluation_enabled=True,
            score=normalized_score,
            rule_version=self.rule_version,
            price_at_signal=float(price),
            source_payload=payload,
            benchmark_profile="market_equal_weight_liquid_tw_v1",
        )

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