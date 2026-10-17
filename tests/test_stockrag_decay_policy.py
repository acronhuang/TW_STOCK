"""TDD: RAG 時間衰減依文件類型分開處理——快照類舊報告被新結論壓過，維護中的舊文件不被新文件壓過。

題目集在 tests/rag_eval/conflict_cases.json：舊報告的語意相似度比新文件高（真實語料就是如此），
所以只有衰減能讓新文件排第一。
"""

import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from scripts import stockrag_search as rag

pytestmark = pytest.mark.unit

SPEC = json.loads((Path(__file__).parent / "rag_eval" / "conflict_cases.json").read_text(encoding="utf-8"))
AS_OF = rag.parse_as_of(SPEC["as_of"])
CASES = SPEC["cases"]
MAINTAINED = SPEC["maintained_cases"]


def build(spec_docs, monkeypatch):
    """spec_docs: [(path, kind, date, text, sim)]；查詢向量固定為 [1, 0]，sim 就是與查詢的 cosine。"""
    docs, rows = [], []
    for path, kind, date, text, sim in spec_docs:
        docs.append({"path": path, "chunk_idx": 0, "title": path, "kind": kind,
                     "doc_date": datetime.fromisoformat(date), "content": text})
        rows.append([sim, math.sqrt(1 - sim * sim)])
    monkeypatch.setattr(rag, "embed", lambda text: [1.0, 0.0])
    return docs, np.array(rows, dtype=np.float32)


def conflict_corpus(case, monkeypatch):
    s, f = case["stale"], case["fresh"]
    return build([(s["path"], s["kind"], s["date"], s["text"], 0.97), (f["path"], f["kind"], f["date"], f["text"], 0.90)], monkeypatch)


def maintained_corpus(case, monkeypatch):
    m = case["maintained"]
    spec = [(m["path"], m["kind"], m["date"], m["text"], 0.97)]
    spec += [(n["path"], n["kind"], n["date"], n["text"], 0.80 - 0.05 * i) for i, n in enumerate(case["newer"])]
    return build(spec, monkeypatch)


def ids(cases):
    return [c["id"] for c in cases]


@pytest.mark.parametrize("case", CASES, ids=ids(CASES))
def test_the_newer_conclusion_beats_the_older_report_that_looks_more_similar(case, monkeypatch):
    docs, mat = conflict_corpus(case, monkeypatch)

    hits = rag.search(case["q"], docs, mat, k=5, as_of=AS_OF)

    assert hits[0]["path"] == case["fresh"]["path"]


@pytest.mark.parametrize("case", CASES, ids=ids(CASES))
def test_without_decay_the_older_report_wins_so_the_case_can_tell_the_difference(case, monkeypatch):
    docs, mat = conflict_corpus(case, monkeypatch)

    hits = rag.search(case["q"], docs, mat, k=5, as_of=AS_OF, half_life=10**9)

    assert hits[0]["path"] == case["stale"]["path"]


@pytest.mark.parametrize("case", MAINTAINED, ids=ids(MAINTAINED))
def test_an_old_maintained_document_is_not_buried_by_newer_snapshots(case, monkeypatch):
    docs, mat = maintained_corpus(case, monkeypatch)

    hits = rag.search(case["q"], docs, mat, k=5, as_of=AS_OF)

    assert hits[0]["path"] == case["maintained"]["path"]


def test_a_maintained_document_still_reports_its_age(monkeypatch):
    docs, mat = maintained_corpus(MAINTAINED[0], monkeypatch)

    top = rag.search(MAINTAINED[0]["q"], docs, mat, k=1, as_of=AS_OF)[0]

    assert top["path"] == MAINTAINED[0]["maintained"]["path"] and top["age_days"] == (AS_OF - datetime(2026, 1, 15)).days


@pytest.mark.parametrize("kind,path,expected", [
    ("report", "ARCHITECTURE.md", True),
    ("result", "results/x.json", True),
    ("doc", "docs/archive/reports/OLD.md", True),
    ("doc", "docs/archive/CURRENT_STATE_2026-07-20.md", True),
    ("doc", "docs/reports/2026-10-10-x.md", True),
    ("doc", "docs/chat_history.md", True),
    ("doc", "docs/adr/0003-x.md", False),
    ("doc", "docs/guides/GUIDE.md", False),
    ("doc", "docs/data_dictionary.md", False),
    ("doc", "docs/archive-notes/x.md", False),
])
def test_only_snapshot_types_decay_with_age(kind, path, expected):
    assert rag.decays_with_age({"kind": kind, "path": path}) is expected


def test_a_chunk_without_a_path_is_treated_as_a_maintained_document():
    assert rag.decays_with_age({"kind": "doc"}) is False


def test_the_case_set_covers_every_snapshot_type_it_claims_to_protect():
    def snapshot_type(d):
        if d["kind"] in ("report", "result"):
            return d["kind"]
        return "archive" if d["path"].startswith("docs/archive/") else "reports"

    assert {snapshot_type(c["stale"]) for c in CASES} == {"report", "result", "archive", "reports"}
    assert len(CASES) >= 5 and len({c["id"] for c in CASES}) == len(CASES)
    assert all(rag.decays_with_age(c["stale"]) for c in CASES)


def test_the_toggle_that_turns_decay_off_still_turns_it_off_for_every_type(monkeypatch):
    docs, mat = maintained_corpus(MAINTAINED[1], monkeypatch)

    off = rag.search(MAINTAINED[1]["q"], docs, mat, k=3, as_of=AS_OF, half_life=10**9)

    assert all(h["score"] == pytest.approx(h["rrf"]) for h in off)
