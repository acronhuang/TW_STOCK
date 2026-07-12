# 規劃 · 檔案盤點與 BACKUP 清單

> 全專案檔案使用情況稽核。標記「未被引用、可搬移到 `BACKUP/`」的檔案。
> **本文件只做標記與建議，不刪除任何檔案**；搬移為可逆操作，執行前請核准。
> 每支檔案「做什麼 + 依賴/被誰用」的逐檔明細見 [檔案功能與關聯總目錄](規劃-檔案功能與關聯總目錄.md)。

> 🕒 **決策（2026-07-12）**：先保留全部檔案、**觀察約一個月確認不影響功能後再搬**（預計 2026-08 中旬後執行）。
> 觀察期間若某支「建議搬移」的腳本其實被手動/臨時流程用到，即從清單移除；到期無異狀再依第三節搬入 `BACKUP/`。

---

## 摘要

| 範圍 | 保留 | 建議搬 BACKUP | 說明 |
|---|--:|--:|---|
| 腳本 `scripts/*.py`、`*.sh` | 61 | 127 | 依 cron/systemd/檔名引用追蹤 |
| 根目錄鬆散檔（報告/plist/bak）| 27 | 139 | 一次性過程產物為主 |
| 大型目錄（Node 腳手架）| — | ~257.1MB | 執行期為 Python/Streamlit，未用 Node |

**可回收**：腳本 127 檔 + 根檔 139 檔 + Node 腳手架約 257.1MB（含 `node_modules` 256.1MB）。

## 判定方法（如何認定「未使用」）

一個腳本視為**使用中**，若滿足任一：
1. 出現在 **crontab**（20 個排程根）；
2. 是 **systemd 進入點**（`src/api/server.py`、`dashboard/app.py`）；
3. 其**檔名被其他程式/編排腳本引用**（subprocess、`import`、`.sh` 呼叫）。

否則為 **孤兒（orphan）**。孤兒再依用途細分：多數是一次性診斷/遷移/測試/研究腳本或舊下載系統殘留；少數是合法「手動工具」（保留）。

> 稽核範圍：`scripts/`、根目錄鬆散檔。**不含** `src/`（核心函式庫，多被 import，另案處理）、`data/`、`logs/`、`dashboard/` 內部模組。

---

## 一、保留（KEEP）

### cron 排程根（20）
daily_alert_check.py　daily_recommendations.py　daily_senvision.sh　data_health.py　hourly_data_update.sh　log_rotation.sh　macro_signal_reminder.py　macro_sync.py　obv_bottom_divergence_scan.py　quarterly_earnings_sync.sh　sync_dividend_detail.py　sync_revenue_openapi.py　sync_shares_openapi.py　team_daily_50.sh　twse_openapi_sync.py　verify_backup.py　volume_price_scan.py　watchdog.py　weekly_team_full.sh　weekly_team_verify.py

### 被引用的腳本/函式庫（36）
add_data_validation.py　backfill_by_date.py　backfill_recent_gaps.py　backtest_integrated_v21.py　backtest_patterns.py　backup_mongodb.sh　calculate_adjustment_factors.py　calculate_all_indicators.py　calculate_pe_pb_ratios.py　check_table_coverage.py　cleanup_field_redundancy.py　complete_data_download_pro.py　consolidate_collections.py　download_missing_data.py　download_stock_prices.py　execute_all_improvements.sh　execute_all_improvements_auto.sh　final_system_validation.py　finmind_quarterly_backfill.py　main_download.py　migrate_team_to_db.py　monitor_download.sh　monitor_download_progress.py　notify_failure.sh　parallel_factor_calculation.py　reorganize_financial_data.py　reverify_team.py　senvision_market_scan.py　sync_balance_openapi.py　sync_monthly_revenue.py　team_analyze.py　team_daily_verified.py　twse_daily_update.py　twse_quarterly_sync.py　validate_patterns.py　verify_outstanding_shares.py

### 手動工具（孤兒但保留，5）
- `restore_mongodb.sh` — 災難還原（與 backup 對稱）
- `scripts/apply_schema_validation.py` — P3 schema 驗證工具
- `scripts/line_get_user_id.py` — LINE 設定用
- `scripts/list_databases.py` — 維運速查
- `scripts/query_team.py` — 團隊分析查詢

### 核心文件/設定
.dockerignore　.env　.env.example　.gitignore　API.md　ARCHITECTURE.md　ARCHITECTURE_DETAIL.md　CHANGELOG.md　CONTRIBUTING.md　DOCUMENTATION.md　Dockerfile　INSTALL.md　Makefile　PROJECT_GUIDE.md　QUICK_START.md　Readme.md　SENVISION_ARCHITECTURE.md　SENVISION_QUICKSTART.md　START_HERE.md　crontab_examples.txt　docker-compose.yml　init-mongo.js　pyproject.toml　pytest.ini　requirements.lock.txt　requirements.txt　twstock

