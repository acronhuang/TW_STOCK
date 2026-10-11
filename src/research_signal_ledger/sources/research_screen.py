"""將 research_screen 每日研究名單正規化為研究訊號快照。"""

import hashlib
import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Callable, Mapping

from src.research_signal_ledger.models import ResearchSignalSnapshot, SignalDirection
from src.research_signal_ledger.sources.base import (
    TAIPEI,
    SourceCollectionResult,
    build_snapshot_key,
)

PriceLookup = Callable[[list[str], date], Mapping[str, float]]


class ResearchScreenSource:
    name = "research_screen"
    rule_version = "research_screen_v1"

    def __init__(self, results_dir: Path, price_lookup: PriceLookup):
        self.results_dir = results_dir
        self.price_lookup = price_lookup

    def collect(self, as_of: date) -> SourceCollectionResult:
        path = self.results_dir / f"research_screen_{as_of.isoformat()}.json"
        if not path.exists():
            return SourceCollectionResult(self.name, [], "no_output", "no research screen file")

        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = [row for row in payload.get("rows", []) if isinstance(row.get("symbol"), str)]
        if not rows:
            return SourceCollectionResult(self.name, [], "no_output", "empty research screen")
        prices = self.price_lookup([row["symbol"] for row in rows], as_of)
        source_event_id = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}:{as_of.isoformat()}"
        # 檔案實際寫出時間才是訊號可用時間；內文只有日期。
        available_at = datetime.fromtimestamp(path.stat().st_mtime, tz=TAIPEI)
        snapshots = [
            snapshot
            for row in rows
            if (snapshot := self._normalize(row, prices, as_of, available_at, source_event_id)) is not None
        ]
        return SourceCollectionResult(self.name, snapshots, "captured" if snapshots else "no_output")

    def _normalize(
        self,
        row: dict,
        prices: Mapping[str, float],
        as_of: date,
        available_at: datetime,
        source_event_id: str,
    ) -> ResearchSignalSnapshot | None:
        price = prices.get(row["symbol"])
        if not isinstance(price, (int, float)) or price <= 0:
            return None
        is_green = row.get("tier") == "🟢"
        direction = SignalDirection.LONG if is_green else SignalDirection.OBSERVE
        score = row.get("score")
        return ResearchSignalSnapshot(
            snapshot_key=build_snapshot_key(
                source=self.name,
                source_event_id=source_event_id,
                symbol=row["symbol"],
                analysis_date=as_of,
                signal_kind="research_tier",
                direction=direction,
                rule_version=self.rule_version,
            ),
            source=self.name,
            source_event_id=source_event_id,
            symbol=row["symbol"],
            analysis_date=as_of,
            available_at=available_at,
            captured_at=datetime.now(UTC),
            signal_kind="research_tier",
            direction=direction,
            evaluation_enabled=is_green,
            score=float(score) if isinstance(score, (int, float)) and 0 <= score <= 100 else None,
            rule_version=self.rule_version,
            price_at_signal=float(price),
            source_payload={key: row.get(key) for key in ("tier", "score", "grade")},
            benchmark_profile="market_equal_weight_liquid_tw_v1",
        )
