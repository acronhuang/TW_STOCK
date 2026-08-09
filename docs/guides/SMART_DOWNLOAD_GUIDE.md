# 智能下載系統 v2 - 快速指南

## 🎯 核心功能

本系統解決了原始下載器的三大問題：

1. **斷點續傳** - API 配額用完後，下次執行自動從中斷點繼續
2. **智能跳過 ETF** - 自動識別並跳過沒有財報數據的 ETF（00XXX 格式）
3. **黑名單機制** - 記住哪些股票沒有數據，避免重複浪費 API 配額
4. **自動重試**（可選） - 配額用完後自動等待 1 小時繼續下載

## 📋 當前進度

根據最新日誌，您的下載進度是：

- ✅ 已完成 3/10 個基本面資料表
  - 綜合損益表
  - 資產負債表
  - 現金流量表
- ⏸️ 停在第 4 個表（股利政策表）
- 📊 API 使用: 590/600 (98.33%)

## 🚀 使用方法

### 方式一：手動執行（推薦先試用）

```bash
# 導出 API Token
export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)"

# 從中斷點繼續下載基本面數據
python3 src/downloaders/unified_downloader_v2.py --categories 基本面 --verbose
```

### 方式二：自動等待重試（全自動模式）

```bash
# 導出 API Token
export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)"

# 自動模式：配額用完後等待 1 小時繼續，直到全部完成
python3 src/downloaders/unified_downloader_v2.py --categories 基本面 --auto-retry --verbose
```

**注意**: 自動模式會一直運行直到所有數據下載完成！

### 其他常用命令

```bash
# 查看當前進度
python3 src/downloaders/unified_downloader_v2.py --show-progress

# 重置進度（從頭開始，但保留黑名單）
python3 src/downloaders/unified_downloader_v2.py --categories 基本面 --reset

# 下載所有類別
python3 src/downloaders/unified_downloader_v2.py --all --verbose
```

## 📝 進度檔案

進度自動保存在：`logs/download_progress.json`

內容包括：
- 已完成的資料表
- 當前表的已處理股票
- 黑名單（ETF/無數據股票）
- API 使用統計

## 💡 智能優化

### 自動跳過的股票類型：

1. **ETF（交易所買賣基金）**
   - 格式：00XXX, 00XXXL, 00XXXR, 00XXXK 等
   - 例如：0050, 0056, 00632R, 00657K
   - 原因：ETF 沒有個股財報數據

2. **黑名單股票**
   - API 返回空數據的股票
   - 多次請求失敗的股票
   - 自動記憶，避免重複請求

### API 配額管理：

- 每小時限額：600 次
- 安全閾值：590 次（達到後停止）
- 自動重試：等待下一個整點小時後繼續

## 🔍 預期效果

### 第一次執行：
```
📊 處理股票數: 1,345
🚫 自動跳過 ETF: ~50 支
✅ 實際下載: ~1,295 支
⏸️ API 配額用完，保存進度
```

### 第二次執行（1 小時後）：
```
🔄 發現未完成的下載，從中斷點繼續
📝 已處理: 150 支
✅ 繼續下載: ~1,145 支
```

### 預計總耗時：
- 基本面 10 個表
- 每表處理 ~1,300 支股票
- 每小時可處理 ~600 支
- **總計: 約 20-25 小時**（分散在 2-3 天）

## 🎯 最佳實踐

### 推薦流程：

1. **首次執行**（測試模式）
   ```bash
   # 先執行到 API 配額用完，看看效果
   python3 src/downloaders/unified_downloader_v2.py --categories 基本面 --verbose
   ```

2. **確認進度**
   ```bash
   # 查看進度和黑名單
   python3 src/downloaders/unified_downloader_v2.py --show-progress
   ```

3. **全自動模式**（適合長時間運行）
   ```bash
   # 在 screen 或 tmux 中運行
   screen -S stock_download
   python3 src/downloaders/unified_downloader_v2.py --categories 基本面 --auto-retry --verbose
   # Ctrl+A, D 分離會話
   ```

### 中斷後恢復：

如果下載被中斷（Ctrl+C、關機等），直接重新執行相同命令即可：

```bash
export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)"
python3 src/downloaders/unified_downloader_v2.py --categories 基本面 --verbose
```

系統會自動從中斷點繼續！

## 📊 監控進度

### 查看實時日誌：
```bash
# 最新日誌檔案
tail -f logs/smart_download_*.log | grep -E "✅|❌|⚠️|📊"
```

### 檢查資料庫：
```bash
# 查看已下載的數據量
mongosh tw_stock_analysis --eval "
  db.dividend_detail.countDocuments()
"
```

## ⚠️ 注意事項

1. **API Token 安全**
   - Token 已保存在 `.env` 檔案中
   - 不要將 Token 提交到 Git

2. **MongoDB 連線**
   - 確保 MongoDB 正在運行
   - 預設連線: `mongodb://localhost:27017/`

3. **磁碟空間**
   - 基本面數據量較大
   - 建議預留至少 5GB 空間

4. **網路穩定性**
   - 建議在穩定的網路環境執行
   - 使用 screen/tmux 避免 SSH 斷線中斷

## 🆘 常見問題

### Q: 如何重新開始下載？
```bash
python3 src/downloaders/unified_downloader_v2.py --categories 基本面 --reset
```

### Q: 如何只看進度不下載？
```bash
python3 src/downloaders/unified_downloader_v2.py --show-progress
```

### Q: 進度檔案在哪裡？
```
logs/download_progress.json
```

### Q: 黑名單如何清除？
手動編輯 `logs/download_progress.json`，刪除 `blacklist` 陣列中的項目。

### Q: 為什麼 ETF 被跳過？
ETF 是指數型基金，沒有個別公司的財報數據（如損益表、資產負債表），這是正常的。

## 📈 估算下載時間

假設：
- API 配額: 600/小時
- 股票數: 1,300（扣除 ETF）
- 表數: 10 個

計算：
- 每小時可處理: 600 支
- 單表耗時: 1,300 / 600 ≈ 2.2 小時
- 10 個表總計: 22 小時

**實際時間可能更少**，因為：
- 某些股票沒有所有類型的數據
- 系統會跳過已存在的最新數據
- 黑名單機制避免重複請求

---

**準備好了嗎？** 執行以下命令開始智能下載：

```bash
export FINMIND_API_TOKEN="$(grep FINMIND_API_TOKEN .env | cut -d'=' -f2)"
python3 src/downloaders/unified_downloader_v2.py --categories 基本面 --verbose
```
