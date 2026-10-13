# Tasks

## 1. 量測並修正 402

- [ ] 1.1 以 FinMind 用戶資訊端點每 5 分鐘取樣連續 3 小時（含一個整點與其後 10 分鐘），驗證額度窗口是滾動 60 分鐘（日誌時間線已指向這個結論）還是固定整點；驗證：取樣表附在 design.md，Open Questions 已結案。
- [x] 1.2 新增 `scripts/check_finmind_quota.py` 與測試（2026-10-13 完成）：掃最近每小時下載日誌，有 `HTTP 錯誤: 402`、輪次不足、日誌不存在或最新一輪太舊就以非零狀態結束；驗證：`tests/test_finmind_quota_check.py` 8 個測試，五處實作被破壞時皆失敗；以真實日誌執行，72 輪看到 4 輪、共 212 次 402。已排程每日 10:20（最近 24 輪，`--alert`）。
- [ ] 1.3 把 `sync_dividend_detail.py` 的排程參數改為 `--limit 250`；2026-10-13 已套用（live crontab 與 `deploy/crontab.txt`，漂移檢查 OK，67 條）。尚缺驗證：連續 7 天 `check_finmind_quota.py` 通過，且 01:05 的 402 消失。
- [ ] 1.4 量測每小時重抓的價值：已於 2026-10-13 排入每小時 :50 的快照（`scripts/measure_hourly_refetch.py snapshot`，暫時排程），24 小時後執行 `report`；驗證：產出「24 小時內內容有變動的文件數」表附在 design.md，並據此在方案 B 與維持現狀之間下結論，之後移除暫時排程。
- [x] 1.5 FinMind 客戶端遇 402 不重試，同一程序連續 2 次 402 後略過剩餘請求（2026-10-13 完成）；驗證：`tests/test_finmind_client_quota.py` 5 個測試，三處實作被破壞時皆失敗，`tests/test_downloaders.py` 仍通過，全量回歸 822 passed。

## 2. 可觀測性

- [ ] 2.1 每小時下載在開始與結束時查詢並記錄伺服器端用量（「伺服器端用量 N/上限」），查詢失敗記「無資料」；驗證：以假的用量回應與失敗回應寫測試，確認失敗時不會出現 0%，並在真實日誌看到一行實際數字。

## 3. 決策紀錄

- [ ] 3.1 新增 `docs/adr/0022-不訂閱FinMind付費方案.md`：決策、理由與重新評估條件（D2 之後每週仍有 402，或出現已寫成可執行檢查的整市場核對、分點需求）；驗證：ADR 連回本變更的 design.md。

## Workflow follow-up

- 若重新評估條件成立，另開變更處理 Backer 一個月試用：先核對官方價格與授權條款，再訂閱，完成整市場交叉核對與缺口補寫並輸出報告，期滿不續訂。
- 全部任務完成後執行 `/opsx-archive`，把 `finmind-quota-budget` 併入 `openspec/specs/`。
