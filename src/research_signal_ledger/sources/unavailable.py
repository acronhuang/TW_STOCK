"""尚未具備可稽核持久化輸出的來源狀態。"""

from datetime import date

from src.research_signal_ledger.sources.base import SourceCollectionResult


class UnsupportedSource:
    def __init__(self, name: str, reason: str):
        self.name = name
        self.reason = reason

    def collect(self, as_of: date) -> SourceCollectionResult:
        return SourceCollectionResult(self.name, [], "unsupported", self.reason)