"""將每日帶日期的 CSV 掃描輸出（籌碼、雙訊號、量價）正規化為研究訊號快照。"""

import csv
import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from src.research_signal_ledger.models import ResearchSignalSnapshot, SignalDirection
from src.research_signal_ledger.sources.base import (
    TAIPEI,
    SourceCollectionResult,
    build_snapshot_key,
)

LONG = SignalDirection.LONG
RISK = SignalDirection.RISK_REDUCE


@dataclass(frozen=True)
class CsvScanSpec:
    name: str
    subdir: str
    filename: str  # 含 {day:%Y%m%d}
    column: str
    signal_kind: str
    rule_version: str
    directions: dict[str, SignalDirection]


# 未列入的類別一律不產生快照：寧可漏記，也不憑猜測給方向。
SPECS = (
    CsvScanSpec(
        "chip", "chip", "chip_scan_{day:%Y%m%d}.csv", "研判", "chip_verdict", "chip_scan_v1",
        {
            "主力吸籌·散戶退": LONG, "法人散戶齊買": LONG,
            "主力出貨·散戶接": RISK, "法人散戶齊賣": RISK,
        },
    ),
    CsvScanSpec(
        "dual_signal", "dual", "dual_scan_{day:%Y%m%d}.csv", "雙訊號結論", "dual_signal", "dual_scan_v1",
        {"🚀 雙多共振": LONG, "🕳️ 雙空警示": RISK, "🎭 假突破陷阱": RISK, "⚡ 量升籌退": RISK},
    ),
    CsvScanSpec(
        "volume_price", "volume_price", "vp_scan_{day:%Y%m%d}.csv", "分類", "volume_price_class", "vp_scan_v1",
        {"爆量突破": LONG, "資金流入": LONG, "多頭背離": LONG, "資金流出": RISK, "空背警示": RISK},
    ),
)


def _squash(text: str) -> str:
    return "".join(text.split())


class CsvScanSource:
    def __init__(self, results_dir: Path, spec: CsvScanSpec):
        self.results_dir = results_dir
        self.spec = spec
        self.name = spec.name

    def collect(self, as_of: date) -> SourceCollectionResult:
        path = self.results_dir / self.spec.subdir / self.spec.filename.format(day=as_of)
        if not path.exists():
            return SourceCollectionResult(self.name, [], "no_output", f"no {path.name}")

        source_event_id = f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}:{as_of.isoformat()}"
        # 檔案寫出時間才是可用時間；內容只有日期。
        available_at = datetime.fromtimestamp(path.stat().st_mtime, tz=TAIPEI)
        snapshots = []
        with open(path, encoding="utf-8-sig", newline="") as handle:
            for raw in csv.DictReader(handle):
                row = {_squash(key): (value or "").strip() for key, value in raw.items() if key}
                snapshot = self._normalize(row, as_of, available_at, source_event_id)
                if snapshot is not None:
                    snapshots.append(snapshot)
        return SourceCollectionResult(self.name, snapshots, "captured" if snapshots else "no_output")

    def _normalize(self, row, as_of, available_at, source_event_id) -> ResearchSignalSnapshot | None:
        direction = self.spec.directions.get(row.get(_squash(self.spec.column), ""))
        symbol = row.get("代碼", "")
        try:
            price = float(row.get("收盤", ""))
        except ValueError:
            return None
        if direction is None or not symbol or price <= 0:
            return None
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
            price_at_signal=price,
            source_payload={"label": row.get(_squash(self.spec.column), "")},
            benchmark_profile="market_equal_weight_liquid_tw_v1",
        )


def build_csv_sources(results_dir: Path) -> list[CsvScanSource]:
    return [CsvScanSource(results_dir, spec) for spec in SPECS]
