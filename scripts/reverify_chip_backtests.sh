#!/bin/bash
# 籌碼面回測重驗（institutional_flow 欄位錯位修復後）
#
# 2026-07-19 建立。起因：institutional_flow 上市股 trust_net/dealer_net/total_net
# 錯位五個月，且 ChipAnalyzer 兩個 analyze 方法恆回 0
# → 所有吃籌碼面的回測結論都是在污染資料上跑出來的，必須重跑。
#
# 串在 chain_backfill.sh 之後：回填沒成功就不重驗（在舊資料上重跑毫無意義）。

set -u
cd /home/mdsadmin/Stock/tw-stock-analysis

PY=/home/mdsadmin/Stock/.venv/bin/python
CHAIN_PID="${1:?需帶 chain_backfill 的 PID}"
TS=$(date +%Y%m%d_%H%M%S)
OUT=reports/chip_reverify_$TS
LOG=logs/reverify_chip_$TS.log
exec >> "$LOG" 2>&1

say() { echo "[$(date '+%F %T')] $*"; }

line_notify() {
    $PY - "$1" <<'PYEOF'
import sys
from pathlib import Path
from dotenv import load_dotenv
P = Path('/home/mdsadmin/Stock/tw-stock-analysis')
load_dotenv(str(P / '.env'))
sys.path.insert(0, str(P))
try:
    from src.alerts.line_notifier import LineNotifier
    n = LineNotifier()
    if n.enabled:
        n.send(sys.argv[1]); print('LINE 已送出')
    else:
        print('LINE notifier 未啟用')
except Exception as e:
    print(f'LINE 發送失敗: {e.__class__.__name__}: {e}')
PYEOF
}

say "等待回填 PID $CHAIN_PID 結束..."
while kill -0 "$CHAIN_PID" 2>/dev/null; do sleep 60; done
say "回填行程已結束"

# ── 中止條件：回填必須真的成功 ─────────────────────────────────
FILLED=$(mongosh tw_stock_analysis --quiet --eval \
  'print(db.institutional_flow.countDocuments({backfilled_at:{$exists:true}}))')
say "已回填筆數 = $FILLED"

if [ "${FILLED:-0}" -lt 800000 ]; then
    say "中止：回填筆數 $FILLED < 800000，資料仍不可信，不進行重驗"
    line_notify "⚠️ 籌碼面回測重驗已中止
institutional_flow 只回填 $FILLED 筆（應約 910,000）
在污染資料上重跑沒有意義，請先查回填為何未完成
log: $LOG"
    exit 1
fi

mkdir -p "$OUT"
say "輸出目錄 $OUT"

run() {
    local name="$1"; shift
    say "▶ $name"
    local t0=$(date +%s)
    timeout 5400 "$@" > "$OUT/$name.txt" 2>&1
    local rc=$?
    local el=$(( $(date +%s) - t0 ))
    say "  $name exit=$rc 耗時 ${el}s ($(wc -l < "$OUT/$name.txt") 行輸出)"
    echo "$name $rc $el" >> "$OUT/_summary.txt"
}

# 🔴 結論作廢等級 —— 一定要重跑
run chip_score_scan            $PY scripts/chip_score_scan.py --top 30 --no-line
run backtest_holder_incremental $PY scripts/backtest_holder_incremental.py --with-inst
run backtest_holder_conc       $PY scripts/backtest_holder_conc.py
run backtest_integrated_v21    $PY scripts/backtest_integrated_v21.py \
                                   --output "$OUT/v21_result.json"

# 🟡 只用 foreign_net，影響小但一併跑作對照
run backtest_ma_inst           $PY scripts/backtest_ma_inst.py

FAIL=$(awk '$2!=0' "$OUT/_summary.txt" 2>/dev/null | wc -l)
TOTAL=$(wc -l < "$OUT/_summary.txt")
say "完成：$TOTAL 項，失敗 $FAIL 項"

line_notify "📊 籌碼面回測重驗完成
回填 $FILLED 筆後重跑 $TOTAL 項，失敗 $FAIL 項
結果在 $OUT
⚠️ 修復前的舊回測結論一律作廢，請以本次為準
$(cat "$OUT/_summary.txt" | awk '{printf "  %s exit=%s %ss\n", $1, $2, $3}')"
say "完成"
