#!/bin/bash
# 形態學12神招 - 快速啟動腳本
# 作者: 技術分析系統
# 日期: 2026-02-13

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# 專案目錄
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 顯示標題
show_header() {
    echo -e "${CYAN}${BOLD}"
    echo "================================================================================"
    echo "                    形態學12神招 - 快速啟動工具"
    echo "================================================================================"
    echo -e "${NC}"
}

# 顯示選單
show_menu() {
    echo -e "${BOLD}請選擇功能:${NC}"
    echo ""
    echo -e "${GREEN}  1.${NC} 掃描全市場 - 尋找所有買入機會"
    echo -e "${GREEN}  2.${NC} 掃描全市場 - 尋找所有賣出信號"
    echo -e "${GREEN}  3.${NC} 顯示前20個最佳買入機會"
    echo -e "${GREEN}  4.${NC} 查看特定股票型態"
    echo -e "${GREEN}  5.${NC} 進階篩選 - 自訂條件"
    echo -e "${GREEN}  6.${NC} 列出所有支援的型態"
    echo -e "${GREEN}  7.${NC} 執行系統測試"
    echo -e "${GREEN}  8.${NC} 查看使用說明"
    echo -e "${RED}  9.${NC} 離開"
    echo ""
    echo -n "請輸入選項 [1-9]: "
}

# 檢查Python環境
check_python() {
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}錯誤: 找不到 python3${NC}"
        echo "請先安裝 Python 3.8 或以上版本"
        exit 1
    fi
}

# 檢查MongoDB
check_mongodb() {
    if ! pgrep -x "mongod" > /dev/null; then
        echo -e "${YELLOW}警告: MongoDB 似乎未運行${NC}"
        echo -e "某些功能可能無法使用"
        echo -n "是否繼續? (y/n): "
        read -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            exit 0
        fi
    fi
}

# 功能1: 掃描全市場 - 買入信號
scan_buy_signals() {
    echo -e "\n${CYAN}${BOLD}掃描全市場 - 尋找買入機會${NC}\n"
    
    echo -n "請輸入最低信心度 (0.70-0.95, 預設0.75): "
    read -r confidence
    confidence=${confidence:-0.75}
    
    echo -n "是否儲存到資料庫? (y/n, 預設n): "
    read -r save_db
    
    cmd="python3 $SCRIPT_DIR/pattern_cli.py scan --buy --confidence $confidence"
    
    if [[ "$save_db" =~ ^[Yy]$ ]]; then
        cmd="$cmd --save-db"
    fi
    
    echo -e "\n${YELLOW}執行掃描...${NC}\n"
    eval "$cmd"
}

# 功能2: 掃描全市場 - 賣出信號
scan_sell_signals() {
    echo -e "\n${CYAN}${BOLD}掃描全市場 - 尋找賣出信號${NC}\n"
    
    echo -n "請輸入最低信心度 (0.70-0.95, 預設0.75): "
    read -r confidence
    confidence=${confidence:-0.75}
    
    echo -n "是否儲存到資料庫? (y/n, 預設n): "
    read -r save_db
    
    cmd="python3 $SCRIPT_DIR/pattern_cli.py scan --sell --confidence $confidence"
    
    if [[ "$save_db" =~ ^[Yy]$ ]]; then
        cmd="$cmd --save-db"
    fi
    
    echo -e "\n${YELLOW}執行掃描...${NC}\n"
    eval "$cmd"
}

# 功能3: 顯示最佳機會
show_top_opportunities() {
    echo -e "\n${CYAN}${BOLD}顯示最佳投資機會${NC}\n"
    
    echo -n "請輸入顯示數量 (預設20): "
    read -r num
    num=${num:-20}
    
    echo "請選擇信號類型:"
    echo "  1. 買入信號"
    echo "  2. 賣出信號"
    echo -n "選擇 [1-2]: "
    read -r signal_type
    
    cmd="python3 $SCRIPT_DIR/pattern_cli.py top --n $num"
    
    if [[ "$signal_type" == "2" ]]; then
        cmd="$cmd --sell"
    fi
    
    echo -e "\n${YELLOW}正在分析...${NC}\n"
    eval "$cmd"
}

# 功能4: 查看特定股票
view_stock() {
    echo -e "\n${CYAN}${BOLD}查看特定股票型態${NC}\n"
    
    echo -n "請輸入股票代碼 (例如: 2330): "
    read -r symbol
    
    if [[ -z "$symbol" ]]; then
        echo -e "${RED}錯誤: 請輸入股票代碼${NC}"
        return
    fi
    
    echo -e "\n${YELLOW}分析中...${NC}\n"
    python3 "$SCRIPT_DIR/pattern_cli.py" stock "$symbol"
}

