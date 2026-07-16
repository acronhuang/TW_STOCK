#!/bin/bash
# 收盤後分析總管線（heal → 重算 → 分析 → 彙整推播）
# =====================================================
# 取代原本 17:00–18:30 分散的 9 支 cron。改為「先補齊當日資料，再在完整資料上
# 跑分析」，且各分析以 LINE_SPOOL 暫存不即時發，最後 evening_digest 彙整成 2-3 則。
# 保證順序、單一 spool 範圍，避免舊架構「分析跑在 heal 之前用到舊價/partial」。
set -uo pipefail
cd /home/mdsadmin/Stock/tw-stock-analysis || exit 1
PY=/home/mdsadmin/Stock/.venv/bin/python3
SPOOL=/home/mdsadmin/Stock/tw-stock-analysis/logs/line_spool.jsonl
LOG=/home/mdsadmin/Stock/tw-stock-analysis/logs/evening_pipeline_$(date +%Y%m%d).log
exec >>"$LOG" 2>&1
echo "===== 收盤後管線 $(date '+%F %T %Z') ====="

export LINE_SPOOL="$SPOOL"
rm -f "$SPOOL"                       # 清上一輪殘留，避免跨日污染

step(){ echo "--- [$(date +%H:%M:%S)] $1 ---"; }

# 順序關鍵：必須「先下載股價 → 再 heal → 才算因子」。
# twse_openapi_sync(17:30 cron)只抓周邊表(融資/當沖/零股/盤後)，stock_price 是
# twse_daily_update 抓的。若 heal 排在下載前，DB 內最新日還是昨天 → 完整度檢查
# 拿昨天(完整)比對 → 誤判「全部正常」→ heal 空轉，當日缺價全部沿用舊值。
step "1/9 下載當日股價（stock_price）"
$PY scripts/twse_daily_update.py || echo "  twse_daily_update 失敗（續）"

step "2/9 完整度自癒 heal（補齊當日缺漏）"
$PY scripts/twse_openapi_sync.py --heal || echo "  heal 非零退出（續）"

step "3/9 重算因子 + 蔡森掃描（在補齊後的價上）"
bash scripts/daily_senvision.sh || echo "  senvision 失敗（續）"

step "4/9 北大四大法則日檢"
$PY scripts/daily_alert_check.py || echo "  alert_check 失敗（續）"

step "5/9 每日選股推薦"
$PY scripts/daily_recommendations.py || echo "  recommendations 失敗（續）"

step "6/9 量價掃描 / OBV 背離"
$PY scripts/volume_price_scan.py || echo "  volume_price 失敗（續）"
$PY scripts/obv_bottom_divergence_scan.py || echo "  obv 失敗（續）"

step "7/9 主力散戶籌碼 / 雙訊號"
$PY scripts/chip_score_scan.py || echo "  chip 失敗（續）"
$PY scripts/dual_signal_scan.py || echo "  dual 失敗（續）"

step "8/9 團隊分析（Phase1+2）"
bash scripts/team_daily_50.sh || echo "  team 失敗（續）"

step "9/9 彙整推播（2-3 則）"
unset LINE_SPOOL                     # digest 需實發（內部亦會 pop 一次防呆）
$PY scripts/evening_digest.py --spool "$SPOOL" || echo "  digest 失敗"

echo "===== 完成 $(date '+%F %T %Z') ====="
