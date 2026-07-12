# 📋 檔案刪除確認清單

**建立日期：** 2026-02-20  
**執行前必讀：** ⚠️ **刪除前請先完成備份與新模組開發**

---

## 🔴 第一批：高重複度下載腳本（8 個）

### 1. download_all_finmind_data.py
```
路徑：scripts/download_all_finmind_data.py
行數：228 行
功能：下載所有 FinMind 資料（43 個資料表）
重複度：95%（與 complete_data_download_pro.py 重複）

刪除理由：
- 功能完全被 complete_data_download_pro.py 涵蓋
- 程式碼較舊，錯誤處理不完善
- 缺少詳細日誌記錄

整合到：src/downloaders/downloader_coordinator.py

確認刪除：[ ]
```

### 2. download_complete_finmind_v2.py
```
路徑：scripts/download_complete_finmind_v2.py
行數：350 行
功能：下載所有 FinMind 資料（V2 版本）
重複度：95%

刪除理由：
- V2 版本與 V1 功能一致
- complete_data_download_pro.py 是更新的專業版
- 保留多個版本導致維護困難

整合到：src/downloaders/downloader_coordinator.py

確認刪除：[ ]
```

### 3. unified_download.py
```
路徑：scripts/unified_download.py
行數：182 行
功能：「統一」下載腳本（支援 43 個資料表）
重複度：90%

刪除理由：
- 名稱有「統一」字樣，但實際上與其他腳本重複
- 功能被更完整的版本取代
- 未實際達到「統一」目標

整合到：src/downloaders/downloader_coordinator.py

確認刪除：[ ]
```

### 4. batch_download_all_financials.py
```
路徑：scripts/batch_download_all_financials.py
行數：349 行
功能：批次下載所有股票的財報
重複度：90%

刪除理由：
- 功能與 batch_download_financials.py 重複
- 也與 fast_download_financials.py 功能重疊
- 三個財報下載腳本應整合為一個

整合到：src/downloaders/financial_downloader.py

確認刪除：[ ]
```

### 5. batch_download_financials.py
```
路徑：scripts/batch_download_financials.py
行數：211 行
功能：批次下載財報（三大報表）
重複度：85%

刪除理由：
- 與 batch_download_all_financials.py 功能重複
- 邏輯應整合到統一的財報下載器中

整合到：src/downloaders/financial_downloader.py

確認刪除：[ ]
```

### 6. fast_download_financials.py
```
路徑：scripts/fast_download_financials.py
行數：207 行
功能：快速下載財報（僅上市股票，排除上櫃）
重複度：85%

刪除理由：
- 與前兩個腳本功能重複
- 差異僅在過濾邏輯（上市/上櫃）
- 應通過參數控制，而非獨立腳本

整合到：src/downloaders/financial_downloader.py
（新增參數：include_otc=True/False）

確認刪除：[ ]
```

### 7. download_financial_2330.py
```
路徑：scripts/download_financial_2330.py
行數：171 行
功能：下載單一股票 (2330) 的財報
重複度：50%

刪除理由：
- 僅用於測試/開發
- 不應保留在生產環境
- 測試應使用 pytest 而非獨立腳本

移至：tests/test_financial_download.py（重寫為單元測試）

確認刪除：[ ]
```

### 8. download_finmind_complete.py
```
路徑：scripts/download_finmind_complete.py
行數：138 行
功能：完整 FinMind 資料下載
重複度：90%

刪除理由：
- 與其他「完整下載」腳本功能重複
- 較早期版本，功能不如後續版本完整

整合到：src/downloaders/downloader_coordinator.py

確認刪除：[ ]
```

---

## 🟡 第二批：資料庫優化腳本（1 個）

### 9. optimize_collections.py
```
路徑：scripts/optimize_collections.py
行數：418 行
功能：MongoDB Collection 最佳化
重複度：70%（與 safe_optimize_collections.py）

刪除理由：
- safe_optimize_collections.py 有備份機制，更安全
- 兩個腳本功能幾乎一致
- 無備份機制的優化工具風險過高

保留替代：scripts/safe_optimize_collections.py

確認刪除：[ ]
```

---

## 🟢 第三批：一次性遷移腳本（2-3 個）

⚠️ **注意：這批腳本需在執行完畢並驗證後才能刪除**

