#!/bin/bash
# P2 腳本清理 - 移動重複腳本到 deprecated 目錄
# 根據 CODE_REFACTOR_EXECUTION_PLAN.md 和 REFACTOR_AUDIT_REPORT.md

set -e

echo "=================================="
echo "🧹 P2 程式碼重構 - 清理重複腳本"
echo "=================================="
echo ""

cd /home/mdsadmin/Stock/tw-stock-analysis

# 創建 deprecated 目錄結構
echo "📁 創建 deprecated 目錄結構..."
mkdir -p scripts/deprecated/downloaders
mkdir -p scripts/deprecated/financial_downloaders
mkdir -p scripts/deprecated/calculators
echo "✅ 目錄已創建"
echo ""

# 記錄需要移動的檔案
MOVED_FILES=0
MISSING_FILES=0

# A. 完整下載器（保留 complete_data_download_pro.py，其他移除）
echo "📋 第 1 批：完整下載器（低風險）"
echo "-----------------------------------"

DOWNLOADERS=(
    "download_all_finmind_data.py"
    "download_complete_finmind_v2.py"
    "unified_download.py"
    "background_full_download.py"
)

for file in "${DOWNLOADERS[@]}"; do
    if [ -f "scripts/$file" ]; then
        echo "  ✅ 移動: $file"
        mv "scripts/$file" "scripts/deprecated/downloaders/"
        ((MOVED_FILES++))
    else
        echo "  ⏭️  跳過: $file (不存在)"
        ((MISSING_FILES++))
    fi
done

echo ""

# B. 財報下載器
echo "📋 第 2 批：財報下載器（低風險）"
echo "-----------------------------------"

FINANCIAL_DOWNLOADERS=(
    "batch_download_all_financials.py"
    "download_financial_reports.py"
    "fetch_financials.py"
)

for file in "${FINANCIAL_DOWNLOADERS[@]}"; do
    if [ -f "scripts/$file" ]; then
        echo "  ✅ 移動: $file"
        mv "scripts/$file" "scripts/deprecated/financial_downloaders/"
        ((MOVED_FILES++))
    else
        echo "  ⏭️  跳過: $file (不存在)"
        ((MISSING_FILES++))
    fi
done

echo ""

# C. 創建 README 說明
echo "📝 創建 deprecated 目錄說明文件..."

cat > scripts/deprecated/README.md << 'EOF'
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
EOF

echo "✅ README.md 已創建"
echo ""

# 統計結果
echo "=================================="
echo "📊 清理完成統計"
echo "=================================="
echo "已移動檔案: $MOVED_FILES 個"
echo "不存在檔案: $MISSING_FILES 個"
echo ""

# 顯示目錄結構
echo "📁 deprecated 目錄結構:"
tree scripts/deprecated 2>/dev/null || find scripts/deprecated -type f

echo ""
echo "=================================="
echo "✅ P2 腳本清理完成"
echo "=================================="
echo ""
echo "📝 下一步："
echo "   1. 檢查 scripts/deprecated/ 目錄"
echo "   2. 確認沒有其他腳本依賴這些檔案"
echo "   3. 30 天後可永久刪除"
echo ""
