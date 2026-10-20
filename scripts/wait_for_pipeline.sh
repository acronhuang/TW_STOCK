#!/bin/bash
# 週五全市場週跑啟動前：收盤後管線（evening_pipeline.sh）還在跑就等它結束，
# 避免兩批 LLM 工作同時搶 .28（10-16 實測重疊約 28 分鐘）。
# 最多等 WEEKLY_WAIT_PIPELINE_MAX_SEC（預設 7200 秒）；逾時仍照常往下走，0 = 不等。
PATTERN="${WEEKLY_PIPELINE_PATTERN:-scripts/evening_pipeline\.sh}"
MAX="${WEEKLY_WAIT_PIPELINE_MAX_SEC:-7200}"
POLL="${WEEKLY_WAIT_PIPELINE_POLL_SEC:-60}"
waited=0
[ "$MAX" -le 0 ] && exit 0
while pgrep -f "$PATTERN" > /dev/null; do
  if [ "$waited" -ge "$MAX" ]; then
    echo "⚠️ 等待收盤後管線已超過 ${MAX} 秒，仍照常啟動週跑 $(date '+%F %T')"
    exit 0
  fi
  [ "$waited" -eq 0 ] && echo "⏳ 收盤後管線仍在執行，等它結束再開跑 $(date '+%F %T')"
  sleep "$POLL"
  waited=$((waited + POLL))
done
[ "$waited" -gt 0 ] && echo "收盤後管線已結束，共等待 ${waited} 秒 $(date '+%F %T')"
exit 0
