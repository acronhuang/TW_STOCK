#!/bin/bash
#
# 形態學12神招 - 啟動腳本
# 解決Python環境問題
#

# 尋找正確的Python
PYTHON_CMD=""

# 檢查可能的Python路徑
if /Library/Frameworks/Python.framework/Versions/3.14/bin/python3 -c "import pymongo" 2>/dev/null; then
    PYTHON_CMD="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
elif /usr/local/bin/python3 -c "import pymongo" 2>/dev/null; then
    PYTHON_CMD="/usr/local/bin/python3"
elif python3 -c "import pymongo" 2>/dev/null; then
    PYTHON_CMD="python3"
else
    echo "❌ 錯誤: 找不到安裝了 pymongo 的 Python"
    echo ""
    echo "請執行以下命令安裝必要套件："
    echo "  python3 -m pip install pymongo pandas numpy --user"
    exit 1
fi

echo "✅ 使用 Python: $PYTHON_CMD"
echo ""

# 切換到專案目錄
cd /home/mdsadmin/Stock/tw-stock-analysis

# 執行形態掃描
$PYTHON_CMD pattern_recognition/pattern_cli.py "$@"
