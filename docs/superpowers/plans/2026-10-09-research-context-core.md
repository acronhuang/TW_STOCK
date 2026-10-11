# Research Context Core Implementation Plan

> **For agentic workers:** Execute one task at a time. Each production change must be preceded by a correctly failing test and followed immediately by its focused passing test.

**Goal:** 實作平台中立、唯讀且可引用的研究上下文核心，供未來任意 adapter 使用，但不加入 API、UI、LLM、Dify 或外部入口。

**Architecture:** 核心置於 `src/research_context/`。請求模型負責標準化與驗證；`ResearchRepository` 隔離 MongoDB；`RagRetriever` 快取既有 RAG 並輸出白名單 citation；`ResearchContextBuilder` 只組合這兩個依賴。單元測試以 fake repository/fake retriever 隔離，Mongo 查詢以現有 `write_db` 專用測試資料庫驗證。

**Tech Stack:** Python 3、Pydantic 2.13.4、PyMongo、Numpy、pytest、既有 `stockrag_search`。

**Spec:** `docs/designs/2026-10-09-research-context-sdd.md`

## Global Constraints

- 正式機 `.166` 是權威；不在本機備存副本先行實作。
- 不新增 FastAPI route、HTTP 認證、反向代理、UI、LLM、Dify 或部署設定。
- 不直連正式 MongoDB/Ollama 的 unit test；禁止依賴未安裝的 `mongomock`。
- 核心模組不得 import `streamlit`、`fastapi` 或第三方平台 SDK。
- 所有 Mongo 寫入測試只用 `write_db`，不得使用 `db` fixture。
- 不自行建立 git commit；每個 Task 完成後停在可審核狀態。

---

### Task 1: 請求、回應與白名單模型

**Files:**
- Create: `src/research_context/__init__.py`
- Create: `src/research_context/models.py`
- Create: `tests/test_research_context_models.py`

**Interfaces:**
- Produces: `ResearchContextRequest`, `TeamSummary`, `FactorSummary`, `StockResearchContext`, `RagCitation`, `ResearchContextResponse`。
- Consumes: 無。

**Status:** Complete on 2026-10-09. Red: `ModuleNotFoundError: src.research_context`; green: 9 model-contract tests passed on `.166`.

- [ ] **Step 1: Write failing tests**

```python
import pytest
from pydantic import ValidationError

from src.research_context.models import ResearchContextRequest

def test_request_strips_question_before_length_validation():
    request = ResearchContextRequest(question="  2330 的風險  ")
    assert request.question == "2330 的風險"

@pytest.mark.parametrize("payload", [
    {"question": "  "},
    {"question": "ok", "symbols": ["TSMC"]},
    {"question": "ok", "symbols": ["2330"] * 7},
    {"question": "ok", "max_sources": 9},
    {"question": "ok", "unexpected": True},
])
def test_request_rejects_each_invalid_contract_case(payload):
    with pytest.raises(ValidationError):
        ResearchContextRequest(**payload)
```

- [ ] **Step 2: Run tests and verify red**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_context_models.py -v`

Expected: FAIL because `src.research_context.models` does not exist.

- [ ] **Step 3: Implement minimum production code**

Use Pydantic 2 `ConfigDict(extra="forbid")` and `field_validator("question", mode="before")` to strip input before enforcing length. Apply the symbol regex to the list element type:

```python
Symbol = Annotated[str, Field(pattern=r"^\d{4}$")]
symbols: list[Symbol] = Field(default_factory=list, max_length=6)
```

Define response models with `extra="forbid"`. `TeamSummary` and `FactorSummary` contain only the fields listed in the SDD; `RagCitation.excerpt` has `max_length=500`.

- [ ] **Step 4: Run focused green tests**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_context_models.py -v`

Expected: PASS for stripped question, each independent invalid case, defaults, citation bound, and JSON serialization.

- [ ] **Step 5: Review checkpoint**

Run: `git diff --check -- src/research_context tests/test_research_context_models.py`

Expected: no whitespace errors; do not commit.

### Task 2: MongoDB repository behind an explicit interface

**Files:**
- Create: `src/research_context/repository.py`
- Create: `tests/test_research_context_repository.py`

**Interfaces:**
- Produces: `ResearchRepository` protocol, `MongoResearchRepository`, `get_team_summary(symbol: str) -> TeamSummary | None`, `get_factor_summary(symbol: str) -> FactorSummary | None`。
- Consumes: a PyMongo database and `src.domain.collections` collection constants.

**Status:** Complete on 2026-10-09. Red: `ModuleNotFoundError: src.research_context.repository`; green: 3 repository tests and the 16-test focused regression suite passed on `.166`.

- [ ] **Step 1: Write failing tests**

