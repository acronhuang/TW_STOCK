"""FinMind 額度檢查：掃每小時下載日誌；有 HTTP 402、輪次不足、沒有日誌或最新一輪太舊，都算異常。

無資料不是通過：日誌不存在或停止產生時，不能因為「沒看到 402」就判定正常。
"""
import math
import re
from datetime import datetime, timedelta
from pathlib import Path

LOG_DIR = Path("/home/mdsadmin/Stock/tw-stock-analysis/logs/hourly_updates")
STAMP = re.compile(r"hourly_update_(\d{8})_(\d{6})\.log$")
MARK = "HTTP 錯誤: 402"
MAX_AGE = timedelta(hours=3)  # 每小時一輪，超過 3 小時沒有新日誌就是排程停了


def run_logs(log_dir) -> list[tuple[datetime, Path]]:
    runs = []
    for path in Path(log_dir).glob("hourly_update_*.log"):
        match = STAMP.search(path.name)
        if match:
            runs.append((datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S"), path))
    return sorted(runs)


def check(log_dir, now: datetime, runs: int = 72, min_runs: int | None = None,
          max_age: timedelta = MAX_AGE) -> tuple[bool, str, list]:
    """回 (是否正常, 說明, [(輪次時間, 402 次數)])。"""
    min_runs = min_runs if min_runs is not None else math.ceil(runs * 0.75)
    found = run_logs(log_dir)
    if not found:
        return False, f"無資料：{log_dir} 沒有任何每小時下載日誌", []
    newest = found[-1][0]
    if now - newest > max_age:
        return False, f"無資料：最新一輪是 {newest:%Y-%m-%d %H:%M}，已超過 {max_age.total_seconds() / 3600:.0f} 小時沒有新日誌", []
    window = found[-runs:]
    if len(window) < min_runs:
        return False, f"輪次不足：只有 {len(window)} 輪，預期至少 {min_runs} 輪（要看最近 {runs} 輪）", []
    hits = []
    for stamp, path in window:
        count = path.read_text(encoding="utf-8", errors="ignore").count(MARK)
        if count:
            hits.append((stamp, count))
    if hits:
        where = "、".join(f"{stamp:%m-%d %H:%M}({count})" for stamp, count in hits[:6])
        return False, f"最近 {len(window)} 輪中 {len(hits)} 輪出現 HTTP 402（共 {sum(c for _, c in hits)} 次）：{where}", hits
    return True, f"最近 {len(window)} 輪沒有 HTTP 402", []
