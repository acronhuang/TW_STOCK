#!/bin/bash
# 第四段：補跑股票池遺漏的 ETF → 補回填 → 重跑修好的 v21 回測
#
# 2026-07-19 建立。起因：原股票池以「4-5 碼」定義，把 taiwan_stock_info 裡的
# 132 檔 6 碼誤當權證排除，但那些全是 ETF（含 0050 相關）且有法人資料，
# 導致 22,104 筆 institutional_flow 仍是錯位的舊資料。
# 股票池定義已在 rebuild_institutional_investors.py 內永久修正，本腳本只負責執行。

set -u
cd /home/mdsadmin/Stock/tw-stock-analysis

PY=/home/mdsadmin/Stock/.venv/bin/python
TS=$(date +%Y%m%d_%H%M%S)
LOG=logs/stage4_etf_supplement_$TS.log
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

BEFORE=$(mongosh tw_stock_analysis --quiet --eval \
  'print(db.institutional_flow.countDocuments({data_source:"TWSE_T86", backfilled_at:{$exists:false}}))')
say "開工。目前未回填的 TWSE_T86 列 = $BEFORE"

# ── 1. 補跑遺漏股票（已完成者自動略過）─────────────────────────
say "▶ 補跑重建"
$PY scripts/rebuild_institutional_investors.py
RC1=$?
say "  重建 exit=$RC1"

ERR=$(mongosh tw_stock_analysis --quiet --eval \
  'print(db.institutional_rebuild_progress.countDocuments({status:"error"}))')
if [ "${ERR:-0}" -gt 50 ]; then
    say "中止：失敗 $ERR 檔 > 50"
    line_notify "⚠️ ETF 補跑已中止：重建失敗 $ERR 檔，未動 institutional_flow
log: $LOG"
    exit 1
fi

# ── 2. 補回填 ──────────────────────────────────────────────────
BK=/home/mdsadmin/backup_institutional_flow_stage4_$TS
say "▶ 備份 → $BK"
if ! mongodump --db tw_stock_analysis --collection institutional_flow --out "$BK"; then
    say "中止：備份失敗"
    line_notify "⚠️ ETF 補回填已中止：mongodump 失敗，未動正式資料
log: $LOG"
    exit 1
fi

say "▶ 補回填"
$PY scripts/backfill_institutional_flow.py --execute
RC2=$?
AFTER=$(mongosh tw_stock_analysis --quiet --eval \
  'print(db.institutional_flow.countDocuments({data_source:"TWSE_T86", backfilled_at:{$exists:false}}))')
say "  回填 exit=$RC2，未回填列 $BEFORE → $AFTER"

# ── 3. 重跑修好的 v21 回測（重驗時因日期查詢 bug 失敗）──────────
say "▶ 重跑 backtest_integrated_v21"
OUT=reports/chip_reverify_stage4_$TS
mkdir -p "$OUT"
timeout 5400 $PY scripts/backtest_integrated_v21.py \
    --start-date 2023-04-01 --end-date 2026-07-16 \
    --output "$OUT/v21_result.json" > "$OUT/backtest_integrated_v21.txt" 2>&1
RC3=$?
say "  v21 exit=$RC3（$(wc -l < "$OUT/backtest_integrated_v21.txt") 行輸出）"

line_notify "🧩 ETF 補跑完成
未回填列：$BEFORE → $AFTER
重建 exit=$RC1／回填 exit=$RC2／v21 回測 exit=$RC3
v21 結果：$OUT
（v21 先前因日期查詢 bug 從未成功執行，已修）"
say "完成"
