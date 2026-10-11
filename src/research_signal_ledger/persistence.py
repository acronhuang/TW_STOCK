"""上游腳本的每日訊號落地：只新增、不覆寫，失敗不影響呼叫端。"""

import json
from datetime import date, datetime
from pathlib import Path


def _as_day(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value


def write_daily_signals(results_dir: Path, name: str, data_day, rows: list[dict]) -> Path | None:
    """寫入 results/<name>/<name>_YYYYMMDD[.N].json；同日重跑以序號新增，絕不覆寫。

    空結果也要寫檔，才能區分「今日沒有訊號」與「腳本沒有跑」。任何失敗只回傳 None，
    因為這是附加的落地步驟，不得讓原本的掃描、LINE 或告警流程中斷。
    """
    try:
        day = _as_day(data_day)
        directory = Path(results_dir) / name
        directory.mkdir(parents=True, exist_ok=True)
        payload = {"data_date": day.isoformat(), "rows": rows}
        text = json.dumps(payload, ensure_ascii=False, default=str)
        sequence = 1
        while True:
            suffix = "" if sequence == 1 else f".{sequence}"
            path = directory / f"{name}_{day:%Y%m%d}{suffix}.json"
            try:
                # 獨佔建立：並行或重跑時不會覆寫既有檔案。
                with open(path, "x", encoding="utf-8") as handle:
                    handle.write(text)
                return path
            except FileExistsError:
                sequence += 1
    except OSError:
        return None
