#!/bin/bash
# =============================================================================
# SenVision 每日自動分析腳本
#
# 執行流程：
#   [1/4] 更新股價 + 三大法人 + PE/PB（TWSE/TPEX 免費 API）
#   [2/4] 同步最新季報（TWSE/TPEX OpenAPI，申報季期間每日增量）
#   [3/4] 計算技術因子（RSI / KD / MACD / BB，本機運算）
#   [4/4] 全市場多時間框架技術掃描
#   清理 30 天前舊檔
#
# API 預算：
#   本腳本只使用 TWSE/TPEX 免費 API，不消耗 FinMind 600次/小時額度。
#   FinMind 額度保留給：
#     - finmind_quarterly_backfill.py（手動，五年季報回補）
#     - weekly_outstanding_shares（週日 2AM，launchd）
#
# 排程（crontab）：
#   0 17 * * 1-5  /path/to/daily_senvision.sh
#
# 作者：SenVision Team  日期：2026-02-25
# =============================================================================

set -euo pipefail

# 確保 Homebrew 路徑在 PATH 中（launchd 環境下 PATH 不含 /opt/homebrew/bin）
export PATH="/opt/homebrew/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON="/home/mdsadmin/Stock/.venv/bin/python3"
LOG_DIR="$PROJECT_DIR/logs"
RESULTS_DIR="$PROJECT_DIR/results"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
TODAY="$(date +%Y%m%d)"
LOG="$LOG_DIR/daily_senvision_${TIMESTAMP}.log"

mkdir -p "$LOG_DIR" "$RESULTS_DIR"

# 輸出同時寫入終端與日誌
exec > >(tee -a "$LOG") 2>&1

# ── MongoDB 連線檢查（斷線自動啟動 + 重試）───────────────────
check_mongodb() {
    mongosh --eval "db.runCommand('ping').ok" --quiet 2>/dev/null | grep -q "1"
}

echo "[pre] 檢查 MongoDB 連線..."
if ! check_mongodb; then
    echo "  ⚠️  MongoDB 未連線，嘗試啟動..."
    # 優先用 mongod --fork（brew services 在 launchd 環境下常失敗）
    mongod --config /opt/homebrew/etc/mongod.conf --fork 2>/dev/null || \
        brew services start mongodb-community 2>/dev/null || true
    # 等待最多 30 秒
    for i in $(seq 1 6); do
        sleep 5
        if check_mongodb; then
            echo "  ✅ MongoDB 已啟動（等待 ${i}x5 秒）"
            break
        fi
        echo "  ⏳ 等待中... (${i}/6)"
    done
    if ! check_mongodb; then
        echo "  ❌ MongoDB 無法啟動，中止執行"
        bash "$SCRIPT_DIR/notify_failure.sh" "❌ MongoDB 無法啟動，每日分析中止"
        exit 1
    fi
else
    echo "  ✅ MongoDB 連線正常"
fi

echo ""
echo "============================================================"
echo "  SenVision 每日自動分析"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

# ── [1/4] 股價 + 三大法人 + PE/PB ──────────────────────────────
echo ""
echo "[1/4] 更新股價、三大法人籌碼、PE/PB（TWSE / TPEX 免費 API）..."
"$PYTHON" "$SCRIPT_DIR/twse_daily_update.py" || {
    echo ""
    echo "  ⚠️  股價更新失敗，繼續執行掃描（使用既有資料）"
}

# 隔日自動回補近期缺漏交易日（法人 T86 / PE-PB 有 T+1 延遲，當日常抓不到）
# 掃描近 7 天「有股價但法人或 PE/PB 缺」的過去交易日，逐日用 twse_daily_update --date 補齊。
echo ""
echo "[1.5/4] 回補近期缺漏交易日（法人 / PE-PB，T+1 延遲）..."
"$PYTHON" "$SCRIPT_DIR/backfill_recent_gaps.py" --lookback 7 || \
    echo "  ⚠️ 缺漏回補腳本執行失敗（不影響後續步驟）"

# ── [2/4] 季報即時同步（申報季期間每日增量收集）──────────────
echo ""
echo "[2/4] 同步最新季報（TWSE + TPEX OpenAPI）..."
"$PYTHON" "$SCRIPT_DIR/twse_quarterly_sync.py" || {
    echo "  ⚠️  季報同步失敗，繼續執行（不影響技術掃描）"
}

# ── [3/4] 技術因子增量計算（RSI / KD / MACD / BB 等）────────
# 本腳本於收盤後（17:00）執行，當日 OHLCV 已定案，故 end-date 帶「今天」把當日因子也算進去
# （預設 end_date=昨天會讓 stock_factors 永遠落後股價 1 個交易日）。
echo ""
echo "[3/4] 計算近 10 日技術因子（stock_factors 增量，含今日）..."
FACTOR_START="$(date -v-10d +%Y-%m-%d 2>/dev/null || date -d '10 days ago' +%Y-%m-%d)"
FACTOR_END="$(date +%Y-%m-%d)"
"$PYTHON" "$SCRIPT_DIR/parallel_factor_calculation.py" \
    --workers 4 \
    --start-date "$FACTOR_START" \
    --end-date "$FACTOR_END" || {
    echo "  ⚠️  因子計算失敗，繼續執行（不影響本次掃描）"
}

# ── [4/4] 全市場技術掃描 ──────────────────────────────────────
echo ""
echo "[4/4] 執行全市場技術掃描（日線 + 週線）..."

SCAN_CSV="$RESULTS_DIR/scan_auto_${TODAY}.csv"

"$PYTHON" "$SCRIPT_DIR/senvision_market_scan.py" \
    --timeframes D W \
    --days 500 \
    --min-rrr 0.5 \
    --min-score 0.60 \
    --top 50 \
    --workers 4 \
    --output "$SCAN_CSV"

# 掃描結果摘要
if [ -f "$SCAN_CSV" ]; then
    LINE_COUNT=$(wc -l < "$SCAN_CSV" | tr -d ' ')
    echo ""
    echo "  掃描完成：$SCAN_CSV"
    echo "     共 $((LINE_COUNT - 1)) 個信號"
else
    echo "  ⚠️  掃描未產生結果檔案"
fi

# ── 清理舊檔（保留最近 30 天）─────────────────────────────
echo ""
echo "清理 30 天前的舊日誌與掃描結果..."
find "$LOG_DIR"     -name "daily_senvision_*.log"   -mtime +30 -delete 2>/dev/null || true
find "$RESULTS_DIR" -name "scan_auto_*.csv"          -mtime +30 -delete 2>/dev/null || true
echo "  清理完成"

# ── 完成摘要 ─────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  完成！$(date '+%Y-%m-%d %H:%M:%S')"
if [ -f "$SCAN_CSV" ]; then
    echo "  今日掃描結果：$SCAN_CSV"
fi
echo "============================================================"
echo ""
