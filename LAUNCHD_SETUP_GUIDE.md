# 🚀 launchd 自動更新服務設置指南

## 📋 概述

本指南將幫助您使用 macOS 原生的 **launchd** 替代 crontab，實現更穩定可靠的台股數據自動更新。

---

## ✨ launchd vs Crontab 優勢

| 特性 | launchd | crontab |
|------|---------|---------|
| **穩定性** | ⭐⭐⭐⭐⭐ 系統級服務 | ⭐⭐⭐ 可能受權限影響 |
| **日誌記錄** | ⭐⭐⭐⭐⭐ 完整的 stdout/stderr 分離 | ⭐⭐⭐ 需手動配置 |
| **錯誤恢復** | ⭐⭐⭐⭐⭐ 自動重試機制 | ⭐⭐ 無自動恢復 |
| **權限管理** | ⭐⭐⭐⭐⭐ 不受 Full Disk Access 限制 | ⭐⭐ 可能需要額外權限 |
| **macOS 整合** | ⭐⭐⭐⭐⭐ 原生推薦方案 | ⭐⭐⭐ 傳統 Unix 工具 |

---

## 📦 已創建的服務

### 1. 每小時數據更新
- **檔案**: `com.twstock.hourly_update.plist`
- **執行時間**: 每小時第 5 分鐘 (XX:05)
- **功能**: 下載技術面、基本面、籌碼面、衍生性商品數據

### 2. 每週流通股數更新
- **檔案**: `com.twstock.weekly_outstanding_shares.plist`
- **執行時間**: 每週日凌晨 2:00
- **功能**: 增量更新流通股數數據（最多執行 3 小時）

### 3. 每週日誌清理
- **檔案**: `com.twstock.weekly_log_cleanup.plist`
- **執行時間**: 每週日凌晨 3:00
- **功能**: 刪除 30 天前的舊日誌檔案

---

## 🔧 快速安裝（推薦）

### 方法一：一鍵腳本安裝

```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis
./scripts/install_launchd.sh
```

這個腳本會自動：
1. ✅ 複製 plist 檔案到 `~/Library/LaunchAgents/`
2. ✅ 設置正確的權限
3. ✅ 加載所有 launchd 服務
4. ✅ 驗證服務狀態

---

## 🛠️ 手動安裝（進階）

如果您想手動控制每個步驟：

### 步驟 1: 複製 plist 檔案

```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

# 複製到 LaunchAgents 目錄
cp com.twstock.hourly_update.plist ~/Library/LaunchAgents/
cp com.twstock.weekly_outstanding_shares.plist ~/Library/LaunchAgents/
cp com.twstock.weekly_log_cleanup.plist ~/Library/LaunchAgents/

# 設置權限
chmod 644 ~/Library/LaunchAgents/com.twstock.*.plist
```

### 步驟 2: 加載服務

```bash
# 加載每小時更新服務
launchctl load ~/Library/LaunchAgents/com.twstock.hourly_update.plist

# 加載每週流通股數更新服務
launchctl load ~/Library/LaunchAgents/com.twstock.weekly_outstanding_shares.plist

# 加載每週日誌清理服務
launchctl load ~/Library/LaunchAgents/com.twstock.weekly_log_cleanup.plist
```

### 步驟 3: 驗證狀態

```bash
# 檢查服務是否運行
launchctl list | grep twstock
```

**預期輸出**：
```
-	0	com.twstock.hourly_update
-	0	com.twstock.weekly_outstanding_shares
-	0	com.twstock.weekly_log_cleanup
```

---

## 📊 監控與管理

### 查看服務狀態

```bash
# 列出所有 twstock 相關服務
launchctl list | grep twstock

# 查看特定服務詳細信息
launchctl print gui/$(id -u)/com.twstock.hourly_update
```

### 查看日誌

```bash
# 每小時更新日誌
tail -f logs/launchd_hourly_stdout.log
tail -f logs/launchd_hourly_stderr.log

# 每週流通股數更新日誌
tail -f logs/launchd_weekly_outstanding_shares.log

# 日誌清理記錄
tail -f logs/launchd_log_cleanup.log
```

### 手動觸發執行

```bash
# 手動啟動每小時更新服務（立即執行一次）
launchctl start com.twstock.hourly_update

# 手動啟動流通股數更新
launchctl start com.twstock.weekly_outstanding_shares
```

### 停用服務

```bash
# 停用特定服務
launchctl unload ~/Library/LaunchAgents/com.twstock.hourly_update.plist

# 停用所有服務
launchctl unload ~/Library/LaunchAgents/com.twstock.*.plist
```

### 重新加載服務

```bash
# 修改 plist 後重新加載
launchctl unload ~/Library/LaunchAgents/com.twstock.hourly_update.plist
launchctl load ~/Library/LaunchAgents/com.twstock.hourly_update.plist
```

---

## 🔄 移除舊的 Crontab（可選）

安裝 launchd 後，您可以停用舊的 crontab 配置：

```bash
# 先備份現有 crontab
crontab -l > ~/Desktop/crontab_backup_$(date +%Y%m%d).txt

# 查看當前 crontab
crontab -l

# 如果確認 launchd 工作正常，可以移除 crontab
crontab -r
```

**⚠️ 注意**: 移除前請確保 launchd 服務已經正常運行至少 24 小時。

