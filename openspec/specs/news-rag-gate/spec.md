# news-rag-gate Specification

## Purpose

新聞與重大訊息檢索（`stockrag.news_docs`）只有在查詢集評估近期通過時，才提供給決策問答使用。
通過與否記錄在 `logs/rag_news_gate.json`，由 `scripts/stockrag_news_eval.py` 寫入、
`dashboard/pages/decision_qa.py` 讀取。決策理由見 `docs/adr/0021-RAG向量檢索維持MongoDB加Numpy.md`（草稿）。

## Requirements

### Requirement: The gate opens only for a recent passing evaluation
系統 SHALL 僅在門檻檔記錄 `passed` 為真，且 `checked_at` 距現在不超過 14 天（不得為未來時間）時，視為開放。

驗證：`tests/test_stockrag_news.py::test_the_gate_opens_only_for_a_recent_passing_result`

#### Scenario: Passing result within 14 days
- **WHEN** 門檻檔記錄通過，且評估在 3 天前
- **THEN** 檢索 SHALL 啟用

#### Scenario: Passing result older than 14 days
- **WHEN** 門檻檔記錄通過，但評估在 30 天前
- **THEN** 檢索 SHALL 關閉，必須重新評估

#### Scenario: Failed result
- **WHEN** 最近一次評估未通過
- **THEN** 檢索 SHALL 關閉，不論多新

### Requirement: Missing or unreadable gate state keeps retrieval closed
門檻檔不存在、無法解析或欄位缺漏時，系統 MUST 視為關閉，不得當成通過（無資料不等於通過）。

驗證：`tests/test_stockrag_news.py::test_a_corrupt_gate_file_keeps_the_gate_closed`、
`tests/test_stockrag_news.py::test_the_gate_opens_only_for_a_recent_passing_result`（無紀錄案例）

#### Scenario: No gate file
- **WHEN** 從未評估過，門檻檔不存在
- **THEN** 檢索 SHALL 關閉

#### Scenario: Corrupt gate file
- **WHEN** 門檻檔內容不是合法 JSON
- **THEN** 檢索 SHALL 關閉

### Requirement: A closed gate is visible to the user
關閉時，決策問答的檢索結果 MUST 為空，並以「新聞檢索未啟用」說明原因與重新開放的方法（先執行 `scripts/stockrag_news_eval.py`）；
該說明 SHALL 寫進回傳的 context（【新聞檢索】段落），且 context 不得含新聞與重大訊息區塊，
不得默默略過新聞來源而讓 context 看起來完整。

驗證：`tests/test_decision_qa_rag.py::test_a_closed_gate_gives_no_news_and_says_so_with_the_way_to_reopen_it`、
`tests/test_decision_qa_rag.py::test_the_context_names_the_closed_gate_instead_of_quoting_news`

#### Scenario: Question asked while the gate is closed
- **WHEN** 使用者提問，且門檻為關閉
- **THEN** 檢索 SHALL 回傳空清單與「新聞檢索未啟用」說明，context SHALL 含該說明且不含新聞區塊

### Requirement: Evaluation passes only when every condition holds
評估 SHALL 在 recall、MRR 皆不低於查詢集設定的門檻、前視洩漏為 0、截止案例全數符合、
且每個截止案例的對照組（不設截止）都找得到目標文件時，才判定通過。
對照組找不到目標文件的案例視為無鑑別力，MUST 令評估失敗。

驗證：`tests/test_stockrag_eval.py::test_gates_report_each_failed_condition_in_words`

#### Scenario: Recall below threshold
- **WHEN** recall@5 低於門檻
- **THEN** 評估 SHALL 判定未通過，並以文字說明低於哪個門檻

#### Scenario: Any look-ahead leak
- **WHEN** 任一查詢在截止日之後或無日期的文件被檢出
- **THEN** 評估 SHALL 判定未通過（洩漏必須為 0）

### Requirement: Thresholds come from the first query file
合併多個查詢集時，k、門檻、決策時點與掃描截止日 SHALL 取自第一個檔案；題目與截止案例則全部串接。
變更門檻或判準語意 MUST 另留 ADR。

驗證：`tests/test_stockrag_news.py::test_merged_query_files_keep_the_first_files_thresholds_and_chain_every_query_and_case`、
`tests/test_stockrag_news.py::test_no_default_query_file_is_stricter_than_the_first_one_that_sets_the_thresholds`

#### Scenario: Adding a new query file
- **WHEN** 新題目檔加入預設查詢集
- **THEN** 門檻 SHALL 維持第一個檔案的值，且後加入的檔案門檻不得高於第一個檔案（否則該門檻形同被忽略）