---

## 二、建議搬移 BACKUP（未使用）

### 2.1 孤兒腳本 127 檔（依用途）

**臨時檢查（多已被完整度檢查取代）（25）**  
check_actual_values.py　check_adj_close.py　check_data_completeness.py　check_data_coverage.py　check_data_range.py　check_data_readiness.py　check_data_status.py　check_dividend_status.py　check_download_progress.sh　check_factor_data.py　check_factor_quality.py　check_financial_coverage.py　check_financial_ratios.py　check_financial_reports_quality.py　check_financial_structure.py　check_finmind_data_completeness.py　check_outstanding_shares_coverage.py　check_outstanding_shares_data.py　check_per_coverage.py　check_per_distribution.py　check_priority_missing.py　check_system_status.sh　check_taiwan_stock_per.py　check_tools.sh　check_yearly_coverage.py

**臨時/一次性（19）**  
clean_invalid_prices.py　cleanup_duplicate_scripts.sh　complete_finmind_data.py　comprehensive_schema_audit.py　extract_cashflow_data.py　find_capital_data.py　generate_final_report.py　monitor_dividend_progress.py　monitor_sync.sh　quick_check.py　quick_coverage_check.py　quick_status.py　quick_test_api.py　quick_test_morphology.py　run_improvement_tasks.py　safe_optimize_collections.py　senvision_chart.py　tej_market_sync.py　update_stock_names.py

**一次性測試（17）**  
test_backtesting_factors.py　test_date_formats.py　test_download_system.py　test_dupont_industry.py　test_etf_filter.py　test_factor_calculation.py　test_factor_calculation_2330.py　test_filter_complete.py　test_financial_api.py　test_finmind_api.py　test_new_value_factors.py　test_other_tables.py　test_p2_unified_downloader.sh　test_restored_value_factors.py　test_roe_query.py　test_senvision.py　test_senvision_simple.py

**舊下載系統（9）**  
auto_retry_missing_data.sh　classified_downloader.py　download_dividend_data.py　download_missing_financials.py　download_other_4_tables.py　download_priority_stocks.sh　restart_download.sh　start_hourly_download.sh　start_price_download.sh

**一次性重算/造資料（7）**  
calculate_adjustment_factors_v2.py　calculate_bull_bear_indicators.py　calculate_river_charts.py　calculate_technical_indicators.py　create_test_financial_data.py　recalculate_factors.py　recalculate_value_factors.py

**一次性修復/遷移（7）**  
fix_company_names.py　fix_critical_issues.py　fix_data_quality_issues.py　fix_database_roe.py　fix_dividend_decimal128.py　fix_p0_issues.py　fix_quarterly_units.py

**一次性稽核驗證（7）**  
verify_audit_fixes.py　verify_collection_migration.py　verify_db_improvements.sh　verify_dupont_calculations.sh　verify_financial_data.py　verify_finmind_migration.py　verify_plan_a_results.py

**研究用回測（6）**  
backtest_capitulation.py　backtest_historical.py　backtest_ma_inst.py　backtest_obv_divergence.py　backtest_pattern_yearline.py　backtest_volume_states.py

**一次性診斷（6）**  
diagnose_backtest.py　diagnose_factor_coverage.py　diagnose_momentum_coverage.py　diagnose_p0.py　diagnose_plan_a.py　diagnose_value_factors_failure.py

**研究分析（5）**  
analyze_factor_distribution.py　analyze_financial_coverage.py　analyze_parameter_sensitivity.py　analyze_special_codes.py　analyze_財報_factor_coverage.py

**未分類孤兒（5）**  
audit_database_quality.py　classification_integration_example.py　install_backup_service.sh　master_backfill.sh　validate_finmind_data.py

**參數研究（5）**  
compare_v1_v2_params.py　optimize_multifactor_params.py　optimize_v21_params.py　validate_best_params.py　validate_best_params_v2.py

**一次性回補（4）**  
backfill_331.py　backfill_gross_margin.py　backfill_missing_dates.py　backfill_price_history.py

**一次性資料遷移（4）**  
migrate_all_collections_fields.py　migrate_financial_statements_to_reports.py　migrate_stock_price_to_decimal128.py　migrate_to_finmind_format.py

**macOS/舊排程（1）**  
install_launchd.sh

### 2.2 根目錄一次性報告/產物 139 檔

