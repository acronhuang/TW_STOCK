"""沒有當日持久化輸出的按需來源。"""

from datetime import date

from src.research_signal_ledger.sources.base import SourceCollectionResult


class OnDemandSource:
    name = "on_demand"

    def collect(self, as_of: date) -> SourceCollectionResult:
        return SourceCollectionResult(
            self.name,
            [],
            "no_output",
            f"no persistent on-demand output for {as_of.isoformat()}",
        )