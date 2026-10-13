# mops-major-news-sync Specification

## Purpose

把上市、上櫃、興櫃的重大訊息補進 `major_news`，並以公開資訊觀測站（MOPS）按日期對帳，補上每日快照漏掉的列。
實作於 `src/data_gap/mops_major.py` 與 `scripts/mops_major_sync.py`，每日 23:30 對近 3 天執行。

## Requirements

### Requirement: Only rows missing from the database are fetched and written
對帳 SHALL 比對官方清單與資料庫，只對缺少的列取得明細並寫入；已存在的列不得重寫或重複。

驗證：`tests/test_data_gap_mops_major.py::test_only_rows_absent_from_the_database_are_reported_missing`、
`tests/test_data_gap_mops_major.py::test_reconcile_fetches_details_only_for_missing_rows_and_keeps_failures_out_of_the_result`、
`tests/test_mops_major_sync.py::test_apply_writes_full_documents_logs_the_run_and_a_rerun_finds_nothing_missing`

#### Scenario: Rerun after a full apply
- **WHEN** 套用寫入後立即重跑同一日期
- **THEN** 缺列數 SHALL 為 0

#### Scenario: Dry run
- **WHEN** 以預演模式執行
- **THEN** 系統 SHALL 回報缺列數，且 MUST NOT 呼叫明細端點或寫入資料庫

驗證（預演）：`tests/test_mops_major_sync.py::test_dry_run_counts_what_is_missing_and_writes_nothing`

### Requirement: Two notices with the same subject at different times are both kept
同公司、同日、同主旨但發言時間不同的公告 SHALL 保留為兩筆；比對鍵 MUST 包含發言時間。
發言時間無法判讀時才以主旨文字比對。

驗證：`tests/test_data_gap_mops_major.py::test_save_new_skips_known_rows_and_keeps_two_same_subject_notices_with_different_times`、
`tests/test_data_gap_mops_major.py::test_a_repeat_with_the_same_subject_at_a_different_time_is_not_mistaken_for_the_known_one`

#### Scenario: Repeated notice later the same day
- **WHEN** 同一公司同日同主旨再次刊登，時間不同
- **THEN** 資料庫 SHALL 有兩筆，且對帳不得把後者視為已存在

### Requirement: Time notations are normalised before comparison
時間 SHALL 正規化為 6 位數字；官方 OpenAPI 的 5 位無補零時間 MUST 被視為已持有，不得重複寫入。

驗證：`tests/test_data_gap_mops_major.py::test_clock_times_are_normalised_to_six_digits`、
`tests/test_mops_major_sync.py::test_documents_from_the_twse_openapi_with_a_five_digit_time_count_as_already_held`

#### Scenario: TWSE OpenAPI document with a five-digit time
- **WHEN** 資料庫已有時間為 5 位數的上市公告
- **THEN** 對帳 SHALL 視為已持有

### Requirement: A failed detail is never stored as a complete document
明細取得失敗或為空時，系統 MUST NOT 寫入該列，使它在下次執行時仍被視為缺漏而重試。

驗證：`tests/test_data_gap_mops_major.py::test_a_failed_or_empty_detail_gives_no_document_so_the_row_stays_missing_for_the_next_run`、
`tests/test_mops_major_sync.py::test_a_failing_detail_is_not_written_and_is_retried_by_the_next_run`

#### Scenario: Detail endpoint fails
- **WHEN** 明細請求失敗
- **THEN** 該列 SHALL 不寫入，且下次對帳仍列為缺漏

### Requirement: Securities with no detail are stored once with a marker
存託憑證等明細端點回 406（無對應資料）的列，系統 SHALL 只存主旨並標記 `detail_missing`，避免永遠重試。

驗證：`tests/test_data_gap_mops_major.py::test_a_406_no_match_detail_still_stores_the_listed_row_so_it_is_not_retried_forever`

#### Scenario: DR security notice
- **WHEN** 明細端點對某列回 406
- **THEN** 該列 SHALL 以 `detail_missing` 標記寫入，下次不再列為缺漏

### Requirement: A failed or malformed list is not treated as an empty day
清單請求失敗或格式不符時，系統 MUST 回傳無資料並使該日算失敗，不得把半截內容當成清單，
也不得把「無資料」當成「該日沒有公告」。任一日清單失敗時，腳本 SHALL 以非零狀態結束。

驗證：`tests/test_data_gap_mops_major.py::test_a_failed_or_malformed_response_yields_no_rows_instead_of_partial_garbage`、
`tests/test_mops_major_sync_exit.py::test_a_failed_day_list_makes_the_exit_code_nonzero_but_the_other_days_still_run`、
`tests/test_mops_major_sync_exit.py::test_when_every_day_succeeds_the_exit_code_is_zero`

#### Scenario: Malformed list response
- **WHEN** 清單回應不是預期格式
- **THEN** 該日 SHALL 不產生任何列，且記為清單失敗

#### Scenario: One failed day among several
- **WHEN** 多日對帳中有一天清單失敗
- **THEN** 其餘日期 SHALL 照常執行，腳本最後 SHALL 以非零狀態結束

### Requirement: Each run leaves a reconciliation record
每次套用寫入的對帳 SHALL 在 `mops_reconcile_log` 留下紀錄，內含日期、各市場的官方筆數與已有筆數、缺漏數、補寫數與失敗數。

驗證：`tests/test_mops_major_sync.py::test_apply_writes_full_documents_logs_the_run_and_a_rerun_finds_nothing_missing`

#### Scenario: Apply run
- **WHEN** 以套用模式完成一日對帳
- **THEN** SHALL 新增一筆對帳紀錄