**一次性過程報告（111）**  
ALL_STOCKS_VERIFICATION_REPORT.md　AUDIT_COMPARISON_ANALYSIS.md　AUDIT_COMPLETE.txt　AUDIT_COMPLETION_STATUS.json　AUDIT_FIXES_COMPLETION_REPORT.md　AUDIT_SUMMARY.txt　AUTONOMOUS_VALIDATION_COMPLETE.md　BACKTESTING_FACTOR_COMPLETION_REPORT.md　BACKTESTING_FACTOR_GUIDE.md　BACKTEST_ANALYSIS_REPORT.md　CODE_REFACTOR_EXECUTION_PLAN.md　COLLECTION_OPTIMIZATION_COMPLETE.md　COLLECTION_OPTIMIZATION_REPORT_20260217_170158.json　COLLECTION_UNIFICATION_REPORT.md　COMPLETE.md　COMPLETE_DATA_COVERAGE_REPORT.md　COMPLETE_SYSTEM_AUDIT_REPORT.md　COMPLETE_SYSTEM_TEST_REPORT.md　COMPLETE_SYSTEM_VERIFICATION.md　COMPLETE_VALIDATION_REPORT.md　COMPREHENSIVE_SYSTEM_CHECK.md　CRITICAL_ISSUES_FIX_REPORT.md　CURRENT_STATUS_SUMMARY.md　DATABASE_AUDIT_REPORT.md　DATABASE_CONSOLIDATION_ANALYSIS.md　DATABASE_CONSOLIDATION_COMPLETE.md　DATABASE_IMPROVEMENT_COMPLETION_REPORT.md　DATABASE_IMPROVEMENT_EXECUTION_GUIDE.md　DATABASE_IMPROVEMENT_FINAL_REPORT.md　DATABASE_IMPROVEMENT_REPORT.md　DATABASE_IMPROVEMENT_SUMMARY.md　DATABASE_MIGRATION_GUIDE.md　DATABASE_PROFESSIONAL_IMPROVEMENTS.md　DATABASE_QUALITY_FINAL_SUMMARY.md　DATABASE_SCHEMA_AUDIT.md　DATABASE_SCHEMA_AUDIT_REPORT.md　DATABASE_VERIFICATION_REPORT.md　DATA_TABLES_COVERAGE.md　DATA_UPDATE_PROGRESS.md　DEVELOPMENT_SUMMARY_20260222.md　DOWNLOAD_SYSTEM_COMPLETION_REPORT.md　DUPONT_ANALYSIS_IMPROVEMENT.md　EXECUTION_GUIDE.md　EXECUTION_PLAN.json　EXECUTIVE_SUMMARY.txt　FIELD_STANDARDIZATION_COMPLETE.md　FINAL_COMPLETE_REPORT.md　FINAL_COMPREHENSIVE_AUDIT_REPORT.md　FINAL_SIMPLE_REPORT.md　FINAL_STATUS.md　FINAL_STATUS_REPORT.md　FINAL_THREE_PHASE_COMPLETE_REPORT.md　FINMIND_API_LIMIT_REPORT.md　FINMIND_INTEGRATION_COMPLETE_REPORT.md　HOURLY_AUTO_UPDATE_GUIDE.md　HOURLY_DOWNLOAD_GUIDE.md　HOURLY_UPDATE_FINAL_STATUS.md　INCREMENTAL_SYNC_GUIDE.md　LAUNCHD_SETUP_GUIDE.md　MONGODB_BACKUP_GUIDE.md　MORPHOLOGY_SYSTEM_COMPLETE_REPORT.md　MULTIFACTOR_STRATEGY_REPORT.md　MULTITIMEFRAME_IMPLEMENTATION_COMPLETE.md　OPTIMIZATION_FINAL_SUMMARY.md　OUTSTANDING_SHARES_DIAGNOSIS.md　P0_FIX_COMPLETE_REPORT.md　P0_P1_COMPLETE_SUMMARY.md　P0_P1_EXECUTION_COMPLETE_REPORT.md　P0_P1_P2_COMPLETION_REPORT.md　P1_REFACTOR_PROGRESS.md　P2B_EXECUTION_PLAN.md　P2B_PARTIAL_SUCCESS_REPORT.md　P2_SOLUTION_REPORT.md　PHASE1_COMPLETION_REPORT.md　PHASE2_COMPLETION_SUMMARY.md　PHASE_COMPLETION_SUMMARY.md　PLAN_A_FAILURE_ANALYSIS.md　PLAN_B_SUCCESS_REPORT.md　PRD_v2.1_FinMind_Morphology.md　PRIORITY2_OPTIMIZATION_PROGRESS.md　PRIORITY2_OPTIMIZATION_REPORT.md　PRIORITY_1_2_3_STATUS.md　PRIORITY_3_IMPLEMENTATION_PLAN.md　PRIORITY_3_QUICK_START.md　PRIORITY_TASKS_STATUS.md　PROJECT_COMPLETION_REPORT.json　PROJECT_COMPLETION_REPORT.md　QUICK_EXECUTION_GUIDE.md　QUICK_START_IMPROVEMENTS.md　REFACTOR_AUDIT_REPORT.md　REFACTOR_DELETE_CHECKLIST.md　REFACTOR_QUICK_SUMMARY.md　REFACTOR_STATUS.md　ROE_CALCULATION_FIX_REPORT.md　SAFE_OPTIMIZATION_REPORT_20260217_170448.json　SCHEMA_MIGRATION_GUIDE.md　SENVISION_V21_DELIVERY_REPORT.md　SMART_DOWNLOAD_GUIDE.md　STAGE_2_COMPLETION_REPORT.md　STOCK_CLASSIFICATION_ARCHITECTURE.md　STOCK_CLASSIFICATION_COMPLETION.md　STOCK_CLASSIFICATION_DELIVERY.md　STOCK_CLASSIFICATION_GUIDE.md　STOCK_CLASSIFICATION_REFERENCE.md　SYSTEM_ORGANIZATION_COMPLETE.md　SYSTEM_STATUS_REPORT.md　SYSTEM_TEST_REPORT.json　SYSTEM_VALIDATION_REPORT.md　V21_EXECUTION_GUIDE.md　VALIDATION_COMPLETE.md　backtest_v21_results.json

