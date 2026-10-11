from dataclasses import dataclass


@dataclass(frozen=True)
class Gap:
    collection: str
    day: str      # YYYYMMDD
    kind: str = "gap"   # gap=整天缺；thin=筆數殘缺

    @property
    def key(self) -> str:
        return f"{self.collection}:{self.day}:{self.kind}"
