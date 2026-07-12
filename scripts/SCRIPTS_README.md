# Scripts Directory - 腳本目錄說明

## 📁 核心驗證腳本 (Core Validation Scripts)

### ✅ 必須保留 (Must Keep)

1. **final_system_validation.py** - 完整系統驗證 (推薦使用)
   - 一次性檢查所有功能
   - 包含: 資料庫、API、前端、ROE計算、資料品質
   - 使用: `python3 scripts/final_system_validation.py`

2. **fix_database_roe.py** - 修正資料庫 ROE 值
   - 重新計算季度報表 ROE（套用年化）
   - 已執行完成，未來新資料下載可再次使用
   - 使用: `python3 scripts/fix_database_roe.py`

3. **batch_download_all_financials.py** - 批次下載財報
   - 從 FinMind API 批次下載所有台股財報
   - 支援斷點續傳
   - 使用: `python3 scripts/batch_download_all_financials.py`

## 🗑️ 可以刪除的腳本 (Safe to Delete)

以下腳本功能已整合至 `final_system_validation.py`，可以安全刪除:

1. ~~validate_system.py~~ - 已被 final_system_validation.py 取代
2. ~~validate_frontend.py~~ - 已整合至 final_system_validation.py
3. ~~system_health_check.py~~ - 功能重複
4. ~~functional_tests.py~~ - 功能重複
5. ~~deep_data_quality_check.py~~ - 功能重複
6. ~~check_data_structure.py~~ - 一次性檢查，已完成
7. ~~check_download_status.py~~ - 可用 MongoDB 直接查詢替代
8. ~~create_test_financial_data.py~~ - 測試用，生產環境不需要
9. ~~test_dupont_industry.py~~ - 測試用，生產環境不需要

## 📝 建議清理命令

```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis/scripts

# 刪除冗余驗證腳本
rm validate_system.py \
   validate_frontend.py \
   system_health_check.py \
   functional_tests.py \
   deep_data_quality_check.py \
   check_data_structure.py \
   check_download_status.py \
   create_test_financial_data.py \
   test_dupont_industry.py

# 僅保留核心腳本:
# - final_system_validation.py
# - fix_database_roe.py
# - batch_download_all_financials.py
```

## 🎯 最佳實踐

**日常驗證**: 使用 `final_system_validation.py` 一次完成所有檢查  
**新增資料**: 使用 `batch_download_all_financials.py` 下載財報  
**ROE 修正**: 使用 `fix_database_roe.py` 重算 ROE（如果發現錯誤）

---

*遵循「一個目的一個檔案」原則，避免腳本氾濫*
