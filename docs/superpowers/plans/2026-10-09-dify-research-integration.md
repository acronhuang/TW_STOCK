# Dify Research Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** Deferred. Do not execute this plan or provision Dify infrastructure.

**Goal:** 讓獨立部署的 Dify 能安全呼叫正式機的唯讀研究上下文 API，產生帶有可追溯引用的台股研究回答。

**Architecture:** Dify 不持有權威語料、不直連資料庫。`.166` 的 FastAPI 新增受 API key 保護的研究上下文端點，並透過僅允許 Dify IP 的 TLS reverse proxy 對外提供；端點重用現有 RAG 排序與 MongoDB 資料。

**Tech Stack:** Python 3、FastAPI、Pydantic、PyMongo、Numpy、pytest、Dify Chatflow、Nginx TLS reverse proxy。

**Spec:** `docs/designs/2026-10-09-dify-research-integration-sdd.md`

> Superseded for current work by `docs/designs/2026-10-09-research-context-sdd.md`.

## Global Constraints

- 正式機 `.166` 是權威；本機僅用於測試與備存。
- Dify 不直連 MongoDB/Ollama，且只可讀取研究上下文端點。
- 不導入 Milvus、不啟用 Dify Knowledge Base、不新增雙寫語料。
- `DIFY_INTEGRATION_API_KEY` 是祕密，不得進版控、測試輸出、log 或 Dify workflow 定義。
- 每一段 production code 都必須先有一個失敗且原因正確的 pytest。
- 每項任務結束前執行其指定測試，再執行既有 RAG/API 迴歸測試。

---

### Task 1: 鎖定研究上下文資料契約

**Files:**
- Create: `src/api/dify_models.py`
- Create: `tests/test_dify_models.py`

**Interfaces:**
- Produces: `ResearchContextRequest`, `ResearchContextResponse`, `RagCitation`, `StockResearchContext`。
- Consumes: 無。

- [ ] **Step 1: Write the failing test**

```python
from pydantic import ValidationError
import pytest

from src.api.dify_models import ResearchContextRequest

def test_research_request_rejects_non_four_digit_symbol_and_unknown_field():
    with pytest.raises(ValidationError):
        ResearchContextRequest(question="2330 的風險", symbols=["TSMC"], unknown=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dify_models.py::test_research_request_rejects_non_four_digit_symbol_and_unknown_field -v`

Expected: FAIL because `src.api.dify_models` does not exist.

- [ ] **Step 3: Write the minimal implementation**

```python
from pydantic import BaseModel, ConfigDict, Field

class ResearchContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=2, max_length=500)
    symbols: list[str] = Field(default_factory=list, max_length=6, pattern=r"^\d{4}$")
    max_sources: int = Field(default=4, ge=1, le=8)
```

Add response models exactly as specified in the SDD, with `id`, `title`, `path`, `chunk_idx`, `document_date`, `age_days`, `score`, and `excerpt` on `RagCitation`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dify_models.py -v`

Expected: PASS for valid bounds, invalid symbols, unknown fields, and response serialisation.

- [ ] **Step 5: Commit**

```bash
git add src/api/dify_models.py tests/test_dify_models.py
git commit -m "feat: define Dify research context contract"
```

### Task 2: 建立可測試的 RAG 快取與引用轉換

**Files:**
- Create: `src/api/rag_cache.py`
- Create: `tests/test_rag_cache.py`

**Interfaces:**
- Consumes: `scripts.stockrag_search.load`, `scripts.stockrag_search.search`。
- Produces: `RagRetriever.search(question: str, max_sources: int) -> list[RagCitation]`。

- [ ] **Step 1: Write the failing test**

```python
from src.api.rag_cache import RagRetriever

def test_retriever_uses_cached_corpus_and_preserves_citation_metadata(monkeypatch):
    load_calls = 0
    def fake_load():
        nonlocal load_calls
        load_calls += 1
        return ([{"path": "docs/a.md"}], object())
    retriever = RagRetriever(load_fn=fake_load, search_fn=lambda *_args, **_kwargs: [])
    retriever.search("測試問題", 4)
    retriever.search("另一問題", 4)
    assert load_calls == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_rag_cache.py::test_retriever_uses_cached_corpus_and_preserves_citation_metadata -v`

Expected: FAIL because `RagRetriever` does not exist.

- [ ] **Step 3: Write the minimal implementation**

Implement `RagRetriever` with injected `load_fn`, `search_fn`, a monotonic-clock TTL of 600 seconds, and an internal `(docs, matrix)` cache. Convert only the SDD allowlisted fields to `RagCitation`; truncate `excerpt` to 500 characters.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_rag_cache.py tests/test_rag_page.py -v`

