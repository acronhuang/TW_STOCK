#!/bin/bash
#
# 日誌輪替腳本 — 由 weekly_log_cleanup launchd 排程呼叫
# 也可手動執行：bash scripts/log_rotation.sh
#
# 策略：
#   - 保留最近 7 天的日誌
#   - 單檔超過 50MB 視為異常，直接刪除
#   - launchd stdout/stderr 超過 10MB 截斷至最後 2000 行
#   - 清理空目錄
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_BASE="$PROJECT_DIR/logs"

# === 設定 ===
RETAIN_DAYS=7
MAX_FILE_SIZE_MB=50
LAUNCHD_MAX_MB=10

echo "[$(date +'%Y-%m-%d %H:%M:%S')] 日誌輪替開始"
echo "  保留天數: ${RETAIN_DAYS}"
echo "  日誌目錄: ${LOG_BASE}"

BEFORE=$(du -sm "$LOG_BASE" 2>/dev/null | cut -f1)
DELETED=0

# 1. 刪除超過保留天數的所有日誌
while IFS= read -r f; do
    rm -f "$f" && ((DELETED++))
done < <(find "$LOG_BASE" -type f -name "*.log" -mtime +${RETAIN_DAYS} 2>/dev/null)

echo "  已刪除 ${RETAIN_DAYS} 天前的日誌: $DELETED 個"

# 2. 刪除異常大的日誌（單檔 > MAX_FILE_SIZE_MB）
MAX_BYTES=$((MAX_FILE_SIZE_MB * 1024 * 1024))
LARGE_DELETED=0
while IFS= read -r f; do
    SIZE=$(stat -f%z "$f" 2>/dev/null || echo 0)
    if [ "$SIZE" -gt "$MAX_BYTES" ]; then
        echo "  刪除超大檔: $(basename "$f") ($((SIZE / 1024 / 1024))MB)"
        rm -f "$f" && ((LARGE_DELETED++))
    fi
done < <(find "$LOG_BASE" -type f -name "*.log" 2>/dev/null)
echo "  已刪除超大日誌: $LARGE_DELETED 個"

# 3. 截斷 launchd stdout/stderr 日誌
LAUNCHD_MAX_BYTES=$((LAUNCHD_MAX_MB * 1024 * 1024))
for f in "$LOG_BASE"/launchd_*.log; do
    [ -f "$f" ] || continue
    SIZE=$(stat -f%z "$f" 2>/dev/null || echo 0)
    if [ "$SIZE" -gt "$LAUNCHD_MAX_BYTES" ]; then
        tail -2000 "$f" > "${f}.tmp" && mv "${f}.tmp" "$f"
        echo "  截斷: $(basename "$f") (原 $((SIZE / 1024 / 1024))MB)"
    fi
done

# 4. 清理 api_server.log（超過 10MB 截斷）
for f in "$LOG_BASE"/api_server.log "$LOG_BASE"/api_server_err.log; do
    [ -f "$f" ] || continue
    SIZE=$(stat -f%z "$f" 2>/dev/null || echo 0)
    if [ "$SIZE" -gt "$LAUNCHD_MAX_BYTES" ]; then
        tail -2000 "$f" > "${f}.tmp" && mv "${f}.tmp" "$f"
        echo "  截斷: $(basename "$f") (原 $((SIZE / 1024 / 1024))MB)"
    fi
done

# 5. 清理空目錄
find "$LOG_BASE" -type d -empty -delete 2>/dev/null

AFTER=$(du -sm "$LOG_BASE" 2>/dev/null | cut -f1)
FREED=$((BEFORE - AFTER))

echo ""
echo "  清理前: ${BEFORE}MB"
echo "  清理後: ${AFTER}MB"
echo "  釋放:   ${FREED}MB"
echo "  剩餘檔案: $(find "$LOG_BASE" -type f -name "*.log" 2>/dev/null | wc -l | tr -d ' ') 個"
echo "[$(date +'%Y-%m-%d %H:%M:%S')] 日誌輪替完成"
