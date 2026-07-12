# 已廢棄的腳本

這些腳本已被新的統一下載系統取代。

## 替代方案

### 完整下載器 → unified_downloader.py

**舊腳本**（已廢棄）:
- `download_all_finmind_data.py`
- `download_complete_finmind_v2.py`
- `unified_download.py`
- `background_full_download.py`

**新腳本**:
```bash
python3 src/downloaders/unified_downloader.py --all
```

### 財報下載器 → unified_downloader.py

**舊腳本**（已廢棄）:
- `batch_download_all_financials.py`
- `download_financial_reports.py`
- `fetch_financials.py`

**新腳本**:
```bash
python3 src/downloaders/unified_downloader.py --categories 基本面
```

## 為什麼被廢棄？

1. **功能重複**: 95% 的程式碼重複
2. **維護困難**: 修改需要同步多個檔案
3. **設計不良**: 缺乏模組化
4. **難以擴展**: 新增功能需要大量重複工作

## 新架構優勢

- ✅ 單一入口 (`unified_downloader.py`)
- ✅ 模組化設計 (`src/downloaders/`)
- ✅ 完整測試覆蓋
- ✅ 詳細日誌記錄
- ✅ 配置驅動（`table_config.py`）
- ✅ 統一驗證邏輯

## 遷移日期

2026-02-21

## 可以刪除嗎？

建議保留 30 天後再永久刪除，以防需要回溯。
