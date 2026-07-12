# SenVision 全市場掃描完整指南

**版本**: v2.1
**更新日期**: 2026-02-24
**功能**: 全市場多時間週期形態掃描

---

## 🎯 功能說明

全市場掃描器能夠：
- ✅ 自動掃描所有台股（3000+支）
- ✅ 支援多時間週期分析（日/週/月/季/半年/年）
- ✅ 12神招形態自動識別
- ✅ 共振強度分析
- ✅ 智能交易建議
- ✅ CSV/JSON報告匯出
- ✅ 產業分類過濾

---

## 🚀 快速使用

### 1. 基礎全市場掃描

```bash
# 掃描全市場（日線+週線）
python3 pattern_recognition/market_multi_timeframe_scanner.py

# 顯示前30名最佳機會
python3 pattern_recognition/market_multi_timeframe_scanner.py --top 30

# 儲存CSV報告
python3 pattern_recognition/market_multi_timeframe_scanner.py --save-csv
```

### 2. 週線月線長線選股

```bash
# 週線+月線組合（適合長期投資）
python3 pattern_recognition/market_multi_timeframe_scanner.py \
  --timeframes W M \
  --min-resonance 0.80 \
  --top 50 \
  --save-csv
```

### 3. 僅顯示多頭機會

```bash
# 只看買進機會
python3 pattern_recognition/market_multi_timeframe_scanner.py \
  --timeframes D W \
  --bullish-only \
  --top 20
```

### 4. 特定產業掃描

```bash
# 僅掃描半導體產業
python3 pattern_recognition/market_multi_timeframe_scanner.py \
  --industry 半導體 \
  --timeframes W M

# 僅掃描電子業
python3 pattern_recognition/market_multi_timeframe_scanner.py \
  --industry 電子 \
  --timeframes D W
```

---

## 📊 參數說明

### 核心參數

| 參數 | 說明 | 預設值 | 範例 |
|------|------|--------|------|
| `-t, --timeframes` | 時間週期列表 | D W | `--timeframes D W M` |
| `--min-confidence` | 最小形態信心度 | 0.75 | `--min-confidence 0.80` |
| `--min-resonance` | 最小共振強度 | 0.60 | `--min-resonance 0.70` |
| `--top` | 顯示前N名 | 20 | `--top 50` |

### 過濾參數

| 參數 | 說明 | 範例 |
|------|------|------|
| `--industry` | 產業類別過濾 | `--industry 半導體` |
| `--bullish-only` | 僅顯示多頭機會 | `--bullish-only` |
| `--bearish-only` | 僅顯示空頭機會 | `--bearish-only` |
| `--limit` | 限制掃描數量（測試用） | `--limit 100` |

### 輸出參數

| 參數 | 說明 | 輸出位置 |
|------|------|---------|
| `--save-csv` | 儲存CSV報告 | `reports/market_scan_YYYYMMDD_HHMMSS.csv` |
| `--save-json` | 儲存JSON報告 | `reports/market_scan_YYYYMMDD_HHMMSS.json` |

---

## 📈 實際輸出範例

### 終端輸出

```
====================================================================================================
🚀 SenVision 全市場多時間週期形態掃描器
====================================================================================================

🔍 開始掃描 50 支股票...
   時間週期: W, M
   最小信心度: 75%
   最小共振強度: 70%

掃描中: 100%|███████████████████████████████████████████| 50/50 [00:15<00:00,  3.2it/s]

====================================================================================================
📊 全市場多時間週期形態分析報告 - Top 20
====================================================================================================

總共找到 15 個交易機會

📈 多頭機會: 8
📉 空頭機會: 7
🔥 強勢共振(≥80%): 12

====================================================================================================
排名 | 代碼 | 股票名稱      | 產業      | 型態      | 共振 | 動作 | 當前價 | 目標價 | 風報比 | 理由
====================================================================================================
  1  | 2330 | 台積電      | 半導體業     | W底       | 🔥 100% | 🟢 buy  | 1915.0 | 2100.0 |  3.2 | 多時間週期強勢多頭共振(100%)，建議全倉進場
  2  | 2317 | 鴻海       | 電子工業     | 破底翻W底    | 🔥  95% | 🟢 buy  |  120.5 |  135.0 |  2.8 | 多時間週期強勢多頭共振(95%)，建議全倉進場
  3  | 2454 | 聯發科      | 半導體業     | 頭肩底      | 🔥  92% | 🟢 buy  |  850.0 |  920.0 |  3.5 | 多時間週期強勢多頭共振(92%)，建議全倉進場
  ...
====================================================================================================

✅ 已儲存報告: reports/market_scan_20260224_183632.csv

====================================================================================================
✅ 掃描完成！
====================================================================================================
```

