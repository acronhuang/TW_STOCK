"""每小時重抓的價值量測：每小時存一次「剛被每小時下載碰過的文件」的內容雜湊，之後比對相鄰兩次有多少真的變動。

內容雜湊不含 _id、updated_at、created_at：只被改了時間戳記不算內容變動。
"""
import hashlib
import json
import re
from pathlib import Path

from src.ops.audit_chain import canonical

COLLECTIONS = ("dividend_detail", "dividend_results", "month_revenue_detail")
IGNORED = {"_id", "updated_at", "created_at"}
CODE = re.compile(r"\[\d+/\d+\]\s+(\S+?)\.\.\.")


def content_hash(doc: dict) -> str:
    body = {k: v for k, v in doc.items() if k not in IGNORED}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()[:16]


def hourly_codes(log_path) -> set[str]:
    """從最近一輪每小時下載日誌取出它逐檔處理過的股票代號。"""
    text = Path(log_path).read_text(encoding="utf-8", errors="ignore")
    return set(CODE.findall(text))


def compare(previous: dict, current: dict) -> dict:
    """previous、current 都是 {文件 id: 內容雜湊}；只比對兩次都有的文件，新出現的另計。"""
    both = previous.keys() & current.keys()
    changed = sum(1 for key in both if previous[key] != current[key])
    return {"touched": len(current), "compared": len(both), "changed": changed,
            "new": len(current.keys() - previous.keys())}


def report(snapshots: list[dict]) -> dict:
    """snapshots：依時間排序的 {ts, collections: {名稱: {id: 雜湊}}}。回傳每個集合的合計。"""
    totals = {}
    for before, after in zip(snapshots, snapshots[1:]):
        for name, current in after["collections"].items():
            row = compare(before["collections"].get(name, {}), current)
            total = totals.setdefault(name, {"touched": 0, "compared": 0, "changed": 0, "new": 0, "hours": 0})
            for key in ("touched", "compared", "changed", "new"):
                total[key] += row[key]
            total["hours"] += 1
    return totals


def load_snapshots(path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