```python
import pytest

from src.research_context.repository import MongoResearchRepository

@pytest.mark.integration
def test_repository_projects_only_allowlisted_team_fields(write_db):
    write_db.team_analysis.insert_one({
        "symbol": "2330", "date": "2026-10-08", "name": "台積電",
        "final_verdict": "持有", "consensus": {"tally": {"持有": 4}},
        "verify": {"status": "verified"}, "role_reports": {"prompt": "secret"},
    })
    result = MongoResearchRepository(write_db).get_team_summary("2330")
    assert result.model_dump() == {
        "analysis_date": "2026-10-08", "final_verdict": "持有",
        "consensus_tally": {"持有": 4}, "verify_status": "verified",
    }
```

- [ ] **Step 2: Run test and verify red**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_context_repository.py::test_repository_projects_only_allowlisted_team_fields -v`

Expected: FAIL because `MongoResearchRepository` does not exist.

- [ ] **Step 3: Implement minimum production code**

Implement a `Protocol` and Mongo implementation. Query `team_analysis` by symbol with descending analysis date and an explicit projection containing only `date`, `final_verdict`, `consensus.tally`, `verify.status`; query the latest factor record with a projection for `date`, `pe`, `pb`, `roe`, `rsi`, `dividend_yield`. Normalize dates and `Decimal128` values before constructing response models.

- [ ] **Step 4: Run focused green tests**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_context_repository.py -v`

Expected: PASS for latest-record selection, null return for absent team/factor, whitelist projection, date normalization, and Decimal128 conversion.

- [ ] **Step 5: Review checkpoint**

Run: `git diff --check -- src/research_context/repository.py tests/test_research_context_repository.py`

Expected: no whitespace errors; no test touches the production database.

### Task 3: Cached citation retriever

**Files:**
- Create: `src/research_context/retriever.py`
- Create: `tests/test_research_context_retriever.py`

**Interfaces:**
- Produces: `RagRetriever(load_fn, search_fn, clock, ttl_seconds=600)`, `search(question: str, max_sources: int) -> list[RagCitation]`。
- Consumes: existing `scripts.stockrag_search.load` and `scripts.stockrag_search.search` through injection.

**Status:** Complete on 2026-10-09. Red: `ModuleNotFoundError: src.research_context.retriever`; green: 3 retriever tests and the 19-test focused regression suite passed on `.166`.

- [ ] **Step 1: Write failing tests**

```python
from src.research_context.retriever import RagRetriever

def test_retriever_reuses_corpus_until_ttl_expires():
    calls, now = {"load": 0}, {"value": 10.0}
    def load():
        calls["load"] += 1
        return ([{"path": "docs/a.md"}], object())
    retriever = RagRetriever(load, lambda *_args, **_kwargs: [], lambda: now["value"])
    retriever.search("問題", 4)
    retriever.search("另一問題", 4)
    assert calls["load"] == 1
    now["value"] = 611.0
    retriever.search("第三題", 4)
    assert calls["load"] == 2
```

- [ ] **Step 2: Run test and verify red**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_context_retriever.py::test_retriever_reuses_corpus_until_ttl_expires -v`

Expected: FAIL because `RagRetriever` does not exist.

- [ ] **Step 3: Implement minimum production code**

Cache the `(docs, matrix)` pair by monotonic time. Call `search_fn(question, docs, matrix, k=max_sources)` after loading. Convert returned rows to `RagCitation`, truncate excerpt to 500 characters, and construct id as `rag:{path}:{chunk_idx}`. Do not catch or replace load/search exceptions in this layer.

- [ ] **Step 4: Run focused green tests**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_context_retriever.py tests/test_rag_page.py -v`

Expected: PASS for TTL hit/expiry, `k=max_sources`, order preservation, allowlisted citation fields, 500-character excerpt, and exception propagation.

- [ ] **Step 5: Review checkpoint**

Run: `git diff --check -- src/research_context/retriever.py tests/test_research_context_retriever.py`

Expected: no whitespace errors; no regression in existing RAG page tests.

### Task 4: Compose the read-only research context

**Files:**
- Create: `src/research_context/builder.py`
- Create: `tests/test_research_context_builder.py`

**Interfaces:**
- Produces: `ResearchContextBuilder(repository, retriever, now).build(request: ResearchContextRequest) -> ResearchContextResponse`。
- Consumes: `ResearchRepository`, `RagRetriever`, all Task 1 models.

**Status:** Complete on 2026-10-09. Red: `ModuleNotFoundError: src.research_context.builder`; green: 3 builder tests and the 22-test focused regression suite passed on `.166`.

- [ ] **Step 1: Write failing tests**

