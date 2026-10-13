## Purpose

FinMind 免費帳號每小時只有 600 次請求，專案的每小時下載、每日股利同步、每日交叉核對與持倉補價共用同一個 token。本能力規範這些例行作業如何維持在額度內，並讓額度用盡看得見，而不是靜默失敗或白白重試。

## ADDED Requirements

### Requirement: Routine FinMind jobs stay within the hourly quota
同一個小時內，所有共用同一個 FinMind token 的例行作業，其請求總數 SHALL 低於帳號的每小時上限，使每小時下載不會收到 HTTP 402。

驗證：`tests/test_finmind_quota_check.py::test_a_quiet_stretch_passes`、
`tests/test_finmind_quota_check.py::test_a_run_with_402_fails_and_names_the_run_and_the_count`、
`tests/test_finmind_quota_check.py::test_a_402_older_than_the_window_is_not_counted`；
排程檢查為 `scripts/check_finmind_quota.py`（每日 10:20 看最近 24 輪）。

#### Scenario: A quiet stretch of hourly runs
- **WHEN** 檢查的最近 N 輪（手動預設 72、排程用 24）每小時下載日誌都沒有 HTTP 402
- **THEN** 檢查 SHALL 通過

#### Scenario: A daily job takes the whole quota just before the hourly download
- **WHEN** 每日股利同步在整點用掉大部分額度，緊接著每小時下載啟動
- **THEN** 該輪日誌 SHALL 出現 HTTP 402，檢查 SHALL 未通過並列出發生的輪次與次數（2026-10-13 01:05 出現 51 次即是此情況）

### Requirement: Missing hourly logs are no data, not a pass
檢查在找不到每小時下載日誌、最新一輪日誌已超過 3 小時，或輪次不足預期數量時，SHALL 回報「無資料」或「輪次不足」並以非零狀態結束，不得當成沒有 402 而通過。

驗證：`tests/test_finmind_quota_check.py::test_no_logs_is_no_data_not_a_pass`、
`tests/test_finmind_quota_check.py::test_logs_that_stopped_arriving_are_no_data_even_if_clean`、
`tests/test_finmind_quota_check.py::test_too_few_runs_to_judge_is_reported_instead_of_passing`。

#### Scenario: No logs at all
- **WHEN** 日誌目錄沒有任何每小時下載日誌
- **THEN** 檢查 SHALL 回報「無資料」且未通過

#### Scenario: The hourly job stopped
- **WHEN** 日誌雖然都沒有 402，但最新一輪已是一天前
- **THEN** 檢查 SHALL 回報「無資料」並說明已超過 3 小時沒有新日誌

#### Scenario: Too few runs to judge
- **WHEN** 日誌只有 10 輪，而預期要看 72 輪
- **THEN** 檢查 SHALL 回報實際輪數不足，不得以 10 輪的結果宣告通過

### Requirement: A quota error is not retried and stops further requests
FinMind 回 HTTP 402 時，下載客戶端 MUST NOT 重試；同一程序內連續 2 次 402 後，SHALL 略過該程序剩下的請求；中間只要成功一次就清掉連續計數。其他伺服器錯誤仍照原本的退避重試。

驗證：`tests/test_finmind_client_quota.py`（5 個測試，涵蓋單次 402 不重試、連續兩次後不再送出、成功後清除連續計數、其他錯誤仍重試）。

#### Scenario: One 402
- **WHEN** 一次請求回 402
- **THEN** 客戶端 SHALL 立刻回傳無資料，不等待、不重試

#### Scenario: Two consecutive 402s
- **WHEN** 連續兩次請求都回 402
- **THEN** 之後同一程序的請求 SHALL 不送出

#### Scenario: A server error other than 402
- **WHEN** 請求回 HTTP 500
- **THEN** 客戶端 SHALL 照原本的 2、4、8 秒退避重試

### Requirement: Each hourly run records the server-side usage
每小時下載 SHALL 在開始與結束時記錄 FinMind 伺服器端回報的已用量與上限；取不到時 SHALL 記為「無資料」，不得記成 0。

驗證：尚無檢查（tasks 2.1）。

#### Scenario: The server reports usage
- **WHEN** 伺服器回報已用 301、上限 600
- **THEN** 日誌 SHALL 含「伺服器端用量 301/600」

#### Scenario: The usage query fails
- **WHEN** 用量查詢逾時或回傳錯誤
- **THEN** 日誌 SHALL 記「伺服器端用量無資料」，且不得出現 0% 或 0/600