### CSV報告內容

匯出的CSV檔案包含以下欄位：

| 欄位名稱 | 說明 | 範例 |
|---------|------|------|
| symbol | 股票代碼 | 2330 |
| name | 股票名稱 | 台積電 |
| industry | 產業類別 | 半導體業 |
| pattern_name | 形態名稱 | W底 |
| pattern_type | 形態類型 | bullish |
| resonance_strength | 共振強度 | 1.00 |
| action | 建議動作 | buy |
| current_price | 當前價格 | 1915.00 |
| entry_price | 進場價 | 1650.00 |
| stop_loss | 停損價 | 1534.50 |
| target_1 | 目標價1 | 2100.00 |
| target_2 | 目標價2 | 2350.00 |
| risk_reward | 風報比 | 3.2 |
| timeframe | 依據週期 | Weekly |
| reason | 建議理由 | 多時間週期強勢多頭共振(100%)... |

---

## 💡 實戰案例

### 案例1: 每週固定選股流程

**目標**: 找出下週可進場的波段標的

```bash
# 週日晚上執行
python3 pattern_recognition/market_multi_timeframe_scanner.py \
  --timeframes W M \
  --min-resonance 0.80 \
  --bullish-only \
  --top 30 \
  --save-csv

# 結果: 得到30支週線月線共振的多頭股票
# 動作: 週一開盤觀察日線進場點
```

### 案例2: 特定產業深度分析

**目標**: 找出半導體產業的投資機會

```bash
# 掃描半導體產業（週線+月線）
python3 pattern_recognition/market_multi_timeframe_scanner.py \
  --industry 半導體 \
  --timeframes W M \
  --min-resonance 0.70 \
  --save-csv

# 再用日線確認進場點
python3 pattern_recognition/multi_timeframe_scanner.py \
  --symbol 2330 \
  --timeframes D W M \
  --show-suggestion
```

### 案例3: 短線交易機會

**目標**: 找出當日/隔日可進場的短線標的

```bash
# 日線+週線組合
python3 pattern_recognition/market_multi_timeframe_scanner.py \
  --timeframes D W \
  --min-resonance 0.60 \
  --bullish-only \
  --top 20

# 過濾風報比 > 2 的機會（需手動查看CSV）
```

### 案例4: 風險警示（找空頭信號）

**目標**: 找出手中持股是否出現空頭形態

```bash
# 掃描空頭機會
python3 pattern_recognition/market_multi_timeframe_scanner.py \
  --timeframes W M \
  --bearish-only \
  --min-resonance 0.80 \
  --save-csv

# 檢查CSV，看持股是否在列表中
```

---

## ⚙️ 效能優化建議

### 1. 分批掃描

全市場掃描需要較長時間，建議分批執行：

```bash
# 先測試少量股票
python3 pattern_recognition/market_multi_timeframe_scanner.py --limit 100

# 確認無誤後，全市場掃描
python3 pattern_recognition/market_multi_timeframe_scanner.py
```

### 2. 時間週期選擇

不同週期組合的掃描時間：

| 組合 | 平均時間（100支） | 建議用途 |
|------|-----------------|---------|
| D | ~2分鐘 | 短線交易 |
| D W | ~3分鐘 | 波段交易 |
| W M | ~4分鐘 | 長線投資 |
| D W M | ~5分鐘 | 完整分析 |