Expected: PASS; include tests for TTL reload, `k=max_sources`, and citation field cleaning.

- [ ] **Step 5: Commit**

```bash
git add src/api/rag_cache.py tests/test_rag_cache.py
git commit -m "feat: add cached RAG retriever for integrations"
```

### Task 3: 組合唯讀研究上下文

**Files:**
- Create: `src/api/research_context.py`
- Create: `tests/test_research_context.py`

**Interfaces:**
- Consumes: `RagRetriever`, PyMongo database, `ResearchContextRequest`。
- Produces: `ResearchContextBuilder.build(request: ResearchContextRequest) -> ResearchContextResponse`。

- [ ] **Step 1: Write the failing test**

```python
from src.api.dify_models import ResearchContextRequest
from src.api.research_context import ResearchContextBuilder

def test_builder_returns_warning_for_missing_symbol_and_never_exposes_mongo_id(mongomock_db, fake_retriever):
    response = ResearchContextBuilder(mongomock_db, fake_retriever).build(
        ResearchContextRequest(question="9999 的結論", symbols=["9999"])
    )
    assert response.stocks[0] is None
    assert response.warnings == ["找不到 9999 的可用資料"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_research_context.py::test_builder_returns_warning_for_missing_symbol_and_never_exposes_mongo_id -v`

Expected: FAIL because `ResearchContextBuilder` does not exist.

- [ ] **Step 3: Write the minimal implementation**

Query only the latest `team_analysis` and latest non-null `stock_factors` values needed for the SDD response. Remove `_id`, convert `Decimal128` and datetime values, append the exact missing-data warning, and delegate citations to `RagRetriever`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_research_context.py -v`

Expected: PASS for complete data, missing data, citation propagation, and absence of `_id` or unapproved internal fields.

- [ ] **Step 5: Commit**

```bash
git add src/api/research_context.py tests/test_research_context.py
git commit -m "feat: build read-only Dify research context"
```

### Task 4: 加入金鑰驗證、限流與 FastAPI 端點

**Files:**
- Create: `src/api/dify_auth.py`
- Modify: `src/api/server.py`
- Create: `tests/test_dify_endpoint.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `DIFY_INTEGRATION_API_KEY`, `ResearchContextBuilder`。
- Produces: `POST /api/integrations/dify/research-context`。

- [ ] **Step 1: Write the failing test**

```python
def test_context_endpoint_rejects_missing_key(api_client):
    response = api_client.post("/api/integrations/dify/research-context", json={"question": "2330 的風險"})
    assert response.status_code == 401
    assert response.json() == {"detail": "unauthorized"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dify_endpoint.py::test_context_endpoint_rejects_missing_key -v`

Expected: FAIL because the route does not exist.

- [ ] **Step 3: Write the minimal implementation**

Use a FastAPI dependency that reads `X-Dify-Integration-Key` and compares it with `os.environ["DIFY_INTEGRATION_API_KEY"]` using `hmac.compare_digest`. Add an in-memory per-key rolling 60-second counter that returns 429 after request 30. Register only the specified POST route and map backend exceptions to the specified 503 detail. Add only this empty secret entry to `.env.example`:

```dotenv
# Dify read-only research-context API key; never commit its real value.
DIFY_INTEGRATION_API_KEY=
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dify_endpoint.py tests/test_api.py -v`

Expected: PASS for absent/wrong/correct key, 422 validation, 429 request 31, 503 backend fault, and no regression of `/api/health`.

- [ ] **Step 5: Commit**

```bash
git add src/api/dify_auth.py src/api/server.py tests/test_dify_endpoint.py .env.example
git commit -m "feat: expose protected Dify research context API"
```

### Task 5: 部署受限 TLS proxy 與 Dify 平台

