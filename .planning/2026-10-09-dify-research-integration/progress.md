# Progress

## 2026-10-09

- 已以正式機為準完成環境取證。
- 已完成 SDD 與 TDD 實作計畫。
- SDD 與 TDD 計畫已同步至 `.166`，並確認兩檔存在且非空。
- 已完成正式機實測的 SDS 需求補充並同步至 `.166`；其中定義 Dify 基礎設施、入口、資料
	白名單與結構化引用的實作前閘門。
- 尚未安裝 Dify、未變更 API、未變更正式服務。
- 使用者決定暫不導入 Dify；已建立平台中立的台股研究上下文 SDD，Dify 專屬計畫標記為暫緩。
- 正式機為 Pydantic 2.13.4、FastAPI 0.139.0，未安裝 mongomock；平台中立 TDD 計畫採 fake
	repository 與既有 write_db fixture，而非新增 mongomock 相依。
- 平台中立 SDD 與研究上下文核心 TDD 計畫已同步至 `.166`；下一步是 Task 1 的模型契約紅燈測試，
	範圍不含任何平台或部署整合。
- Task 1 完成：正式機先因缺少 `src.research_context` 紅燈，新增平台中立 Pydantic 模型後，
	`tests/test_research_context_models.py` 的 9 項測試全數通過。
- Task 2 完成：正式機先因缺少 `src.research_context.repository` 紅燈，新增 allowlist MongoDB
	repository 後 3 項專用測試資料庫測試通過；加上模型及既有 RAG 回歸共 16 項通過。
- Task 3 完成：正式機先因缺少 `src.research_context.retriever` 紅燈，新增注入式 TTL cache 與
	citation 白名單轉換後 3 項 retriever 測試通過；核心及既有 RAG 回歸共 19 項通過。
- Task 4 完成：正式機先因缺少 `src.research_context.builder` 紅燈，新增純組合器後 3 項 builder
	測試通過；核心及既有 RAG 回歸共 22 項通過。
- Task 5 完成：先以 SDD 缺少測試可追溯性紅燈，補上第 4–7 節測試矩陣後 2 項架構測試通過；
	focused regression 共 24 項通過，完整非 slow、非 API suite 為 249 passed、13 skipped、11 deselected。
- 補強：builder 明確驗證 Mongo repository 故障會向上傳遞，不回傳部分資料；目前 focused regression
	共 25 項通過。
- 後續階段：建立 `research-context-adapter-selection-gate.md`，將 SDD 第 9 節轉成平台中立的
	選型證據清單；未選定候選平台，未新增 adapter、API、proxy、祕密或部署。
- 審查補強：RagRetriever 現在即使既有搜尋多回傳結果，也只輸出 `max_sources` 筆 citation；
	focused regression 共 26 項通過，完整非 slow、非 API suite 為 251 passed、13 skipped、11 deselected。
- Task 1 尚未開始：2026-10-09 從本機 `192.168.0.78` 連往 `.166:22` 的 TCP 與 ICMP
	均逾時；需恢復可達 `172.16.9.0/24` 的內網或 VPN 後，才可在權威工作副本進行 TDD。