### 3. 產業過濾

先過濾產業可大幅加速：

```bash
# 僅掃描半導體（約50-100支）
python3 pattern_recognition/market_multi_timeframe_scanner.py \
  --industry 半導體 \
  --timeframes D W M
```

---

## 📋 掃描結果解讀

### 共振強度分級

| 等級 | 共振強度 | 建議倉位 | 操作策略 |
|------|---------|---------|---------|
| 🔥 強勢共振 | ≥80% | 100% | 全倉進場，嚴守止損 |
| ✅ 一般共振 | 60-80% | 50% | 半倉進場，分批建倉 |
| ⚠️ 信號分歧 | <60% | 0-20% | 觀望或小倉測試 |

### 風報比評估

| 風報比 | 評級 | 建議 |
|-------|------|------|
| ≥3 | 優秀 | 優先考慮 |
| 2-3 | 良好 | 可以進場 |
| 1-2 | 普通 | 謹慎評估 |
| <1 | 不佳 | 建議放棄 |

### 形態優先順序

**多頭形態優先順序**:
1. 破底翻W底（最安全）
2. 頭肩底（目標價大）
3. W底（經典形態）
4. 下飄旗形（中繼突破）

**空頭形態優先順序**:
1. M頭 + 頭肩頂（高風險）
2. 假突破（反轉確認）
3. 上飄旗形（趨勢延續）

---

## ⚠️ 注意事項

### 1. 數據要求

- 每支股票需至少60天日線數據
- 週線分析需至少20週數據
- 月線分析需至少12個月數據

### 2. 掃描限制

- 全市場掃描約需10-20分鐘
- MongoDB 需保持運行
- 建議非交易時間執行

### 3. 結果驗證

- CSV報告需人工審核
- 建議搭配K線圖確認
- 切勿盲目跟單

### 4. API限制

- FinMind API 每日600次限制
- 掃描不會觸發API（使用本地數據）
- 僅下載數據時會使用API

---

## 🔄 自動化建議

### Cron 定時執行

```bash
# 每週日晚上22:00執行週線月線掃描
0 22 * * 0 cd /Users/ming/Desktop/Stock/tw-stock-analysis && python3 pattern_recognition/market_multi_timeframe_scanner.py --timeframes W M --bullish-only --save-csv

# 每天下午15:00執行日線週線掃描
0 15 * * 1-5 cd /Users/ming/Desktop/Stock/tw-stock-analysis && python3 pattern_recognition/market_multi_timeframe_scanner.py --timeframes D W --top 30 --save-csv
```

### Shell 腳本包裝

創建 `scripts/daily_scan.sh`:

```bash
#!/bin/bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

echo "開始每日掃描..."
python3 pattern_recognition/market_multi_timeframe_scanner.py \
  --timeframes D W \
  --min-resonance 0.70 \
  --bullish-only \
  --top 50 \
  --save-csv

echo "掃描完成！"
```

---

## 📚 相關文檔

- [SENVISION_QUICKSTART.md](../SENVISION_QUICKSTART.md) - 單股分析指南
- [MULTI_TIMEFRAME_GUIDE.md](MULTI_TIMEFRAME_GUIDE.md) - 多時間週期理論
- [Readme.md](../Readme.md) - 系統完整文檔

---

## 💡 最佳實踐

### 推薦工作流程

1. **週日晚上** - 執行週線月線掃描，找出下週關注標的
2. **週一早上** - 檢視CSV報告，挑選5-10支重點股票
3. **每日盤中** - 用日線確認進場點
4. **每日收盤** - 更新持倉狀態，調整停損

### 選股標準

✅ **必要條件**:
- 共振強度 ≥ 70%
- 風報比 ≥ 2
- 成交量配合

✅ **加分條件**:
- 週線月線同時確認
- 產業熱門
- 基本面良好

---

**版本**: v2.1
**最後更新**: 2026-02-24
**維護者**: Ming

**祝您掃描順利，投資獲利！📊📈**
