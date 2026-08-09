#!/bin/bash
#
# 每小時自動資料更新腳本
# 用途：定期下載所有 FinMind 台股資料（技術面、基本面、籌碼面、衍生性商品）
# 特點：完整日誌記錄、自動跳過已存在資料、API 配額管理、自動日誌輪替
#

# 注意：不使用 set -e，允許單一類別失敗後繼續執行其他類別


# 設定路徑
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs/hourly_updates"
LOG_BASE="$PROJECT_DIR/logs"

# 建立日誌目錄
mkdir -p "$LOG_DIR"

# 時間戳記
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DATE=$(date +%Y-%m-%d)

# 日誌檔案 — 所有輸出只寫檔案，不輸出到 stdout（避免 launchd 重複寫入）
LOG_FILE="$LOG_DIR/hourly_update_${TIMESTAMP}.log"
SUMMARY_FILE="$LOG_DIR/daily_summary_$(date +%Y%m%d).log"

# === 日誌輪替設定 ===
LOG_RETAIN_DAYS=7        # 保留天數
LOG_MAX_SIZE_MB=50       # 單檔超過此大小視為異常，直接刪除
LAUNCHD_MAX_SIZE_MB=10   # launchd stdout/stderr 超過此大小則截斷

# 函數：記錄訊息（只寫入檔案）
log_info()    { echo "[$(date +'%Y-%m-%d %H:%M:%S')] INFO  $1" >> "$LOG_FILE"; }
log_warn()    { echo "[$(date +'%Y-%m-%d %H:%M:%S')] WARN  $1" >> "$LOG_FILE"; }
log_error()   { echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR $1" >> "$LOG_FILE"; }
log_success() { echo "[$(date +'%Y-%m-%d %H:%M:%S')] OK    $1" >> "$LOG_FILE"; }

# 函數：檢查 API Token
check_api_token() {
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        log_error ".env 檔案不存在"
        exit 1
    fi

    TOKEN=$(grep FINMIND_API_TOKEN "$PROJECT_DIR/.env" | cut -d'=' -f2)
    if [ -z "$TOKEN" ]; then
        log_error "找不到 FINMIND_API_TOKEN"
        exit 1
    fi

    export FINMIND_API_TOKEN="$TOKEN"
    log_info "API Token 已載入"
}

# 函數：顯示標題
print_header() {
    {
        echo "========================================================================"
        echo "每小時自動資料更新系統"
        echo "========================================================================"
        echo "日期: $DATE"
        echo "時間: $(date +'%H:%M:%S')"
        echo "日誌檔: $LOG_FILE"
        echo "========================================================================"
        echo ""
    } >> "$LOG_FILE"
}

# 函數：下載資料
download_data() {
    local category=$1
    local start_time=$(date +%s)

    log_info "開始下載: $category"

    # 執行下載 — 只寫入日誌檔，不輸出到 stdout
    #
    # 2026-07-19 修：原本寫成 `if python3 ... | head -500 >> LOG; then`，
    # 但 pipeline 的結束狀態取自最後一個指令（head），head 幾乎永遠成功
    # → download_data() 恆回 0 → 永遠走 log_success、永遠不觸發 notify_failure.sh。
    # 實測每次執行有 287~435 個 ERROR 仍回報「OK 下載完成」，
    # 這是本專案多起「靜默失效」能長期不被發現的共同機制。
    # 改用 PIPESTATUS[0] 取 python 自己的結束碼。
    python3 "$PROJECT_DIR/src/downloaders/unified_downloader.py" \
        --categories "$category" \
        2>&1 | head -500 >> "$LOG_FILE"
    local rc=${PIPESTATUS[0]}

    if [ "$rc" -eq 0 ]; then

        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        log_success "$category 下載完成 (耗時: ${duration}s)"
        return 0
    else
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        log_error "$category 下載失敗 (耗時: ${duration}s)"
        return 1
    fi
}

# 函數：生成每日總結
generate_summary() {
    local total_success=$1
    local total_failed=$2
    local total_duration=$3

    {
        echo ""
        echo "========================================================================"
        echo "更新總結 - $(date +'%Y-%m-%d %H:%M:%S')"
        echo "========================================================================"
        echo "成功: $total_success 個類別"
        echo "失敗: $total_failed 個類別"
        echo "總耗時: $total_duration 秒"
        echo "詳細日誌: $LOG_FILE"
        echo "========================================================================"
    } >> "$SUMMARY_FILE"
}

# 函數：日誌輪替 — 每次執行時自動清理
cleanup_old_logs() {
    log_info "日誌輪替開始（保留 ${LOG_RETAIN_DAYS} 天）..."
    local deleted=0

    # 1. 刪除超過保留天數的日誌
    while IFS= read -r f; do
        rm -f "$f" && ((deleted++))
    done < <(find "$LOG_DIR" -name "*.log" -mtime +${LOG_RETAIN_DAYS} 2>/dev/null)

    while IFS= read -r f; do
        rm -f "$f" && ((deleted++))
    done < <(find "$LOG_BASE" -maxdepth 1 -name "unified_download_*.log" -mtime +${LOG_RETAIN_DAYS} 2>/dev/null)

    # 2. 刪除異常大的日誌檔（超過 LOG_MAX_SIZE_MB）
    local max_bytes=$((LOG_MAX_SIZE_MB * 1024 * 1024))
    while IFS= read -r f; do
        local size
        # stat -c%s 為 GNU/Linux 語法，-f%z 為 BSD/macOS；本專案由 macOS 移機至 Ubuntu，
        # 原本只有 BSD 版 → 在 Linux 恆回 0，日誌輪替靜默失效（2026-07-19 修）
        size=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null || echo 0)
        if [ "$size" -gt "$max_bytes" ]; then
            log_warn "刪除異常大的日誌: $(basename "$f") ($(( size / 1024 / 1024 ))MB)"
            rm -f "$f" && ((deleted++))
        fi
    done < <(find "$LOG_DIR" -name "*.log" 2>/dev/null)

    while IFS= read -r f; do
        local size
        # stat -c%s 為 GNU/Linux 語法，-f%z 為 BSD/macOS；本專案由 macOS 移機至 Ubuntu，
        # 原本只有 BSD 版 → 在 Linux 恆回 0，日誌輪替靜默失效（2026-07-19 修）
        size=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null || echo 0)
        if [ "$size" -gt "$max_bytes" ]; then
            log_warn "刪除異常大的日誌: $(basename "$f") ($(( size / 1024 / 1024 ))MB)"
            rm -f "$f" && ((deleted++))
        fi
    done < <(find "$LOG_BASE" -maxdepth 1 -name "unified_download_*.log" 2>/dev/null)

    # 3. 截斷所有 launchd stdout/stderr 日誌
    local launchd_max_bytes=$((LAUNCHD_MAX_SIZE_MB * 1024 * 1024))
    for f in "$LOG_BASE"/launchd_*.log; do
        [ -f "$f" ] || continue
        local size
        # stat -c%s 為 GNU/Linux 語法，-f%z 為 BSD/macOS；本專案由 macOS 移機至 Ubuntu，
        # 原本只有 BSD 版 → 在 Linux 恆回 0，日誌輪替靜默失效（2026-07-19 修）
        size=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null || echo 0)
        if [ "$size" -gt "$launchd_max_bytes" ]; then
            tail -2000 "$f" > "${f}.tmp" && mv "${f}.tmp" "$f"
            log_info "已截斷 $(basename "$f") (原 $(( size / 1024 / 1024 ))MB)"
        fi
    done

    local remaining
    remaining=$(find "$LOG_DIR" -name "*.log" 2>/dev/null | wc -l | tr -d ' ')
    log_info "日誌輪替完成: 刪除 $deleted 個, 剩餘 $remaining 個"
}

