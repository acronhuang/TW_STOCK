"""將上游腳本落地的每日訊號 JSON（OBV 底背離、核心池進出場）正規化為研究訊號快照。"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Callable, Mapping

from pydantic import ValidationError

from src.research_signal_ledger.models import ResearchSignalSnapshot, SignalDirection
from src.research_signal_ledger.sources.base import (
    TAIPEI,
    SourceCollectionResult,
    build_snapshot_key,
)

PriceLookup = Callable[[list[str], date], Mapping[str, float]]
LONG = SignalDirection.LONG
RISK = SignalDirection.RISK_REDUCE


@dataclass(frozen=True)
class UpstreamSpec:
    name: str  # 帳本來源名稱
    directory: str  # results/ 下的目錄與檔名前綴
    signal_kind: str
    rule_version: str


SPECS = (
    UpstreamSpec("obv_bottom", "obv_bottom", "obv_bottom_divergence", "obv_bottom_v1"),
    UpstreamSpec("core_watchlist", "core_signals", "core_pool_timing", "core_watchlist_v1"),
    UpstreamSpec("hsieh_growth", "hsieh_growth", "hsieh_growth_pick", "hsieh_growth_v1"),
    UpstreamSpec("quality_growth", "quality_growth", "quality_growth_pick", "quality_growth_v1"),
    UpstreamSpec("agan_moat", "agan_moat", "agan_moat_pick", "agan_moat_v1"),
)


def _row_price(row: dict):
    """OBV 記的是 close，基本面篩選記的是 price。"""
    for key in ("close", "price"):
        if isinstance(row.get(key), (int, float)):
            return row[key]
    return None


def _latest_rerun(directory: Path, prefix: str, day: date) -> Path | None:
    """同日重跑以 .N 序號新增；以序號最大者為最終版本。"""
    pattern = re.compile(rf"^{re.escape(prefix)}_{day:%Y%m%d}(?:\.(\d+))?\.json$")
    candidates = []
    if directory.is_dir():
        for path in directory.iterdir():
            match = pattern.match(path.name)
            if match:
                candidates.append((int(match.group(1) or 1), path))
    return max(candidates)[1] if candidates else None


class UpstreamSignalSource:
    def __init__(self, results_dir: Path, spec: UpstreamSpec, price_lookup: PriceLookup):
        self.results_dir = results_dir
        self.spec = spec
        self.price_lookup = price_lookup
        self.name = spec.name

    def collect(self, as_of: date) -> SourceCollectionResult:
        path = _latest_rerun(self.results_dir / self.spec.directory, self.spec.directory, as_of)
        if path is None:
            return SourceCollectionResult(self.name, [], "no_output", f"no {self.spec.directory} file")

        rows = json.loads(path.read_text(encoding="utf-8")).get("rows", [])
        if not rows:
            return SourceCollectionResult(self.name, [], "no_output", "file has no signals")

        source_event_id = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}:{as_of.isoformat()}"
        available_at = datetime.fromtimestamp(path.stat().st_mtime, tz=TAIPEI)
        symbols = [row["symbol"] for row in rows if isinstance(row.get("symbol"), str)]
        needs_price = any(_row_price(row) is None for row in rows)
        prices = self.price_lookup(symbols, as_of) if needs_price and symbols else {}

        snapshots, skipped = [], 0
        for row in rows:
            for direction in self._directions(row):
                try:
                    snapshot = self._normalize(row, direction, prices, as_of, available_at, source_event_id)
                except ValidationError:
                    skipped += 1
                    continue
                if snapshot is not None:
                    snapshots.append(snapshot)
        message = f"skipped={skipped}" if skipped else None
        return SourceCollectionResult(self.name, snapshots, "captured" if snapshots else "no_output", message)

    def _directions(self, row: dict) -> list[SignalDirection]:
        if self.spec.directory == "core_signals":
            directions = []
            if row.get("entry"):
                directions.append(LONG)
            if row.get("warn"):
                directions.append(RISK)
            return directions
        return [LONG]  # OBV 底部承接

    def _normalize(self, row, direction, prices, as_of, available_at, source_event_id):
        symbol = row.get("symbol")
        price = _row_price(row)
        if price is None:
            price = prices.get(symbol)
        if not isinstance(symbol, str) or not isinstance(price, (int, float)) or price <= 0:
            return None
        payload = {k: v for k, v in row.items() if k not in ("symbol",)}
        return ResearchSignalSnapshot(
            snapshot_key=build_snapshot_key(
                source=self.name,
                source_event_id=source_event_id,
                symbol=symbol,
                analysis_date=as_of,
                signal_kind=self.spec.signal_kind,
                direction=direction,
                rule_version=self.spec.rule_version,
            ),
            source=self.name,
            source_event_id=source_event_id,
            symbol=symbol,
            analysis_date=as_of,
            available_at=available_at,
            captured_at=datetime.now(UTC),
            signal_kind=self.spec.signal_kind,
            direction=direction,
            evaluation_enabled=True,
            rule_version=self.spec.rule_version,
            price_at_signal=float(price),
            source_payload=payload,
            benchmark_profile="market_equal_weight_liquid_tw_v1",
        )


def build_upstream_sources(results_dir: Path, price_lookup: PriceLookup) -> list[UpstreamSignalSource]:
    return [UpstreamSignalSource(results_dir, spec, price_lookup) for spec in SPECS]
