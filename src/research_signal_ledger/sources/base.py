"""研究訊號來源的共用契約與不可變快照鍵。"""

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal, Protocol

from src.research_signal_ledger.models import ResearchSignalSnapshot, SignalDirection


TAIPEI = timezone(timedelta(hours=8))


def as_taipei_aware(value: datetime) -> datetime:
    """專案慶例：Mongo 與報告存 naive 本地(台北)時間，不是 UTC。"""
    return value if value.tzinfo else value.replace(tzinfo=TAIPEI)


CaptureStatus = Literal["captured", "no_output", "unsupported", "failed"]


@dataclass(frozen=True)
class SourceCollectionResult:
    source: str
    snapshots: list[ResearchSignalSnapshot]
    status: CaptureStatus
    message: str | None = None


class SignalSource(Protocol):
    name: str

    def collect(self, as_of: date) -> SourceCollectionResult: ...


def build_snapshot_key(
    *,
    source: str,
    source_event_id: str,
    symbol: str,
    analysis_date: date,
    signal_kind: str,
    direction: SignalDirection,
    rule_version: str,
) -> str:
    """依 SDD 的 stable fields 產生 canonical JSON SHA-256。"""
    payload = {
        "analysis_date": analysis_date.isoformat(),
        "direction": direction.value,
        "rule_version": rule_version,
        "signal_kind": signal_kind,
        "source": source,
        "source_event_id": source_event_id,
        "symbol": symbol,
    }
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()