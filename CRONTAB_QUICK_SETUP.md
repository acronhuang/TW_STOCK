# Crontab 快速設定指南

## 🎯 推薦配置（二選一）

### 方案 A：每小時全自動更新（推薦）

**適用**: 一般使用者，API 配額充足 (600 次/小時)

```bash
# 編輯 crontab
crontab -e

# 加入以下 3 行配置
# 1. 每小時自動下載所有資料
5 * * * * /Users/ming/Desktop/Stock/tw-stock-analysis/scripts/hourly_data_update.sh >> /Users/ming/Desktop/Stock/tw-stock-analysis/logs/hourly_cron.log 2>&1

# 2. 每週日凌晨 2:00 更新流通股數
0 2 * * 0 cd /Users/ming/Desktop/Stock/tw-stock-analysis && export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)" && python3 src/downloaders/hourly_outstanding_shares_downloader.py --all --max-hours 3 >> logs/weekly_outstanding_shares.log 2>&1

# 3. 每週日凌晨 3:00 清理舊日誌
0 3 * * 0 find /Users/ming/Desktop/Stock/tw-stock-analysis/logs -name "*.log" -mtime +30 -delete
```

**API 消耗**: 約 1,200 次/天（每小時 50 次 × 24 小時）  
**優點**: 配置簡單，一行搞定，數據最新  
**缺點**: API 消耗較高

---

### 方案 B：分時段更新（節省配額）

**適用**: API 配額有限，只需特定時段更新

```bash
# 編輯 crontab
crontab -e

# 加入以下 6 行配置
# 1. 交易日盤中更新技術面（每 30 分鐘）
0,30 9-13 * * 1-5 cd /Users/ming/Desktop/Stock/tw-stock-analysis && export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)" && python3 src/downloaders/unified_downloader.py --categories 技術面 --verbose >> logs/intraday_tech.log 2>&1

# 2. 交易日收盤後更新籌碼面
0 15 * * 1-5 cd /Users/ming/Desktop/Stock/tw-stock-analysis && export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)" && python3 src/downloaders/unified_downloader.py --categories 籌碼面 --verbose >> logs/daily_chips.log 2>&1

# 3. 每天晚上更新基本面
0 21 * * * cd /Users/ming/Desktop/Stock/tw-stock-analysis && export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)" && python3 src/downloaders/unified_downloader.py --categories 基本面 --verbose >> logs/daily_fundamental.log 2>&1

# 4. 每週一晚上更新衍生性商品
0 22 * * 1 cd /Users/ming/Desktop/Stock/tw-stock-analysis && export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)" && python3 src/downloaders/unified_downloader.py --categories 衍生性商品 --verbose >> logs/weekly_derivatives.log 2>&1

# 5. 每週日凌晨 2:00 更新流通股數
0 2 * * 0 cd /Users/ming/Desktop/Stock/tw-stock-analysis && export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)" && python3 src/downloaders/hourly_outstanding_shares_downloader.py --all --max-hours 3 >> logs/weekly_outstanding_shares.log 2>&1

# 6. 每週日凌晨 3:00 清理舊日誌
0 3 * * 0 find /Users/ming/Desktop/Stock/tw-stock-analysis/logs -name "*.log" -mtime +30 -delete
```

**API 消耗**: 約 120-150 次/天（節省 85%）  
**優點**: API 消耗最低，精細控制  
**缺點**: 配置較複雜，非交易時段無更新

---

## ⚠️ 重要注意事項

1. **方案 A 和方案 B 只能擇一使用，不可同時啟用！**
2. **流通股數更新（第 5 行）** 和 **日誌清理（第 6 行）** 兩個方案都需要
3. 如果已經使用方案 A，就不要再加入方案 B 的前 4 行

---

## 🔍 驗證配置

### 查看當前 crontab
```bash
crontab -l
```

### 查看 cron 執行日誌（macOS）
```bash
log show --predicate 'process == "cron"' --last 1h
```

### 查看 cron 執行日誌（Linux）
```bash
grep CRON /var/log/syslog
```

### 測試腳本是否正常
```bash
# 手動執行一次測試
cd /Users/ming/Desktop/Stock/tw-stock-analysis
./scripts/hourly_data_update.sh
```

---

## 🔧 修改配置

### 編輯 crontab
```bash
crontab -e
```

### 刪除所有 crontab
```bash
crontab -r
```

### 暫時禁用某行（加上 # 註解）
```bash
# 5 * * * * /path/to/script.sh
```

---

## 📊 API 配額監控

### 當前配額狀態
- **限制**: 600 次/小時
- **已使用**: 160 次
- **剩餘**: 440 次

### 查看 API 使用量
訪問 FinMind 官網查看即時使用量：
https://finmindtrade.com/analysis/#/data/dashboard

---

## 🆘 故障排除

### 問題 1：Crontab 沒有執行

**檢查**:
```bash
# 確認腳本有執行權限
ls -la /Users/ming/Desktop/Stock/tw-stock-analysis/scripts/hourly_data_update.sh
# 應該顯示 -rwxr-xr-x

# 如果沒有，加上執行權限
chmod +x /Users/ming/Desktop/Stock/tw-stock-analysis/scripts/hourly_data_update.sh
```

### 問題 2：找不到 Python 或 MongoDB

**解決**: 在 crontab 開頭加上環境變數
```bash
# 在所有 cron job 之前加上
PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
SHELL=/bin/bash
```

### 問題 3：API Token 找不到

**檢查**:
```bash
# 確認 .env 檔案存在且格式正確
cat /Users/ming/Desktop/Stock/tw-stock-analysis/.env | grep FINMIND_API_TOKEN
```

---

## ✅ 最簡配置（初學者適用）

如果不確定選哪個，**使用這 3 行就夠了**：

```bash
# 每小時更新所有資料 + 每週流通股數 + 每週清理日誌
5 * * * * /Users/ming/Desktop/Stock/tw-stock-analysis/scripts/hourly_data_update.sh >> /Users/ming/Desktop/Stock/tw-stock-analysis/logs/hourly_cron.log 2>&1
0 2 * * 0 cd /Users/ming/Desktop/Stock/tw-stock-analysis && export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)" && python3 src/downloaders/hourly_outstanding_shares_downloader.py --all --max-hours 3 >> logs/weekly_outstanding_shares.log 2>&1
0 3 * * 0 find /Users/ming/Desktop/Stock/tw-stock-analysis/logs -name "*.log" -mtime +30 -delete
```

**完成！系統將每小時自動更新所有台股資料。**
