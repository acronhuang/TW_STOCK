# FinMind 增量同步系統使用指南

**創建時間**: 2026-02-23 23:44  
**狀態**: ✅ 已啟用（每小時自動執行）

---

## 🎯 系統概述

由於 FinMind API 有請求限制，我們採用**增量同步策略**：
- 每小時同步 50 支股票
- 自動斷點續傳
- 按優先級同步 6 個數據集

---

## ✅ 已完成設置

### 1. 增量同步腳本
- ✅ [scripts/finmind_incremental_sync.py](scripts/finmind_incremental_sync.py)
- ✅ [scripts/hourly_finmind_sync_cron.sh](scripts/hourly_finmind_sync_cron.sh)

### 2. Cron Job
```bash
# FinMind 每小時增量同步（每小時 00 分執行）
0 * * * * /Users/ming/Desktop/Stock/tw-stock-analysis/scripts/hourly_finmind_sync_cron.sh
```

### 3. 首次測試
- ✅ 成功同步 10 支股票
- ✅ 記錄 4,769 筆股價數據
- ✅ 進度檔案創建成功

---

## 📊 同步優先級

系統按以下順序同步數據集：

| 優先級 | 數據集 | 說明 | 狀態 |
|--------|--------|------|------|
| 1 | **stock_price** | 股價日線（5年） | ⏳ 進行中（46/3065） |
| 2 | **per** | 本益比/市值比 | ⏳ 待同步（480/3065） |
| 3 | **dividend** | 除權息 | ⏳ 待同步（0/3065） |
| 4 | **financial** | 財務報表 | ⏳ 部分完成（207/3065） |
| 5 | **holdings** | 大戶持股 | ⏳ 待同步（0/3065） |
| 6 | **institutional_trading** | 法人買賣 | ⏳ 待同步（0/3065） |

---

## 🕐 同步時程表

### 每小時自動執行
```
00:00 - 同步 50 支股票
01:00 - 同步 50 支股票
02:00 - 同步 50 支股票
...（每小時重複）
```

### 預計完成時間
| 階段 | 股票數 | 完成時間 |
|------|--------|----------|
| **優先級 1-3**（stock_price + per + dividend） | 3,065 | **約 2.5 天** |
| **完整同步**（全部 6 個數據集） | 3,065 × 6 | **約 15 天** |

**加速方法**：
- 修改批次大小：`--batch-size 100`（需確保不超過 API 限制）
- 或購買 Premium 版（$99/月，無限制）

---

## 🔍 監控與管理

### 1. 查看同步進度
```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

# 查看進度檔案
cat logs/finmind_sync_progress.json

# 查看同步日誌
ls -lt logs/hourly_finmind_sync/ | head -5
tail -50 logs/hourly_finmind_sync/sync_*.log

# 查看資料庫狀態
python3 scripts/quick_status.py
```

### 2. 手動觸發同步
```bash
# 同步 50 支股票（預設）
export FINMIND_API_TOKEN="your_token"
python3 scripts/finmind_incremental_sync.py

# 同步特定數量
python3 scripts/finmind_incremental_sync.py --batch-size 100

# 同步特定數據集
python3 scripts/finmind_incremental_sync.py --dataset stock_price --batch-size 50
```

### 3. 查看 Cron Job 狀態
```bash
# 查看 crontab
crontab -l | grep finmind

# 查看最近的執行日誌
tail -100 logs/hourly_finmind_sync/sync_*.log

# 測試 cron 腳本
./scripts/hourly_finmind_sync_cron.sh
```

### 4. 檢查資料庫數據
```bash
# 快速狀態
python3 scripts/quick_status.py

# 詳細檢查
python3 scripts/check_data_readiness.py

# MongoDB 直接查詢
mongosh tw_stock_analysis --quiet --eval "
print('stock_price 記錄數:', db.stock_price.countDocuments({}));
print('涵蓋股票數:', db.stock_price.distinct('stock_id').length);
"
```

---

## 🛠️ 常見操作

### 修改同步頻率

**每 2 小時執行一次**：
```bash
crontab -e
# 修改為：
0 */2 * * * /Users/ming/Desktop/Stock/tw-stock-analysis/scripts/hourly_finmind_sync_cron.sh
```

**每 30 分鐘執行一次**：
```bash
*/30 * * * * /Users/ming/Desktop/Stock/tw-stock-analysis/scripts/hourly_finmind_sync_cron.sh
```

