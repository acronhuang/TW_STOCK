"""上櫃／興櫃重大訊息：MOPS 清單與明細解析、與既有 major_news 對帳、TPEX OpenAPI 轉換。

來源：
  - MOPS  POST https://mops.twse.com.tw/mops/api/t05st02（民國 year/month/day）：一次回該日全市場清單（只有主旨），
    含前一日 17:30 後的列；marketKind 為 sii 上市、otc 上櫃、rotc 興櫃、pub 公發。
  - MOPS  POST /mops/api/t05st02_detail：帶清單列的 parameters，回說明全文、條款、事實發生日。
  - TPEX OpenAPI mopsfin_t187ap04_O：上櫃每日（最新一個發言日），含說明全文。
文件形狀與 TWSE 的 major_news 相同（再加 market、source），既有的新聞佐證與 RAG 入庫不必改。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

LISTED_MARKETS = {"sii": "上市", "otc": "上櫃", "rotc": "興櫃"}   # pub（公發）不納入


def roc_date(text) -> datetime | None:
    s = str(text or "").strip()
    m = re.fullmatch(r"(\d{2,3})/(\d{1,2})/(\d{1,2})", s) or re.fullmatch(r"(\d{3})(\d{2})(\d{2})", s)
    if not m:
        return None
    try:
        return datetime(int(m[1]) + 1911, int(m[2]), int(m[3]))
    except ValueError:
        return None


def clock(text) -> str | None:
    """'17:31:28'、'211554'、'70003'（TWSE 不補零）→ 六位 HHMMSS；讀不出來回 None。"""
    s = str(text or "").strip()
    m = re.fullmatch(r"(\d{1,2}):(\d{2}):(\d{2})", s)
    if m:
        hh, mm, ss = int(m[1]), int(m[2]), int(m[3])
    elif re.fullmatch(r"\d{5,6}", s):
        s = s.zfill(6)
        hh, mm, ss = int(s[:2]), int(s[2:4]), int(s[4:])
    else:
        return None
    return f"{hh:02d}{mm:02d}{ss:02d}" if hh < 24 and mm < 60 and ss < 60 else None


def _plain(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def parse_list(payload: dict) -> list[dict]:
    if not isinstance(payload, dict) or payload.get("code") != 200:
        return []
    rows = []
    for raw in ((payload.get("result") or {}).get("data") or []):
        if len(raw) < 6 or not isinstance(raw[5], dict):
            continue
        params = raw[5].get("parameters") or {}
        day, when = roc_date(raw[0]), clock(raw[1])
        if day is None or when is None or not str(raw[2]).strip():
            continue
        rows.append({"stock_id": str(raw[2]).strip(), "name": str(raw[3]).strip(), "date": day, "time": when,
                     "subject": str(raw[4]), "market": params.get("marketKind"), "params": params})
    return rows


def only_markets(rows: list[dict], markets) -> list[dict]:
    return [r for r in rows if r["market"] in set(markets)]


def _time_key(stock_id: str, day: datetime, when: str) -> str:
    return f"{stock_id}|{day:%Y%m%d}|{when}"


def _subject_key(stock_id: str, day: datetime, subject: str) -> str:
    return f"{stock_id}|{day:%Y%m%d}|?{_plain(subject)}"


def existing_keys(docs) -> set[str]:
    """既有文件的比對鍵：有可讀發言時間的用時間鍵；讀不出時間的舊資料才退而用主旨鍵
    （同日同主旨但不同時間的重複公告要能分得開）。"""
    keys: set[str] = set()
    for d in docs:
        if not d.get("stock_id") or not isinstance(d.get("date"), datetime):
            continue
        when = clock(d.get("time"))
        keys.add(_time_key(d["stock_id"], d["date"], when) if when else _subject_key(d["stock_id"], d["date"], d.get("subject")))
    return keys


def is_known(row: dict, keys: set[str]) -> bool:
    return (_time_key(row["stock_id"], row["date"], row["time"]) in keys
            or _subject_key(row["stock_id"], row["date"], row.get("subject")) in keys)


def missing(rows: list[dict], keys: set[str]) -> list[dict]:
    return [r for r in rows if not is_known(r, keys)]


def coverage(rows: list[dict], keys: set[str]) -> tuple[int, int]:
    """(官方列數, 其中我們已有的列數)。"""
    return len(rows), sum(1 for r in rows if is_known(r, keys))


def detail_to_doc(row: dict, payload: dict, now: datetime) -> dict | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("code") == 406:
        # 存託憑證（-DR）等列在清單有、明細端點「查無相符資料」：只存主旨並標記，否則永遠被當成缺而重試
        return {"stock_id": row["stock_id"], "name": row["name"], "date": row["date"], "time": row["time"], "subject": row["subject"],
                "clause": "", "fact_date": None, "detail": "", "detail_missing": True, "market": row["market"], "source": "mops",
                "updated_at": now}
    if payload.get("code") != 200:
        return None
    entries = ((payload.get("result") or {}).get("data")) or []
    if not entries:
        return None
    serial = row["params"].get("serialNumber")
    entry = next((e for e in entries if e and e[0] == serial), entries[0])
    if len(entry) < 10:
        return None
    clause = str(entry[7]).strip()
    return {"stock_id": row["stock_id"], "name": row["name"], "date": row["date"], "time": row["time"],
            "subject": str(entry[6]), "clause": f"第{clause}款" if clause.isdigit() else clause,
            "fact_date": roc_date(entry[8]), "detail": str(entry[9]), "market": row["market"], "source": "mops",
            "updated_at": now}


def key_of(doc: dict) -> str:
    when = clock(doc.get("time"))
    return _time_key(doc["stock_id"], doc["date"], when) if when else _subject_key(doc["stock_id"], doc["date"], doc.get("subject"))


def save_new(col, docs: list[dict]) -> int:
    """已有的不重複寫。寫入的比對條件包含發言時間：同一公司同日、同主旨但不同時間的公告要分成兩筆
    （舊条件只用 stock_id+date+subject，後一筆會覆蓋前一筆）。"""
    if not docs:
        return 0
    days = [d["date"] for d in docs]
    keys = existing_keys(col.find({"date": {"$gte": min(days) - timedelta(days=1), "$lte": max(days)}},
                                  {"stock_id": 1, "date": 1, "time": 1, "subject": 1}))
    saved = 0
    for d in docs:
        if key_of(d) in keys or is_known(d, keys):
            continue
        col.update_one({"stock_id": d["stock_id"], "date": d["date"], "time": d["time"], "subject": d["subject"]}, {"$set": d}, upsert=True)
        keys.add(key_of(d))
        saved += 1
    return saved


def reconcile(rows: list[dict], keys: set[str], markets, fetch_detail, now: datetime) -> dict:
    """清單中缺的列才呼叫明細；fetch_detail 為 None 時只統計（dry-run）。明細失敗的列不寫入，下次仍算缺。"""
    todo = missing(only_markets(rows, markets), keys)
    docs, failed = [], 0
    if fetch_detail is not None:
        for row in todo:
            try:
                doc = detail_to_doc(row, fetch_detail(row["params"]), now)
            except Exception:  # noqa: BLE001 - 單筆失敗留給下一輪
                doc = None
            if doc is None:
                failed += 1
            else:
                docs.append(doc)
    return {"missing": len(todo), "docs": docs, "failed": failed}


def tpex_doc(row: dict, now: datetime) -> dict | None:
    code, day = str(row.get("SecuritiesCompanyCode", "")).strip(), roc_date(row.get("發言日期"))
    if not code or day is None:
        return None
    return {"stock_id": code, "name": str(row.get("CompanyName", "")).strip(), "date": day,
            "time": clock(row.get("發言時間")) or "", "subject": str(row.get("主旨", "")),
            "clause": str(row.get("符合條款", "")), "fact_date": roc_date(row.get("事實發生日")),
            "detail": str(row.get("說明", "")), "market": "otc", "source": "tpex_openapi", "updated_at": now}
