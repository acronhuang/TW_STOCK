"""財報重編版本歷史：quarterly_earnings 被各來源覆寫前，把「已公布數字被改動」的舊版留下來。

不改動 6 支寫入 quarterly_earnings 的腳本，改由每日快照比對：
- 首次看到的季度存成 baseline（v1）；其 observed_at 只是我們第一次看到的時間，不是公司公告時間。
- 既有欄位的數值被改動 → 新增下一版，並記錄 changed_fields；
- 只是補上原本缺的欄位（如先寫損益、後補資產負債）→ 併入現行版本，不算重編。
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime

SECTIONS = ("income", "balance", "cashflow")
RELATIVE_TOLERANCE = 1e-6


def _number(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if hasattr(value, "to_decimal"):
        value = value.to_decimal()
    if isinstance(value, (int, float)) or hasattr(value, "as_tuple"):
        number = float(value)
        return None if math.isnan(number) else number
    return None


def flatten(doc: dict) -> dict[str, float]:
    """損益、資產負債、現金流量的數值欄位攤平成 {"income.net_income": 123.0}；旗標與字串不算內容。"""
    flat = {}
    for section in SECTIONS:
        for name, value in (doc.get(section) or {}).items():
            number = _number(value)
            if number is not None:
                flat[f"{section}.{name}"] = number
    return flat


def content_hash(flat: dict[str, float]) -> str:
    payload = json.dumps(sorted((k, round(v, 6)) for k, v in flat.items()), separators=(",", ":"))
    return hashlib.sha1(payload.encode()).hexdigest()


def _close(old: float, new: float) -> bool:
    return abs(old - new) <= RELATIVE_TOLERANCE * max(abs(old), abs(new), 1.0)


def _version_doc(doc: dict, version: int, now: datetime, **extra) -> dict:
    key = (doc["symbol"], doc["year"], doc["season"])
    return {
        "_id": f"{key[0]}:{key[1]}:{key[2]}:v{version}", "symbol": key[0], "year": key[1], "season": key[2],
        "version": version, "observed_at": now, "data_source": doc.get("data_source"),
        "report_type": doc.get("report_type"), "content_hash": content_hash(flatten(doc)),
        **{section: doc.get(section) or {} for section in SECTIONS}, **extra,
    }


def build_actions(docs, hashes: dict, load_latest, now: datetime):
    """docs: 現行 quarterly_earnings；hashes: {(symbol,year,season): (version, content_hash)}；
    load_latest(key) 取該季最新版完整文件（僅在雜湊不同時呼叫）。回 (actions, summary)。"""
    actions = []
    summary = {"baseline": 0, "restated": 0, "merged": 0, "unchanged": 0}
    for doc in docs:
        key = (doc["symbol"], doc["year"], doc["season"])
        known = hashes.get(key)
        if known is None:
            actions.append({"op": "insert", "doc": _version_doc(doc, 1, now, baseline=True)})
            summary["baseline"] += 1
            continue
        flat = flatten(doc)
        if content_hash(flat) == known[1]:
            summary["unchanged"] += 1
            continue
        latest = load_latest(key)
        previous = flatten(latest)
        changed = sorted(k for k, old in previous.items() if k in flat and not _close(old, flat[k]))
        added = sorted(k for k in flat if k not in previous)
        if changed:
            actions.append({"op": "insert", "doc": _version_doc(
                doc, latest["version"] + 1, now, baseline=False, changed_fields=changed, added_fields=added,
                source_changed=latest.get("data_source") != doc.get("data_source"))})
            summary["restated"] += 1
        elif added:
            merged = {section: {**(latest.get(section) or {}), **(doc.get(section) or {})} for section in SECTIONS}
            actions.append({"op": "merge", "id": latest["_id"],
                            "set": {**merged, "content_hash": content_hash(flatten(merged)), "merged_at": now}})
            summary["merged"] += 1
        else:
            summary["unchanged"] += 1
    return actions, summary


def version_as_of(versions: list[dict], as_of: datetime) -> dict | None:
    """時點查詢：baseline 視為一直可用；重編版本要在 observed_at 之後才算可見。"""
    visible = [v for v in versions if v.get("baseline") or v["observed_at"] <= as_of]
    return max(visible, key=lambda v: v["version"]) if visible else None