# 功能5: 進階篩選
advanced_filter() {
    echo -e "\n${CYAN}${BOLD}進階篩選 - 自訂條件${NC}\n"
    
    echo -n "最小潛在獲利% (預設10): "
    read -r min_gain
    min_gain=${min_gain:-10}
    
    echo -n "最小風險報酬比 (預設2.0): "
    read -r min_rr
    min_rr=${min_rr:-2.0}
    
    echo -n "最大形成天數 (預設60): "
    read -r max_days
    max_days=${max_days:-60}
    
    echo -n "顯示數量 (預設20): "
    read -r num
    num=${num:-20}
    
    cmd="python3 $SCRIPT_DIR/pattern_cli.py filter"
    cmd="$cmd --min-gain $min_gain --min-rr $min_rr --max-days $max_days --n $num"
    
    echo -e "\n${YELLOW}篩選中...${NC}\n"
    eval "$cmd"
}

# 功能6: 列出所有型態
list_patterns() {
    echo -e "\n${CYAN}${BOLD}列出所有支援的型態${NC}\n"
    python3 "$SCRIPT_DIR/pattern_cli.py" list
}

# 功能7: 執行測試
run_tests() {
    echo -e "\n${CYAN}${BOLD}執行系統測試${NC}\n"
    
    echo "請選擇測試類型:"
    echo "  1. 執行所有測試"
    echo "  2. 型態檢測測試"
    echo "  3. 掃描器測試"
    echo "  4. 篩選器測試"
    echo "  5. 匯出功能測試"
    echo "  6. 效能測試"
    echo -n "選擇 [1-6]: "
    read -r test_type
    
    case $test_type in
        1) test_arg="all" ;;
        2) test_arg="pattern" ;;
        3) test_arg="scanner" ;;
        4) test_arg="screener" ;;
        5) test_arg="export" ;;
        6) test_arg="performance" ;;
        *) test_arg="all" ;;
    esac
    
    echo -e "\n${YELLOW}執行測試...${NC}\n"
    python3 "$SCRIPT_DIR/test_patterns.py" --test "$test_arg"
}

# 功能8: 查看說明
show_help() {
    echo -e "\n${CYAN}${BOLD}使用說明${NC}\n"
    
    if [[ -f "$SCRIPT_DIR/PATTERN_12_MASTERS_GUIDE.md" ]]; then
        echo "正在開啟使用指南..."
        if command -v less &> /dev/null; then
            less "$SCRIPT_DIR/PATTERN_12_MASTERS_GUIDE.md"
        else
            cat "$SCRIPT_DIR/PATTERN_12_MASTERS_GUIDE.md"
        fi
    else
        echo -e "${YELLOW}找不到使用指南檔案${NC}"
        echo ""
        echo "基本使用方法:"
        echo ""
        echo "1. 命令行使用:"
        echo "   python3 pattern_cli.py scan              # 掃描全市場"
        echo "   python3 pattern_cli.py scan --buy        # 只掃描買入信號"
        echo "   python3 pattern_cli.py top --n 20        # 顯示前20個機會"
        echo "   python3 pattern_cli.py stock 2330        # 查看特定股票"
        echo ""
        echo "2. Python程式使用:"
        echo "   from pattern_recognition.market_scanner import MarketScanner"
        echo "   scanner = MarketScanner()"
        echo "   results = scanner.scan_market()"
        echo ""
        echo "詳細說明請參考: PATTERN_12_MASTERS_GUIDE.md"
    fi
}

# 主程式
main() {
    # 顯示標題
    show_header
    
    # 檢查環境
    check_python
    check_mongodb
    
    # 主迴圈
    while true; do
        show_menu
        read -r choice
        
        case $choice in
            1) scan_buy_signals ;;
            2) scan_sell_signals ;;
            3) show_top_opportunities ;;
            4) view_stock ;;
            5) advanced_filter ;;
            6) list_patterns ;;
            7) run_tests ;;
            8) show_help ;;
            9)
                echo -e "\n${GREEN}謝謝使用，再見！${NC}\n"
                exit 0
                ;;
            *)
                echo -e "${RED}無效的選項，請重新選擇${NC}"
                ;;
        esac
        
        echo ""
        echo -n "按 Enter 鍵繼續..."
        read -r
        clear
        show_header
    done
}

# 執行主程式
main