**Files:**
- Create: `deploy/nginx/twstock-dify.conf`
- Create: `deploy/dify/README.md`
- Create: `deploy/dify/workflow-research-assistant.md`
- Create: `tests/test_dify_proxy_config.py`

**Interfaces:**
- Consumes: `DIFY_HOST_IP`, private TLS certificate paths, integration API key secret reference.
- Produces: restricted HTTPS route to the endpoint and importable Dify Chatflow configuration instructions.

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

def test_dify_proxy_only_proxies_the_integration_prefix():
    config = Path("deploy/nginx/twstock-dify.conf").read_text(encoding="utf-8")
    assert "location /api/integrations/dify/" in config
    assert "proxy_pass http://127.0.0.1:8888" in config
    assert "location /" in config and "return 404" in config
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dify_proxy_config.py::test_dify_proxy_only_proxies_the_integration_prefix -v`

Expected: FAIL because the proxy configuration does not exist.

- [ ] **Step 3: Write the minimal implementation**

Create a config template that listens on private `:9443`, restricts with `allow ${DIFY_HOST_IP}; deny all;`, sets a 1 MiB request limit, forwards only the integration prefix to localhost, and sets `proxy_set_header X-Dify-Integration-Key $http_x_dify_integration_key`. Document Dify's HTTP Request node with POST, 15-second timeout, CA verification, secret header, and the exact workflow nodes in the SDD. Provision Dify on an isolated host with vendor-supported pinned images, persistent PostgreSQL/Redis volumes, encrypted backup, and no Knowledge Base source.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dify_proxy_config.py -v`

Expected: PASS for path restriction, localhost proxy target, allowlist, TLS directives, and request-size limit.

- [ ] **Step 5: Commit**

```bash
git add deploy/nginx/twstock-dify.conf deploy/dify tests/test_dify_proxy_config.py
git commit -m "ops: document and restrict Dify integration ingress"
```

### Task 6: 驗收與上線

**Files:**
- Modify: `docs/designs/2026-10-09-dify-research-integration-sdd.md`
- Create: `tests/e2e/test_dify_research_workflow.py`

**Interfaces:**
- Consumes: deployed Dify Workflow and protected integration endpoint.
- Produces: repeatable acceptance evidence.

- [ ] **Step 1: Write the failing test**

```python
def test_dify_workflow_surfaces_citation_id_for_research_claim(dify_client):
    answer = dify_client.chat("2330 目前的研究結論與主要風險？")
    assert "rag:" in answer
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DIFY_E2E_URL=https://<dify-private-host> DIFY_E2E_TOKEN=<secret> python -m pytest tests/e2e/test_dify_research_workflow.py -v`

Expected: FAIL before the Workflow is configured.

- [ ] **Step 3: Write the minimal implementation**

Configure the six SDD Workflow nodes, publish only to the approved Dify workspace, and add the test client that calls Dify's documented chat API using `DIFY_E2E_TOKEN` from the environment.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dify_models.py tests/test_rag_cache.py tests/test_research_context.py tests/test_dify_endpoint.py tests/test_dify_proxy_config.py tests/test_rag_page.py tests/test_stockrag_answer.py -v`

Then run the protected-environment command from Step 2.

Expected: all unit and integration tests PASS; normal question returns citations, missing-data question states insufficiency, and forced 503 is shown without fabricated content.

- [ ] **Step 5: Commit**

```bash
git add docs/designs/2026-10-09-dify-research-integration-sdd.md tests/e2e/test_dify_research_workflow.py
git commit -m "test: verify Dify research workflow evidence contract"
```

## Self-Review

- Spec coverage: Tasks 1-4 implement the contract, read-only data boundary, authentication, rate limit and RAG semantics; Task 5 implements isolated Dify/proxy operations; Task 6 verifies all acceptance paths.
- Placeholder scan: no implementation task delegates unspecified behavior; each task defines concrete files, interfaces, test command, expected failure and expected passing behavior.
- Type consistency: `ResearchContextRequest` flows from endpoint to `ResearchContextBuilder`; `RagRetriever` produces `RagCitation`; `ResearchContextResponse` is the sole endpoint response type.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-10-09-dify-research-integration.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task and review between tasks.
2. **Inline Execution** - execute tasks in this session with checkpoints.