```python
from src.research_context.builder import ResearchContextBuilder
from src.research_context.models import ResearchContextRequest, TeamSummary

class FakeRepository:
    def get_team_summary(self, symbol):
        return TeamSummary(analysis_date="2026-10-08", final_verdict="持有",
                           consensus_tally={"持有": 4}, verify_status="verified") if symbol == "2330" else None
    def get_factor_summary(self, symbol):
        return None

class FakeRetriever:
    def search(self, question, max_sources):
        return []

def fixed_now():
    return "2026-10-09T15:30:00+08:00"

def test_builder_preserves_symbol_order_and_warns_when_both_sources_are_missing():
    response = ResearchContextBuilder(FakeRepository(), FakeRetriever(), fixed_now).build(
        ResearchContextRequest(question="9999 的結論", symbols=["2330", "9999"])
    )
    assert response.stocks[0].symbol == "2330"
    assert response.stocks[1] is None
    assert response.warnings == ["找不到 9999 的可用資料"]
```

- [ ] **Step 2: Run test and verify red**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_context_builder.py::test_builder_preserves_symbol_order_and_warns_when_both_sources_are_missing -v`

Expected: FAIL because `ResearchContextBuilder` does not exist.

- [ ] **Step 3: Implement minimum production code**

Call retriever once per request. For each symbol in request order, obtain team and factor summaries. Create `StockResearchContext` whenever either exists; append `None` and the exact SDD warning only when both are absent. Set `as_of` from injected `now`; do not access MongoDB or RAG globals directly.

- [ ] **Step 4: Run focused green tests**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_context_builder.py -v`

Expected: PASS for order preservation, complete data, each one-sided missing-data case, both-missing warning, citations, fixed as_of, and retriever exception propagation.

- [ ] **Step 5: Review checkpoint**

Run: `git diff --check -- src/research_context/builder.py tests/test_research_context_builder.py`

Expected: no whitespace errors; builder has no PyMongo, FastAPI, Streamlit or platform imports.

### Task 5: Core regression gate and SDD traceability

**Files:**
- Modify: `docs/designs/2026-10-09-research-context-sdd.md`
- Create: `tests/test_research_context_architecture.py`

**Interfaces:**
- Consumes: implemented core package.
- Produces: enforceable architecture boundaries and final SDD implementation status.

**Status:** Complete on 2026-10-09. Red: missing SDD test-file traceability; green: 2 architecture tests, 26-test focused regression (including repository-failure propagation and retriever source-limit enforcement), and production-wide `251 passed, 13 skipped, 11 deselected` non-slow/non-API suite.

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path

def test_sdd_lists_all_core_test_files():
    source = Path("docs/designs/2026-10-09-research-context-sdd.md").read_text(encoding="utf-8")
    for test_file in (
        "tests/test_research_context_models.py",
        "tests/test_research_context_repository.py",
        "tests/test_research_context_retriever.py",
        "tests/test_research_context_builder.py",
        "tests/test_research_context_architecture.py",
    ):
        assert test_file in source

def test_research_context_core_has_no_platform_imports():
    source = "\n".join(path.read_text(encoding="utf-8") for path in Path("src/research_context").glob("*.py"))
    assert "import streamlit" not in source
    assert "from fastapi" not in source
    assert "dify" not in source.lower()
```

- [ ] **Step 2: Run test and verify red**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_context_architecture.py -v`

Expected: FAIL because the SDD does not yet list the core test files.

- [ ] **Step 3: Implement minimum documentation change**

Update the SDD status to `核心實作完成，尚無 adapter` only after Tasks 1–4 pass. Add an implementation traceability table mapping SDD sections 4–7 to the five test files asserted above; do not add any platform integration.

- [ ] **Step 4: Run full focused regression gate**

Run: `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/test_research_context_models.py tests/test_research_context_repository.py tests/test_research_context_retriever.py tests/test_research_context_builder.py tests/test_research_context_architecture.py tests/test_rag_page.py tests/test_stockrag_answer.py -v`

Expected: all PASS. Then run `/home/mdsadmin/Stock/.venv/bin/python3 -m pytest tests/ -m "not slow" -k "not api" -q` before proposing deployment.

- [ ] **Step 5: Review checkpoint**

Run: `git diff --check -- src/research_context tests/test_research_context_*.py docs/designs/2026-10-09-research-context-sdd.md`

Expected: no whitespace errors; no deployment command is run because there is still no adapter or external surface.

## Self-Review

- SDD coverage: Task 1 covers the logical contract; Task 2 implements the data authority boundary; Task 3 preserves RAG semantics; Task 4 enforces read-only composition and warnings; Task 5 protects platform neutrality and runs the regression gate.
- Test isolation: unit tests use injected fakes and a controlled clock; Mongo integration tests use the existing separate `write_db` fixture; no test requires `mongomock`, live RAG, live Ollama, or the production database.
- Deferral: API, authentication, reverse proxy, UI, LLM, Agent, Dify and deployment are intentionally outside this plan.