---

## 📅 執行時間表

| 服務 | 執行時間 | 說明 |
|------|---------|------|
| 每小時更新 | **每小時 XX:05** | 全部43個數據表增量更新 |
| 流通股數 | **每週日 02:00** | 增量更新，最多3小時 |
| 日誌清理 | **每週日 03:00** | 刪除30天前日誌 |

---

## 🐛 故障排除

### 問題 1: 服務未顯示在列表中

**症狀**: `launchctl list | grep twstock` 無輸出

**解決方案**:
```bash
# 檢查 plist 文件是否存在
ls -l ~/Library/LaunchAgents/com.twstock.*.plist

# 手動加載服務
launchctl load ~/Library/LaunchAgents/com.twstock.hourly_update.plist
```

---

### 問題 2: plist 格式錯誤

**症狀**: 加載時出現 "Invalid property list" 錯誤

**解決方案**:
```bash
# 驗證 plist 格式
plutil -lint ~/Library/LaunchAgents/com.twstock.hourly_update.plist

# 應該看到: "OK" 或具體錯誤信息
```

---

### 問題 3: 服務執行失敗

**症狀**: 服務已加載但沒有執行

**解決方案**:
```bash
# 1. 檢查錯誤日誌
tail -50 logs/launchd_hourly_stderr.log

# 2. 手動測試腳本
/Users/ming/Desktop/Stock/tw-stock-analysis/scripts/hourly_data_update.sh

# 3. 檢查權限
ls -l scripts/hourly_data_update.sh
# 應該是: -rwxr-xr-x

# 4. 手動觸發一次
launchctl start com.twstock.hourly_update
```

---

### 問題 4: Python 找不到

**症狀**: 日誌顯示 "python3: command not found"

**解決方案**:

編輯 plist 文件，確保 PATH 包含 Python：

```bash
nano ~/Library/LaunchAgents/com.twstock.hourly_update.plist
```

找到 `<key>EnvironmentVariables</key>` 部分，確保包含：
```xml
<key>PATH</key>
<string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin</string>
```

然後重新加載：
```bash
launchctl unload ~/Library/LaunchAgents/com.twstock.hourly_update.plist
launchctl load ~/Library/LaunchAgents/com.twstock.hourly_update.plist
```

---

## ✅ 驗證安裝成功

執行以下檢查清單：

```bash
# 1. 檢查服務狀態 ✓
launchctl list | grep twstock
# 應該看到 3 個服務

# 2. 檢查 plist 文件 ✓
ls -l ~/Library/LaunchAgents/com.twstock.*.plist
# 應該看到 3 個文件

# 3. 查看最近日誌 ✓
ls -lt logs/launchd_*.log 2>/dev/null | head -5
# 等待下次執行後會出現日誌

# 4. 手動觸發測試 ✓
launchctl start com.twstock.hourly_update
tail -f logs/launchd_hourly_stdout.log
# Ctrl+C 退出
```

---

## 📚 進階配置

### 修改執行時間

編輯 plist 文件中的 `StartCalendarInterval`：

```xml
<!-- 每小時第 5 分鐘 -->
<key>StartCalendarInterval</key>
<dict>
    <key>Minute</key>
    <integer>5</integer>
</dict>

<!-- 每天 09:00 -->
<key>StartCalendarInterval</key>
<dict>
    <key>Hour</key>
    <integer>9</integer>
    <key>Minute</key>
    <integer>0</integer>
</dict>

<!-- 每週一 14:30 -->
<key>StartCalendarInterval</key>
<dict>
    <key>Weekday</key>
    <integer>1</integer>
    <key>Hour</key>
    <integer>14</integer>
    <key>Minute</key>
    <integer>30</integer>
</dict>
```

**Weekday 數值**:
- 0 = 週日
- 1 = 週一
- 2 = 週二
- ...
- 6 = 週六

---

## 🎯 最佳實踐

1. **定期檢查日誌** (每週一次)
   ```bash
   tail -100 logs/launchd_hourly_stdout.log
   ```

2. **監控 API 配額使用**
   - 查看日誌中的 API 使用率
   - 確保未超過 600/小時限制

3. **備份配置文件**
   ```bash
   cp ~/Library/LaunchAgents/com.twstock.*.plist ~/Desktop/launchd_backup/
   ```

4. **重啟後自動加載**
   - launchd 會在登錄後自動加載 `~/Library/LaunchAgents/` 中的服務
   - 無需手動操作

---

## 📞 需要幫助？

如果遇到問題：

1. 檢查 [故障排除](#故障排除) 章節
2. 查看錯誤日誌：`logs/launchd_hourly_stderr.log`
3. 手動測試腳本：`./scripts/hourly_data_update.sh`
4. 驗證系統日誌：`log show --predicate 'process == "launchd"' --last 1h`

---

## 🎉 總結

✅ **優勢**: 更穩定、更可靠、更好的日誌記錄  
✅ **安裝**: 一鍵腳本或手動 3 步驟  
✅ **管理**: 簡單的 launchctl 命令  
✅ **兼容**: 可與 crontab 並存或替代  

**下一步**: 等待下個整點 XX:05，檢查 `logs/launchd_hourly_stdout.log` 確認首次執行成功！ 🚀
