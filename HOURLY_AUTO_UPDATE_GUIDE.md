# 每小時自動資料更新系統 - 使用指南

## 📚 目錄

1. [系統概述](#系統概述)
2. [快速開始](#快速開始)
3. [設定 Crontab 自動執行](#設定-crontab-自動執行)
4. [日誌管理](#日誌管理)
5. [監控與故障排除](#監控與故障排除)
6. [效能調校](#效能調校)

---

## 系統概述

### 功能特點

✅ **全自動更新** - 每小時自動下載所有 FinMind 資料  
✅ **完整日誌** - 每次執行都產生詳細日誌（含時間戳記）  
✅ **智能跳過** - 自動跳過已存在的資料，節省 API 配額  
✅ **分類下載** - 依序下載技術面、基本面、籌碼面、衍生性商品  
✅ **錯誤復原** - 單一類別失敗不影響其他類別  
✅ **每日總結** - 自動產生每日更新總結報告  

### 覆蓋的資料範圍

| 類別 | 資料表數 | 更新頻率建議 | API 消耗 |
|------|---------|-------------|---------|
| **技術面** | 9 個 | 每 30-60 分鐘 | ~15-20 次 |
| **基本面** | 10 個 | 每天 1 次 | ~10-15 次 |
| **籌碼面** | 10 個 | 每天 1 次 | ~10-15 次 |
| **衍生性商品** | 8 個 | 每天 1 次 | ~8-10 次 |

**總計**: 43 個資料表 (每次完整更新約消耗 40-60 次 API 配額)

---

## 快速開始

### 方式一：立即執行一次（測試用）

```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

# 執行每小時更新腳本
./scripts/hourly_data_update.sh
```

**執行結果**:
- 日誌檔: `logs/hourly_updates/hourly_update_YYYYMMDD_HHMMSS.log`
- 總結檔: `logs/hourly_updates/daily_summary_YYYYMMDD.log`
- 螢幕輸出: 即時顯示進度

### 方式二：背景執行（不佔用終端機）

```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

# 背景執行並將輸出導向日誌
nohup ./scripts/hourly_data_update.sh > logs/hourly_cron.log 2>&1 &

# 查看背景程序
ps aux | grep hourly_data_update.sh

# 即時查看日誌
tail -f logs/hourly_cron.log
```

### 方式三：只下載特定類別

```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

# 手動下載技術面資料
export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)"
python3 src/downloaders/unified_downloader.py \
    --categories 技術面 \
    --verbose \
    2>&1 | tee logs/manual_tech_$(date +%Y%m%d_%H%M%S).log
```

---

## 設定 Crontab 自動執行

### 步驟 1：編輯 Crontab

```bash
crontab -e
```

### 步驟 2：加入以下配置

#### 🔥 推薦設定：每小時自動更新

```bash
# 每小時第 5 分鐘執行（避開整點高峰）
5 * * * * /Users/ming/Desktop/Stock/tw-stock-analysis/scripts/hourly_data_update.sh >> /Users/ming/Desktop/Stock/tw-stock-analysis/logs/hourly_cron.log 2>&1
```

**執行時間範例**:
- 00:05, 01:05, 02:05 ... 23:05（每天 24 次）

#### ⚡ 節省配額：分時段更新

```bash
# 交易日盤中：每 30 分鐘更新技術面
0,30 9-13 * * 1-5 cd /Users/ming/Desktop/Stock/tw-stock-analysis && export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)" && python3 src/downloaders/unified_downloader.py --categories 技術面 --verbose >> logs/intraday_tech.log 2>&1

# 交易日收盤後：更新籌碼面
0 15 * * 1-5 cd /Users/ming/Desktop/Stock/tw-stock-analysis && export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)" && python3 src/downloaders/unified_downloader.py --categories 籌碼面 --verbose >> logs/daily_chips.log 2>&1

# 每天晚上：更新基本面
0 21 * * * cd /Users/ming/Desktop/Stock/tw-stock-analysis && export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)" && python3 src/downloaders/unified_downloader.py --categories 基本面 --verbose >> logs/daily_fundamental.log 2>&1
```

### 步驟 3：驗證設定

```bash
# 列出當前 crontab
crontab -l

# 查看 cron 日誌（macOS）
log show --predicate 'process == "cron"' --last 1h

# 查看 cron 日誌（Linux）
grep CRON /var/log/syslog
```

---

## 日誌管理

### 日誌檔案結構

```
logs/
├── hourly_updates/                          # 每小時更新日誌
│   ├── hourly_update_20260222_000500.log
│   ├── hourly_update_20260222_010500.log
│   ├── daily_summary_20260222.log           # 每日總結
│   └── ...
├── hourly_cron.log                          # Crontab 執行日誌
├── unified_download_*.log                   # Unified Downloader 日誌
└── ...
```

### 查看最新日誌

```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

# 查看最新的每小時更新日誌
ls -lt logs/hourly_updates/hourly_update_*.log | head -1 | awk '{print $NF}' | xargs tail -50

# 查看今天的每日總結
tail -100 logs/hourly_updates/daily_summary_$(date +%Y%m%d).log

# 即時監控
tail -f logs/hourly_cron.log
```

### 日誌清理（自動化）

```bash
# 加入 crontab：每週清理超過 30 天的日誌
0 3 * * 0 find /Users/ming/Desktop/Stock/tw-stock-analysis/logs -name "*.log" -mtime +30 -delete
```

---

## 監控與故障排除

### 檢查執行狀態

```bash
# 方法 1：查看進程
ps aux | grep -E "(hourly_data_update|unified_downloader)"

# 方法 2：查看最新日誌時間
ls -lt logs/hourly_updates/ | head -5

# 方法 3：檢查今天有沒有更新
grep "$(date +'%Y-%m-%d')" logs/hourly_updates/daily_summary_*.log | tail -20
```

### 常見問題與解決方式

#### ❌ 問題 1：Crontab 沒有執行

**檢查項目**:
```bash
# 1. 確認 cron 服務運行
# macOS
sudo launchctl list | grep cron

# Linux
sudo service cron status

# 2. 檢查腳本權限
ls -la scripts/hourly_data_update.sh
# 應該是 -rwxr-xr-x

# 3. 手動測試執行
./scripts/hourly_data_update.sh
```

**解決方式**:
```bash
# 重新賦予執行權限
chmod +x scripts/hourly_data_update.sh
```

#### ❌ 問題 2：API Token 找不到

**檢查項目**:
```bash
# 確認 .env 檔案存在
ls -la .env

# 確認 Token 格式正確
grep FINMIND_API_TOKEN .env
# 應該是: FINMIND_API_TOKEN=eyJ0eXAi...
```

**解決方式**:
```bash
# 手動設定環境變數
export FINMIND_API_TOKEN="your_token_here"
```

#### ❌ 問題 3：API 配額耗盡 (402 Error)

**症狀**:
- 日誌中大量出現 "HTTP 錯誤: 402"
- API 已使用次數超過 600

**解決方式**:
1. **降低執行頻率** - 從每小時改為每 2-4 小時
2. **分批下載** - 不要一次下載所有類別
3. **使用智能跳過** - 啟用 `--skip-existing`（預設已啟用）

```bash
# 修改 crontab 為每 2 小時執行
5 */2 * * * /Users/ming/Desktop/Stock/tw-stock-analysis/scripts/hourly_data_update.sh >> /Users/ming/Desktop/Stock/tw-stock-analysis/logs/hourly_cron.log 2>&1
```

#### ❌ 問題 4：MongoDB 連線失敗

**症狀**:
- 日誌中出現 "Connection refused"
- 資料無法寫入資料庫

**解決方式**:
```bash
# 1. 檢查 MongoDB 是否運行
ps aux | grep mongod

# 2. 啟動 MongoDB（Docker）
docker start mongodb

# 3. 測試連線
mongosh tw_stock_analysis --eval "db.runCommand({ ping: 1 })"
```

---

## 效能調校

### API 配額管理策略

| 策略 | 頻率 | API 消耗/天 | 適用情境 |
|------|------|------------|---------|
| **激進更新** | 每小時 | ~1,200 次 | 付費 API 用戶 |
| **平衡更新** | 每 2 小時 | ~600 次 | 免費 API，高時效需求 |
| **保守更新** | 每 4 小時 | ~300 次 | 免費 API，低時效需求 |
| **分時段更新** | 依類別 | ~200-400 次 | **推薦**，最節省配額 |

### 推薦的分時段策略

```bash
# 加入 crontab_examples.txt 的「方案二」設定：

# 1. 交易日盤中 (9:00-13:30)：每 30 分鐘更新技術面
0,30 9-13 * * 1-5 [技術面更新命令]

# 2. 交易日收盤後 (15:00)：更新籌碼面
0 15 * * 1-5 [籌碼面更新命令]

# 3. 每天晚上 (21:00)：更新基本面
0 21 * * * [基本面更新命令]

# 4. 每週一晚上 (22:00)：更新衍生性商品
0 22 * * 1 [衍生性商品更新命令]
```

**每天 API 消耗估算**:
- 技術面: 10 次/更新 × 10 次/天 = 100 次
- 籌碼面: 10 次 × 1 次/天 = 10 次
- 基本面: 10 次 × 1 次/天 = 10 次
- 衍生性商品: 8 次 × 1 次/週 = ~1-2 次/天
- **總計**: 約 120-130 次/天（遠低於 14,400 次/天的配額）

### 資料庫效能優化

```bash
# 1. 建立索引（加速查詢）
mongosh tw_stock_analysis --eval "
db.stock_price.createIndex({ stock_id: 1, date: -1 });
db.taiwan_stock_info.createIndex({ stock_id: 1 });
db.dividend_detail.createIndex({ stock_id: 1, date: -1 });
"

# 2. 定期清理舊資料（保留最近 5 年）
# 加入 crontab：每月 1 號凌晨 5:00 執行
0 5 1 * * mongosh tw_stock_analysis --eval "db.stock_price.deleteMany({ date: { \$lt: new Date(new Date().setFullYear(new Date().getFullYear() - 5)) } })"
```

---

## 進階功能

### 郵件/Slack 通知（當下載失敗時）

編輯 `scripts/hourly_data_update.sh`，在 `log_error` 函數中加入：

```bash
log_error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} ❌ $1" | tee -a "$LOG_FILE"
    
    # 發送郵件通知（需要安裝 mailutils）
    # echo "$1" | mail -s "[台股系統] 下載失敗通知" your-email@example.com
    
    # 發送 Slack 通知（需要 webhook URL）
    # curl -X POST -H 'Content-type: application/json' \
    #   --data "{\"text\":\"❌ 台股資料下載失敗: $1\"}" \
    #   YOUR_SLACK_WEBHOOK_URL
}
```

### 監控儀表板（Grafana + Prometheus）

可整合 MongoDB Exporter 將資料覆蓋率、更新頻率等指標視覺化。

---

## 相關檔案

| 檔案 | 說明 |
|------|------|
| `scripts/hourly_data_update.sh` | 每小時自動更新主腳本 |
| `crontab_examples.txt` | Crontab 設定範例大全 |
| `src/downloaders/unified_downloader.py` | 統一資料下載器 |
| `DEVELOPMENT_SUMMARY_20260222.md` | 開發階段總結 |
| `HOURLY_DOWNLOAD_GUIDE.md` | 流通股數每小時下載指南 |

---

## 支援與回饋

- 問題回報: 查看日誌檔 `logs/hourly_updates/`
- 系統狀態: 執行 `python3 scripts/verify_*.py`
- 資料庫監控: `mongosh tw_stock_analysis --eval "db.stats()"`

**最後更新**: 2026-02-22  
**腳本版本**: 1.0.0  
**API 版本**: FinMind v4