# 函數：確保 MongoDB 運行
ensure_mongodb() {
    if mongosh --eval "db.runCommand('ping').ok" --quiet 2>/dev/null | grep -q "1"; then
        return 0
    fi
    log_warn "MongoDB 未連線，嘗試啟動..."
    mongod --config /opt/homebrew/etc/mongod.conf --fork 2>/dev/null || true
    for i in $(seq 1 6); do
        sleep 5
        if mongosh --eval "db.runCommand('ping').ok" --quiet 2>/dev/null | grep -q "1"; then
            log_info "MongoDB 已啟動"
            return 0
        fi
    done
    log_error "MongoDB 無法啟動，中止執行"
    return 1
}

# 主程式
main() {
    cd "$PROJECT_DIR"

    # 顯示標題
    print_header

    # 日誌輪替（每次執行時自動清理）
    cleanup_old_logs

    # 確保 MongoDB 運行
    if ! ensure_mongodb; then
        bash "$SCRIPT_DIR/notify_failure.sh" "❌ MongoDB 無法啟動，每小時資料更新中止"
        exit 1
    fi

    # 檢查 API Token
    check_api_token

    # 開始時間
    TOTAL_START=$(date +%s)

    # 下載類別列表（根據重要性排序）
    # 共 5 大類別，涵蓋 43 個 FinMind 資料表
    CATEGORIES=("技術面" "基本面" "籌碼面" "衍生性商品" "其他")
    TOTAL_CATEGORIES=${#CATEGORIES[@]}

    SUCCESS_COUNT=0
    FAILED_COUNT=0
    FAILED_LIST=""
    CURRENT_INDEX=0
    STATE_FILE="$LOG_BASE/.hourly_notify_state"

    # 逐一下載各類別
    for category in "${CATEGORIES[@]}"; do
        ((CURRENT_INDEX++))

        log_info "========================================"
        log_info "類別 [$CURRENT_INDEX/$TOTAL_CATEGORIES]: $category"
        log_info "========================================"

        if download_data "$category"; then
            ((SUCCESS_COUNT++))
        else
            ((FAILED_COUNT++))
            FAILED_LIST="${FAILED_LIST}${category} "
            log_warn "繼續處理下一個類別..."
        fi

        # 類別之間等待 5 秒（避免 API 過載）
        if [ $CURRENT_INDEX -lt $TOTAL_CATEGORIES ]; then
            sleep 5
        fi
    done

    # 結束時間
    TOTAL_END=$(date +%s)
    TOTAL_DURATION=$((TOTAL_END - TOTAL_START))

    # 生成總結
    generate_summary "$SUCCESS_COUNT" "$FAILED_COUNT" "$TOTAL_DURATION"

    # 最終狀態
    if [ $FAILED_COUNT -eq 0 ]; then
        log_success "所有類別下載完成！"
        rm -f "$STATE_FILE"
        exit 0
    else
        log_warn "部分類別下載失敗，請檢查日誌"

        # 通知節流（2026-07-19 加）。
        # 背景：download_data() 先前因 `| head` 遮蔽結束碼而恆回成功，失敗從不通知；
        # 修好之後若照原樣每次都發，會變成「每小時一則 LINE」的噪音
        # （見記憶 evening-digest-noise-reduction：曾特意把 ~15 則降到 2-3 則）。
        # 規則：同一組失敗類別，每 12 小時最多通知一次；失敗組合改變則立即通知。
        local sig="${FAILED_COUNT}:${FAILED_LIST}"
        local now_ts=$(date +%s)
        local last_sig="" last_ts=0
        if [ -f "$STATE_FILE" ]; then
            last_sig=$(sed -n 1p "$STATE_FILE")
            last_ts=$(sed -n 2p "$STATE_FILE")
        fi

        if [ "$sig" != "$last_sig" ] || [ $((now_ts - last_ts)) -ge 43200 ]; then
            bash "$SCRIPT_DIR/notify_failure.sh" \
                "⚠️ 每小時資料更新：${FAILED_COUNT}/${TOTAL_CATEGORIES} 類別失敗（成功 ${SUCCESS_COUNT}）
失敗類別：${FAILED_LIST}
（相同失敗每 12 小時最多通知一次）"
            printf '%s\n%s\n' "$sig" "$now_ts" > "$STATE_FILE"
            log_info "已發送失敗通知"
        else
            log_info "失敗組合與上次相同且未逾 12 小時，略過通知（sig=$sig）"
        fi
        exit 1
    fi
}

# 執行主程式
main "$@"
