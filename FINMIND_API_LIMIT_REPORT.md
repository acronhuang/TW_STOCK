# FinMind API 限制狀況報告

**生成時間**: 2026-02-23 22:13  
**問題**: FinMind API 達到請求上限（Status 402）

---

## 🔴 當前狀況

### API 限制錯誤
```
Status: 402
Response: {
  'msg': 'Requests reach the upper limit. https://finmindtrade.com/',
  'status': 402
}
```

**影響**：
- ❌ 無法從 FinMind API 獲取新數據
- ❌ `finmind_full_sync.py` 無法執行完整同步
- ⏳ 需等待 24 小時限制重置

---

## 📊 現有數據狀況

### 可用數據
| 集合 | 記錄數 | 股票數 | 日期範圍 | 狀態 |
|------|--------|--------|----------|------|
| **stock_price** | 5,119,117 | 36 | 2016-01-11 ~ 2026-02-15 | ⚠️ 股票數太少 |
| **financial_reports** | 4,238 | 207 | - | ✅ 可用 |
| **taiwan_stock_per** | 537,665 | 480 | 2021-02-24 ~ 2026-02-11 | ✅ 可用 |
| **stock_list** | 3,065 | 3,065 | - | ✅ 可用 |

### 缺失數據（關鍵）
- ❌ **dividend**（除權息）- 0 筆 - **影響還原股價計算**
- ❌ **institutional_holdings**（大戶持股）- 0 筆 - 籌碼分析需要
- ❌ **institutional_trading**（法人買賣）- 0 筆 - 籌碼分析需要

### 因子計算狀況
- ❌ **技術因子**（return_3m, volatility_3m, RSI 等）- 未計算
- ❌ **基本面因子**（ROE, ROA, 毛利率等）- 未計算
- ⚠️ **估值因子**（PE, PB）- 部分可用

---

## 💡 解決方案

### 方案 1: 等待 API 限制重置（推薦）⏰

**時程**：24 小時後（2026-02-24 22:13 之後）

**步驟**：
```bash
# 2026-02-24 22:13 之後執行
cd /Users/ming/Desktop/Stock/tw-stock-analysis

export FINMIND_API_TOKEN=""

# 執行完整同步（僅下載缺失數據）
python3 scripts/finmind_full_sync.py --initial 2>&1 | tee logs/finmind_sync_$(date +%Y%m%d).log
# 輸入 yes 確認
```

**優點**：
- ✅ 免費
- ✅ 可獲得完整數據

**缺點**：
- ⏳ 需等待 24 小時

---

### 方案 2: 升級到 FinMind Premium（最快）💰

**費用**：$99/月

**優點**：
- ✅ 立即可用
- ✅ 無請求限制
- ✅ 更快的下載速度

**購買連結**：https://finmindtrade.com/

**設置步驟**：
```bash
# 1. 購買 Premium
# 2. 更新 .env 中的 API Token
# 3. 執行同步
python3 scripts/finmind_full_sync.py --initial
```

---

### 方案 3: 使用現有數據進行初步測試（立即可行）🚀

雖然數據不完整，但可以：

#### 3.1 補充除權息數據

除權息數據可從其他來源獲取：

```bash
# 使用 unified_downloader（可能有其他數據源）
python3 src/downloaders/unified_downloader.py --categories 基本面 --verbose

# 或手動補充（Taiwan Stock Exchange 公開資料）
# https://www.twse.com.tw/zh/
```

#### 3.2 計算因子（使用現有數據）

```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

# 計算技術因子（使用 stock_price）
python3 scripts/parallel_factor_calculation.py \
    --workers 4 \
    --start-date 2023-01-01 \
    --end-date 2026-02-23

# 這將計算：
# - return_3m, return_6m, return_12m
# - volatility_3m
# - volume_ratio_20d
# - rsi_14d, macd
```

#### 3.3 初步回測（v2.0 基準測試）

即使數據不完整，也可以進行初步測試：

