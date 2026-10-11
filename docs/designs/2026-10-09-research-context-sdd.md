# 台股研究上下文 SDD

**狀態：** 核心實作完成，尚無 adapter  
**日期：** 2026-10-09  
**權威環境：** `172.16.9.166`

## 1. 問題與目標

系統已有三種權威研究資料：

- `team_analysis`：合議定案及復驗狀態。
- `stock_factors`：個股最新因子。
- `stockrag.docs`：專案文件切塊；現行排序是向量 cosine、繁中文字元 bigram、RRF 與時間衰減。

這些資料目前分散於 dashboard 與內部 Python 程式。需要一個**唯讀研究上下文能力**，讓未來的
UI、聊天介面或工作流可取得一致、可引用、可辨識資料日期的研究證據。

本 SDD 的目標是定義資料與行為契約；它不選定 UI、LLM、Agent、工作流或第三方平台。

## 2. 範圍

### In scope

- 依問題檢索權威 RAG 段落。
- 依股票代號取得最新合議定案與有限的因子摘要。
- 回傳資料日期、警告與穩定 citation id。
- 保留既有 RAG 排序語意。

### Out of scope

- LLM 生成答案、聊天介面、知識庫產品與第三方平台整合。
- 寫入任何 MongoDB 集合、交易、排程或合議定案。
- 改換 Milvus 或其他向量資料庫。
- 公開網際網路入口與身分治理實作。

## 3. 設計原則

1. **資料權威性：** MongoDB 與既有 `stockrag_search` 是唯一資料與排序來源；不得建立第二份語料。
2. **唯讀：** 研究上下文能力不寫資料、不執行副作用。
3. **資料最小化：** 只輸出明確白名單欄位，禁止原始 MongoDB 文件穿透。
4. **可追溯：** 每一個檢索段落有可重建的 path、chunk index、文件日期與分數。
5. **誠實缺資料：** 找不到資料以 warnings 表達，不能以推測補足。
6. **平台可替換：** 呼叫端可為 dashboard、CLI 或未來平台，但不改變此能力的資料契約。

## 4. 邏輯資料契約

### 請求模型

```json
{
  "question": "2330 目前的研究結論與主要風險？",
  "symbols": ["2330"],
  "max_sources": 4
}
```

| 欄位 | 規則 |
|---|---|
| `question` | `strip()` 後長度 2–500 |
| `symbols` | 0–6 個元素；每個元素符合 `^\d{4}$` |
| `max_sources` | 整數 1–8，預設 4 |
| 未定義欄位 | 拒絕 |

### 回應模型

```json
{
  "as_of": "2026-10-09T15:30:00+08:00",
  "question": "2330 目前的研究結論與主要風險？",
  "stocks": [{
    "symbol": "2330",
    "team": {
      "analysis_date": "2026-10-08",
      "final_verdict": "持有",
      "consensus_tally": {"買進": 1, "持有": 4, "賣出": 1},
      "verify_status": "verified"
    },
    "factors": {"date": "2026-10-08", "pe": 20.1, "pb": 4.8, "roe": 28.0, "rsi": 52.0, "dividend_yield": 1.4}
  }],
  "citations": [{
    "id": "rag:docs/example.md:0",
    "title": "文件標題",
    "path": "docs/example.md",
    "chunk_idx": 0,
    "document_date": "2026-10-09",
    "age_days": 0,
    "score": 0.021,
    "excerpt": "最多 500 字的原文節錄"
  }],
  "warnings": []
}
```

`team` 只允許 `analysis_date`、`final_verdict`、`consensus_tally`、`verify_status`；`factors` 只允許
`date`、`pe`、`pb`、`roe`、`rsi`、`dividend_yield`。回應不得含 `_id`、角色報告、prompt、
環境變數、stack trace 或未經白名單核准的欄位。

## 5. 元件邊界

| 元件 | 責任 |
|---|---|
| `ResearchContextRequest` | 請求規則與標準化 |
| `RagRetriever` | 快取既有語料並呼叫既有 RAG 排序；只轉出引用白名單 |
| `ResearchRepository` | 以受限查詢讀取合議定案與因子摘要；隔離 MongoDB 細節 |
| `ResearchContextBuilder` | 透過 repository 與 retriever 組合股票摘要、產生 warnings 與回應模型 |
| 呼叫端 adapter | 將已驗證的請求交給 builder；平台、認證與網路傳輸在此層決定 |

核心元件不得依賴特定 UI、特定模型 SDK 或第三方平台 SDK。

## 6. 行為需求

- 對不存在的股票代號，維持輸入順序輸出 `null`，並加入 `找不到 <symbol> 的可用資料` warning。
- citation 數量不得超過 `max_sources`；excerpt 最多 500 字。
- RAG 載入可快取 600 秒；快取失效時才重新載入。
- RAG 或 MongoDB 不可用時，呼叫端 adapter 必須回報「研究上下文暫時不可用」，不得回傳部分未標示資料。
- 回應的 `as_of`、factor date、analysis date 與 document date 必須保留，讓呼叫端能顯示資料新鮮度。

## 7. TDD 驗收需求

實作前必須建立獨立、離線的測試 fixture：fake repository、fake RAG retriever 與可控制時鐘；
不得連正式 MongoDB 或 Ollama。對 MongoDB 查詢的整合測試只可使用既有 `write_db` fixture 的
`MONGODB_TEST_DATABASE`，不得依賴目前正式機未安裝的 `mongomock`。

下列測試均須遵循紅燈、最小實作、綠燈：

1. 空白問題、過長問題、非法代號、超過六個代號、非法 `max_sources` 與未知欄位各自被拒絕。
2. 有效請求經標準化後保留問題、代號與 `max_sources`。
3. citation 的欄位、數量、500 字 excerpt 與排序完全對應既有 RAG 結果。
4. MongoDB 樣本含 `_id`、`prompt`、`role_reports` 時，輸出仍只含白名單欄位。
5. 缺少股票、缺少 factor、缺少 team analysis 都產生明確 warning，不拋出未處理例外。
6. cache 在 600 秒內不重載，逾時重載；RAG/MongoDB 故障不回傳未標示的部分內容。
7. 既有 `tests/test_rag_page.py` 與 `tests/test_stockrag_answer.py` 保持通過。

## 8. 實作可追溯性

| SDD 章節 | 驗證測試 |
|---|---|
| 4. 邏輯資料契約 | `tests/test_research_context_models.py` |
| 4. 回應模型與 5. 元件邊界 | `tests/test_research_context_repository.py` |
| 4. citation 與 6. RAG 行為 | `tests/test_research_context_retriever.py` |
| 5. 元件邊界與 6. 缺資料行為 | `tests/test_research_context_builder.py` |
| 2. 範圍與 3. 平台可替換原則 | `tests/test_research_context_architecture.py` |
| 6. 既有 RAG 相容性 | `tests/test_rag_page.py`、`tests/test_stockrag_answer.py` |

核心測試均以 injected fakes 或 `write_db` 隔離；目前沒有 adapter、API、UI、LLM 或第三方平台整合。

## 9. 後續選型閘門

本 SDD 驗收通過後，才可評估任何 UI、LLM 編排、Agent 或工作流產品。選型文件必須證明：

- 不改變本文件的資料契約與引用規則。
- 不直連 MongoDB、Ollama 或主機檔案系統。
- 不新增未經測試的寫入或副作用。
- 有完整的網路、身分、祕密、備份與故障復原設計。