**macOS launchd（已遷 systemd，死）（9）**  
com.twstock.api_server.plist　com.twstock.daily_alert_check.plist　com.twstock.daily_dividend_sync.plist　com.twstock.hourly_update.plist　com.twstock.monthly_revenue_sync.plist　com.twstock.quarterly_earnings_sync.plist　com.twstock.weekly_log_cleanup.plist　com.twstock.weekly_mongodb_backup.plist　com.twstock.weekly_outstanding_shares.plist

**其他文件（待審）（8）**  
CRONTAB_QUICK_SETUP.md　DATABASE_QUICK_REFERENCE.md　DOWNLOAD_SYSTEM_README.md　FILE_ORGANIZATION.md　FINMIND_DATA_EXPLANATION.md　QUICK_START_DOWNLOAD.md　SCRIPTS_ORGANIZATION.md　ls-r.txt

**舊版備份檔（4）**  
ARCHITECTURE.md.bak_v2　PROJECT_GUIDE_old_backup.md　README_old.md　README_old_backup.md

**Node 腳手架（執行期未用）（4）**  
nest-cli.json　package-lock.json　package.json　tsconfig.json

**執行期殘留/暫存（2）**  
download_status.json　server.pid

**macOS 垃圾檔（1）**  
.DS_Store

### 2.3 大型目錄（整包評估）

| 目錄 | 大小 | 建議 |
|---|--:|---|
| `node_modules/` | 256.1MB | Node 依賴；執行期未用 → 確認無 Node 服務後整包移除 |
| `results/` | 16.5MB | 回測/分析輸出 → 可搬（非程式） |
| `charts/` | 3.6MB | 產生的圖 → 可搬 |
| `models/` | 1.9MB | 訓練模型檔 → 視 ML 是否啟用（保留較安全） |
| `dist/` | 922KB | Node 編譯輸出 → 同上 |
| `_legacy/` | 179KB | 既有 legacy 區 → 併入 BACKUP |
| `reports/` | 78KB | 產生的報告 → 可搬 |
| `views/` | 66KB | Node 樣板 → 同上 |
| `public/` | 6KB | Node 靜態 → 同上 |

---

## 三、建議 BACKUP 結構與執行（待核准）

搬移為可逆操作。建議結構：
```
BACKUP/
  scripts_orphan/     # 孤兒腳本（診斷/遷移/測試/研究/舊下載）
  root_reports/       # 根目錄一次性報告 .md/.txt/.json
  macos_launchd/      # com.twstock.*.plist（已遷 systemd）
  old_backups/        # *.bak / *_old / *_backup
  node_scaffold/      # node_modules, dist, views, public, package*.json, tsconfig, nest-cli
```
執行前務必：`mv` 而非 `rm`；先在 `.166` 跑，本機同步；保留一份 `BACKUP/清單.txt` 記錄來源路徑。

> ⚠️ 風險註記：`src/` 未納入本次（核心庫，需 import 追蹤另案）；`models/`、`data/` 建議保留。搬移後跑一次 `twse_openapi_sync.py --check-only` 與重啟兩個 systemd 服務確認無誤。

---
*產生：檔名引用追蹤（cron 20 根 + systemd 2 進入點 + 全樹檔名比對）。逐檔明細見 `scratchpad/audit_full.json`。*