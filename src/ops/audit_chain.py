"""防篡改指紋鏈：為只增不改的帳本逐筆登記指紋，之後能發現被繞過程式改動、刪除或整條鏈被重寫。

每筆登記：{seq, collection, key, digest, prev, hash}，hash = sha256(prev|seq|collection|key|digest)。
digest 是該文件內容（不含 _id）的標準化 JSON 的 sha256；prev 是前一筆的 hash，形成一條鏈。
鏈頭（最後一筆）另存一份檔案備份；能同時改資料庫與鏈頭檔的人仍可重寫，所以鏈頭要抄到別處（異機）。
"""
import hashlib
import json
from datetime import datetime
from pathlib import Path

CHAIN = "audit_chain"
LEDGERS = ("research_signal_snapshots", "portfolio_trades")  # 只增不改的帳本
GENESIS = "0" * 64


def _default(value):
    if hasattr(value, "to_decimal"):
        return str(value.to_decimal())
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def canonical(doc: dict) -> str:
    body = {k: v for k, v in doc.items() if k != "_id"}
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=_default)


def digest(doc: dict) -> str:
    return hashlib.sha256(canonical(doc).encode("utf-8")).hexdigest()


def entry_hash(prev: str, seq: int, collection: str, key: str, doc_digest: str) -> str:
    return hashlib.sha256(f"{prev}|{seq}|{collection}|{key}|{doc_digest}".encode("utf-8")).hexdigest()


def _head(db):
    return db[CHAIN].find_one(sort=[("seq", -1)])


def register(db, collection: str, now: datetime | None = None) -> int:
    """登記尚未入鏈的文件（依 _id 順序）。回登記筆數。"""
    now = now or datetime.now()
    db[CHAIN].create_index("seq", unique=True)
    db[CHAIN].create_index([("collection", 1), ("key", 1)], unique=True)
    known = {e["key"] for e in db[CHAIN].find({"collection": collection}, {"key": 1})}
    head = _head(db)
    seq, prev = (head["seq"], head["hash"]) if head else (0, GENESIS)
    added = 0
    for doc in db[collection].find().sort("_id", 1):
        key = str(doc["_id"])
        if key in known:
            continue
        seq += 1
        doc_digest = digest(doc)
        current = entry_hash(prev, seq, collection, key, doc_digest)
        db[CHAIN].insert_one({"seq": seq, "collection": collection, "key": key, "digest": doc_digest,
                              "prev": prev, "hash": current, "ts": now})
        prev, added = current, added + 1
    return added


def write_head(db, path: Path, now: datetime | None = None) -> dict | None:
    head = _head(db)
    if not head:
        return None
    record = {"seq": head["seq"], "hash": head["hash"], "written_at": (now or datetime.now()).isoformat()}
    Path(path).write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    return record


def _anchor_problems(by_seq: dict, saved: dict, label: str = "") -> list:
    prefix = f"{label}：" if label else ""
    mine = by_seq.get(saved["seq"])
    if mine is None:
        return [f"{prefix}鏈頭備份的第 {saved['seq']} 筆已不在鏈上（鏈被截斷）"]
    if mine["hash"] != saved["hash"]:
        return [f"{prefix}第 {saved['seq']} 筆的雜湊與鏈頭備份不同（鏈被重寫）"]
    return []


def anchor_files(directory) -> list:
    """異機錨點：目錄下所有 audit_chain_head_*.json；目錄不存在回空。"""
    directory = Path(directory) if directory else None
    return sorted(directory.glob("audit_chain_head_*.json")) if directory and directory.is_dir() else []


def verify(db, collections=LEDGERS, head_file: Path | None = None, anchors=()) -> dict:
    """回報：鏈本身斷裂、文件被改、文件被刪、鏈頭與備份不符。全空才算通過。

    head_file 是同一台機器上的鏈頭檔（每晚登記時重寫，只能防「忘了寫」）；
    anchors 是從異機抄回的歷史鏈頭，鏈上同序號的雜湊必須一致，這才防得住整條鏈被重寫。"""
    problems = {"broken_links": [], "modified": [], "missing": [], "anchor": []}
    prev, last_seq = GENESIS, 0
    entries = list(db[CHAIN].find().sort("seq", 1))
    by_seq = {e["seq"]: e for e in entries}
    for entry in entries:
        if entry["seq"] != last_seq + 1:
            problems["broken_links"].append(f"序號不連續：{last_seq} → {entry['seq']}")
        if entry["prev"] != prev or entry["hash"] != entry_hash(entry["prev"], entry["seq"], entry["collection"],
                                                                 entry["key"], entry["digest"]):
            problems["broken_links"].append(f"第 {entry['seq']} 筆的雜湊不符")
        prev, last_seq = entry["hash"], entry["seq"]

    wanted = {}
    for entry in entries:
        if entry["collection"] in collections:
            wanted.setdefault(entry["collection"], {})[entry["key"]] = entry["digest"]
    for collection, keys in wanted.items():
        seen = set()
        for doc in db[collection].find():
            key = str(doc["_id"])
            seen.add(key)
            if key in keys and digest(doc) != keys[key]:
                problems["modified"].append(f"{collection}/{key}")
        problems["missing"] += [f"{collection}/{key}" for key in keys if key not in seen]

    if head_file and Path(head_file).exists():
        saved = json.loads(Path(head_file).read_text(encoding="utf-8"))
        problems["anchor"] += _anchor_problems(by_seq, saved)
    for path in anchors:
        try:
            saved = json.loads(Path(path).read_text(encoding="utf-8"))
            problems["anchor"] += _anchor_problems(by_seq, {"seq": saved["seq"], "hash": saved["hash"]}, Path(path).name)
        except (OSError, ValueError, KeyError, TypeError):
            problems["anchor"].append(f"{Path(path).name}：錨點檔無法讀取")
    return {"entries": len(entries), "anchors_checked": len(list(anchors)), "ok": not any(problems.values()), **problems}