### 修改批次大小

編輯 [scripts/hourly_finmind_sync_cron.sh](scripts/hourly_finmind_sync_cron.sh)：
```bash
# 原本
python3 scripts/finmind_incremental_sync.py --batch-size 50

# 改為 100 支
python3 scripts/finmind_incremental_sync.py --batch-size 100
```

### 重置進度

如需重新開始同步：
```bash
rm logs/finmind_sync_progress.json
```

### 暫停自動同步

```bash
# 註解掉 cron job
crontab -e
# 在行首加 #：
# 0 * * * * /Users/ming/Desktop/Stock/tw-stock-analysis/scripts/hourly_finmind_sync_cron.sh

# 或直接移除
crontab -l | grep -v "hourly_finmind_sync_cron.sh" | crontab -
```

---

## 📈 預期結果

### 1 天後（24 小時）
- ✅ stock_price: ~1,200 支股票（40%）
- ✅ 可開始初步回測

### 2.5 天後（60 小時）
- ✅ stock_price: 3,065 支股票（100%）
- ✅ per: 完成（100%）
- ✅ dividend: 完成（100%）
- ✅ **可執行完整回測**

### 15 天後
- ✅ 全部 6 個數據集完成
- ✅ **可執行 v2.1 策略（含籌碼分析）**

---

## 🚨 故障排除

### 問題 1: API 仍然達到限制

**症狀**：日誌顯示 "API 達到限制"

**解決**：
1. 減少批次大小：`--batch-size 20`
2. 增加同步間隔：改為每 2 小時
3. 或購買 Premium 版

### 問題 2: Cron Job 未執行

**檢查**：
```bash
# 查看 cron 日誌
tail -f /var/log/cron.log  # Linux
tail -f /var/mail/$USER    # macOS

# 確認 cron 服務運行
launchctl list | grep cron  # macOS
```

**解決**：
- 確保腳本有執行權限：`chmod +x scripts/hourly_finmind_sync_cron.sh`
- 使用絕對路徑
- 檢查環境變數（FINMIND_API_TOKEN）

### 問題 3: 進度檔案損壞

**解決**：
```bash
# 刪除進度檔案重新開始
rm logs/finmind_sync_progress.json

# 或手動修正
vim logs/finmind_sync_progress.json
```

---

## 📚 相關文檔

- **API 限制報告**: [FINMIND_API_LIMIT_REPORT.md](FINMIND_API_LIMIT_REPORT.md)
- **執行指南**: [V21_EXECUTION_GUIDE.md](V21_EXECUTION_GUIDE.md)
- **完整計劃**: [docs/FINMIND_INTEGRATION_12_WEEK_PLAN.md](docs/FINMIND_INTEGRATION_12_WEEK_PLAN.md)

---

## 🎉 下一步行動

### 立即可做
- ✅ 系統已自動運行，無需人工干預
- ⏰ 等待 24 小時後檢查進度

### 1 天後（2026-02-24 23:44）
```bash
# 檢查同步進度
python3 scripts/quick_status.py

# 如果已有 ~1,200 支股票，可開始測試
python3 scripts/backtest_integrated_v21.py \
    --start-date 2024-01-01 \
    --end-date 2024-12-31
```

### 2.5 天後（2026-02-26 中午）
```bash
# 確認 stock_price 完成
python3 scripts/check_data_readiness.py

# 執行完整回測
python3 scripts/backtest_integrated_v21.py \
    --start-date 2023-01-01 \
    --end-date 2024-12-31
```

---

## 📊 當前狀態總覽

```
資料庫狀態（2026-02-23 23:44）
==============================
✓ 股價     5,123,886 筆  (46/3065 支股票)
✓ 財報         4,238 筆  (207 支)
✓ PE/PB      537,665 筆  (480 支)
✗ 除權息           0 筆
✗ 大戶持股         0 筆
✗ 法人買賣         0 筆

系統狀態
========
✅ 增量同步腳本：已創建
✅ Cron Job：已設置（每小時 00 分）
✅ 首次同步：成功（10 支股票，4,769 筆）
✅ 進度追蹤：啟用
⏳ 預計完成：2.5 天（優先級 1-3）
```

---

**最後更新**: 2026-02-23 23:44  
**系統狀態**: 🟢 運行中  
**下次同步**: 2026-02-24 00:00
