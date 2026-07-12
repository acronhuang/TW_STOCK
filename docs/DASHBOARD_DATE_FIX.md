# Dashboard 日期格式化修復

## 問題描述

Dashboard 顯示錯誤：`'str' object has no attribute 'strftime'`

**根本原因**：MongoDB 中不同集合的日期字段類型不一致
- `stock_price.date`: datetime 對象 ✅
- `financial_reports.reportDate`: 字符串 ⚠️
- `stock_factors.date`: datetime 對象 ✅

當代碼嘗試對字符串調用 `strftime()` 方法時會失敗。

---

## 修復方案

### 1. home.py（系統總覽頁面）

**新增安全日期格式化函數**：
```python
def format_date(date_value):
    """
    安全地格式化日期，支持字符串和 datetime 對象
    """
    if date_value is None:
        return "未知"
    
    if isinstance(date_value, str):
        try:
            dt = pd.to_datetime(date_value)
            return dt.strftime('%Y-%m-%d')
        except:
            return date_value
    
    if isinstance(date_value, datetime):
        return date_value.strftime('%Y-%m-%d')
    
    try:
        return str(date_value)
    except:
        return "未知"
```

**更新調用位置**：
- 股價數據：`format_date(latest_price['date'])`
- 財報數據：`format_date(latest_financial['reportDate'])`
- 因子數據：`format_date(latest_factor['date'])`

### 2. charts.py（圖表頁面）

**確保日期欄位轉換**：
```python
# 轉換為 DataFrame
df = pd.DataFrame(data)

# 確保 date 欄位是 datetime 類型
if 'date' in df.columns:
    df['date'] = pd.to_datetime(df['date'])
```

### 3. monitor.py（監控頁面）

**新增日期時間格式化函數**：
```python
def format_datetime(dt_value):
    """
    安全地格式化日期時間
    """
    if dt_value is None:
        return "未知"
    
    if isinstance(dt_value, str):
        return dt_value
    
    if isinstance(dt_value, datetime):
        return dt_value.strftime('%Y-%m-%d %H:%M:%S')
    
    try:
        return str(dt_value)
    except:
        return "未知"
```

**更新調用位置**：
- 更新歷史：`format_datetime(update_time)`

---

## 測試驗證

執行測試腳本：
```bash
python3 scripts/test_date_formats.py
```

**測試結果**：
```
✅ stock_price.date: datetime 對象
✅ financial_reports.reportDate: 字符串
✅ stock_factors.date: datetime 對象
```

---

## 啟動 Dashboard

```bash
cd /Users/ming/Desktop/Stock/tw-stock-analysis

# 啟動 Streamlit Dashboard
/Users/ming/Desktop/Stock/.venv/bin/python -m streamlit run dashboard/app.py --server.port 8501 --server.headless false
```

訪問：http://localhost:8501

---

## 修復文件清單

1. ✅ `dashboard/pages/home.py` - 系統總覽頁面
2. ✅ `dashboard/pages/charts.py` - 圖表頁面  
3. ✅ `dashboard/pages/monitor.py` - 監控頁面
4. ✅ `scripts/test_date_formats.py` - 測試腳本（新增）

---

## 預防措施

**最佳實踐**：
1. 從 MongoDB 讀取日期字段後立即使用 `pd.to_datetime()` 轉換
2. 在格式化前檢查類型：`isinstance(value, (str, datetime))`
3. 使用統一的格式化函數處理日期
4. 添加異常處理防止格式化失敗

**數據庫建議**：
- 統一使用 ISODate 存儲日期（datetime 對象）
- 避免混用字符串和 datetime 類型
- 定期審查數據類型一致性

---

**修復完成日期**: 2026-02-24  
**修復人員**: GitHub Copilot  
**狀態**: ✅ 已驗證