### 10. migrate_financial_statements_to_reports.py
```
路徑：scripts/migrate_financial_statements_to_reports.py
功能：將舊的 financial_statements 遷移到新的 financial_reports

刪除條件：
- [ ] 遷移已完成
- [ ] 新集合資料完整性驗證通過
- [ ] 舊集合已備份
- [ ] 確認無其他程式碼引用舊集合

執行狀態：
- [ ] 尚未執行
- [ ] 已執行，等待驗證
- [ ] 已驗證完成，可以刪除

確認刪除：[ ]
```

### 11. verify_collection_migration.py
```
路徑：scripts/verify_collection_migration.py
功能：驗證集合遷移完整性

刪除條件：
- [ ] 所有集合遷移已完成
- [ ] 驗證報告已產生並儲存
- [ ] 遷移問題已全部修正

執行狀態：
- [ ] 尚未執行
- [ ] 已執行，發現問題
- [ ] 已驗證完成，可以刪除

確認刪除：[ ]
```

### 12. reorganize_financial_data.py
```
路徑：scripts/reorganize_financial_data.py
功能：重組財報資料結構

刪除條件：
- [ ] 資料重組已完成
- [ ] 新結構已被系統採用
- [ ] 驗證資料完整性

執行狀態：
- [ ] 尚未執行
- [ ] 已執行，等待驗證
- [ ] 已驗證完成，可以刪除

確認刪除：[ ]
```

---

## 🔵 第四批：測試/開發腳本（建議移動而非刪除）

### 13. create_test_financial_data.py
```
路徑：scripts/create_test_financial_data.py
功能：建立測試用財報資料

建議動作：移動而非刪除
- [ ] 移至 tests/fixtures/create_test_data.py
- [ ] 整合到 pytest 測試框架
- [ ] 支援多種測試場景

確認移動：[ ]
```

---

## 📊 刪除統計

### 確定刪除
```
第一批（高重複度）：8 個檔案
第二批（資料庫優化）：1 個檔案
-----------------------------------
立即可刪除：9 個檔案
預估減少程式碼：~2,500 行
```

### 條件刪除
```
第三批（一次性任務）：2-3 個檔案
條件：執行並驗證完成後刪除
```

### 建議移動
```
第四批（測試腳本）：1 個檔案
動作：移至 tests/ 目錄
```

---

## 🚀 執行計畫

### 階段 1：準備工作（執行前）
```bash
# 1. Git 備份
git add -A
git commit -m "重構前備份"
git tag -a v1.0-before-refactor -m "重構前完整備份"

# 2. 資料庫備份
mongodump --db tw_stock_analysis --out backup_$(date +%Y%m%d)

# 3. 建立刪除記錄
cp REFACTOR_DELETE_CHECKLIST.md backup/DELETE_LOG_$(date +%Y%m%d).md
```

### 階段 2：新模組開發（刪除前）
```bash
# 1. 建立新架構
mkdir -p src/downloaders src/calculators src/validators src/database

# 2. 實作核心模組
# - src/downloaders/finmind_client.py
# - src/downloaders/financial_downloader.py
# - src/downloaders/downloader_coordinator.py

# 3. 測試新模組
python -m pytest tests/test_downloaders.py

# 4. 並行運行驗證（舊腳本 vs 新模組）
python scripts/compare_old_new_output.py
```

### 階段 3：刪除執行（新模組驗證後）
```bash
# 第一批：高重複度下載腳本
rm scripts/download_all_finmind_data.py
rm scripts/download_complete_finmind_v2.py
rm scripts/unified_download.py
rm scripts/batch_download_all_financials.py
rm scripts/batch_download_financials.py
rm scripts/fast_download_financials.py
rm scripts/download_financial_2330.py
rm scripts/download_finmind_complete.py

# 第二批：無備份機制的優化腳本
rm scripts/optimize_collections.py

# 提交刪除
git add -A
git commit -m "重構：刪除 9 個重複的下載與優化腳本

- 已整合到 src/downloaders/ 模組化架構
- 功能完整性已驗證
- 詳見 REFACTOR_AUDIT_REPORT.md"

# 建立重構後 Tag
git tag -a v2.0-after-refactor -m "重構完成"
```

### 階段 4：遷移腳本處理
```bash
# 執行遷移（如尚未執行）
python scripts/migrate_financial_statements_to_reports.py

# 驗證遷移
python scripts/verify_collection_migration.py

# 確認無誤後刪除
rm scripts/migrate_financial_statements_to_reports.py
rm scripts/verify_collection_migration.py
rm scripts/reorganize_financial_data.py

git commit -m "清理：刪除已完成的一次性遷移腳本"
```

