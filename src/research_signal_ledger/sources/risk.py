"""將 risk_analysis 的持倉風控合議正規化為研究訊號快照。"""

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Callable, Mapping

from pydantic import ValidationError

from src.research_signal_ledger.models import ResearchSignalSnapshot, SignalDirection
from src.research_signal_ledger.sources.base import (
    TAIPEI,
    SourceCollectionResult,
    as_taipei_aware,
    build_snapshot_key,
)

PriceLookup = Callable[[list[str], date], Mapping[str, float]]

# 未列入的判斷不產生快照：寧可漏記，也不憑猜測給方向。
_DIRECTIONS = {
    "減碼": SignalDirection.RISK_REDUCE,
    "出場": SignalDirection.RISK_REDUCE,
    "續抱": SignalDirection.HOLD,
}


class RiskAnalysisSource:
    name = "risk"
    rule_version = "risk_deliberation_v1"

    def __init__(self, database, price_lookup: PriceLookup):
        self.collection = database["risk_analysis"]
        self.price_lookup = price_lookup

    def collect(self, as_of: date) -> SourceCollectionResult:
        start = datetime.combine(as_of, time.min)
        query = {"date": {"$gte": start, "$lt": start + timedelta(days=1)}}
        documents = [
            document
            for document in self.collection.find(query)
            if isinstance(document.get("symbol"), str) and document.get("verdict") in _DIRECTIONS
        ]
        if not documents:
            return SourceCollectionResult(self.name, [], "no_output")
        prices = self.price_lookup([document["symbol"] for document in documents], as_of)
        snapshots = []
        skipped = 0
        for document in documents:
            try:
                snapshot = self._normalize(document, prices, as_of)
            except ValidationError:
                skipped += 1  # 不符合契約(如 ETF 五碼代號)的持倉不能拖垮整批。
                continue
            if snapshot is not None:
                snapshots.append(snapshot)
        message = f"skipped={skipped}" if skipped else None
        return SourceCollectionResult(
            self.name, snapshots, "captured" if snapshots else "no_output", message
        )

    def _normalize(self, document: dict, prices: Mapping[str, float], as_of: date) -> ResearchSignalSnapshot | None:
        price = prices.get(document["symbol"])
        if not isinstance(price, (int, float)) or price <= 0:
            return None
        direction = _DIRECTIONS[document["verdict"]]
        content = {
            "document_id": str(document.get("_id", "")),
            "verdict": document["verdict"],
            "tally": document.get("tally") or {},
        }
        content_hash = hashlib.sha256(
            json.dumps(content, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        source_event_id = f"mongo:{content['document_id']}:sha256:{content_hash}"
        updated_at = document.get("updated_at")
        available_at = (
            as_taipei_aware(updated_at)
            if isinstance(updated_at, datetime)
            else datetime.combine(as_of, time.min, tzinfo=TAIPEI)
        )
        return ResearchSignalSnapshot(
            snapshot_key=build_snapshot_key(
                source=self.name,
                source_event_id=source_event_id,
                symbol=document["symbol"],
                analysis_date=as_of,
                signal_kind="position_risk",
                direction=direction,
                rule_version=self.rule_version,
            ),
            source=self.name,
            source_event_id=source_event_id,
            symbol=document["symbol"],
            analysis_date=as_of,
            available_at=available_at,
            captured_at=datetime.now(UTC),
            signal_kind="position_risk",
            direction=direction,
            evaluation_enabled=direction is SignalDirection.RISK_REDUCE,
            rule_version=self.rule_version,
            price_at_signal=float(price),
            source_payload={
                "verdict": document["verdict"],
                "tally": content["tally"],
                "rules": document.get("rules"),
            },
            benchmark_profile="market_equal_weight_liquid_tw_v1",
        )
