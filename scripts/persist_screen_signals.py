#!/usr/bin/env python3
"""每日落地基本面選股法（謝富旭成長精選、品質成長、阿甘護城河）供研究訊號成效帳本使用。

這三個掃描原本只在 daily_recommendations.py 內轉成 LINE 文字、沒有結構化輸出。
本腳本獨立執行，不改動 daily_recommendations.py 與其推播流程。
"""
import argparse
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import RESULTS_DIR, get_db  # noqa: E402
from src.domain.collections import COLL_STOCK_PRICE  # noqa: E402
from src.research_signal_ledger.persistence import write_daily_signals  # noqa: E402

# 輸出目錄名 -> 掃描方法名
SCREENS = (
    ("hsieh_growth", "hsieh_growth"),
    ("quality_growth", "quality_growth"),
    ("agan_moat", "agan"),
)


class Screens:
    """以同一個資料庫連線建立三個掃描；每個掃描只在被呼叫時計算一次。"""

    def __init__(self, database):
        self.database = database

    def hsieh_growth(self):
        from src.strategy.hsieh_value import HsiehValueScreen

        return HsiehValueScreen(self.database).growth_picks()

    def quality_growth(self):
        from src.strategy.quality_growth import QualityGrowthScreen

        return QualityGrowthScreen(self.database).screen()

    def agan(self):
        from src.strategy.agan import AganMoatScreen

        return AganMoatScreen(self.database).screen()


def build_screens() -> Screens:
    return Screens(get_db())


def latest_data_day() -> date:
    latest = get_db()[COLL_STOCK_PRICE].find_one({}, {"date": 1}, sort=[("date", -1)])
    value = latest["date"]
    return value.date() if isinstance(value, datetime) else value


def persist_all(results_dir: Path, data_day: date, screens) -> list[Path]:
    """逐一執行並落地；單一掃描失敗不影響其他（失敗者不產生檔案，也不會被補造）。"""
    written = []
    for directory, method in SCREENS:
        try:
            rows = getattr(screens, method)()
        except Exception as error:  # noqa: BLE001 - screen isolation is the contract here.
            print(f"{directory} failed: {error}")
            continue
        path = write_daily_signals(results_dir, directory, data_day, rows)
        if path is not None:
            written.append(path)
            print(f"{directory} rows={len(rows)} -> {path.name}")
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    written = persist_all(RESULTS_DIR, latest_data_day(), build_screens())
    return 0 if len(written) == len(SCREENS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