### 階段 5：整理測試腳本
```bash
# 移動到測試目錄
mkdir -p tests/fixtures
mv scripts/create_test_financial_data.py tests/fixtures/

git commit -m "整理：測試資料生成腳本移至 tests/"
```

---

## ✅ 檔案完整性驗證

### 刪除前檢查清單
```bash
# 1. 確認沒有其他程式碼引用這些腳本
grep -r "download_all_finmind_data" --exclude-dir=node_modules --exclude-dir=.git

# 2. 確認沒有 cron job 或排程任務
crontab -l | grep "download"

# 3. 確認沒有 shell 腳本呼叫
grep -r "python.*download.*\.py" *.sh

# 4. 確認沒有文檔引用
grep -r "download_all_finmind_data" *.md
```

### 刪除後驗證
```bash
# 1. 執行完整系統測試
python src/main.py --validate

# 2. 驗證資料下載功能
python src/main.py --download financial --symbols 2330 --test-mode

# 3. 比對資料一致性
python tests/compare_data_integrity.py

# 4. 檢查無殘留引用
grep -r "download_all_finmind_data\|batch_download_all" src/
```

---

## 🎯 完成標準

### 必須達成
- [x] 所有待刪除檔案已確認
- [ ] 新模組已開發並測試完成
- [ ] 功能完整性驗證通過
- [ ] 資料一致性驗證通過
- [ ] Git 備份已建立
- [ ] 資料庫備份已建立
- [ ] 所有引用已更新
- [ ] 文檔已同步更新

### 建議達成
- [ ] 單元測試覆蓋率 ≥ 80%
- [ ] 效能測試：新系統不慢於舊系統
- [ ] 程式碼審查通過
- [ ] 團隊成員培訓完成

---

## 🆘 回滾方案

### 如果刪除後發現問題
```bash
# 方案 1：從 Git 恢復特定檔案
git checkout v1.0-before-refactor -- scripts/download_all_finmind_data.py

# 方案 2：完全回滾到重構前
git reset --hard v1.0-before-refactor

# 方案 3：從備份目錄恢復
cp backup_20260220/scripts/*.py scripts/
```

### 如果資料庫出現問題
```bash
# 方案 1：從備份恢復特定集合
mongorestore --db tw_stock_analysis --collection financial_reports backup_20260220/

# 方案 2：完全恢復資料庫
mongorestore --db tw_stock_analysis backup_20260220/tw_stock_analysis/
```

---

## 📞 支援與問題回報

### 刪除過程中發現問題
1. **立即停止** 刪除操作
2. **記錄問題** 到 `logs/refactor_issues.log`
3. **評估影響** 範圍（測試環境 vs 生產環境）
4. **執行回滾** （如必要）
5. **更新計畫** 並重新評估

### 聯絡資訊
- **審計人員：** AI Senior Systems Architect
- **確認人員：** Ming (huang.acron@gmail.com)
- **緊急備份：** backup_20260220/

---

## 📝 刪除日誌模板

```markdown
### 刪除記錄

**執行日期：** 2026-02-__
**執行人員：** Ming
**備份位置：** backup_20260220/

#### 已刪除檔案
- [ ] download_all_finmind_data.py
- [ ] download_complete_finmind_v2.py
- [ ] unified_download.py
- [ ] batch_download_all_financials.py
- [ ] batch_download_financials.py
- [ ] fast_download_financials.py
- [ ] download_financial_2330.py
- [ ] download_finmind_complete.py
- [ ] optimize_collections.py

#### 驗證結果
- [ ] 功能測試：通過 / 失敗
- [ ] 效能測試：通過 / 失敗
- [ ] 資料完整性：通過 / 失敗

#### 問題記錄
（如無問題，填寫「無」）

#### 回滾決策
- [ ] 無需回滾，刪除成功
- [ ] 部分回滾：__________________
- [ ] 完全回滾：__________________
```

---

**⚠️ 重要提醒**
> - 刪除是不可逆操作（除非有備份）
> - 必須先開發並測試新模組
> - 刪除前必須完整備份
> - 建議在非工作時間執行
> - 建議先在測試環境執行

---

**📌 待辦事項**
- [ ] 審閱此清單
- [ ] 確認刪除決策
- [ ] 授權執行重構
- [ ] 指定備份負責人
- [ ] 安排執行時間

---

*檔案刪除確認清單 v1.0 | 2026-02-20*
