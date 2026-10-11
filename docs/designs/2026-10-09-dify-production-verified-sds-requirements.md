# Dify 研究助理：正式環境驗證 SDS 需求

**狀態：** 待實作前置條件確認  
**驗證環境：** `172.16.9.166` (`ming-ai02`)  
**驗證日期：** 2026-10-09  
**關聯設計：** `docs/designs/2026-10-09-dify-research-integration-sdd.md`

本文件使用本專案既有的 **SDS**（Software Design Specification）命名。需求以正式機實測為準，
本機工作區不作為部署與容量依據。

## 1. 已驗證現況

| 項目 | 正式機結果 | 設計影響 |
|---|---|---|
| Git revision | `daba5ab` | 所有實作與驗收均以此正式工作副本為起點 |
| MongoDB | active；僅 `127.0.0.1:27017` | Dify 不可直連資料庫 |
| FastAPI | active；僅 `127.0.0.1:8888` | Dify 必須透過新增的受限入口呼叫整合端點 |
| Streamlit dashboard | active；`0.0.0.0:8501` | 不得把 Dify 或 API 流量掛入 dashboard |
| Nginx / 容器 runtime | 未部署 | `.166` 不能直接部署 Dify；proxy 是獨立受控變更 |
| 可用記憶體 / 磁碟 | 約 7.0 GiB / 135 GiB | 不得以 `.166` 容量承載 Dify 的 PostgreSQL、Redis 與檔案卷 |
| API health | `status=ok`；股價最新日 `2026-10-08` | Dify 回答必須暴露資料日期，不能假設即時 |

## 2. 必要需求

### SDS-DIFY-01：獨立 Dify 執行面

Dify 必須部署在獨立的內網 VM 或受管容器平台，不得安裝於 `.166`。在任何程式實作前，
平台負責人必須提供固定私網 IP、DNS 名稱、TLS 憑證簽發鏈、備份位置與還原責任人。

**驗收：** Dify 主機故障、重啟或升級不會改變 `.166` 的 MongoDB、FastAPI、Streamlit 或排程服務狀態。

### SDS-DIFY-02：唯一且唯讀的整合邊界

`.166` 只新增 `POST /api/integrations/dify/research-context`。此端點只能讀取
`team_analysis`、`stock_factors` 與權威 RAG 搜尋結果，不得接受寫入參數、執行 shell、呼叫
交易、觸發排程或直通既有 `/api/*` 端點。

**驗收：** 路由測試證明僅接受已定義的 JSON 欄位；所有未授權方法與非整合路徑均被拒絕。

### SDS-DIFY-03：網路與傳輸安全

對 Dify 的入口必須是 `.166` 私有介面上的 TLS reverse proxy，代理目標固定為
`127.0.0.1:8888`。入口只允許已登錄的 Dify 固定私網 IP，僅允許
`/api/integrations/dify/` 前綴；其餘路徑回傳 404。不得把 Uvicorn 改為監聽 `0.0.0.0`。

**驗收：** allowlist 外來源被拒絕；proxy 設定測試確認 localhost upstream、TLS、1 MiB
request body 限制與路徑拒絕規則；既有 `:8888` 仍只在 loopback 監聽。

### SDS-DIFY-04：服務對服務身分驗證與限流

每一個整合請求都必須攜帶 `X-Dify-Integration-Key`。FastAPI 以
`hmac.compare_digest` 比對 `.166/.env` 的 `DIFY_INTEGRATION_API_KEY`；缺失或錯誤一律回傳
401 `{"detail":"unauthorized"}`，不得揭露金鑰狀態。每把金鑰限制 30 requests/minute；
超額回傳 429。

**驗收：** 正確、缺失、錯誤金鑰及第 31 次請求都有獨立自動化測試；真實金鑰不出現在 Git、
測試 fixture、log、Dify workflow 匯出檔或畫面截圖。

### SDS-DIFY-05：輸入與資料最小化

請求的 `question` 必須先 `strip()`，再驗證長度 2–500。`symbols` 最多 6 個，且每個元素都必須
符合 `^\d{4}$`；`max_sources` 限制為 1–8，未知欄位回傳 422。

回應只能含定義的 `TeamSummary`、`FactorSummary`、`RagCitation` 與 warning 欄位。
`TeamSummary` 僅允許 `symbol`、`name`、`analysis_date`、`final_verdict`、`consensus_tally`、
`verify_status`；`FactorSummary` 僅允許 `date`、`pe`、`pb`、`roe`、`rsi`、`dividend_yield`。
不得回傳 `_id`、角色報告、prompt、環境變數、堆疊追蹤或任意 MongoDB 原始文件。

**驗收：** 每條輸入規則各有獨立紅燈/綠燈測試；含巢狀 `_id`、`prompt`、`role_reports` 的 Mongo
樣本經端點後均不存在於 JSON 回應。

### SDS-DIFY-06：權威檢索與引用完整性

Dify 不使用 Knowledge Base，不持有第二份文件向量。整合端點重用現有 `stockrag_search` 的
向量、繁中文字元 bigram、RRF 與時間衰減排序。每個 citation 必須含穩定 `id`、文件 path、
chunk index、文件日期、age、score 與最多 500 字 excerpt。

Dify workflow 必須以結構化輸出傳回 `answer` 與 `citation_ids`。`citation_ids` 必須是本次
整合端點回傳 citations 的子集合；無資料或端點 503 時，workflow 不得產生任何 citation id。

**驗收：** E2E 測試以固定 context response 驗證每個 citation id 均可在該 response 找到，
而非只搜尋回答字串是否包含 `rag:`。

### SDS-DIFY-07：資料新鮮度與可觀測性

研究 context 回應必須帶 `as_of` 和每個資料來源日期；模型提示詞必須將資料不足及過期資料
表達為限制，而非當作即時事實。API log 僅記錄 request id、狀態碼、耗時、citation 數與錯誤類別，
不得記錄問題全文、金鑰或原始 context。

RAG cache TTL 固定為 600 秒；weekly ingest 後最多 10 分鐘必須反映新語料。若需立即生效，
僅可由 `.166` localhost 管理操作清除快取，該操作不得由 Dify 呼叫。

**驗收：** 快取 TTL、503 fail-closed 回應、過期資料 warning 與 log 遮罩皆有自動化測試。

## 3. 實作前閘門

下列項目未完成前，不得執行 Dify、Nginx 或 API 的部署：

1. 已指定 Dify 主機與固定私網 IP。
2. 已核發並驗證私有 TLS 憑證鏈。
3. 已建立 Dify 資料庫、Redis 與檔案卷的備份及還原演練紀錄。
4. 已補齊 `mongomock_db`、`fake_retriever`、`api_client` 測試 fixture，且不連正式 MongoDB。
5. 已把 [Dify TDD 計畫](../superpowers/plans/2026-10-09-dify-research-integration.md) 修訂為符合
   SDS-DIFY-04 至 SDS-DIFY-07 的獨立測試。

## 4. 非部署結論

目前正式機只有設計與規劃文件變更，尚無 Dify 主機、入口 proxy、API 實作或組態祕密；
**此階段不得執行 `deploy.ps1` 或 `scripts/deploy.sh`。**