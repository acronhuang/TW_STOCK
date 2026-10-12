#!/usr/bin/env python3
"""新聞與重大訊息的 RAG 語料：文件組裝、檢索、決策截止時點與上線門檻。

與專案文件語料（stockrag.docs）分開存在 stockrag.news_docs：
  - 筆數多（重大訊息每月數千筆），混在一起會拖慢字面比對、稀釋專案文件的檢索品質；
  - 檢索幾乎都帶代號與截止時點，先過濾再排序，成本很低。

時間規則（前視防護的核心）：doc_date 是「這則資訊最早何時能被看到」，不是抓取時間。
  - 重大訊息：發言日期 + 發言時間；時間讀不出來就取當天 23:59:59（寧可晚、不可早）。
  - 媒體新聞標題：快取沒有各則發布時間，只能用「第一次抓到的時間」，同一組標題不重複入庫。
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

try:
    from scripts import stockrag_search as base
except ImportError:  # 直接從 scripts/ 執行、專案根目錄不在 sys.path 時
    import stockrag_search as base

COLLECTION = "news_docs"
HALF_LIFE_NEWS = 30      # 天；新聞比專案文件老得快
MAX_CHARS = 900          # 單則上限：控制嵌入成本，也避免超長公告主宰排序
GATE_MAX_AGE_DAYS = 14
RRF_K = base.RRF_K


def _clean(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _sha(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:10]


def major_available_at(row: dict) -> datetime:
    day = row["date"]
    digits = re.sub(r"\D", "", str(row.get("time") or ""))
    text = str(row.get("time") or "").strip()
    if digits and digits == text and len(digits) <= 6:
        digits = digits.zfill(6)
        hh, mm, ss = int(digits[:2]), int(digits[2:4]), int(digits[4:])
        if hh < 24 and mm < 60 and ss < 60:
            return day.replace(hour=hh, minute=mm, second=ss, microsecond=0)
    return day.replace(hour=23, minute=59, second=59, microsecond=0)


def major_doc(row: dict) -> dict | None:
    symbol, day = _clean(row.get("stock_id")), row.get("date")
    if not symbol or not isinstance(day, datetime):
        return None
    available = major_available_at(row)
    subject = _clean(row.get("subject"))
    fact = row.get("fact_date")
    head = f"重大訊息 {_clean(row.get('name'))}({symbol}) 發言時間 {available:%Y-%m-%d %H:%M}"
    body = f"主旨：{subject}\n條款：{_clean(row.get('clause'))}"
    if isinstance(fact, datetime):
        body += f"\n事實發生日：{fact:%Y-%m-%d}"
    body += f"\n說明：{_clean(row.get('detail'))}"
    return {"key": f"major:{symbol}:{available:%Y%m%d%H%M%S}:{_sha(subject + _clean(row.get('detail')))}",
            "source": "twse_major", "kind": "announcement", "symbol": symbol, "name": _clean(row.get("name")),
            "event_date": day.replace(hour=0, minute=0, second=0, microsecond=0), "doc_date": available,
            "title": subject[:200], "content": f"{head}\n{body}"[:MAX_CHARS]}


def media_doc(row: dict) -> dict | None:
    symbol, titles, fetched = _clean(row.get("stock_id")), [_clean(t) for t in row.get("titles") or [] if _clean(t)], row.get("fetched_at")
    if not symbol or not titles or not isinstance(fetched, datetime):
        return None
    head = f"媒體新聞標題 {_clean(row.get('name'))}({symbol}) 擷取時間 {fetched:%Y-%m-%d %H:%M}"
    return {"key": f"media:{symbol}:{_sha(chr(10).join(titles))}", "source": "media_news", "kind": "news", "symbol": symbol,
            "name": _clean(row.get("name")), "event_date": fetched.replace(hour=0, minute=0, second=0, microsecond=0),
            "doc_date": fetched, "title": titles[0][:200], "content": (head + "\n" + "\n".join(f"- {t}" for t in titles))[:MAX_CHARS]}


def load(mongo_uri="mongodb://localhost:27017/"):
    from pymongo import MongoClient

    col = MongoClient(mongo_uri)["stockrag"][COLLECTION]
    docs = list(col.find({}, {"embedding": 1, "key": 1, "symbol": 1, "name": 1, "kind": 1, "source": 1, "title": 1,
                              "content": 1, "event_date": 1, "doc_date": 1}))
    if not docs:
        return None, None
    mat = np.array([d["embedding"] for d in docs], dtype=np.float32)
    mat /= (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    for d in docs:
        d.pop("embedding", None)
        d["path"], d["chunk_idx"] = d["key"], 0
    return docs, mat


DATE_BOOST = 4.0         # 題目指定日期時，事件日相符的加權
_RECENT = re.compile(r"最近|近期|最新|近日|近況|這幾天|今天|今日|昨天|昨日|本週|這週|剛剛")


def wants_recent(question: str) -> bool:
    """題目明說要「最近」的才偏愛較新的新聞。實測（2026-10-12 查詢集）對所有查詢套 30 天半衰期會讓較舊但最相關的公告排不進前五：
    不含日期的個股查詢 recall@5 為 0.56，完全不衰減則為 1.00。"""
    return _RECENT.search(question) is not None


def extract_dates(question: str, ref: datetime) -> list[datetime]:
    """題目中的日期（YYYY-MM-DD、YYYY/M/D、M月D日、M/D）。無年份者取 ref 所在年，若晚於 ref 則視為去年。"""
    found: list[tuple[int, datetime]] = []

    def add(pos: int, year: int, month: int, day: int) -> None:
        try:
            when = datetime(year, month, day)
        except ValueError:
            return
        if all(when != w for _, w in found):
            found.append((pos, when))

    rest = question
    for m in re.finditer(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", question):
        add(m.start(), int(m[1]), int(m[2]), int(m[3]))
        rest = rest[:m.start()] + " " * (m.end() - m.start()) + rest[m.end():]
    for pattern in (r"(\d{1,2})月(\d{1,2})日?", r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])"):
        for m in re.finditer(pattern, rest):
            month, day = int(m[1]), int(m[2])
            year = ref.year
            try:
                if datetime(year, month, day) > ref:
                    year -= 1
            except ValueError:
                continue
            add(m.start(), year, month, day)
    return [when for _, when in sorted(found)]


def search(query, docs, mat, k=5, symbols=None, as_of=None, window_days=None, half_life=None, pool=60, dates=None):
    """symbols：只看這些代號。as_of：決策時點，之後的、以及沒有日期的一律排除。window_days：只看截止前這幾天內。
    dates：題目指定的事件日（預設自動從題目辨識），事件日相符者加權。
    half_life：預設只在題目說「最近」時才用 HALF_LIFE_NEWS 衰減；明確指定則強制套用（對照實驗用）。同分時較新者在前。"""
    qv = np.array(base.embed(query), dtype=np.float32)
    qv /= (np.linalg.norm(qv) + 1e-9)
    wanted = set(symbols) if symbols else None
    floor = (as_of - timedelta(days=window_days)) if (as_of is not None and window_days) else None

    def visible(d):
        when = d.get("doc_date")
        if wanted is not None and d.get("symbol") not in wanted:
            return False
        if as_of is not None and not (isinstance(when, datetime) and when <= as_of):
            return False
        return floor is None or (isinstance(when, datetime) and when >= floor)

    idx_all = np.array([i for i, d in enumerate(docs) if visible(d)], dtype=int)
    if idx_all.size == 0:
        return []
    vec = mat[idx_all] @ qv
    lit = base.literal_scores(query, [docs[i] for i in idx_all])
    newest = -np.array([d["doc_date"].timestamp() if isinstance(d.get("doc_date"), datetime) else 0.0
                        for d in (docs[i] for i in idx_all)])
    rank_v = {int(g): r + 1 for r, g in enumerate(idx_all[np.lexsort((newest, -vec))[:pool]])}   # 分數相同時較新者在前
    rank_l = {int(g): r + 1 for r, g in enumerate(idx_all[np.lexsort((newest, -lit))[:pool]])}
    sim = {int(g): float(v) for g, v in zip(idx_all, vec)}
    ref = as_of if as_of is not None else datetime.now()
    wanted_days = set(dates if dates is not None else extract_dates(query, ref))
    decay_half_life = half_life if half_life is not None else (HALF_LIFE_NEWS if wants_recent(query) else None)
    fused = []
    for gi in set(rank_v) | set(rank_l):
        rrf = (1.0 / (RRF_K + rank_v[gi]) if gi in rank_v else 0.0) + (1.0 / (RRF_K + rank_l[gi]) if gi in rank_l else 0.0)
        d = docs[gi]
        age = max((ref - d["doc_date"]).days, 0) if isinstance(d.get("doc_date"), datetime) else 0
        weight = DATE_BOOST if d.get("event_date") in wanted_days else 1.0
        if decay_half_life and not wanted_days:
            weight = 0.5 ** (age / float(decay_half_life))
        fused.append({**d, "rrf": rrf, "age_days": age, "vec_sim": sim[gi], "score": rrf * weight})
    fused.sort(key=lambda x: (-x["score"], -(x["doc_date"].timestamp() if isinstance(x.get("doc_date"), datetime) else 0)))
    return fused[:k]


def _aliases(name: str) -> set[str]:
    """「康霈*」「愛爾達-創」「矽力*-KY」這類標記後綴，使用者不會打，去掉後當作别名。"""
    plain = re.sub(r"-(KY|創|DR|F)$", "", name.strip())
    plain = re.sub(r"[*＊]+$", "", plain)
    return {a for a in (name.strip(), plain) if len(a) >= 2}


def extract_symbols(question: str, known: dict[str, str]) -> list[str]:
    """依出現順序回傳題目中的代號：4～6 碼且在已知名單內的數字，以及（至少 2 字的）公司名稱。"""
    found: list[tuple[int, str]] = []
    for m in re.finditer(r"(?<![0-9A-Za-z])(\d{4,6}[A-Z]?)(?![0-9A-Za-z])", question):
        if m.group(1) in known:
            found.append((m.start(), m.group(1)))
    for code, name in known.items():
        for alias in _aliases(name or ""):
            if (pos := question.find(alias)) >= 0:
                found.append((pos, code))
    out: list[str] = []
    for _, code in sorted(found):
        if code not in out:
            out.append(code)
    return out


def decision_cutoff(docs: list[dict], decision_date: datetime) -> datetime:
    """決策的產出時間（取當日文件 created_at 的最大值）；讀不到就用決策日當天結束。"""
    created = [d["created_at"] for d in docs if isinstance(d.get("created_at"), datetime)]
    if created:
        return max(created)
    return decision_date.replace(hour=23, minute=59, second=59, microsecond=0)


def write_gate(path, summary: dict, passed: bool, k: int, now: datetime) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({"passed": bool(passed), "k": k, "recall": summary.get("recall"), "mrr": summary.get("mrr"),
                                      "checked_at": now.isoformat(timespec="seconds")}, ensure_ascii=False), encoding="utf-8")


def gate_open(path, now: datetime, max_age_days: int = GATE_MAX_AGE_DAYS) -> bool:
    """近期通過查詢集門檻才開放；沒有紀錄、過期、未通過、檔案壞掉一律關閉。"""
    try:
        gate = json.loads(Path(path).read_text(encoding="utf-8"))
        checked = datetime.fromisoformat(gate["checked_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return bool(gate.get("passed")) and timedelta(0) <= now - checked <= timedelta(days=max_age_days)