```bash
# 使用現有 36 支股票的數據進行回測
python3 scripts/backtest_multifactor.py \
    --start-date 2023-01-01 \
    --end-date 2024-12-31 \
    --max-stocks 30

# 這可以：
# 1. 驗證策略邏輯
# 2. 測試參數配置
# 3. 評估系統性能
```

**優點**：
- ✅ 立即可行
- ✅ 可驗證策略邏輯

**缺點**：
- ⚠️ 樣本偏小（僅 36 支股票）
- ⚠️ 缺少籌碼數據
- ⚠️ 無法進行 v2.1 完整回測

---

## 📋 建議執行順序

### 立即執行（今天）

1. **計算現有股價數據的技術因子**
   ```bash
   python3 scripts/parallel_factor_calculation.py \
       --workers 4 \
       --start-date 2023-01-01 \
       --end-date 2026-02-23
   ```

2. **驗證 v2.0 策略邏輯**
   ```bash
   python3 scripts/backtest_multifactor.py \
       --start-date 2023-01-01 \
       --end-date 2024-12-31
   ```

3. **檢查回測結果**
   ```bash
   cat results/backtest_results_*.json | jq '.metrics'
   ```

### 明天執行（2026-02-24 22:13 之後）

4. **執行完整 FinMind 同步**
   ```bash
   export FINMIND_API_TOKEN="..."
   python3 scripts/finmind_full_sync.py --initial
   # 輸入 yes
   ```

5. **重新計算所有因子**
   ```bash
   python3 scripts/parallel_factor_calculation.py \
       --workers 4 \
       --start-date 2023-01-01 \
       --end-date 2026-02-23 \
       --force
   ```

6. **執行 v2.0 vs v2.1 完整回測**
   ```bash
   python3 scripts/backtest_integrated_v21.py \
       --start-date 2023-01-01 \
       --end-date 2024-12-31
   ```

---

## 🔧 已修正

### 1. `finmind_full_sync.py` 改進

**修正內容**：
- ✅ 優先從資料庫獲取股票列表（避免 API 調用）
- ✅ 偵測 API 限制錯誤（402, KeyError: 'data'）
- ✅ 自動停止並給出建議
- ✅ 加長請求間隔（0.1s → 0.3s）

**修正代碼**：
```python
# 1. 優先使用資料庫股票列表
existing = list(self.db.stock_list.find({}))
if existing:
    stock_ids = [s['stock_id'] for s in existing]
    print(f"✓ 從資料庫獲取 {len(stock_ids)} 支股票")
    return stock_ids

# 2. 偵測 API 限制
except KeyError as e:
    if str(e) == "'data'":
        print("⚠️  FinMind API 達到請求上限！")
        print("建議：等待 24 小時或升級 Premium")
        return

# 3. 加長間隔
time.sleep(0.3)  # 原本 0.1s
```

### 2. 新增 `check_data_readiness.py`

**功能**：
- ✅ 檢查所有必要集合
- ✅ 檢查因子計算狀況
- ✅ 評估數據新鮮度
- ✅ 給出具體建議

**使用**：
```bash
python3 scripts/check_data_readiness.py
```

---

## 📞 如需協助

### FinMind Support
- 官網：https://finmindtrade.com/
- 文件：https://finmind.github.io/
- Discord：https://discord.gg/finmind

### API 限制說明
- **免費版**：每日 1,000 次請求
- **Premium**：無限請求（$99/月）
- **限制重置**：每日 00:00（UTC+8）

---

## 總結

**當前狀況**：FinMind API 達到請求上限，無法繼續同步

**最佳方案**：
1. **今天**：使用現有數據進行初步測試（驗證策略邏輯）
2. **明天**：等待 API 限制重置後，執行完整同步
3. **後天**：進行 v2.0 vs v2.1 完整回測

**或**：升級到 FinMind Premium（$99/月）立即獲得完整數據

---

**最後更新**: 2026-02-23 22:13  
**狀態**: 等待 API 限制重置或升級 Premium
